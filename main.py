# main.py
import asyncio
import ccxt.async_support as ccxt_async
import ccxt
import time
from datetime import datetime, timezone
import traceback
import csv
import os

# Импорты детекторов
from detectors.brush_detector import check_brush_pattern, BRUSH_LOOKBACK_CANDLES
# Импортируем только нужные настройки и функцию детектора лесенки
from detectors.ladder_detector import check_ladder_pattern, LADDER_LOOKBACK_CANDLES

# Импорт поиска символов
from utils.find_tokens import find_and_filter_symbols # Убедитесь, что имя файла верное

# --- НАСТРОЙКИ ---
CHECK_INTERVAL_SECONDS = 60
CANDLE_TIMEFRAME = '1m'
PRINT_COOLDOWN_SECONDS = 300
BRUSH_PATTERN_LOG_CSV = 'brush_patterns_log.csv'
LADDER_PATTERN_LOG_CSV = 'ladder_patterns_log.csv'
LOG_COOLDOWN_SECONDS = 60 * 10 # Кулдаун для записи в лог (10 минут)
# -----------------

# Пересчет CANDLES_TO_FETCH
try:
    # Требуется максимальное количество свечей для обоих детекторов + запас
    CANDLES_TO_FETCH = max(BRUSH_LOOKBACK_CANDLES, LADDER_LOOKBACK_CANDLES + 1) + 50 # Исправлено: +1 для лесенки
except NameError:
    print("Ошибка импорта настроек детекторов. Установлены значения по умолчанию для FETCH.")
    BRUSH_LOOKBACK_CANDLES = 120
    LADDER_LOOKBACK_CANDLES = 60
    CANDLES_TO_FETCH = max(BRUSH_LOOKBACK_CANDLES, LADDER_LOOKBACK_CANDLES + 1) + 50 # Исправлено: +1 для лесенки

# Словари для кулдаунов
last_brush_log_times = {}
last_ladder_log_times = {}
last_pattern_print_times = {}

# --- Функция проверки таймфреймов ---
async def check_exchange_timeframes(exchange):
    try:
        if not getattr(exchange, 'markets', None): await exchange.load_markets()
        if exchange.has['fetchOHLCV']:
            print("\nПоддерживаемые биржей MEXC таймфреймы (по данным ccxt):")
            tf = getattr(exchange, 'timeframes', None)
            if tf: print(list(tf.keys()))
            else: print("Не удалось получить список таймфреймов от ccxt.")
            print(f"Используемый таймфрейм: {CANDLE_TIMEFRAME}")
            if tf and CANDLE_TIMEFRAME not in tf:
                print(f"ПРЕДУПРЕЖДЕНИЕ: Используемый таймфрейм '{CANDLE_TIMEFRAME}' может не поддерживаться!")
        else: print("Биржа MEXC (по данным ccxt) не поддерживает fetchOHLCV."); return False
        return True
    except Exception as e: print(f"Ошибка при проверке таймфреймов: {e}"); return False

# --- Функция получения OHLCV ---
async def fetch_ohlcv_safe(exchange: ccxt_async.Exchange, symbol: str, timeframe: str, limit: int):
    reported_errors = set() # Локальные ошибки для одного цикла
    try:
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        if not ohlcv:
            return symbol, None
        if all(len(candle) >= 5 for candle in ohlcv):
            return symbol, ohlcv
        else:
             valid_ohlcv = [candle for candle in ohlcv if len(candle) >= 5]
             # Проверяем на МИНИМАЛЬНО необходимое количество свечей
             required_min_len = max(BRUSH_LOOKBACK_CANDLES, LADDER_LOOKBACK_CANDLES + 1) # Исправлено: +1
             if len(valid_ohlcv) >= required_min_len:
                 return symbol, valid_ohlcv
             else:
                 # print(f"Предупреждение: Слишком мало валидных свечей ({len(valid_ohlcv)}/{required_min_len}) для {symbol}.")
                 return symbol, None
    except ccxt.BadRequest as e:
        error_key = f"{symbol}_{timeframe}_invalid_interval"
        if error_key not in fetch_ohlcv_safe.reported_errors:
             print(f"Ошибка BadRequest ('Invalid interval'?) для {symbol} [{timeframe}]: {e}. Пропуск.")
             fetch_ohlcv_safe.reported_errors.add(error_key)
    except ccxt.RateLimitExceeded as e: print(f"RateLimit для {symbol}: {e}. Пауза..."); await asyncio.sleep(10)
    except ccxt.NetworkError as e: print(f"NetworkError для {symbol}: {e}.")
    except ccxt.ExchangeError as e: print(f"ExchangeError для {symbol}: {e}.")
    except Exception as e: print(f"Unknown Error для {symbol}: {e}"); # traceback.print_exc()
    return symbol, None

