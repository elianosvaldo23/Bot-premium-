import json
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest

from helpers import check_admin_permissions, truncate_text, format_date, format_welcome_message, add_premium_emojis


class CallbackHandlers:
    def __init__(self, db_manager, message_handler):
        self.db = db_manager
        self.message_handler = message_handler

    def _is_public_callback(self, data: str) -> bool:
        return data.startswith("wb_") or data.startswith("wb_home_")

    async def safe_edit_message_text(self, query, text: str, reply_markup=None, parse_mode=None):
        try:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except BadRequest as e:
            msg = str(e).lower()
            if "message is not modified" in msg:
                try:
                    await query.answer("Contenido ya actualizado")
                except:
                    pass
            else:
                if "can't parse entities" in msg:
                    try:
                        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=None)
                        return
                    except:
                        pass
                raise

    async def safe_edit_message_caption(self, query, caption: str, reply_markup=None, parse_mode=None):
        try:
            await query.edit_message_caption(caption=caption, reply_markup=reply_markup, parse_mode=parse_mode)
        except BadRequest as e:
            msg = str(e).lower()
            if "message is not modified" in msg:
                try:
                    await query.answer("Contenido ya actualizado")
                except:
                    pass
            else:
                if "can't parse entities" in msg:
                    try:
                        await query.edit_message_caption(caption=caption, reply_markup=reply_markup, parse_mode=None)
                        return
                    except:
                        pass
                raise

    def _normalize_parse_mode(self, pm: str | None) -> str:
        if not pm:
            return "HTML"
        if pm.lower().startswith("markdown"):
            return "MarkdownV2"
        return "HTML" if pm.upper() == "HTML" else pm

    def _buttons_to_list(self, buttons):
        """
        Normaliza el campo 'buttons' para que siempre sea una lista de listas.
        Acepta: None, str (JSON), list. Cualquier otro tipo → [].
        """
        if not buttons:
            return []
        if isinstance(buttons, str):
            try:
                parsed = json.loads(buttons)
                return parsed if isinstance(parsed, list) else []
            except Exception:
                return []
        if isinstance(buttons, list):
            return buttons
        return []

    async def handle_callback_query(self, update, context):
        query = update.callback_query
        await query.answer()
        data = query.data
        user_id = query.from_user.id

        # Permisos para callbacks no públicos
        if not self._is_public_callback(data):
            if not check_admin_permissions(user_id, data):
                await self.safe_edit_message_text(query, "❌ No tienes permisos para realizar esta acción.")
                return

        # Navegación pública submenús (modo "libro")
        if data.startswith("wb_home_"):
            chat_id = int(data.split("_")[-1])
            node = await self.db.get_root_node(chat_id)
            await self.show_node_content(query, node, book_mode=True)
            return
        if data.startswith("wb_") and data[3:].isdigit():
            node_id = int(data.split("_")[1])
            node = await self.db.get_node(node_id)
            if node:
                await self.show_node_content(query, node, book_mode=True)
            else:
                await query.answer("Contenido no disponible", show_alert=True)
            return

        # Routing admin
        if data == "admin_panel":
            await self.show_admin_panel(query)
        elif data == "view_groups":
            await self.show_groups_list(query)
        elif data == "bot_info":
            await self.show_bot_info(query)
        elif data == "manage_welcomes":
            await self.show_manage_welcomes(query)
        elif data == "global_settings":
            await self.show_global_settings(query)
        elif data == "general_stats":
            await self.show_general_stats(query)
        elif data.startswith("config_welcome_"):
            chat_id = int(data.split("_")[-1])
            await self.show_welcome_config(query, chat_id)
        elif data.startswith("group_settings_"):
            chat_id = int(data.split("_")[-1])
            await self.show_group_settings(query, chat_id)
        elif data.startswith("group_stats_"):
            chat_id = int(data.split("_")[-1])
            await self.show_group_stats(query, chat_id)
        elif data.startswith("config_group_"):
            chat_id = int(data.split("_")[-1])
            await self.show_group_config(query, chat_id)

        # Gestor avanzado
        elif data.startswith("edit_welcome_buttons_"):
            chat_id = int(data.split("_")[-1])
            await self.show_node_manager(query, chat_id, None)
        elif data.startswith("node_mgr_"):
            parts = data.split("_")
            # node_mgr_{chat_id}_{node_id}
            node_id = int(parts[-1])
            chat_id = int(parts[-2])
            await self.show_node_manager(query, chat_id, node_id)
        elif data.startswith("node_add_url_"):
            node_id = int(data.split("_")[-1])
            await self.start_add_url_button(query, node_id)
        elif data.startswith("node_add_sub_"):
            node_id = int(data.split("_")[-1])
            await self.start_add_submenu_button(query, node_id)
        elif data.startswith("node_clear_btns_"):
            node_id = int(data.split("_")[-1])
            await self.db.clear_node_buttons(node_id)
            await query.answer("✅ Botones limpiados")
            node = await self.db.get_node(node_id)
            await self.show_node_manager(query, node['chat_id'], node_id)
        elif data.startswith("node_set_image_"):
            node_id = int(data.split("_")[-1])
            await self.start_node_image_edit(query, node_id)
        elif data.startswith("node_rename_"):
            node_id = int(data.split("_")[-1])
            await self.start_node_rename(query, node_id)
        elif data.startswith("node_list_children_"):
            parts = data.split("_")
            # node_list_children_{chat_id}_{node_id}
            node_id = int(parts[-1])
            chat_id = int(parts[-2])
            await self.show_children_list(query, chat_id, node_id)
        elif data.startswith("node_del_"):
            node_id = int(data.split("_")[-1])
            node = await self.db.get_node(node_id)
            if not node:
                await query.answer("Nodo no encontrado", show_alert=True)
            else:
                parent_id = node['parent_id']
                chat_id = node['chat_id']
                await self.db.delete_node_recursive(node_id)
                await query.answer("🗑️ Submenú eliminado")
                if parent_id:
                    await self.show_node_manager(query, chat_id, parent_id)
                else:
                    await self.show_node_manager(query, chat_id, None)

        # Bienvenida
        elif data.startswith("edit_welcome_message_"):
            chat_id = int(data.split("_")[-1])
            await self.start_welcome_message_edit(query, chat_id)
        elif data.startswith("edit_welcome_image_"):
            chat_id = int(data.split("_")[-1])
            await self.start_welcome_image_edit(query, chat_id)
        elif data.startswith("toggle_welcome_"):
            chat_id = int(data.split("_")[-1])
            await self.toggle_welcome_status(query, chat_id)
        elif data.startswith("test_welcome_"):
            chat_id = int(data.split("_")[-1])
            await self.test_welcome_message(query, chat_id)

        # Grupos
        elif data.startswith("update_group_"):
            chat_id = int(data.split("_")[-1])
            await self.update_group_info(query, chat_id)
        elif data.startswith("deactivate_group_"):
            chat_id = int(data.split("_")[-1])
            await self.deactivate_group(query, chat_id)
        elif data.startswith("refresh_stats_"):
            chat_id = int(data.split("_")[-1])
            await self.refresh_group_stats(query, chat_id)

        # Global settings
        elif data.startswith("gs_lang_"):
            lang = data.split("_")[-1]
            await self.db.set_setting('language', lang)
            await query.answer("Idioma actualizado")
            await self.show_global_settings(query)
        elif data.startswith("gs_datefmt_"):
            code = data.split("_")[-1]
            mapping = {
                '1': '%d/%m/%Y %H:%M',
                '2': '%Y-%m-%d %H:%M',
                '3': '%d/%m/%Y',
            }
            fmt = mapping.get(code, '%d/%m/%Y %H:%M')
            await self.db.set_setting('date_format', fmt)
            await query.answer("Formato de fecha actualizado")
            await self.show_global_settings(query)
        elif data.startswith("gs_parse_"):
            mode = data.split("_")[-1]
            if mode.lower().startswith("markdown"):
                mode = "MarkdownV2"
            await self.db.set_setting('default_parse_mode', mode)
            await query.answer("Parse mode por defecto actualizado")
            await self.show_global_settings(query)

        # Parse mode del nodo
        elif data.startswith("node_parse_"):
            node_id = int(data.split("_")[-1])
            await self.show_parse_mode_selector(query, node_id)
        elif data.startswith("node_set_parse_"):
            parts = data.split("_")
            # node_set_parse_{node_id}_{mode}
            node_id = int(parts[-2])
            mode = parts[-1]
            if mode.lower().startswith("markdown"):
                mode = "MarkdownV2"
            await self.db.update_node_parse_mode(node_id, mode)
            await query.answer("✅ Parse mode actualizado")
            node = await self.db.get_node(node_id)
            await self.show_node_manager(query, node['chat_id'], node_id)

        # Temas (forums)
        elif data.startswith("set_welcome_topic_instr_"):
            chat_id = int(data.split("_")[-1])
            await self.show_set_welcome_topic_instructions(query, chat_id)
        elif data.startswith("clear_welcome_topic_"):
            chat_id = int(data.split("_")[-1])
            await self.db.clear_group_welcome_thread(chat_id)
            await query.answer("✅ Tema de bienvenida limpiado")
            await self.show_group_settings(query, chat_id)

        elif data.startswith("back_"):
            await self.handle_back_navigation(query, data)

    def build_node_keyboard(self, node: dict):
        rows = []
        buttons = self._buttons_to_list(node.get('buttons'))

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

    async def show_node_content(self, query, node: dict, book_mode: bool = True):
        try:
            group_info = await self.db.get_group_info(node['chat_id'])
            group_name = group_info[1] if group_info else (query.message.chat.title if query.message and query.message.chat else "el grupo")
            pmode = self._normalize_parse_mode(node.get('parse_mode') or "HTML")
            text = format_welcome_message(node['text'] or "", query.from_user, group_name, parse_mode=pmode)
            km = self.build_node_keyboard(node)

            # Para mensajes nuevos (no modo libro), usar el chat donde se hizo la consulta
            if not book_mode:
                send_chat_id = query.message.chat.id if query.message and query.message.chat else query.from_user.id
                # Mantener thread_id solo si estamos en el mismo grupo
                message_thread_id = getattr(query.message, "message_thread_id", None) if query.message and query.message.chat.id == node['chat_id'] else None
                
                try:
                    if node.get('image_url'):
                        await query.bot.send_photo(
                            chat_id=send_chat_id, 
                            photo=node['image_url'], 
                            caption=text, 
                            reply_markup=km, 
                            parse_mode=pmode, 
                            message_thread_id=message_thread_id
                        )
                    else:
                        await query.bot.send_message(
                            chat_id=send_chat_id, 
                            text=text, 
                            reply_markup=km, 
                            parse_mode=pmode, 
                            message_thread_id=message_thread_id
                        )
                except BadRequest as e:
                    if "can't parse entities" in str(e).lower():
                        safe_text = format_welcome_message(node['text'] or "", query.from_user, group_name, parse_mode=None)
                        if node.get('image_url'):
                            await query.bot.send_photo(
                                chat_id=send_chat_id, 
                                photo=node['image_url'], 
                                caption=safe_text, 
                                reply_markup=km, 
                                parse_mode=None, 
                                message_thread_id=message_thread_id
                            )
                        else:
                            await query.bot.send_message(
                                chat_id=send_chat_id, 
                                text=safe_text, 
                                reply_markup=km, 
                                parse_mode=None, 
                                message_thread_id=message_thread_id
                            )
                    else:
                        raise
                return

            # Modo libro (público). Preferimos editar el mensaje si es posible
            message = query.message
            has_image = bool(node.get('image_url'))
            is_message_photo = bool(getattr(message, "photo", None))

            # Obtener el chat_id correcto del mensaje actual
            current_chat_id = message.chat.id if message and message.chat else node['chat_id']
            current_thread_id = getattr(message, "message_thread_id", None) if message else None

            if has_image:
                if is_message_photo:
                    # Editar caption de la foto existente
                    await self.safe_edit_message_caption(query, text, reply_markup=km, parse_mode=pmode)
                else:
                    # Enviar nueva foto manteniendo el contexto
                    try:
                        await query.bot.send_photo(
                            chat_id=current_chat_id, 
                            photo=node['image_url'], 
                            caption=text, 
                            reply_markup=km, 
                            parse_mode=pmode, 
                            message_thread_id=current_thread_id
                        )
                    except BadRequest as e:
                        if "can't parse entities" in str(e).lower():
                            safe_text = format_welcome_message(node['text'] or "", query.from_user, group_name, parse_mode=None)
                            await query.bot.send_photo(
                                chat_id=current_chat_id, 
                                photo=node['image_url'], 
                                caption=safe_text, 
                                reply_markup=km, 
                                parse_mode=None, 
                                message_thread_id=current_thread_id
                            )
                        else:
                            raise
            else:
                if is_message_photo:
                    # Enviar texto como nuevo mensaje manteniendo el contexto
                    try:
                        await query.bot.send_message(
                            chat_id=current_chat_id, 
                            text=text, 
                            reply_markup=km, 
                            parse_mode=pmode, 
                            message_thread_id=current_thread_id
                        )
                    except BadRequest as e:
                        if "can't parse entities" in str(e).lower():
                            safe_text = format_welcome_message(node['text'] or "", query.from_user, group_name, parse_mode=None)
                            await query.bot.send_message(
                                chat_id=current_chat_id, 
                                text=safe_text, 
                                reply_markup=km, 
                                parse_mode=None, 
                                message_thread_id=current_thread_id
                            )
                        else:
                            raise
                else:
                    # Editar texto existente
                    await self.safe_edit_message_text(query, text, reply_markup=km, parse_mode=pmode)

        except Exception as e:
            try:
                await query.answer(f"Error mostrando contenido: {e}", show_alert=True)
            except:
                pass

    async def test_welcome_message(self, query, chat_id: int):
        # Enviar vista previa al administrador - CORREGIDO para funcionar siempre
        await self.db.ensure_root_node(chat_id)
        root = await self.db.get_root_node(chat_id)
        if not root:
            await query.answer("❌ No hay configuración de bienvenida")
            return

        try:
            # Intentar crear conversación privada con el admin primero
            try:
                await query.bot.send_message(
                    chat_id=query.from_user.id,
                    text="🔍 Preparando vista previa..."
                )
            except Exception:
                # Si no se puede enviar al privado, informar al usuario
                await query.answer("❌ Necesitas iniciar una conversación privada conmigo primero. Envíame /start en privado.", show_alert=True)
                return

            pmode = self._normalize_parse_mode(root.get('parse_mode') or "HTML")
            group = await self.db.get_group_info(chat_id)
            group_name = group[1] if group else "el grupo"
            text = format_welcome_message(root['text'] or "", query.from_user, group_name, parse_mode=pmode)
            km = self.build_node_keyboard(root)

            # Enviar al chat privado con el administrador
            admin_chat_id = query.from_user.id

            if pmode.lower().startswith("markdown"):
                safe_group_name = group_name.replace('.', '\\.')
                preview_text = f":magic_premium: **Vista previa de bienvenida para:** {safe_group_name}\n\n{text}"
                preview_text = add_premium_emojis(preview_text, pmode)
            else:
                preview_text = f"🧪 **Vista previa de bienvenida para:** {group_name}\n\n{text}"

            try:
                if root.get('image_url'):
                    await query.bot.send_photo(
                        chat_id=admin_chat_id, 
                        photo=root['image_url'], 
                        caption=preview_text, 
                        reply_markup=km, 
                        parse_mode=pmode
                    )
                else:
                    await query.bot.send_message(
                        chat_id=admin_chat_id, 
                        text=preview_text, 
                        reply_markup=km, 
                        parse_mode=pmode
                    )
                await query.answer("✅ Vista previa enviada a tu chat privado")
            except BadRequest as e:
                if "can't parse entities" in str(e).lower():
                    safe_message = format_welcome_message(root['text'] or "", query.from_user, group_name, parse_mode=None)
                    safe_preview = f"🧪 Vista previa de bienvenida para: {group_name}\n\n{safe_message}"
                    try:
                        if root.get('image_url'):
                            await query.bot.send_photo(
                                chat_id=admin_chat_id, 
                                photo=root['image_url'], 
                                caption=safe_preview, 
                                reply_markup=km, 
                                parse_mode=None
                            )
                        else:
                            await query.bot.send_message(
                                chat_id=admin_chat_id, 
                                text=safe_preview, 
                                reply_markup=km, 
                                parse_mode=None
                            )
                        await query.answer("✅ Vista previa enviada (sin formato)")
                    except Exception as e2:
                        await query.answer(f"❌ Error enviando vista previa: {e2}", show_alert=True)
                else:
                    await query.answer(f"❌ Error: {e}", show_alert=True)
        except Exception as e:
            await query.answer(f"❌ Error enviando vista previa: {e}", show_alert=True)

    async def show_admin_panel(self, query):
        keyboard = [
            [InlineKeyboardButton("📊 Ver Grupos", callback_data="view_groups")],
            [InlineKeyboardButton("🎉 Gestionar Bienvenidas", callback_data="manage_welcomes")],
            [InlineKeyboardButton("⚙️ Configuraciones Globales", callback_data="global_settings")],
            [InlineKeyboardButton("📈 Estadísticas Generales", callback_data="general_stats")],
            [InlineKeyboardButton("ℹ️ Información del Bot", callback_data="bot_info")]
        ]
        
        admin_text = """
:crown_premium: **Panel de Administración Principal** :crown_premium:

:rocket_premium: Desde aquí puedes gestionar todos los aspectos del bot\.

:star_premium: Selecciona una opción para continuar:

:magic_premium: **¡Nuevo\!** Sistema completo de emojis premium integrado
"""
        formatted_text = add_premium_emojis(admin_text, "MarkdownV2")
        
        await self.safe_edit_message_text(query,
            formatted_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="MarkdownV2"
        )

    async def show_groups_list(self, query):
        groups = await self.db.get_all_active_groups()
        if not groups:
            no_groups_text = """
:wow_premium: No hay grupos registrados aún\.

:rocket_premium: Añade el bot a un grupo para comenzar\.
"""
            formatted_text = add_premium_emojis(no_groups_text, "MarkdownV2")
            
            await self.safe_edit_message_text(query,
                formatted_text,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Volver", callback_data="admin_panel")]]),
                parse_mode="MarkdownV2"
            )
            return

        text = ":star_premium: **Lista de Grupos Registrados** :star_premium:\n\n"
        keyboard = []
        for group in groups:
            safe_group_name = group[1].replace('.', '\\.')
            safe_date = format_date(group[7]).replace('.', '\\.')
            text += f":check_premium: {safe_group_name}\n"
            text += f"  🆔 ID: `{group[0]}`\n"
            text += f"  👥 Miembros: {group[6]}\n"
            text += f"  📅 Añadido: {safe_date}\n\n"
            keyboard.append([InlineKeyboardButton(
                f"⚙️ {truncate_text(group[1], 25)}",
                callback_data=f"config_group_{group[0]}"
            )])

        keyboard.append([InlineKeyboardButton("🔙 Volver al Panel", callback_data="admin_panel")])
        formatted_text = add_premium_emojis(text, "MarkdownV2")
        
        await self.safe_edit_message_text(query, formatted_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="MarkdownV2")

    async def show_welcome_config(self, query, chat_id: int):
        await self.db.ensure_root_node(chat_id)
        welcome_config = await self.db.get_welcome_settings(chat_id)
        group = await self.db.get_group_info(chat_id)
        if not group:
            await self.safe_edit_message_text(query, "❌ Grupo no encontrado.")
            return

        root_node = await self.db.get_root_node(chat_id)
        buttons = self._buttons_to_list(root_node.get('buttons') if root_node else [])
        buttons_count = sum(len(r) for r in buttons)

        status = ":check_premium: Activado" if welcome_config and welcome_config[1] else "❌ Desactivado"
        message_preview = truncate_text(root_node['text'] or "", 120) if root_node else "Sin mensaje"

        safe_group_name = group[1].replace('.', '\\.')
        safe_message_preview = message_preview.replace('.', '\\.')

        text = f"""
:party_premium: **Configuración de Bienvenida** :party_premium:

**Grupo:** {safe_group_name}
**Estado:** {status}
**Mensaje actual:**
{safe_message_preview}

**Botones configurados:** {buttons_count}
**Imagen:** {':check_premium: Sí' if root_node and root_node.get('image_url') else '❌ No'}
"""

        keyboard = [
            [InlineKeyboardButton("📝 Editar Mensaje", callback_data=f"edit_welcome_message_{chat_id}")],
            [InlineKeyboardButton("🔘 Gestionar Botones/Submenús", callback_data=f"edit_welcome_buttons_{chat_id}")],
            [InlineKeyboardButton("🖼️ Configurar Imagen", callback_data=f"edit_welcome_image_{chat_id}")],
            [InlineKeyboardButton("🔄 Cambiar Estado", callback_data=f"toggle_welcome_{chat_id}")],
            [InlineKeyboardButton("🧪 Probar Bienvenida", callback_data=f"test_welcome_{chat_id}")],
            [InlineKeyboardButton("🔙 Volver", callback_data="back_groups")]
        ]
        formatted_text = add_premium_emojis(text, "MarkdownV2")
        await self.safe_edit_message_text(query, formatted_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="MarkdownV2")

    async def show_node_manager(self, query, chat_id: int, node_id: int | None):
        await self.db.ensure_root_node(chat_id)
        node = await self.db.get_root_node(chat_id) if node_id is None else await self.db.get_node(node_id)
        if not node:
            await self.safe_edit_message_text(query, "❌ Nodo no encontrado.")
            return

        buttons = self._buttons_to_list(node.get('buttons'))
        btn_count = sum(len(r) for r in buttons)
        pmode = self._normalize_parse_mode(node.get('parse_mode') or "HTML")

        node_label = "Raíz" if node['parent_id'] is None else f"ID {node['id']}"
        text = f":gem_premium: **Gestor de Botones/Submenús** :gem_premium:\n\n**Nodo:** {node_label}\n**Botones:** {btn_count}\n**Parse mode actual:** {pmode}\n"

        if buttons:
            for i, row in enumerate(buttons, 1):
                for j, b in enumerate(row, 1):
                    if b.get('type') == 'url':
                        safe_text = b.get('text', '').replace('.', '\\.')
                        safe_url = b.get('url', '').replace('.', '\\.')
                        text += f":point_left_premium: [{i}\\.{j}] URL: {safe_text} → {safe_url}\n"
                    elif b.get('type') == 'node':
                        safe_text = b.get('text', '').replace('.', '\\.')
                        text += f":point_left_premium: [{i}\\.{j}] Submenú: {safe_text} → Node {b.get('node_id')}\n"
        else:
            text += "No hay botones en este nodo\\.\n"

        children = await self.db.get_child_nodes(node['chat_id'], node['id'])
        if children:
            text += f"\n**Submenús hijos:** {len(children)}\n"
            for ch in children:
                prev = truncate_text(ch['text'] or '', 40).replace('.', '\\.')
                text += f":rocket_premium: Node {ch['id']}: {prev}\n"

        keyboard = [
            [InlineKeyboardButton("➕ Botón URL", callback_data=f"node_add_url_{node['id']}")],
            [InlineKeyboardButton("➕ Submenú", callback_data=f"node_add_sub_{node['id']}")],
            [InlineKeyboardButton("📝 Editar texto", callback_data=f"node_rename_{node['id']}")],
            [InlineKeyboardButton("🖼️ Imagen del nodo", callback_data=f"node_set_image_{node['id']}")],
            [InlineKeyboardButton(f"🛠 Parse mode: {pmode}", callback_data=f"node_parse_{node['id']}")],
            [InlineKeyboardButton("🧹 Limpiar botones", callback_data=f"node_clear_btns_{node['id']}")],
        ]
        if node['parent_id'] is not None:
            keyboard.append([InlineKeyboardButton("🗑️ Eliminar este submenú", callback_data=f"node_del_{node['id']}")])
        keyboard.append([InlineKeyboardButton("📂 Ver submenús", callback_data=f"node_list_children_{node['chat_id']}_{node['id']}")])
        keyboard.append([InlineKeyboardButton("🔙 Volver", callback_data=f"config_welcome_{chat_id}")])

        formatted_text = add_premium_emojis(text, "MarkdownV2")
        await self.safe_edit_message_text(query, formatted_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="MarkdownV2")

    async def show_children_list(self, query, chat_id: int, node_id: int):
        children = await self.db.get_child_nodes(chat_id, node_id)
        if not children:
            await query.answer("No hay submenús", show_alert=True)
            await self.show_node_manager(query, chat_id, node_id)
            return
        text = ":rocket_premium: **Submenús:**\n"
        kb = []
        for ch in children:
            prev = truncate_text(ch['text'] or '', 40).replace('.', '\\.')
            text += f":star_premium: Node {ch['id']}: {prev}\n"
            kb.append([InlineKeyboardButton(f"⚙️ Node {ch['id']}", callback_data=f"node_mgr_{chat_id}_{ch['id']}")])
        kb.append([InlineKeyboardButton("🔙 Volver", callback_data=f"node_mgr_{chat_id}_{node_id}")])
        
        formatted_text = add_premium_emojis(text, "MarkdownV2")
        await self.safe_edit_message_text(query, formatted_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="MarkdownV2")

    async def start_add_url_button(self, query, node_id: int):
        node = await self.db.get_node(node_id)
        self.message_handler.waiting_for_input[query.from_user.id] = {
            'action': 'button_text',
            'button_type': 'url',
            'node_id': node_id,
            'chat_id': node['chat_id']
        }
        
        url_text = """
:plus_premium: **Añadir botón URL** :plus_premium:

:rocket_premium: Envía el texto que tendrá el botón:
"""
        formatted_text = add_premium_emojis(url_text, "MarkdownV2")
        
        await self.safe_edit_message_text(query,
            formatted_text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data=f"node_mgr_{node['chat_id']}_{node_id}")]]),
            parse_mode="MarkdownV2"
        )

    async def start_add_submenu_button(self, query, node_id: int):
        node = await self.db.get_node(node_id)
        self.message_handler.waiting_for_input[query.from_user.id] = {
            'action': 'button_sub_text',
            'node_id': node_id,
            'chat_id': node['chat_id']
        }
        
        submenu_text = """
:gem_premium: **Añadir Submenú** :gem_premium:

:star_premium: 1\\) Envía el texto del botón que abrirá el submenú\\.
"""
        formatted_text = add_premium_emojis(submenu_text, "MarkdownV2")
        
        await self.safe_edit_message_text(query,
            formatted_text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data=f"node_mgr_{node['chat_id']}_{node_id}")]]),
            parse_mode="MarkdownV2"
        )

    async def start_node_image_edit(self, query, node_id: int):
        node = await self.db.get_node(node_id)
        self.message_handler.waiting_for_input[query.from_user.id] = {
            'action': 'node_image',
            'node_id': node_id
        }
        
        image_text = """
:magic_premium: **Configurar imagen del nodo** :magic_premium:

:rocket_premium: Envía una URL de imagen o directamente una foto desde tu galería\\.

:check_premium: Escribe 'remove' para quitar la imagen\\.
"""
        formatted_text = add_premium_emojis(image_text, "MarkdownV2")
        
        await self.safe_edit_message_text(query,
            formatted_text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data=f"node_mgr_{node['chat_id']}_{node_id}")]]),
            parse_mode="MarkdownV2"
        )

    async def start_node_rename(self, query, node_id: int):
        node = await self.db.get_node(node_id)
        self.message_handler.waiting_for_input[query.from_user.id] = {
            'action': 'node_rename',
            'node_id': node_id
        }
        
        rename_text = """
:star_premium: **Editar texto del nodo** :star_premium:

:rocket_premium: Envía el nuevo texto \\(variables: {mention}, {name}, {username}, {group\\_name}\\):

:magic_premium: **¡Puedes usar emojis premium\\!** Ejemplo: `:crown_premium:` `:fire_premium:`
"""
        formatted_text = add_premium_emojis(rename_text, "MarkdownV2")
        
        await self.safe_edit_message_text(query,
            formatted_text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data=f"node_mgr_{node['chat_id']}_{node_id}")]]),
            parse_mode="MarkdownV2"
        )

    async def start_welcome_message_edit(self, query, chat_id: int):
        self.message_handler.waiting_for_input[query.from_user.id] = {
            'action': 'welcome_message',
            'chat_id': chat_id
        }
        
        welcome_edit_text = """
:crown_premium: **Editar Mensaje de Bienvenida** :crown_premium:

:rocket_premium: Envía el nuevo mensaje que se mostrará cuando alguien se una al grupo\\.

:star_premium: **Puedes usar estas variables:**
:check_premium: `{mention}` — menciona al usuario
:check_premium: `{name}` — nombre del usuario  
:check_premium: `{username}` — @usuario o nombre si no tiene
:check_premium: `{group_name}` — nombre del grupo

:magic_premium: **Emojis premium disponibles:**
`:crown_premium:` `:fire_premium:` `:star_premium:` `:rocket_premium:` `:diamond_premium:`

:gem_premium: **Formatos soportados:** HTML o MarkdownV2\\.
:lightning_premium: **Sugerencia:** si usas MarkdownV2, recuerda escapar los caracteres especiales\\.
"""
        formatted_text = add_premium_emojis(welcome_edit_text, "MarkdownV2")
        
        await self.safe_edit_message_text(query,
            formatted_text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data=f"config_welcome_{chat_id}")]]),
            parse_mode="MarkdownV2"
        )

    async def start_welcome_image_edit(self, query, chat_id: int):
        root_id = await self.db.ensure_root_node(chat_id)
        self.message_handler.waiting_for_input[query.from_user.id] = {
            'action': 'node_image',
            'node_id': root_id
        }
        
        image_edit_text = """
:magic_premium: **Configurar Imagen de Bienvenida \\(Nodo raíz\\)** :magic_premium:

:rocket_premium: Envía una URL de imagen, o directamente una **foto**\\.

:check_premium: Escribe `remove` para quitarla\\.
"""
        formatted_text = add_premium_emojis(image_edit_text, "MarkdownV2")
        
        await self.safe_edit_message_text(query,
            formatted_text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data=f"config_welcome_{chat_id}")]]),
            parse_mode="MarkdownV2"
        )

    async def toggle_welcome_status(self, query, chat_id: int):
        new_status = await self.db.toggle_welcome_status(chat_id)
        status_text = "activada" if new_status else "desactivada"
        await query.answer(f"Bienvenida {status_text}")
        await self.show_welcome_config(query, chat_id)

    async def show_general_stats(self, query):
        stats = await self.db.get_general_stats()
        text = f"""
:trophy_premium: **Estadísticas Generales del Bot** :trophy_premium:

:star_premium: Grupos activos: {stats['total_groups'][0]}
:wow_premium: Grupos inactivos: {stats['inactive_groups'][0]}
:party_premium: Total bienvenidas: {stats['total_welcomes'][0] or 0}
:gem_premium: Promedio miembros: {int(stats['avg_members'][0]) if stats['avg_members'][0] else 0}

:crown_premium: **Top 5 grupos \\(por bienvenidas\\):**
"""
        for i, group in enumerate(stats['top_groups'], 1):
            safe_group_name = group[0].replace('.', '\\.')
            text += f"{i}\\. {safe_group_name}: {group[1]} bienvenidas\n"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Actualizar Stats", callback_data="general_stats")],
            [InlineKeyboardButton("🔙 Volver al Panel", callback_data="admin_panel")]
        ]
        formatted_text = add_premium_emojis(text, "MarkdownV2")
        await self.safe_edit_message_text(query, formatted_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="MarkdownV2")

    async def show_bot_info(self, query):
        stats = await self.db.get_general_stats()
        text = f"""
:crown_premium: **Información del Bot** :crown_premium:

:rocket_premium: **Nombre:** Bot Administrador Premium
:star_premium: **Versión:** 1\\.5\\.0
:fire_premium: **Grupos activos:** {stats['total_groups'][0]}
:party_premium: **Bienvenidas enviadas:** {stats['total_welcomes'][0] or 0}
:gem_premium: **Base de datos:** MongoDB \\(Motor\\)
:check_premium: **Estado:** Online

:magic_premium: **Funcionalidades:**
:lightning_premium: Sistema de bienvenida con submenús
:diamond_premium: Gestión avanzada de grupos
:trophy_premium: Panel de administración completo
:heart_premium: Estadísticas en tiempo real
:rocket_premium: Notificaciones automáticas
:star_premium: Soporte de temas para hilos específicos
:crown_premium: **¡NUEVO\\!** Sistema completo de emojis premium
"""
        keyboard = [[InlineKeyboardButton("🔙 Volver al Panel", callback_data="admin_panel")]]
        formatted_text = add_premium_emojis(text, "MarkdownV2")
        await self.safe_edit_message_text(query, formatted_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="MarkdownV2")

    async def show_manage_welcomes(self, query):
        groups = await self.db.get_all_active_groups()
        if not groups:
            no_welcomes_text = """
:wow_premium: No hay grupos con configuraciones de bienvenida\\.

:rocket_premium: Añade el bot a un grupo para comenzar\\.
"""
            formatted_text = add_premium_emojis(no_welcomes_text, "MarkdownV2")
            
            await self.safe_edit_message_text(query,
                formatted_text,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Volver", callback_data="admin_panel")]]),
                parse_mode="MarkdownV2"
            )
            return

        text = ":party_premium: **Gestión de Bienvenidas** :party_premium:\n\n"
        keyboard = []
        for group in groups:
            welcome_config = await self.db.get_welcome_settings(group[0])
            status = ":check_premium:" if welcome_config and welcome_config[1] else "❌"
            safe_group_name = group[1].replace('.', '\\.')
            text += f"{status} {safe_group_name}\n"
            keyboard.append([InlineKeyboardButton(
                f"{status} {truncate_text(group[1], 25)}",
                callback_data=f"config_welcome_{group[0]}"
            )])
        keyboard.append([InlineKeyboardButton("🔙 Volver al Panel", callback_data="admin_panel")])
        formatted_text = add_premium_emojis(text, "MarkdownV2")
        await self.safe_edit_message_text(query, formatted_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="MarkdownV2")

    async def show_global_settings(self, query):
        settings = await self.db.get_all_settings()
        language = settings.get('language', 'es')
        datefmt = settings.get('date_format', '%d/%m/%Y %H:%M')
        parse_mode = settings.get('default_parse_mode', 'HTML')

        safe_datefmt = datefmt.replace('%', '\\%')

        text = f"""
:gear_premium: **Configuraciones Globales** :gear_premium:

:globe_premium: **Idioma:** {language}
:calendar_premium: **Formato de fecha:** {safe_datefmt}
:magic_premium: **Parse Mode por defecto:** {parse_mode}

:star_premium: Ajusta una opción:
"""
        kb = [
            [
                InlineKeyboardButton("🌐 ES", callback_data="gs_lang_es"),
                InlineKeyboardButton("EN", callback_data="gs_lang_en"),
            ],
            [
                InlineKeyboardButton("Fecha: DD/MM/YYYY HH:mm", callback_data="gs_datefmt_1"),
                InlineKeyboardButton("YYYY-MM-DD HH:mm", callback_data="gs_datefmt_2"),
                InlineKeyboardButton("DD/MM/YYYY", callback_data="gs_datefmt_3"),
            ],
            [
                InlineKeyboardButton("Parse: HTML", callback_data="gs_parse_HTML"),
                InlineKeyboardButton("MarkdownV2", callback_data="gs_parse_MarkdownV2"),
            ],
            [InlineKeyboardButton("🔙 Volver al Panel", callback_data="admin_panel")]
        ]
        formatted_text = add_premium_emojis(text, "MarkdownV2")
        await self.safe_edit_message_text(query, formatted_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="MarkdownV2")

    async def show_group_settings(self, query, chat_id: int):
        # Traer info en vivo del chat para reflejar si los temas están habilitados
        try:
            chat = await query.bot.get_chat(chat_id)
            member_count = await query.bot.get_chat_member_count(chat_id)
            is_forum_live = getattr(chat, "is_forum", False)
            await self.db.update_group_info(chat_id, chat.title, member_count, is_forum=is_forum_live)
        except Exception:
            pass  # Si falla, usamos lo que haya en DB

        group = await self.db.get_group_info(chat_id)
        if not group:
            await self.safe_edit_message_text(query, "❌ Grupo no encontrado.")
            return

        is_forum = bool(group[9])
        welcome_thread_id = group[10]

        safe_group_name = group[1].replace('.', '\\.')
        safe_added_by = group[5].replace('.', '\\.')
        safe_date = format_date(group[7]).replace('.', '\\.')

        text = f"""
:gear_premium: **Configuraciones del Grupo** :gear_premium:

:star_premium: **Nombre:** {safe_group_name}
:gem_premium: **ID:** `{chat_id}`
:rocket_premium: **Tipo:** {group[2]}
:crown_premium: **Miembros:** {group[6]}
:check_premium: **Añadido por:** {safe_added_by}
:calendar_premium: **Fecha de adición:** {safe_date}
:magic_premium: **Temas habilitados:** {'Sí' if is_forum else 'No'}
:lightning_premium: **Tema de bienvenidas:** {welcome_thread_id if welcome_thread_id is not None else 'No configurado'}
"""
        keyboard = [
            [InlineKeyboardButton("🎉 Configurar Bienvenida", callback_data=f"config_welcome_{chat_id}")],
            [InlineKeyboardButton("🧵 Configurar tema de bienvenida", callback_data=f"set_welcome_topic_instr_{chat_id}")],
            [InlineKeyboardButton("🧹 Limpiar tema de bienvenida", callback_data=f"clear_welcome_topic_{chat_id}")],
            [InlineKeyboardButton("🔄 Actualizar Información", callback_data=f"update_group_{chat_id}")],
            [InlineKeyboardButton("❌ Desactivar Grupo", callback_data=f"deactivate_group_{chat_id}")],
            [InlineKeyboardButton("🔙 Volver", callback_data="view_groups")]
        ]
        formatted_text = add_premium_emojis(text, "MarkdownV2")
        await self.safe_edit_message_text(query, formatted_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="MarkdownV2")

    async def show_group_stats(self, query, chat_id: int):
        group = await self.db.get_group_info(chat_id)
        stats = await self.db.get_group_stats(chat_id)
        if not group:
            await self.safe_edit_message_text(query, "❌ Grupo no encontrado.")
            return

        try:
            days_active = (datetime.utcnow() - datetime.fromisoformat(group[7])).days
        except:
            days_active = "N/D"

        welcomes_sent = stats[1] if stats else 0
        last_activity = format_date(stats[2]) if stats and stats[2] else "Nunca"

        safe_group_name = group[1].replace('.', '\\.')
        safe_last_activity = last_activity.replace('.', '\\.')

        text = f"""
:trophy_premium: **Estadísticas del Grupo** :trophy_premium:

:star_premium: **Grupo:** {safe_group_name}
:crown_premium: **Miembros actuales:** {group[6]}
:calendar_premium: **Días activo:** {days_active}
:party_premium: **Bienvenidas enviadas:** {welcomes_sent}
:lightning_premium: **Última actividad:** {safe_last_activity}
"""
        keyboard = [
            [InlineKeyboardButton("🔄 Actualizar Stats", callback_data=f"refresh_stats_{chat_id}")],
            [InlineKeyboardButton("🔙 Volver", callback_data=f"group_settings_{chat_id}")]
        ]
        formatted_text = add_premium_emojis(text, "MarkdownV2")
        await self.safe_edit_message_text(query, formatted_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="MarkdownV2")

    async def show_group_config(self, query, chat_id: int):
        await self.show_group_settings(query, chat_id)

    async def update_group_info(self, query, chat_id: int):
        try:
            chat = await query.bot.get_chat(chat_id)
            member_count = await query.bot.get_chat_member_count(chat_id)
            is_forum = getattr(chat, "is_forum", False)
            await self.db.update_group_info(chat_id, chat.title, member_count, is_forum=is_forum)
            await query.answer("✅ Información actualizada")
            await self.show_group_settings(query, chat_id)
        except Exception as e:
            await query.answer(f"❌ Error: {str(e)}")

    async def deactivate_group(self, query, chat_id: int):
        await self.db.deactivate_group(chat_id)
        await query.answer("✅ Grupo desactivado")
        await self.show_groups_list(query)

    async def refresh_group_stats(self, query, chat_id: int):
        await query.answer("✅ Estadísticas actualizadas")
        await self.show_group_stats(query, chat_id)

    async def handle_back_navigation(self, query, data: str):
        parts = data.split("_")
        destination = parts[1] if len(parts) > 1 else ""
        if destination == "admin":
            await self.show_admin_panel(query)
        elif destination == "groups":
            await self.show_groups_list(query)
        elif destination == "welcome" and len(parts) > 2:
            # back_welcome_{chat_id}
            chat_id = int(parts[-1])
            await self.show_welcome_config(query, chat_id)
        elif destination == "group" and len(parts) > 2:
            # back_group_{chat_id}
            chat_id = int(parts[-1])
            await self.show_group_settings(query, chat_id)

    async def show_parse_mode_selector(self, query, node_id: int):
        node = await self.db.get_node(node_id)
        if not node:
            await query.answer("Nodo no encontrado", show_alert=True)
            return
        pm = self._normalize_parse_mode(node.get('parse_mode') or "HTML")
        text = f"""
:magic_premium: **Cambiar Parse Mode** :magic_premium:

:gem_premium: **Nodo ID:** {node_id}
:star_premium: **Actual:** {pm}

:rocket_premium: Elige un modo de formato:
"""
        kb = [
            [
                InlineKeyboardButton("HTML", callback_data=f"node_set_parse_{node_id}_HTML"),
                InlineKeyboardButton("MarkdownV2", callback_data=f"node_set_parse_{node_id}_MarkdownV2"),
            ],
            [InlineKeyboardButton("🔙 Volver", callback_data=f"node_mgr_{node['chat_id']}_{node_id}")]
        ]
        formatted_text = add_premium_emojis(text, "MarkdownV2")
        await self.safe_edit_message_text(query, formatted_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="MarkdownV2")

    async def show_set_welcome_topic_instructions(self, query, chat_id: int):
        text = """
:magic_premium: **Configurar tema \\(hilo\\) para bienvenidas** :magic_premium:

:star_premium: **1\\)** En el grupo, abre el tema donde quieras que se envíen las bienvenidas\\.

:rocket_premium: **2\\)** Dentro de ese tema, ejecuta el comando: `/setwelcometopic`

:check_premium: **3\\)** Opcional: para limpiar la configuración, usa `/clearwelcometopic`

:gem_premium: **Nota:** Solo es necesario si el grupo tiene temas habilitados\\.
"""
        kb = [
            [InlineKeyboardButton("🔙 Volver", callback_data=f"group_settings_{chat_id}")]
        ]
        formatted_text = add_premium_emojis(text, "MarkdownV2")
        await self.safe_edit_message_text(query, formatted_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="MarkdownV2")
