# detectors/brush_detector.py
import numpy as np
import traceback
from datetime import timedelta

# --- НАСТРОЙКИ ПАТТЕРНА "ЁРШИК" ---
BRUSH_LOOKBACK_CANDLES = 120 # N: Анализируем последние 2 часа (120 мин)
BRUSH_SMA_PERIOD = 20      # P: Период для расчета SMA
BRUSH_MIN_DEVIATION_PERCENT = 0.1 # X: Минимальное откл. от SMA в %
BRUSH_MIN_CROSSINGS = 5      # C: Минимальное кол-во пересечений SMA

# --- НОВЫЕ НАСТРОЙКИ ---
# Макс. время между соседними локальными пиком и впадиной (в минутах)
MAX_ZIGZAG_DURATION_MINUTES = 20
# Макс. стандартное отклонение SMA в % от среднего значения SMA (показатель "плоскости")
SMA_MAX_STD_DEV_PERCENT = 0.15 # Например, не более 0.15% волатильности у SMA
# Максимально допустимый разрыв между таймстемпами соседних свечей (в минутах)
MAX_ALLOWED_GAP_MINUTES = 1.5 # Допускаем пропуск не более ~1 минуты
# ---------------------------

def find_local_extrema(prices: np.ndarray):
    """Находит индексы локальных минимумов и максимумов."""
    # Добавляем NaN по краям для упрощения сравнения на границах
    padded_prices = np.concatenate(([np.nan], prices, [np.nan]))
    # Минимумы: цена[i] < цена[i-1] и цена[i] < цена[i+1]
    low_indices = np.where((padded_prices[1:-1] < padded_prices[:-2]) & (padded_prices[1:-1] < padded_prices[2:]))[0]
    # Максимумы: цена[i] > цена[i-1] и цена[i] > цена[i+1]
    high_indices = np.where((padded_prices[1:-1] > padded_prices[:-2]) & (padded_prices[1:-1] > padded_prices[2:]))[0]
    # Объединяем и сортируем индексы
    extrema_indices = np.sort(np.concatenate((low_indices, high_indices)))
    return extrema_indices

