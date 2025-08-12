from telegram.constants import ChatMemberStatus
from config import ADMIN_ID
import html

# Permisos
def check_admin_permissions(user_id: int, action: str = None) -> bool:
    if user_id == ADMIN_ID:
        return True
    return False

async def is_group_admin(context, chat_id: int, user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except:
        return False

# Función para manejar emojis premium
def add_premium_emojis(text: str, parse_mode: str = "MarkdownV2") -> str:
    """
    Convierte códigos de emojis premium a su formato correcto según el parse_mode
    """
    # Diccionario de emojis premium
    premium_emojis = {
        ':crown_premium:': '![👑](tg://emoji?id=5769547529993588669)',
        ':crown_gold:': '![👑](tg://emoji?id=5895592506459950634)',
        ':plus_premium:': '![➕](tg://emoji?id=5393194986252542669)',
        ':five_premium:': '![5️⃣](tg://emoji?id=5391197405553107640)',
        ':zero_premium:': '![0️⃣](tg://emoji?id=5393480373944459905)',
        ':cocktail_premium:': '![🍸](tg://emoji?id=5217449524410199951)',
        ':globe_premium:': '![🌐](tg://emoji?id=5895665559558689321)',
        ':free_premium:': '![🆓](tg://emoji?id=5406756500108501710)',
        ':down_arrow_premium:': '![⬇️](tg://emoji?id=5406745015365943482)',
        ':point_left_premium:': '![👈](tg://emoji?id=6319056439096644016)',
        ':tongue_premium:': '![😛](tg://emoji?id=5413341178894493509)',
        ':check_premium:': '![✔️](tg://emoji?id=5206607081334906820)',
        ':wow_premium:': '![😮](tg://emoji?id=5391090636961099009)',
        ':fire_premium:': '![🔥](tg://emoji?id=5469986291380657891)',
        ':star_premium:': '![⭐](tg://emoji?id=5469654991199578830)',
        ':rocket_premium:': '![🚀](tg://emoji?id=5469741319743707297)',
        ':diamond_premium:': '![💎](tg://emoji?id=5469741319743707298)',
        ':party_premium:': '![🎉](tg://emoji?id=5469741319743707299)',
        ':heart_premium:': '![❤️](tg://emoji?id=5469741319743707300)',
        ':lightning_premium:': '![⚡](tg://emoji?id=5469741319743707301)',
        ':trophy_premium:': '![🏆](tg://emoji?id=5469741319743707302)',
        ':gem_premium:': '![💠](tg://emoji?id=5469741319743707303)',
        ':magic_premium:': '![✨](tg://emoji?id=5469741319743707304)'
    }
    
    if parse_mode and parse_mode.lower().startswith("markdown"):
        # Para MarkdownV2, usar formato completo de emojis premium
        for code, emoji in premium_emojis.items():
            text = text.replace(code, emoji)
    else:
        # Para HTML o texto plano, usar emoji normal como fallback
        emoji_fallbacks = {
            ':crown_premium:': '👑',
            ':crown_gold:': '👑',
            ':plus_premium:': '➕',
            ':five_premium:': '5️⃣',
            ':zero_premium:': '0️⃣',
            ':cocktail_premium:': '🍸',
            ':globe_premium:': '🌐',
            ':free_premium:': '🆓',
            ':down_arrow_premium:': '⬇️',
            ':point_left_premium:': '👈',
            ':tongue_premium:': '😛',
            ':check_premium:': '✔️',
            ':wow_premium:': '😮',
            ':fire_premium:': '🔥',
            ':star_premium:': '⭐',
            ':rocket_premium:': '🚀',
            ':diamond_premium:': '💎',
            ':party_premium:': '🎉',
            ':heart_premium:': '❤️',
            ':lightning_premium:': '⚡',
            ':trophy_premium:': '🏆',
            ':gem_premium:': '💠',
            ':magic_premium:': '✨'
        }
        for code, emoji in emoji_fallbacks.items():
            text = text.replace(code, emoji)
    
    return text

# Escapes
def _escape_md_v2(text: str) -> str:
    if not text:
        return ""
    # Caracteres especiales de MarkdownV2: \ _ * [ ] ( ) ~ ` > # + - = | { } . !
    specials = r'\_*[]()~`>#+-=|{}.!'
    for ch in specials:
        text = text.replace(ch, f'\\{ch}')
    return text

def _escape_html(text: str) -> str:
    return html.escape(text or "", quote=False)

# Mensaje de bienvenida, consciente del parse_mode y tolerante a user None
def format_welcome_message(template: str, user, group_name: str, parse_mode: str = "HTML") -> str:
    # Tolerancia a user None
    uid = getattr(user, "id", None)
    raw_name = getattr(user, "first_name", "") or ""
    raw_username = f"@{getattr(user, 'username', None)}" if getattr(user, "username", None) else (raw_name or "usuario")
    raw_group = group_name or ""

    pm = (parse_mode or "HTML").strip()
    if pm.lower().startswith("markdown"):
        # MarkdownV2
        name = _escape_md_v2(raw_name)
        username = _escape_md_v2(raw_username)
        group_e = _escape_md_v2(raw_group)
        mention = f"[{name}](tg://user?id={uid})" if uid else name
        out = (template or "")
        out = out.replace("{mention}", mention)
        out = out.replace("{name}", name)
        out = out.replace("{username}", username)
        out = out.replace("{group_name}", group_e)
        # Procesar emojis premium
        out = add_premium_emojis(out, pm)
        return out

    elif pm.upper() == "HTML":
        name = _escape_html(raw_name)
        username = _escape_html(raw_username)
        group_e = _escape_html(raw_group)
        mention = f"<a href='tg://user?id={uid}'>{name}</a>" if uid else name
        out = (template or "")
        out = out.replace("{mention}", mention)
        out = out.replace("{name}", name)
        out = out.replace("{username}", username)
        out = out.replace("{group_name}", group_e)
        # Procesar emojis premium (fallback a emojis normales)
        out = add_premium_emojis(out, pm)
        return out

    # Plano (sin formato) como fallback
    out = (template or "")
    out = out.replace("{mention}", raw_name or "usuario")
    out = out.replace("{name}", raw_name or "usuario")
    out = out.replace("{username}", raw_username or "usuario")
    out = out.replace("{group_name}", raw_group)
    # Procesar emojis premium (fallback)
    out = add_premium_emojis(out, None)
    return out

def truncate_text(text: str, max_length: int = 50) -> str:
    if not text:
        return ""
    if len(text) > max_length:
        return text[:max_length] + "..."
    return text

def format_date(date_string: str) -> str:
    try:
        from datetime import datetime
        # Soporta fecha ISO con o sin 'Z'
        if date_string and date_string.endswith('Z'):
            date_string = date_string[:-1]
        date_obj = datetime.fromisoformat(date_string)
        return date_obj.strftime('%d/%m/%Y %H:%M')
    except:
        return date_string[:10] if date_string else "Desconocido"
