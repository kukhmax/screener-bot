import asyncio
import ccxt.pro as ccxtpro # Используем ccxt.pro для WebSocket
import time
# from aiogram import Bot # Пока не используем Telegram

# --- НАСТРОЙКИ ---
# BOT_TOKEN = '7565486640:AAG8yM1cB0dAJOpxF26-vrP4DTVe8MI_Z-M' # Пример
# CHAT_ID = '199222002' # ВАШ ЛИЧНЫЙ ID, ПОЛУЧЕННЫЙ ОТ @userinfobot
MEXC_WSS_URL = "wss://wbs.mexc.com/ws" # Адрес WebSocket MEXC V3
TEST_SYMBOL = "BTCUSDT" # Тестовая пара (без '/')
# -----------------


async def watch_mexc_deals():
    """Подключается к MEXC через ccxt.pro и получает поток сделок."""
    exchange = ccxtpro.mexc({
        'options': {
            'defaultType': 'spot', # Указываем, что работаем со спотом
            # 'watchTrades': {'name': 'spot@public.deals.v3.api'}, # Можно кастомизировать имя потока если нужно
        },
        # 'verbose': True # Раскомментируйте для детального логгирования от ccxt
    })
    print(f"Подключаемся к MEXC для отслеживания сделок по {TEST_SYMBOL}...")

    while True:
        try:
            # Используем watch_trades для получения потока сделок
            trades = await exchange.watch_trades(TEST_SYMBOL)
            if trades:
                # trades - это список сделок, полученных с момента последнего вызова
                # Выводим только последнюю сделку из пачки для краткости
                latest_trade = trades[-1]
                print(f"[{latest_trade['datetime']}] {latest_trade['symbol']} | "
                      f"Цена: {latest_trade['price']} | Кол-во: {latest_trade['amount']} | "
                      f"Сторона: {latest_trade['side']}")
                # print(f"Получены сделки: {trades}") # Раскомментируйте, чтобы видеть всю пачку

        except ccxtpro.NetworkError as e:
            print(f"Ошибка сети ccxt: {e}. Попытка переподключения...")
            await asyncio.sleep(1) # Пауза перед переподключением
        except ccxtpro.ExchangeError as e:
            print(f"Ошибка биржи ccxt: {e}")
            break # Выход при ошибке биржи (можно добавить логику переподключения)
        except Exception as e:
            print(f"Произошла общая ошибка: {e}")
            await asyncio.sleep(1) # Пауза перед продолжением
        # finally:
            # Закрытие соединения ccxt обычно обрабатывает сам при выходе из цикла
            # Но для чистоты можно добавить await exchange.close() при завершении

    # Важно закрыть соединение при выходе из цикла (если не используется try/except в основном блоке)
    await exchange.close()
    print("Соединение с MEXC закрыто.")


# async def send_test_message():
#     # ... (код отправки в Telegram пока не нужен)

if __name__ == "__main__":
    print("Запускаем отслеживание сделок MEXC через ccxt.pro...")
    try:
        asyncio.run(watch_mexc_deals())
    except KeyboardInterrupt:
        print("\nЗавершение работы по команде пользователя (Ctrl+C)")
    finally:
        print("Основной скрипт завершил работу.")