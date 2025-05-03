import asyncio
# import ccxt.pro as ccxtpro # Больше не нужен для этого шага
import ccxt.async_support as ccxt_async # Нужен для fetch_ohlcv
import ccxt # Для ошибок
import time
from datetime import datetime, timedelta, timezone
import traceback
import csv
import os

# Импортируем детектор и его настройки
from detectors.brush_detector import check_brush_pattern, BRUSH_LOOKBACK_CANDLES # Импортируем новый параметр
# Импортируем функцию поиска символов
from utils.find_tokens import find_and_filter_symbols

# --- НАСТРОЙКИ ---
CHECK_INTERVAL_SECONDS = 60
CANDLE_TIMEFRAME = '1m'
PRINT_COOLDOWN_SECONDS = 300
PATTERN_LOG_CSV = 'brush_patterns_log.csv' # <-- Имя файла лога паттернов
# --- КОНЕЦ НАСТРОЕК ---

# Пересчет CANDLES_TO_FETCH
try:
    CANDLES_TO_FETCH = BRUSH_LOOKBACK_CANDLES + 50
except NameError:
    print("Ошибка: BRUSH_LOOKBACK_CANDLES не импортирована. Установлено значение по умолчанию.")
    BRUSH_LOOKBACK_CANDLES = 120
    CANDLES_TO_FETCH = BRUSH_LOOKBACK_CANDLES + 50

last_pattern_print_times = {}

async def check_exchange_timeframes(exchange):
    """Проверяет и выводит поддерживаемые биржей таймфреймы."""
    try:
        # Убедимся, что рынки загружены, т.к. timeframes могут зависеть от этого
        if not exchange.markets:
            await exchange.load_markets()

        if exchange.has['fetchOHLCV']:
            print("\nПоддерживаемые биржей MEXC таймфреймы (по данным ccxt):")
            # timeframes может быть None, если не поддерживается или не загружено
            if exchange.timeframes:
                print(list(exchange.timeframes.keys()))
            else:
                print("Не удалось получить список таймфреймов от ccxt (возможно, нужно загрузить рынки).")
            print(f"Используемый таймфрейм: {CANDLE_TIMEFRAME}")
            if exchange.timeframes and CANDLE_TIMEFRAME not in exchange.timeframes:
                print(f"ПРЕДУПРЕЖДЕНИЕ: Используемый таймфрейм '{CANDLE_TIMEFRAME}' может не поддерживаться биржей!")
        else:
            print("Биржа MEXC (по данным ccxt) не поддерживает fetchOHLCV.")
            return False # Не можем продолжать, если OHLCV не поддерживается
        return True
    except Exception as e:
        print(f"Ошибка при проверке таймфреймов: {e}")
        return False # Считаем, что не можем продолжать

async def fetch_ohlcv_safe(exchange, symbol, timeframe, limit):
    """Безопасно запрашивает OHLCV, обрабатывая ошибки."""
    try:
        # print(f"Запрос {limit} {timeframe} свечей для {symbol}...")
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        # print(f"Получено {len(ohlcv)} свечей для {symbol}")
        # Нам нужны только цены закрытия (индекс 4 в списке OHLCV)
        close_prices = [candle[4] for candle in ohlcv if len(candle) >= 5]
        return symbol, close_prices
    except ccxt.RateLimitExceeded as e:
        print(f"Превышен лимит запросов для {symbol}: {e}. Пропуск.")
        await asyncio.sleep(5) # Пауза при лимите
    except ccxt.NetworkError as e:
        print(f"Ошибка сети при запросе OHLCV для {symbol}: {e}. Пропуск.")
    except ccxt.ExchangeError as e:
        print(f"Ошибка биржи при запросе OHLCV для {symbol}: {e}. Пропуск.")
    except Exception as e:
        print(f"Неизвестная ошибка при запросе OHLCV для {symbol}: {e}")
    return symbol, None # Возвращаем None в случае ошибки

