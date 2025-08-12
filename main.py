import asyncio
import aiohttp
import aiohttp.web
from datetime import datetime
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

from config import BOT_TOKEN, logger, ADMIN_ID
from db_manager import DatabaseManager
from commands import CommandHandlers
from messages import MessageHandlers
from callbacks import CallbackHandlers

class KeepAliveService:
    def __init__(self, url: str = None, interval: int = 840):  # 14 minutos
        self.url = url or "https://tu-app.onrender.com"  # Reemplaza con tu URL
        self.interval = interval
        self.running = False
    
    async def ping_self(self):
        """Hace ping a sí mismo para mantener el servicio activo"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.url}/health", timeout=30) as response:
                    if response.status == 200:
                        logger.info(f"✅ Keep-alive ping exitoso - {datetime.now()}")
                    else:
                        logger.warning(f"⚠️ Keep-alive ping falló: {response.status}")
        except Exception as e:
            logger.error(f"❌ Error en keep-alive ping: {e}")
    
    async def start(self):
        """Inicia el servicio de keep-alive"""
        self.running = True
        logger.info("🔄 Servicio Keep-Alive iniciado")
        
        while self.running:
            await asyncio.sleep(self.interval)
            if self.running:
                await self.ping_self()
    
    def stop(self):
        """Detiene el servicio"""
        self.running = False
        logger.info("⏹️ Servicio Keep-Alive detenido")

async def health_check(request):
    return aiohttp.web.json_response({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "telegram-bot-premium"
    })

async def setup_health_server():
    """Configura un servidor HTTP simple para health checks"""
    app = aiohttp.web.Application()
    app.router.add_get('/health', health_check)

    runner = aiohttp.web.AppRunner(app)
    await runner.setup()

    import os
    port = int(os.environ.get('PORT', 8080))

    site = aiohttp.web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"🌐 Servidor de salud iniciado en puerto {port}")

    return runner

class TelegramBot:
    def __init__(self):
        self.application = None
        self.db = DatabaseManager()
        self.keep_alive = KeepAliveService()
        self.health_server = None
        
        self.command_handler = CommandHandlers(self.db)
        self.message_handler = MessageHandlers(self.db)
        self.callback_handler = CallbackHandlers(self.db, self.message_handler)

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        logger.error(f"Error en el bot: {context.error}")
        if update and hasattr(update, 'effective_user'):
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"❌ **Error en el bot:**\n\n`{str(context.error)}`",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"Error al enviar mensaje de error al admin: {e}")

    async def run(self):
        await self.db.initialize_db()

        # Inicia el servidor de salud
        self.health_server = await setup_health_server()

        self.application = Application.builder().token(BOT_TOKEN).build()

        # Comandos
        self.application.add_handler(CommandHandler("start", self.command_handler.start))
        self.application.add_handler(CommandHandler("admin", self.command_handler.admin_command))
        self.application.add_handler(CommandHandler("premiumemojis", self.command_handler.premium_emojis_command))
        self.application.add_handler(CommandHandler("setwelcometopic", self.command_handler.set_welcome_topic))
        self.application.add_handler(CommandHandler("clearwelcometopic", self.command_handler.clear_welcome_topic))

        # Mensajes y callbacks
        self.application.add_handler(MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS, 
            self.message_handler.handle_new_chat_member
        ))
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            self.message_handler.handle_text_input
        ))
        self.application.add_handler(MessageHandler(
            filters.PHOTO,
            self.message_handler.handle_photo_input
        ))
        self.application.add_handler(CallbackQueryHandler(self.callback_handler.handle_callback_query))

        # Agrega el manejador de errores
        self.application.add_error_handler(self.error_handler)

        logger.info("🚀 Iniciando bot premium con soporte para emojis...")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()

        # Inicia el keep-alive en segundo plano
        keep_alive_task = asyncio.create_task(self.keep_alive.start())

        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            logger.info("Deteniendo bot...")
        finally:
            self.keep_alive.stop()
            if not keep_alive_task.done():
                keep_alive_task.cancel()

            if self.health_server:
                await self.health_server.cleanup()

            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()

async def main():
    bot = TelegramBot()
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())
