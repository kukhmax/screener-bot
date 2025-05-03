# detectors/brush_detector.py
import numpy as np
import traceback # Для отладки ошибок

# --- НАСТРОЙКИ ПАТТЕРНА "ЁРШИК" (для OHLCV данных) ---
# Сколько ПОСЛЕДНИХ СВЕЧЕЙ (минут) анализируем
BRUSH_LOOKBACK_CANDLES = 120 # N: Анализируем последние 2 часа (120 мин)
BRUSH_SMA_PERIOD = 20      # P: Период для расчета SMA (в свечах/минутах)
BRUSH_MIN_DEVIATION_PERCENT = 0.1 # X: Минимальное откл. от SMA в % (0.1% = 0.001)
BRUSH_MIN_CROSSINGS = 5      # C: Минимальное кол-во пересечений SMA
# ---------------------------------------------------------

def check_brush_pattern(close_prices: list):
    """
    Проверяет наличие паттерна 'Ёршик' на основе списка цен закрытия свечей.
    Возвращает: (bool, dict) - (найден ли паттерн, детали паттерна или пустой dict)
    """
    # Проверка на минимальное количество данных перед любыми расчетами
    if len(close_prices) < BRUSH_LOOKBACK_CANDLES:
        # print(f"Debug: Недостаточно свечей ({len(close_prices)}/{BRUSH_LOOKBACK_CANDLES})")
        return False, {}

    # Берем только последние N свечей для анализа
    # Убедимся, что все элементы - числа
    try:
        prices_to_analyze = [float(p) for p in close_prices[-BRUSH_LOOKBACK_CANDLES:]]
    except (ValueError, TypeError) as e:
        print(f"Ошибка преобразования цен в float в check_brush_pattern: {e}")
        return False, {}

    prices = np.array(prices_to_analyze)

    # Дополнительная проверка на случай, если после преобразования данных все равно не хватает
    if len(prices) < BRUSH_LOOKBACK_CANDLES:
         return False, {}

    try:
        # Считаем SMA
        if len(prices) < BRUSH_SMA_PERIOD:
            # print(f"Debug: Недостаточно цен ({len(prices)}) для SMA периода {BRUSH_SMA_PERIOD}")
            return False, {}
        sma = np.convolve(prices, np.ones(BRUSH_SMA_PERIOD)/BRUSH_SMA_PERIOD, mode='valid')

        # Сравниваем цены с SMA
        prices_for_comparison = prices[BRUSH_SMA_PERIOD-1:]

        if len(prices_for_comparison) != len(sma):
             print(f"Критическая ошибка: несоответствие длин OHLCV цен ({len(prices_for_comparison)}) и SMA ({len(sma)})")
             return False, {}

        # Считаем пересечения
        crossings = 0
        if len(prices_for_comparison) > 0 and len(sma) > 0: # Проверка на пустые массивы
            price_above_sma = prices_for_comparison[0] > sma[0]
            for i in range(1, len(prices_for_comparison)):
                current_price_above_sma = prices_for_comparison[i] > sma[i]
                if current_price_above_sma != price_above_sma:
                    crossings += 1
                    price_above_sma = current_price_above_sma
        else:
             crossings = 0

        # Считаем отклонения в %
        safe_sma = np.where(sma == 0, 1e-10, sma) # Избегаем деления на ноль
        deviations_percent = (prices_for_comparison - sma) / safe_sma * 100

        if deviations_percent.size == 0:
             max_dev_up = 0
             max_dev_down = 0
        else:
             max_dev_up = np.max(deviations_percent)
             max_dev_down = np.min(deviations_percent)

        # Проверяем условия паттерна
        is_brush = (
            crossings >= BRUSH_MIN_CROSSINGS and
            max_dev_up >= BRUSH_MIN_DEVIATION_PERCENT and
            abs(max_dev_down) >= BRUSH_MIN_DEVIATION_PERCENT
        )

        if is_brush:
            details = {
                "crossings": crossings,
                "max_dev_up_pct": round(max_dev_up, 4),
                "max_dev_down_pct": round(max_dev_down, 4),
                "sma_period": BRUSH_SMA_PERIOD,
                "lookback_candles": BRUSH_LOOKBACK_CANDLES
            }
            return True, details
        else:
            return False, {}

    except Exception as e:
        print(f"Ошибка в расчетах check_brush_pattern: {e}")
        traceback.print_exc()
        return False, {}