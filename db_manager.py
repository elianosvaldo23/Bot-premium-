import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING, ReturnDocument

from config import MONGO_URI, DB_NAME, logger, DEFAULT_WELCOME_MESSAGE

class DatabaseManager:
    def __init__(self):
        self.client = AsyncIOMotorClient(MONGO_URI)
        self.db = self.client[DB_NAME]

    async def initialize_db(self):
        # Limpiar documentos con chat_id nulo
        await self.db.groups.delete_many({"chat_id": None})

        # Crear índices
        await self.db.groups.create_index("chat_id", unique=True)
        await self.db.groups.create_index([("active", ASCENDING), ("added_date", DESCENDING)])

        await self.db.welcome_settings.create_index("chat_id", unique=True)

        await self.db.welcome_nodes.create_index("node_id", unique=True)
        await self.db.welcome_nodes.create_index([("chat_id", ASCENDING), ("parent_id", ASCENDING)])

        await self.db.stats.create_index("chat_id", unique=True)
        await self.db.global_settings.create_index("setting_name", unique=True)

        # Inicializar contador de nodos si no existe
        existing = await self.db.counters.find_one({"_id": "welcome_node_id"})
        if not existing:
            await self.db.counters.insert_one({"_id": "welcome_node_id", "seq": 0})

        logger.info("Base de datos MongoDB inicializada correctamente")

    # Utilidades internas
    async def _get_next_sequence(self, name: str) -> int:
        doc = await self.db.counters.find_one_and_update(
            {"_id": name},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER
        )
        return int(doc["seq"])

    def _node_doc_to_dict(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        if not doc:
            return {}
        return {
            "id": doc.get("node_id"),
            "chat_id": doc.get("chat_id"),
            "parent_id": doc.get("parent_id"),
            "text": doc.get("text"),
            "image_url": doc.get("image_url"),
            "parse_mode": doc.get("parse_mode", "HTML"),
            "buttons": doc.get("buttons", [])
        }

    def _group_doc_to_tuple(self, doc: Dict[str, Any]) -> Tuple[Any, ...]:
        # Añadimos campos nuevos al final para no romper índices previos
        return (
            doc.get("chat_id"),
            doc.get("title"),
            doc.get("type"),
            doc.get("added_by"),
            doc.get("added_by_username"),
            doc.get("added_by_name"),
            doc.get("member_count"),
            doc.get("added_date"),
            doc.get("active", True),
            doc.get("is_forum", False),
            doc.get("welcome_thread_id")
        )

    def _welcome_settings_doc_to_tuple(self, doc: Optional[Dict[str, Any]]) -> Optional[Tuple[Any, ...]]:
        if not doc:
            return None
        return (
            doc.get("chat_id"),
            doc.get("enabled", True),
            doc.get("message"),
            json.dumps(doc.get("buttons", [])),
            doc.get("image_url"),
            doc.get("parse_mode", "HTML")
        )

    # Global settings
    async def get_setting(self, name: str, default=None):
        row = await self.db.global_settings.find_one({"setting_name": name})
        return row["setting_value"] if row and row.get("setting_value") is not None else default

    async def set_setting(self, name: str, value: str):
        await self.db.global_settings.update_one(
            {"setting_name": name},
            {"$set": {"setting_value": str(value)}},
            upsert=True
        )

    async def get_all_settings(self):
        docs = self.db.global_settings.find({})
        out = {}
        async for d in docs:
            out[d["setting_name"]] = d.get("setting_value")
        return out

    # Grupos
    async def add_group(self, chat_id, title, chat_type, added_by, username, name, member_count, is_forum: bool = False):
        await self.db.groups.update_one(
            {"chat_id": chat_id},
            {"$set": {
                "title": title,
                "type": chat_type,
                "added_by": added_by,
                "added_by_username": username,
                "added_by_name": name,
                "member_count": member_count,
                "added_date": datetime.utcnow().isoformat(),
                "active": True,
                "is_forum": bool(is_forum)
            }},
            upsert=True
        )

        default_parse_mode = await self.get_setting('default_parse_mode', 'HTML')

        await self.db.welcome_settings.update_one(
            {"chat_id": chat_id},
            {"$setOnInsert": {
                "enabled": True,
                "message": DEFAULT_WELCOME_MESSAGE,
                "buttons": [],
                "image_url": None,
                "parse_mode": default_parse_mode
            }},
            upsert=True
        )

        await self.db.stats.update_one(
            {"chat_id": chat_id},
            {"$setOnInsert": {
                "welcomes_sent": 0,
                "last_activity": datetime.utcnow().isoformat()
            }},
            upsert=True
        )

        await self.ensure_root_node(chat_id)

    async def get_group_info(self, chat_id):
        doc = await self.db.groups.find_one({"chat_id": chat_id})
        return self._group_doc_to_tuple(doc) if doc else None

    async def get_all_active_groups(self):
        cursor = self.db.groups.find({"active": True}).sort("added_date", DESCENDING)
        groups = []
        async for doc in cursor:
            groups.append(self._group_doc_to_tuple(doc))
        return groups

    async def update_group_info(self, chat_id, title, member_count, is_forum: Optional[bool] = None):
        update = {"title": title, "member_count": member_count}
        if is_forum is not None:
            update["is_forum"] = bool(is_forum)
        await self.db.groups.update_one(
            {"chat_id": chat_id},
            {"$set": update}
        )

    async def deactivate_group(self, chat_id):
        await self.db.groups.update_one({"chat_id": chat_id}, {"$set": {"active": False}})

    async def set_group_welcome_thread(self, chat_id: int, thread_id: Optional[int]):
        await self.db.groups.update_one(
            {"chat_id": chat_id},
            {"$set": {"welcome_thread_id": thread_id}}
        )

    async def clear_group_welcome_thread(self, chat_id: int):
        await self.set_group_welcome_thread(chat_id, None)

    async def get_group_welcome_thread(self, chat_id: int) -> Optional[int]:
        doc = await self.db.groups.find_one({"chat_id": chat_id}, {"welcome_thread_id": 1})
        return doc.get("welcome_thread_id") if doc else None

    # Welcome settings (compat)
    async def get_welcome_settings(self, chat_id):
        doc = await self.db.welcome_settings.find_one({"chat_id": chat_id})
        return self._welcome_settings_doc_to_tuple(doc)

    async def update_welcome_message(self, chat_id, message):
        await self.db.welcome_settings.update_one({"chat_id": chat_id}, {"$set": {"message": message}})

    async def update_welcome_image(self, chat_id, image_url):
        await self.db.welcome_settings.update_one({"chat_id": chat_id}, {"$set": {"image_url": image_url}})

    async def update_welcome_buttons(self, chat_id, buttons):
        await self.db.welcome_settings.update_one({"chat_id": chat_id}, {"$set": {"buttons": buttons}})

    async def toggle_welcome_status(self, chat_id):
        doc = await self.db.welcome_settings.find_one({"chat_id": chat_id})
        current = bool(doc.get("enabled")) if doc else True
        new_status = not current
        await self.db.welcome_settings.update_one({"chat_id": chat_id}, {"$set": {"enabled": new_status}})
        return new_status

    # Stats
    async def get_group_stats(self, chat_id):
        doc = await self.db.stats.find_one({"chat_id": chat_id})
        if not doc:
            return (chat_id, 0, None)
        return (doc.get("chat_id"), doc.get("welcomes_sent", 0), doc.get("last_activity"))

    async def update_welcome_stats(self, chat_id):
        await self.db.stats.update_one(
            {"chat_id": chat_id},
            {"$inc": {"welcomes_sent": 1}, "$set": {"last_activity": datetime.utcnow().isoformat()}},
            upsert=True
        )

    async def get_general_stats(self):
        stats = {}

        total_groups = await self.db.groups.count_documents({"active": True})
        inactive_groups = await self.db.groups.count_documents({"active": False})

        agg = await self.db.stats.aggregate([
            {"$group": {"_id": None, "sum": {"$sum": "$welcomes_sent"}}}
        ]).to_list(1)
        total_welcomes = agg[0]["sum"] if agg else 0

        agg_avg = await self.db.groups.aggregate([
            {"$match": {"active": True}},
            {"$group": {"_id": None, "avg": {"$avg": "$member_count"}}}
        ]).to_list(1)
        avg_members = agg_avg[0]["avg"] if agg_avg and agg_avg[0]["avg"] is not None else 0

        top = await self.db.groups.aggregate([
            {"$match": {"active": True}},
            {"$lookup": {
                "from": "stats",
                "localField": "chat_id",
                "foreignField": "chat_id",
                "as": "stats"
            }},
            {"$unwind": {"path": "$stats", "preserveNullAndEmptyArrays": True}},
            {"$addFields": {"welcomes": {"$ifNull": ["$stats.welcomes_sent", 0]}}},
            {"$sort": {"welcomes": -1}},
            {"$limit": 5},
            {"$project": {"title": 1, "welcomes": 1}}
        ]).to_list(5)
        top_groups = [(g.get("title"), int(g.get("welcomes", 0))) for g in top]

        stats['total_groups'] = (total_groups,)
        stats['inactive_groups'] = (inactive_groups,)
        stats['total_welcomes'] = (total_welcomes,)
        stats['avg_members'] = (avg_members,)
        stats['top_groups'] = top_groups
        return stats

    # Nodos de bienvenida (submenús)
    async def ensure_root_node(self, chat_id):
        doc = await self.db.welcome_nodes.find_one({"chat_id": chat_id, "parent_id": None})
        if doc:
            return int(doc["node_id"])

        ws = await self.db.welcome_settings.find_one({"chat_id": chat_id})
        text = ws.get("message") if ws and ws.get("message") else DEFAULT_WELCOME_MESSAGE
        parse_mode = ws.get("parse_mode") if ws and ws.get("parse_mode") else "HTML"
        image_url = ws.get("image_url") if ws else None

        new_id = await self._get_next_sequence("welcome_node_id")
        await self.db.welcome_nodes.insert_one({
            "node_id": new_id,
            "chat_id": chat_id,
            "parent_id": None,
            "text": text,
            "image_url": image_url,
            "parse_mode": parse_mode,
            "buttons": []
        })
        return new_id

    async def get_root_node(self, chat_id):
        doc = await self.db.welcome_nodes.find_one({"chat_id": chat_id, "parent_id": None})
        if not doc:
            await self.ensure_root_node(chat_id)
            doc = await self.db.welcome_nodes.find_one({"chat_id": chat_id, "parent_id": None})
        return self._node_doc_to_dict(doc) if doc else None

    async def get_node(self, node_id: int):
        doc = await self.db.welcome_nodes.find_one({"node_id": node_id})
        return self._node_doc_to_dict(doc) if doc else None

    async def get_child_nodes(self, chat_id: int, parent_id: int):
        cursor = self.db.welcome_nodes.find({"chat_id": chat_id, "parent_id": parent_id}).sort("node_id", ASCENDING)
        out = []
        async for doc in cursor:
            out.append(self._node_doc_to_dict(doc))
        return out

    async def update_node_text(self, node_id: int, text: str):
        await self.db.welcome_nodes.update_one({"node_id": node_id}, {"$set": {"text": text}})

    async def update_node_image(self, node_id: int, image_url):
        await self.db.welcome_nodes.update_one({"node_id": node_id}, {"$set": {"image_url": image_url}})

    async def update_node_parse_mode(self, node_id: int, parse_mode: str):
        await self.db.welcome_nodes.update_one({"node_id": node_id}, {"$set": {"parse_mode": parse_mode}})

    async def add_child_node(self, chat_id: int, parent_id: int, text: str, parse_mode: str = 'HTML', image_url=None):
        new_id = await self._get_next_sequence("welcome_node_id")
        await self.db.welcome_nodes.insert_one({
            "node_id": new_id,
            "chat_id": chat_id,
            "parent_id": parent_id,
            "text": text,
            "image_url": image_url,
            "parse_mode": parse_mode,
            "buttons": []
        })
        return new_id

    async def get_node_buttons(self, node_id: int):
        doc = await self.db.welcome_nodes.find_one({"node_id": node_id}, {"buttons": 1})
        if not doc:
            return []
        buttons = doc.get("buttons") or []
        if isinstance(buttons, str):
            try:
                return json.loads(buttons)
            except:
                return []
        return buttons

    async def set_node_buttons(self, node_id: int, buttons):
        await self.db.welcome_nodes.update_one({"node_id": node_id}, {"$set": {"buttons": buttons}})

    async def clear_node_buttons(self, node_id: int):
        await self.set_node_buttons(node_id, [])

    async def remove_button_pointing_to_node(self, parent_id: int, child_id: int):
        buttons = await self.get_node_buttons(parent_id)
        new_buttons = []
        for row in buttons:
            new_row = [b for b in row if not (b.get('type') == 'node' and int(b.get('node_id')) == int(child_id))]
            if new_row:
                new_buttons.append(new_row)
        await self.set_node_buttons(parent_id, new_buttons)

    async def delete_node_recursive(self, node_id: int):
        node = await self.get_node(node_id)
        if not node:
            return
        if node['parent_id'] is None:
            return  # no borrar raíz

        children = await self.get_child_nodes(node['chat_id'], node_id)
        for ch in children:
            await self.delete_node_recursive(ch['id'])

        await self.remove_button_pointing_to_node(node['parent_id'], node_id)
        await self.db.welcome_nodes.delete_one({"node_id": node_id})
