import logging

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuración del bot
BOT_TOKEN = "8063509725:AAHsa32julaJ4fst2OWhgj7lkL_HdA5ALN4"  # Tu token
ADMIN_ID = 1742433244

# MongoDB
MONGO_URI = "mongodb+srv://mundocrypto720:mundocrypto720@adminbotonera.8j9gzam.mongodb.net/adminbotonera?retryWrites=true&w=majority&appName=Adminbotonera"
DB_NAME = "adminbotonera"

# Mensajes por defecto con emojis premium
DEFAULT_WELCOME_MESSAGE = """
:crown_premium: ¡Bienvenido/a {mention} al grupo {group_name}! :fire_premium:

:star_premium: Esperamos que disfrutes tu estancia aquí :rocket_premium:

:check_premium: **¡Únete a nuestra comunidad premium!** :diamond_premium:
"""

# Configuraciones globales
SETTINGS = {
    'date_format': '%d/%m/%Y %H:%M',
    'language': 'es',
    'max_buttons_per_welcome': 10,
    'max_message_length': 4096
}