async def periodic_pattern_check(symbols: list):
    """
    Периодически запрашивает OHLCV для списка символов и проверяет паттерн 'Ёршик'.
    """
    if not symbols:
        print("Нет символов для проверки.")
        return

    exchange = ccxt_async.mexc({'options': {'defaultType': 'spot'}})
    print("\nПроверка поддержки OHLCV и таймфреймов...")
    if not await check_exchange_timeframes(exchange):
         print("Завершение работы из-за проблем с поддержкой OHLCV/таймфреймов.")
         await exchange.close()
         return # Выход, если проверка не пройдена

    print(f"\n[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}] Начинаем периодическую проверку ({CHECK_INTERVAL_SECONDS} сек) для {len(symbols)} символов...")

    while True:
        start_time_cycle = time.time()
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Начинаем цикл проверки...")

        # Создаем задачи для параллельного запроса OHLCV
        tasks = [fetch_ohlcv_safe(exchange, symbol, CANDLE_TIMEFRAME, CANDLES_TO_FETCH) for symbol in symbols]
        results = await asyncio.gather(*tasks)

        print(f"Обработка результатов для {len(results)} символов...")
        patterns_found_this_cycle = 0
        current_check_time = time.time()

        for symbol, close_prices in results:
            if close_prices is None or len(close_prices) < BRUSH_LOOKBACK_CANDLES:
                # Пропускаем символ, если данных нет или их недостаточно
                # if close_prices is not None:
                #     print(f"Debug [{symbol}]: Недостаточно данных {len(close_prices)}/{BRUSH_LOOKBACK_CANDLES}")
                continue

            try:
                is_brush, details = check_brush_pattern(close_prices)

                if is_brush:
                    last_print_time = last_pattern_print_times.get(symbol, 0)
                    if current_check_time - last_print_time > PRINT_COOLDOWN_SECONDS:
                        print("-" * 25)
                        print(f"🔥 ПАТТЕРН 'ЁРШИК' ОБНАРУЖЕН! 🔥")
                        print(f"Символ: {symbol}")
                        print(f"Таймфрейм: {CANDLE_TIMEFRAME}")
                        print(f"Детали: {details}")
                        print(f"Последняя цена закрытия: {close_prices[-1]}")
                        print(f"Время обнаружения: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                        print("-" * 25)
                        last_pattern_print_times[symbol] = current_check_time
                        patterns_found_this_cycle += 1

            except Exception as e_check:
                print(f"Ошибка при проверке паттерна для {symbol}: {e_check}")
                traceback.print_exc()


        cycle_duration = time.time() - start_time_cycle
        print(f"Цикл проверки завершен за {cycle_duration:.2f} сек. Найдено паттернов: {patterns_found_this_cycle}.")

        # Ждем перед следующим циклом
        sleep_time = max(0, CHECK_INTERVAL_SECONDS - cycle_duration)
        if sleep_time > 0:
            # print(f"Ожидание {sleep_time:.2f} сек перед следующим циклом...")
            await asyncio.sleep(sleep_time)

    # Закрытие соединения (этот код может быть недостижим в бесконечном цикле)
    print("Закрытие соединения с MEXC...")
    await exchange.close()


if __name__ == "__main__":
    print("Запускаем скринер (режим проверки по OHLCV)...")
    # 1. Получаем и фильтруем символы
    filtered_symbols_data = asyncio.run(find_and_filter_symbols())

    if filtered_symbols_data:
        symbols_to_watch = [item['symbol'] for item in filtered_symbols_data]
        print(f"\nПолучен список из {len(symbols_to_watch)} символов для периодической проверки.")

        # 2. Запускаем периодическую проверку
        if symbols_to_watch:
            print("Запуск основного цикла периодической проверки...")
            try:
                # Запускаем основной цикл проверки
                asyncio.run(periodic_pattern_check(symbols_to_watch))
            except KeyboardInterrupt:
                print("\nЗавершение работы по команде пользователя (Ctrl+C)")
            except Exception as e:
                print(f"Критическая ошибка в основном потоке: {e}")
                traceback.print_exc()
        else:
            print("Список символов для проверки пуст после фильтрации.")
    else:
        print("\nНе найдено символов для проверки или произошла ошибка при поиске.")

    print("\nОсновной скрипт завершил работу.")