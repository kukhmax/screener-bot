import asyncio
import ccxt
import ccxt.pro as ccxtpro
import time
from collections import deque
# УДАЛЕНО: import numpy as np

# Импортируем нашу функцию детектора
from detectors.brush_detector import check_brush_pattern

# --- НАСТРОЙКИ БИРЖИ ---
TEST_SYMBOL = '42069COIN/USDT'
# ----------------------

# --- НАСТРОЙКИ ДЕТЕКТОРА (берем из модуля, но можем переопределить) ---
# Например, максимальная длина deque должна соответствовать lookback из детектора
# Импортируем настройки из модуля детектора, чтобы использовать их
from detectors.brush_detector import BRUSH_LOOKBACK_TRADES

# Хранилище последних цен
price_history = deque(maxlen=BRUSH_LOOKBACK_TRADES)

async def watch_mexc_deals():
    """Подключается к MEXC, получает сделки и вызывает детектор 'Ёршика'."""
    exchange = ccxtpro.mexc({'options': {'defaultType': 'spot'}})
    print(f"Подключаемся к MEXC для отслеживания сделок по {TEST_SYMBOL}...")

    last_pattern_print_time = 0
    cooldown_period = 60 # Период "остывания" в секундах

    while True:
        try:
            trades = await exchange.watch_trades(TEST_SYMBOL)
            if trades:
                new_pattern_found_in_batch = False
                details_for_batch = {}

                for trade in trades:
                    try:
                        price = float(trade['price']) # Получаем цену сделки
                        price_history.append(price) # Добавляем в нашу историю
                    except (ValueError, TypeError, KeyError) as e:
                        print(f"Ошибка получения цены из сделки: {trade}, ошибка: {e}")
                        continue # Пропускаем эту сделку

                    # Вызываем функцию проверки из модуля detectors
                    is_brush, details = check_brush_pattern(price_history) # Передаем историю

                    if is_brush:
                        new_pattern_found_in_batch = True # Запоминаем, что паттерн найден
                        details_for_batch = details # Сохраняем детали для вывода

                # Выводим сообщение только если паттерн найден в этой пачке
                # и прошло время "остывания"
                current_time = time.time()
                if new_pattern_found_in_batch and (current_time - last_pattern_print_time > cooldown_period):
                     print("="*20 + " ПАТТЕРН 'ЁРШИК' ОБНАРУЖЕН! " + "="*20)
                     print(f"Символ: {TEST_SYMBOL}")
                     print(f"Детали: {details_for_batch}")
                     # Выводим цену из последней ОБРАБОТАННОЙ сделки в пачке
                     if price_history: # Проверка, что история не пуста
                         print(f"Последняя цена в истории: {price_history[-1]}")
                     print("="*68)
                     last_pattern_print_time = current_time # Обновляем время

        except ccxt.NetworkError as e:
            print(f"Ошибка сети ccxt: {e}. Попытка переподключения...")
            price_history.clear()
            await asyncio.sleep(5)
        # ИЗМЕНЕНО: Используем ccxt.ExchangeError
        except ccxt.ExchangeError as e:
            print(f"Ошибка биржи ccxt: {e}")
            # Если это BadSymbol, нет смысла переподключаться
            if isinstance(e, ccxt.BadSymbol):
                print(f"Неверный символ {TEST_SYMBOL}. Завершение работы.")
                break
            # Для других ошибок биржи можно добавить логику переподключения
            await asyncio.sleep(5) # Пауза перед возможным продолжением или выходом
        except Exception as e:
            print(f"Произошла общая ошибка в цикле: {e}")
            await asyncio.sleep(1)

    await exchange.close()
    print("Соединение с MEXC закрыто.")

if __name__ == "__main__":
    print("Запускаем отслеживание сделок и детектор 'Ёршика' (модульная версия)...")
    try:
        asyncio.run(watch_mexc_deals())
    except KeyboardInterrupt:
        print("\nЗавершение работы по команде пользователя (Ctrl+C)")
    finally:
        print("Основной скрипт завершил работу.")