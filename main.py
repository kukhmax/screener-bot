import asyncio
from aiogram import Bot

# --- НАСТРОЙКИ ---
BOT_TOKEN = '7565486640:AAG8yM1cB0dAJOpxF26-vrP4DTVe8MI_Z-M' # Пример
CHAT_ID = '199222002' # ВАШ ЛИЧНЫЙ ID, ПОЛУЧЕННЫЙ ОТ @userinfobot
# -----------------

async def send_test_message():
    """Отправляет тестовое сообщение в Telegram с помощью aiogram."""
    bot = Bot(token=BOT_TOKEN, parse_mode=None)
    try:
        message_text = "✅ Тест! Это сообщение должно прийти в чат со мной (ботом)."
        async with bot.context():
             await bot.send_message(chat_id=CHAT_ID, text=message_text)
        print(f"Сообщение успешно отправлено в чат {CHAT_ID}")
    except Exception as e:
        print(f"Ошибка при отправке сообщения: {e}")

if __name__ == "__main__":
    print("Запускаем отправку тестового сообщения (aiogram)...")
    asyncio.run(send_test_message())
    print("Скрипт завершил работу.")