import numpy as np
from collections import deque

# --- НАСТРОЙКИ ПАТТЕРНА "ЁРШИК" (перенесены сюда) ---
BRUSH_LOOKBACK_TRADES = 100  # N: Сколько последних сделок анализируем
BRUSH_SMA_PERIOD = 20      # P: Период для расчета SMA
BRUSH_MIN_DEVIATION_PERCENT = 0.05 # X: Минимальное откл. от SMA в % (0.05% = 0.0005)
BRUSH_MIN_CROSSINGS = 4      # C: Минимальное кол-во пересечений SMA
# ---------------------------------------------------------

def check_brush_pattern(price_history: deque):
    """
    Проверяет наличие паттерна 'Ёршик' на основе переданной истории цен.
    Возвращает: (bool, dict) - (найден ли паттерн, детали паттерна или пустой dict)
    """
    # Нужно достаточно данных для анализа
    if len(price_history) < BRUSH_LOOKBACK_TRADES:
        return False, {} # Недостаточно данных

    # Убедимся, что в deque не попали None или некорректные значения
    valid_prices = [p for p in price_history if isinstance(p, (int, float))]
    if len(valid_prices) < BRUSH_LOOKBACK_TRADES:
         # Если после фильтрации данных не хватает, возвращаем False
         # print(f"Недостаточно валидных цен после фильтрации: {len(valid_prices)}") # Отладочный вывод
         return False, {}

    prices = np.array(valid_prices) # Работаем с валидными ценами

    # Считаем SMA
    if len(prices) < BRUSH_SMA_PERIOD:
        # print(f"Недостаточно цен ({len(prices)}) для SMA периода {BRUSH_SMA_PERIOD}") # Отладочный вывод
        return False, {} # Недостаточно данных для SMA
    sma = np.convolve(prices, np.ones(BRUSH_SMA_PERIOD)/BRUSH_SMA_PERIOD, mode='valid')

    # Сравниваем цены с SMA
    prices_for_comparison = prices[BRUSH_SMA_PERIOD-1:]

    if len(prices_for_comparison) != len(sma):
        print(f"Критическая ошибка: несоответствие длин массивов цен ({len(prices_for_comparison)}) и SMA ({len(sma)})")
        # Здесь лучше логировать ошибку, а не просто печатать
        return False, {}

    # Считаем пересечения
    crossings = 0
    # Проверяем, если массив не пустой, чтобы избежать IndexError
    if len(prices_for_comparison) > 0:
        price_above_sma = prices_for_comparison[0] > sma[0]
        for i in range(1, len(prices_for_comparison)):
            current_price_above_sma = prices_for_comparison[i] > sma[i]
            if current_price_above_sma != price_above_sma:
                crossings += 1
                price_above_sma = current_price_above_sma
    else:
         # Если нет данных для сравнения, пересечений 0
         crossings = 0


    # Считаем отклонения в %
    # Добавляем проверку на случай, если sma содержит нули
    safe_sma = np.where(sma == 0, 1e-10, sma) # Заменяем 0 на очень маленькое число
    deviations_percent = (prices_for_comparison - sma) / safe_sma * 100

    # Проверка на случай пустых массивов перед вызовом np.max/np.min
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
            "lookback": BRUSH_LOOKBACK_TRADES
        }
        return True, details
    else:
        return False, {}

# Можно добавить сюда другие функции-детекторы в будущем