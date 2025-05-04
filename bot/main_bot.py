import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
# --- ДОБАВЛЕН ИМПОРТ ---
from aiogram.client.default import DefaultBotProperties
import os
import dotenv
# Загружаем переменные окружения из .env файла
dotenv.load_dotenv()

# Импортируем router из handlers
from bot.handlers import router as main_router

# --- НАСТРОЙКИ БОТА ---
# Лучше вынести токен в переменные окружения или config файл
BOT_TOKEN = os.getenv("BOT_TOKEN") # !!! ЗАМЕНИТЕ НА СВОЙ ТОКЕН !!!
# ----------------------

async def main():
    """Основная функция запуска бота."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    logger = logging.getLogger(__name__)
    logger.info("Запуск Telegram бота...")

    if not BOT_TOKEN:
        logger.error("Токен бота не установлен! Замените 'СЮДА_ВАШ_API_ТОКЕН' в bot/main_bot.py")
        return

    # Инициализация бота и диспетчера
    storage = MemoryStorage()
    # --- ИЗМЕНЕНА ИНИЦИАЛИЗАЦИЯ BOT ---
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML") # Задаем parse_mode через DefaultBotProperties
    )
    # ----------------------------------
    dp = Dispatcher(storage=storage)

    dp.include_router(main_router)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Начинаем polling...")
        await dp.start_polling(bot)
    finally:
        logger.info("Остановка бота...")
        await bot.session.close()
        logger.info("Бот остановлен.")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Завершение работы бота по команде пользователя.")
    except Exception as e:
         logging.critical(f"Критическая ошибка при запуске бота: {e}", exc_info=True)