# --- Функция дозаписи в CSV ---
def append_patterns_to_csv(patterns_data: list, filename: str):
    if not patterns_data: return
    file_exists = os.path.isfile(filename)
    # Проверка, что все словари в списке имеют одинаковый набор ключей
    if len(patterns_data) > 1:
        first_keys = set(patterns_data[0].keys())
        if not all(set(d.keys()) == first_keys for d in patterns_data[1:]):
            print(f"Предупреждение: Не все записи для {filename} имеют одинаковые ключи. Запись может быть некорректной.")
            # Можно попытаться найти общий набор ключей или записать как есть
    fieldnames = list(patterns_data[0].keys()) # Берем ключи из первой записи

    try:
        with open(filename, 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore') # Игнорировать лишние поля
            if not file_exists or os.path.getsize(filename) == 0:
                writer.writeheader()
            writer.writerows(patterns_data)
    except IOError as e: print(f"Ошибка записи в CSV файл {filename}: {e}")
    except Exception as e: print(f"Непредвиденная ошибка при дозаписи в CSV {filename}: {e}"); traceback.print_exc()

# --- Основная функция проверки паттернов ---
# --- ОСНОВНАЯ ФУНКЦИЯ ОДНОГО ЦИКЛА СКАНИРОВАНИЯ ---
async def run_one_scan_cycle(symbols: list):
    """
    Выполняет ОДИН цикл проверки паттернов для списка символов.
    Возвращает tuple: (list_of_brush_results, list_of_ladder_results)
    Каждый элемент списка - словарь с данными паттерна.
    """
    if not symbols:
        print("Нет символов для сканирования.")
        return [], []

    # Списки для сбора результатов этого цикла
    brush_patterns_found = []
    ladder_patterns_found = []

    exchange = ccxt_async.mexc({'options': {'defaultType': 'spot'}})
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Запуск одного цикла сканирования для {len(symbols)} символов...")
    try:
        # --- Проверка поддержки OHLCV ---
        # Убрана проверка таймфреймов отсюда, ее можно делать перед вызовом этой функции
        # if not await check_exchange_timeframes(exchange): # Можно вернуть, если нужно
        #     print("Проверка таймфреймов не пройдена.")
        #     await exchange.close()
        #     return [], []

        # --- Параллельный запрос OHLCV ---
        start_time_fetch = time.time()
        tasks = [fetch_ohlcv_safe(exchange, symbol, CANDLE_TIMEFRAME, CANDLES_TO_FETCH) for symbol in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        print(f"Запрос OHLCV завершен за {time.time() - start_time_fetch:.2f} сек.")

        # --- Обработка результатов и детекция ---
        print(f"Обработка результатов и детекция паттернов...")
        start_time_detect = time.time()
        detection_time_utc = datetime.now(timezone.utc) # Единое время для всех паттернов цикла

        for result in results:
            if isinstance(result, Exception): continue
            symbol, ohlcv_list = result
            if ohlcv_list is None: continue

            # Проверка Ёршика
            try:
                if len(ohlcv_list) >= BRUSH_LOOKBACK_CANDLES:
                    is_brush, brush_details = check_brush_pattern(ohlcv_list)
                    if is_brush:
                        log_entry = {'timestamp_utc': detection_time_utc.strftime('%Y-%m-%d %H:%M:%S'), 'symbol': symbol, **brush_details}
                        brush_patterns_found.append(log_entry)
            except Exception as e_brush: print(f"Ошибка детектора Brush для {symbol}: {e_brush}"); # traceback.print_exc()

            # Проверка Лесенки
            try:
                req_len_ladder = LADDER_LOOKBACK_CANDLES + 1
                if len(ohlcv_list) >= req_len_ladder:
                    is_ladder, ladder_details = check_ladder_pattern(ohlcv_list)
                    if is_ladder:
                        log_entry = {'timestamp_utc': detection_time_utc.strftime('%Y-%m-%d %H:%M:%S'), 'symbol': symbol, **ladder_details}
                        ladder_patterns_found.append(log_entry)
            except Exception as e_ladder: print(f"Ошибка детектора Ladder для {symbol}: {e_ladder}"); # traceback.print_exc()

        print(f"Детекция завершена за {time.time() - start_time_detect:.2f} сек.")

    except Exception as e_cycle:
        print(f"Ошибка в цикле сканирования: {e_cycle}")
        traceback.print_exc()
    finally:
        # Гарантированное закрытие соединения
        if 'exchange' in locals() and hasattr(exchange, 'close'):
             try: await exchange.close()
             except Exception: pass # Игнорируем ошибки закрытия здесь
        print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Цикл сканирования завершен.")

    return brush_patterns_found, ladder_patterns_found

# --- Блок if __name__ == "__main__": ---
if __name__ == "__main__":
    print("Запускаем скринер (режим проверки по OHLCV v4: Brush + Ladder)...")
    filtered_symbols_data = asyncio.run(find_and_filter_symbols())
    if filtered_symbols_data:
        symbols_to_watch = [item['symbol'] for item in filtered_symbols_data]
        print(f"\nПолучен список из {len(symbols_to_watch)} символов для периодической проверки.")
        if symbols_to_watch:
            print("\nЗапуск основного цикла периодической проверки...")
            try: asyncio.run(run_one_scan_cycle(symbols_to_watch))
            except KeyboardInterrupt: print("\nЗавершение работы по команде пользователя (Ctrl+C)...")
            except Exception as e: print(f"\nКритическая ошибка в основном потоке __main__: {e}"); traceback.print_exc()
        else: print("\nСписок символов для проверки пуст после фильтрации.")
    else: print("\nНе найдено символов для проверки или произошла ошибка при поиске.")
    print("\nОсновной скрипт завершил работу.")