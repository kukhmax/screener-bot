# symbol_finder.py
import asyncio
# Используем async_support для асинхронной работы с REST API
import ccxt.async_support as ccxt_async
import ccxt # Нужен для типов ошибок
import csv
from datetime import datetime, timezone
import traceback # Для вывода деталей ошибки

# --- НАСТРОЙКИ ФИЛЬТРАЦИИ ---
MAX_PRICE = 1.0
MIN_DECIMALS_AFTER_ZERO = 3 # Минимум 3 нуля после запятой (цена < 0.001)
TARGET_QUOTE_CURRENCY = 'USDT' # Ищем пары к USDT
OUTPUT_CSV_FILE = 'filtered_symbols.csv' # Имя файла для сохранения
# ---------------------------

async def find_and_filter_symbols():
    """
    Получает список спотовых пар с MEXC, фильтрует их по цене
    и сохраняет результат с доп. информацией в CSV.
    Использует ccxt.async_support.
    Возвращает список словарей с информацией об отфильтрованных символах.
    """
    print("Инициализация поиска и фильтрации символов (async)...")
    # Создаем асинхронный экземпляр биржи
    exchange = ccxt_async.mexc({'options': {'defaultType': 'spot'}})
    filtered_data = []
    symbols_to_fetch_ticker = []

    try:
        # 1. Загружаем рынки
        print("Загрузка рынков с MEXC...")
        markets = await exchange.load_markets()
        print(f"Загружено {len(markets)} рынков.")

        # 2. Отбираем активные спотовые пары
        for symbol, market_info in markets.items():
             # Добавим проверку типа market_info
            if isinstance(market_info, dict) and \
               market_info.get('spot', False) and \
               market_info.get('active', False) and \
               market_info.get('quote', '').upper() == TARGET_QUOTE_CURRENCY:
                symbols_to_fetch_ticker.append(symbol)

        print(f"Найдено {len(symbols_to_fetch_ticker)} активных спотовых пар к {TARGET_QUOTE_CURRENCY}.")
        if not symbols_to_fetch_ticker:
            print("Не найдено подходящих пар для запроса тикеров.")
            await exchange.close() # Закрываем соединение перед выходом
            return []

        # 3. Получаем тикеры
        print("Запрос тикеров (текущих цен и статистики)...")
        tickers = {} # Инициализируем пустой словарь для тикеров
        if symbols_to_fetch_ticker:
             # Ограничим количество символов за раз, если их очень много
             all_tickers = {}
             chunk_size = 100 # Размер чанка (можно подстроить)
             for i in range(0, len(symbols_to_fetch_ticker), chunk_size):
                 chunk = symbols_to_fetch_ticker[i:i + chunk_size]
                 print(f"Запрос тикеров для чанка {i // chunk_size + 1}/{ (len(symbols_to_fetch_ticker) + chunk_size - 1) // chunk_size } ({len(chunk)} символов)...")
                 try:
                     tickers_chunk = await exchange.fetch_tickers(chunk)
                     all_tickers.update(tickers_chunk)
                 except ccxt.RequestTimeout as e:
                      print(f"Таймаут при запросе чанка тикеров: {e}. Пропуск чанка.")
                 except ccxt.ExchangeError as e:
                      print(f"Ошибка биржи при запросе чанка тикеров: {e}. Пропуск чанка.")
                 except Exception as e_chunk:
                      print(f"Неизвестная ошибка при запросе чанка тикеров: {e_chunk}")
                 await asyncio.sleep(0.2) # Небольшая пауза между запросами чанков
             tickers = all_tickers
             print(f"Получено {len(tickers)} тикеров.")
        else:
            print("Список символов для запроса тикеров пуст.")


        # 4. Фильтруем по цене и собираем данные
        price_threshold = 1 / (10**MIN_DECIMALS_AFTER_ZERO) # Порог < 0.001

        for symbol, ticker_info in tickers.items():
            # Добавим проверку типа ticker_info
            if not isinstance(ticker_info, dict):
                # print(f"Предупреждение: Некорректный формат тикера для {symbol}: {ticker_info}")
                continue

            last_price = ticker_info.get('last')
            if last_price is not None:
                try:
                    price = float(last_price)
                    # Проверяем условия фильтрации
                    if price > 0 and price < MAX_PRICE and price < price_threshold: # Добавили price > 0
                        symbol_data = {
                            'symbol': symbol,
                            'price': price,
                            'high_24h': ticker_info.get('high'),
                            'low_24h': ticker_info.get('low'),
                            'volume_24h_quote': ticker_info.get('quoteVolume'),
                            'timestamp_utc': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S') # Время UTC
                        }
                        filtered_data.append(symbol_data)
                except (ValueError, TypeError):
                    # print(f"Предупреждение: Не удалось обработать цену для {symbol}: {ticker_info}")
                    continue # Пропускаем, если цена некорректна

        print(f"Найдено {len(filtered_data)} символов, соответствующих ценовым критериям.")

        # 5. Сохраняем в CSV
        if filtered_data:
            print(f"Сохранение данных в файл: {OUTPUT_CSV_FILE}")
            try:
                # Сортируем по символу для консистентности файла
                filtered_data.sort(key=lambda x: x['symbol'])
                with open(OUTPUT_CSV_FILE, 'w', newline='', encoding='utf-8') as csvfile:
                    fieldnames = filtered_data[0].keys()
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(filtered_data)
                print("Данные успешно сохранены в CSV.")
            except IOError as e:
                print(f"Ошибка при записи в CSV файл: {e}")
            except Exception as e:
                print(f"Непредвиденная ошибка при сохранении CSV: {e}")
                traceback.print_exc()

    except ccxt.ExchangeError as e: # Ловим ошибки из async_support
        print(f"Ошибка биржи ccxt (async): {e}")
        traceback.print_exc()
    except Exception as e:
        print(f"Общая ошибка при поиске/фильтрации: {e}")
        traceback.print_exc()
    finally:
        # await exchange.close() теперь должен работать
        print("Попытка закрыть соединение с MEXC (REST)...")
        if 'exchange' in locals() and hasattr(exchange, 'close'):
             try:
                 await exchange.close()
                 print("Соединение с MEXC (REST) закрыто.")
             except Exception as e_close:
                 print(f"Ошибка при закрытии соединения: {e_close}")
        else:
             print("Экземпляр биржи не был создан или уже закрыт.")


    return filtered_data

# Пример использования (если запускать этот файл напрямую)
if __name__ == "__main__":
    print("Запуск symbol_finder напрямую для теста...")
    results = asyncio.run(find_and_filter_symbols())
    if results:
        print("\nПервые 5 отфильтрованных символов:")
        for item in results[:5]:
            print(item)
    else:
        print("Не найдено символов по критериям.")