def check_brush_pattern(ohlcv_data: list):
    """
    Проверяет наличие паттерна 'Ёршик' на основе списка OHLCV свечей
    с учетом новых критериев.
    Возвращает: (bool, dict) - (найден ли паттерн, детали паттерна или пустой dict)
    """
    # 1. Проверка достаточного количества данных
    if len(ohlcv_data) < BRUSH_LOOKBACK_CANDLES:
        return False, {}

    # Берем только последние N свечей
    relevant_ohlcv = ohlcv_data[-BRUSH_LOOKBACK_CANDLES:]

    # 2. Извлечение данных и проверка на валидность
    try:
        timestamps_ms = [int(candle[0]) for candle in relevant_ohlcv] # Таймстемп (мс)
        close_prices = np.array([float(candle[4]) for candle in relevant_ohlcv]) # Цены закрытия
        # Проверка, что данные корректно извлеклись
        if len(timestamps_ms) != BRUSH_LOOKBACK_CANDLES or len(close_prices) != BRUSH_LOOKBACK_CANDLES:
             # print("Debug: Не удалось извлечь полные данные")
             return False, {}
    except (ValueError, TypeError, IndexError) as e:
        print(f"Ошибка извлечения данных из OHLCV: {e}")
        return False, {}

    # 3. ПРОВЕРКА НА ПРОПУСКИ В ДАННЫХ (НОВЫЙ КРИТЕРИЙ)
    max_allowed_gap_ms = MAX_ALLOWED_GAP_MINUTES * 60 * 1000
    for i in range(1, len(timestamps_ms)):
        time_diff_ms = timestamps_ms[i] - timestamps_ms[i-1]
        if time_diff_ms > max_allowed_gap_ms:
            # print(f"Debug: Обнаружен пропуск данных > {MAX_ALLOWED_GAP_MINUTES} мин ({time_diff_ms / 60000:.1f} мин)")
            return False, {} # Есть недопустимый пропуск

    # 4. Расчет SMA и базовых метрик (как раньше)
    try:
        if len(close_prices) < BRUSH_SMA_PERIOD: return False, {}
        sma = np.convolve(close_prices, np.ones(BRUSH_SMA_PERIOD)/BRUSH_SMA_PERIOD, mode='valid')
        prices_for_comparison = close_prices[BRUSH_SMA_PERIOD-1:]
        if len(prices_for_comparison) != len(sma): return False, {} # Ошибка длины

        # Пересечения
        crossings = 0
        if len(prices_for_comparison) > 0 and len(sma) > 0:
            price_above_sma = prices_for_comparison[0] > sma[0]
            for i in range(1, len(prices_for_comparison)):
                current_price_above_sma = prices_for_comparison[i] > sma[i]
                if current_price_above_sma != price_above_sma:
                    crossings += 1
                    price_above_sma = current_price_above_sma

        # Отклонения
        safe_sma = np.where(sma <= 0, 1e-10, sma) # Проверка на <= 0
        deviations_percent = (prices_for_comparison - sma) / safe_sma * 100
        if deviations_percent.size == 0: return False, {} # Нет данных для отклонений
        max_dev_up = np.max(deviations_percent)
        max_dev_down = np.min(deviations_percent)

    except Exception as e:
        print(f"Ошибка в расчетах SMA/отклонений: {e}")
        traceback.print_exc()
        return False, {}

    # 5. ПРОВЕРКА "ПЛОСКОСТИ" SMA (НОВЫЙ КРИТЕРИЙ)
    if len(sma) > 1: # Нужно хотя бы 2 точки для std dev
        mean_sma = np.mean(sma)
        std_dev_sma = np.std(sma)
        if mean_sma > 1e-10: # Избегаем деления на ноль
            sma_volatility_percent = (std_dev_sma / mean_sma) * 100
            if sma_volatility_percent > SMA_MAX_STD_DEV_PERCENT:
                # print(f"Debug: SMA слишком волатильна ({sma_volatility_percent:.2f}% > {SMA_MAX_STD_DEV_PERCENT}%)")
                return False, {} # SMA не "плоская"
        else:
             # Если средняя SMA очень мала, считаем ее плоской
             pass
    else:
         # Если точек SMA мало, считаем ее плоской
         pass


    # 6. ПРОВЕРКА ВРЕМЕНИ ЗИГЗАГА (НОВЫЙ КРИТЕРИЙ)
    extrema_indices = find_local_extrema(close_prices)
    if len(extrema_indices) >= 2: # Нужно хотя бы два экстремума для проверки
        max_duration_found = 0
        for i in range(len(extrema_indices) - 1):
            duration = extrema_indices[i+1] - extrema_indices[i]
            if duration > max_duration_found:
                 max_duration_found = duration
            if duration > MAX_ZIGZAG_DURATION_MINUTES:
                # print(f"Debug: Слишком длинный зигзаг ({duration} мин > {MAX_ZIGZAG_DURATION_MINUTES} мин)")
                return False, {} # Найдено слишком большое расстояние между экстремумами
        # print(f"Debug: Макс. длительность зигзага: {max_duration_found} мин")
    else:
        # print("Debug: Недостаточно экстремумов для проверки зигзага")
        return False, {} # Недостаточно экстремумов для формирования зигзага

    # 7. Финальная проверка всех условий
    is_brush = (
        crossings >= BRUSH_MIN_CROSSINGS and
        max_dev_up >= BRUSH_MIN_DEVIATION_PERCENT and
        abs(max_dev_down) >= BRUSH_MIN_DEVIATION_PERCENT
        # Новые условия уже проверены выше (если дошли сюда, они выполнены)
    )

    if is_brush:
        details = {
            "crossings": crossings,
            "max_dev_up_pct": round(max_dev_up, 4),
            "max_dev_down_pct": round(max_dev_down, 4),
            "sma_period": BRUSH_SMA_PERIOD,
            "lookback_candles": BRUSH_LOOKBACK_CANDLES,
            # Доп. инфо (опционально)
            # "sma_volatility_pct": round(sma_volatility_percent, 4) if 'sma_volatility_percent' in locals() else 'N/A',
            # "max_zigzag_duration": max_duration_found if 'max_duration_found' in locals() else 'N/A'
        }
        return True, details
    else:
        return False, {}