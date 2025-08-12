import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest

from config import ADMIN_ID, logger
from helpers import format_welcome_message, add_premium_emojis


class MessageHandlers:
    def __init__(self, db_manager):
        self.db = db_manager
        self.waiting_for_input = {}

    def _build_keyboard_from_node(self, node: dict):
        rows = []
        try:
            buttons = json.loads(node.get('buttons') or '[]') if isinstance(node.get('buttons'), str) else (node.get('buttons') or [])
        except:
            buttons = []
        for row in buttons:
            rb = []
            for b in row:
                if b.get('type') == 'url' and b.get('url'):
                    rb.append(InlineKeyboardButton(b.get('text', 'Abrir'), url=b['url']))
                elif b.get('type') == 'node' and b.get('node_id'):
                    rb.append(InlineKeyboardButton(b.get('text', 'Ver'), callback_data=f"wb_{b['node_id']}"))
            if rb:
                rows.append(rb)
        if node.get('parent_id'):
            rows.append([
                InlineKeyboardButton("◀️ Atrás", callback_data=f"wb_{node['parent_id']}"),
                InlineKeyboardButton("🏠 Inicio", callback_data=f"wb_home_{node['chat_id']}")
            ])
        elif rows:
            rows.append([InlineKeyboardButton("🏠 Inicio", callback_data=f"wb_home_{node['chat_id']}")])
        return InlineKeyboardMarkup(rows) if rows else None

    def _normalize_parse_mode(self, pm: str | None) -> str:
        if not pm:
            return "HTML"
        if pm.lower().startswith("markdown"):
            return "MarkdownV2"
        return "HTML" if pm.upper() == "HTML" else pm

    async def handle_new_chat_member(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        for member in update.message.new_chat_members:
            if member.id == context.bot.id:
                await self.bot_added_to_group(update, context)
                break

        if update.message.new_chat_members:
            await self.send_welcome_message(update, context)

    async def bot_added_to_group(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat = update.effective_chat
        user = update.effective_user

        try:
            # Trae info en vivo para detectar foros/temas con mayor certeza
            chat_live = await context.bot.get_chat(chat.id)
            member_count = await context.bot.get_chat_member_count(chat.id)
            is_forum = getattr(chat_live, "is_forum", False)
            title = chat_live.title or chat.title
        except Exception:
            # Fallback a lo recibido en el update
            is_forum = getattr(chat, "is_forum", False)
            title = chat.title
            try:
                member_count = await context.bot.get_chat_member_count(chat.id)
            except:
                member_count = "No disponible"

        await self.db.add_group(
            chat.id, title, chat.type, user.id if user else None,
            (user.username if user else None), 
            (f"{user.first_name} {user.last_name or ''}".strip() if user else "Desconocido"),
            member_count, is_forum
        )

        keyboard = [[InlineKeyboardButton("✅ Configurar Grupo", callback_data=f"config_group_{chat.id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Escapar caracteres problemáticos antes de usar en f-string
        safe_title = title.replace('.', '\\.')
        safe_username = user.username or 'Sin username' if user else '-'
        safe_first_name = user.first_name.replace('.', '\\.') if user else 'Desconocido'
        safe_date = datetime.now().strftime('%d/%m/%Y %H:%M').replace('.', '\\.')
        
        notification_text = f"""
:crown_premium: **Bot añadido a nuevo grupo** :crown_premium:

:star_premium: **Grupo:** {safe_title}
:gem_premium: **ID:** `{chat.id}`
:rocket_premium: **Añadido por:** {safe_first_name} \\(@{safe_username}\\)
:check_premium: **Miembros:** {member_count}
:magic_premium: **Temas habilitados:** {'Sí' if is_forum else 'No'}
:calendar_premium: **Fecha:** {safe_date}
"""
        
        formatted_notification = add_premium_emojis(notification_text, "MarkdownV2")

        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=formatted_notification,
                reply_markup=reply_markup,
                parse_mode="MarkdownV2"
            )
        except Exception as e:
            logger.error(f"Error enviando notificación al admin: {e}")

        welcome_group_text = """
:crown_premium: ¡Hola! Soy tu nuevo bot administrador premium :rocket_premium:

:star_premium: Los administradores pueden configurarme usando /admin

:party_premium: ¡Gracias por añadirme al grupo!
"""
        formatted_welcome = add_premium_emojis(welcome_group_text, "MarkdownV2")

        await update.message.reply_text(
            formatted_welcome,
            parse_mode="MarkdownV2"
        )

    async def send_welcome_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        chat_title = update.effective_chat.title or "el grupo"
        welcome_config = await self.db.get_welcome_settings(chat_id)
        if not welcome_config or not welcome_config[1]:
            return

        await self.db.ensure_root_node(chat_id)
        root = await self.db.get_root_node(chat_id)
        pmode = self._normalize_parse_mode(root.get('parse_mode') or "HTML")

        # Configuración de thread_id mejorada
        configured_thread_id = await self.db.get_group_welcome_thread(chat_id)
        event_thread_id = getattr(update.message, "message_thread_id", None) if update.message else None
        message_thread_id = configured_thread_id if configured_thread_id is not None else event_thread_id

        for new_member in update.message.new_chat_members:
            if new_member.id == context.bot.id:
                continue
            message = format_welcome_message(root['text'] or "", new_member, chat_title, parse_mode=pmode)
            reply_markup = self._build_keyboard_from_node(root)

            try:
                if root.get('image_url'):
                    sent_message = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=root['image_url'],
                        caption=message,
                        reply_markup=reply_markup,
                        parse_mode=pmode,
                        message_thread_id=message_thread_id
                    )
                    logger.info(f"Mensaje de bienvenida con imagen enviado. Chat: {chat_id}, Message ID: {sent_message.message_id}, Thread: {message_thread_id}")
                else:
                    sent_message = await context.bot.send_message(
                        chat_id=chat_id,
                        text=message,
                        reply_markup=reply_markup,
                        parse_mode=pmode,
                        message_thread_id=message_thread_id
                    )
                    logger.info(f"Mensaje de bienvenida sin imagen enviado. Chat: {chat_id}, Message ID: {sent_message.message_id}, Thread: {message_thread_id}")
                    
                await self.db.update_welcome_stats(chat_id)
            except BadRequest as e:
                low = str(e).lower()
                if "can't parse entities" in low:
                    safe_message = format_welcome_message(root['text'] or "", new_member, chat_title, parse_mode=None)
                    try:
                        if root.get('image_url'):
                            await context.bot.send_photo(
                                chat_id=chat_id,
                                photo=root['image_url'],
                                caption=safe_message,
                                reply_markup=reply_markup,
                                parse_mode=None,
                                message_thread_id=message_thread_id
                            )
                        else:
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=safe_message,
                                reply_markup=reply_markup,
                                parse_mode=None,
                                message_thread_id=message_thread_id
                            )
                        await self.db.update_welcome_stats(chat_id)
                        logger.info(f"Mensaje de bienvenida enviado sin formato (fallback). Chat: {chat_id}")
                    except Exception as e2:
                        logger.error(f"Error fallback bienvenida: {e2}")
                else:
                    logger.error(f"Error enviando bienvenida: {e}")
            except Exception as e:
                logger.error(f"Error enviando mensaje de bienvenida: {e}")

    async def handle_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id if update.effective_user else None
        if not user_id or user_id not in self.waiting_for_input:
            return

        data = self.waiting_for_input[user_id]
        action = data['action']

        if action == "welcome_message":
            chat_id = data['chat_id']
            new_text = update.message.text
            await self.db.update_welcome_message(chat_id, new_text)
            root_id = await self.db.ensure_root_node(chat_id)
            await self.db.update_node_text(root_id, new_text)
            
            success_text = """
:check_premium: **Mensaje de bienvenida actualizado\\.**

:star_premium: ¿Deseas añadir botones?
"""
            formatted_text = add_premium_emojis(success_text, "MarkdownV2")
            
            await update.message.reply_text(
                formatted_text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ Botón URL", callback_data=f"node_add_url_{root_id}")],
                    [InlineKeyboardButton("➕ Submenú", callback_data=f"node_add_sub_{root_id}")],
                    [InlineKeyboardButton("No por ahora", callback_data=f"config_welcome_{chat_id}")]
                ]),
                parse_mode="MarkdownV2"
            )
            del self.waiting_for_input[user_id]

        elif action == "button_text" and data.get('button_type') == 'url':
            self.waiting_for_input[user_id]['button_text'] = update.message.text
            self.waiting_for_input[user_id]['action'] = 'button_url'
            await update.message.reply_text("Ahora envía la URL del botón (o 'cancel' para cancelar):")

        elif action == "button_url":
            node_id = data['node_id']
            button_text = data.get('button_text', 'Abrir')
            button_url = update.message.text.strip()
            if button_url.lower() == 'cancel':
                await update.message.reply_text("❌ Cancelado.")
                del self.waiting_for_input[user_id]
                return
            rows = await self.db.get_node_buttons(node_id)
            rows.append([{"text": button_text, "type": "url", "url": button_url}])
            await self.db.set_node_buttons(node_id, rows)
            await update.message.reply_text("✅ Botón URL añadido.")
            del self.waiting_for_input[user_id]

        elif action == "button_sub_text":
            self.waiting_for_input[user_id]['submenu_button_text'] = update.message.text
            self.waiting_for_input[user_id]['action'] = 'child_node_text'
            await update.message.reply_text("Ahora envía el texto que se mostrará al abrir el submenú:")

        elif action == "child_node_text":
            parent_node_id = data['node_id']
            btn_text = data.get('submenu_button_text', 'Ver más')
            child_text = update.message.text

            parent_node = await self.db.get_node(parent_node_id)
            chat_id = parent_node['chat_id']
            child_id = await self.db.add_child_node(chat_id, parent_node_id, child_text, parent_node.get('parse_mode') or 'HTML')

            rows = await self.db.get_node_buttons(parent_node_id)
            rows.append([{"text": btn_text, "type": "node", "node_id": child_id}])
            await self.db.set_node_buttons(parent_node_id, rows)

            submenu_created_text = """
:check_premium: **Submenú creado\\.**

:star_premium: ¿Deseas añadir botones dentro de este submenú?
"""
            formatted_text = add_premium_emojis(submenu_created_text, "MarkdownV2")

            await update.message.reply_text(
                formatted_text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ Botón URL (hijo)", callback_data=f"node_add_url_{child_id}")],
                    [InlineKeyboardButton("➕ Submenú (hijo)", callback_data=f"node_add_sub_{child_id}")],
                    [InlineKeyboardButton("Listo", callback_data=f"node_mgr_{chat_id}_{parent_node_id}")]
                ]),
                parse_mode="MarkdownV2"
            )
            del self.waiting_for_input[user_id]

        elif action == "node_image":
            node_id = data['node_id']
            image_input = update.message.text.strip()
            if image_input.lower() == 'remove':
                await self.db.update_node_image(node_id, None)
                await update.message.reply_text("✅ Imagen eliminada.")
            else:
                await self.db.update_node_image(node_id, image_input)
                await update.message.reply_text("✅ Imagen actualizada.")
            del self.waiting_for_input[user_id]

        elif action == "node_rename":
            node_id = data['node_id']
            await self.db.update_node_text(node_id, update.message.text)
            await update.message.reply_text("✅ Texto del nodo actualizado.")
            del self.waiting_for_input[user_id]

    async def handle_photo_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id if update.effective_user else None
        if not user_id or user_id not in self.waiting_for_input:
            return
        data = self.waiting_for_input[user_id]
        if data.get('action') != 'node_image':
            return

        node_id = data['node_id']
        try:
            file_id = update.message.photo[-1].file_id
            await self.db.update_node_image(node_id, file_id)
            await update.message.reply_text("✅ Imagen actualizada.")
        except Exception as e:
            logger.error(f"Error guardando imagen de nodo: {e}")
            await update.message.reply_text("❌ No se pudo guardar la imagen.")
        finally:
            del self.waiting_for_input[user_id]
