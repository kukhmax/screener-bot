# chart_generator.py
import asyncio
import ccxt.async_support as ccxt_async
import ccxt # Для ошибок
import pandas as pd
import mplfinance as mpf # Библиотека для графиков
from datetime import datetime, timedelta, timezone
import traceback
import tempfile # Для временного файла
import os

# --- НАСТРОЙКИ ГРАФИКА ---
CHART_TIMEFRAME = '1m'      # Таймфрейм свечей для графика
CHART_CANDLES_LIMIT = 120   # Сколько последних свечей показать (2 часа)
CHART_STYLE = 'yahoo'       # Стили mplfinance: 'yahoo', 'charles', 'binance', 'nightclouds', ...
CHART_MA_PERIODS = (10, 20) # Периоды для скользящих средних на графике (можно убрать или изменить)
CHART_VOLUME = True         # Показывать ли объем на графике
CHART_DPI = 150             # Качество (разрешение) генерируемого изображения
# ---------------------------

async def generate_mexc_chart_image(symbol: str) -> str | None:
    """
    Получает OHLCV данные с MEXC и генерирует изображение графика.
    Возвращает путь к временному PNG файлу или None в случае ошибки.
    """
    print(f"Запрос данных для генерации графика {symbol} [{CHART_TIMEFRAME}]...")
    exchange = ccxt_async.mexc({'options': {'defaultType': 'spot'}})
    filepath = None

    try:
        # Запрашиваем OHLCV данные
        # Не используем fetch_ohlcv_safe, т.к. нужна обработка ошибок специфичная для генерации
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=CHART_TIMEFRAME, limit=CHART_CANDLES_LIMIT)

        if not ohlcv or len(ohlcv) < 5: # Нужно хотя бы несколько свечей
            print(f"Недостаточно OHLCV данных для {symbol} для генерации графика.")
            return None

        # Преобразуем в Pandas DataFrame, как требует mplfinance
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        # Конвертируем timestamp в DatetimeIndex (важно для mplfinance)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
        df = df.set_index('timestamp')

        # Преобразуем столбцы в числовые типы (на всякий случай)
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])

        print(f"Данные для {symbol} подготовлены, генерация графика...")

        # Создаем временный файл для сохранения графика
        # delete=False, чтобы файл не удалился сразу после закрытия
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_png:
            filepath = temp_png.name

            # Генерируем и сохраняем график
            mpf.plot(
                df,
                type='candle',             # Тип графика - свечной
                style=CHART_STYLE,         # Стиль оформления
                title=f'\n{symbol} - {CHART_TIMEFRAME}', # Заголовок графика
                ylabel='Price',            # Подпись оси Y
                volume=CHART_VOLUME,       # Отображать объем
                mav=CHART_MA_PERIODS,      # Скользящие средние
                tight_layout=True,         # Плотная компоновка
                figratio=(16,9),           # Соотношение сторон
                scale_padding={'left': 0.5, 'right': 0.9, 'top': 1.0, 'bottom': 0.5}, # Отступы
                savefig=dict(fname=filepath, dpi=CHART_DPI) # Параметры сохранения
            )
        print(f"График для {symbol} сохранен в: {filepath}")
        return filepath

    except ccxt.BadSymbol as e:
        print(f"Ошибка генерации графика: Неверный символ {symbol}. {e}")
    except ccxt.NetworkError as e:
        print(f"Сетевая ошибка при получении данных для графика {symbol}: {e}")
    except ccxt.ExchangeError as e:
        print(f"Ошибка биржи при получении данных для графика {symbol}: {e}")
    except Exception as e:
        print(f"Неизвестная ошибка при генерации графика для {symbol}: {e}")
        traceback.print_exc()
    finally:
        # Важно закрыть соединение
        if 'exchange' in locals() and hasattr(exchange, 'close'):
            await exchange.close()

    # Если дошли сюда - произошла ошибка, удаляем временный файл, если он создался
    if filepath and os.path.exists(filepath):
        try: os.remove(filepath)
        except OSError: pass
    return None

# Пример использования
if __name__ == '__main__':
    async def run_test():
        test_symbol = "BTC/USDT"
        print(f"Тестовый запуск генерации графика для: {test_symbol}")
        img_path = await generate_mexc_chart_image(test_symbol)
        if img_path:
            print(f"График сохранен: {img_path}")
            # В реальном приложении здесь была бы отправка файла и его удаление
            # os.remove(img_path) # Удаляем после теста
        else:
            print("Не удалось сгенерировать график.")
    asyncio.run(run_test())