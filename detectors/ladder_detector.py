# detectors/ladder_detector.py
import numpy as np
import traceback
# from sklearn.linear_model import LinearRegression # Можно добавить для тренда

# --- НАСТРОЙКИ ПАТТЕРНА "ЛЕСЕНКА" (v3 - последовательный рост OHLCV) ---
# Сколько ПОСЛЕДНИХ СВЕЧЕЙ анализируем для поиска пика
LADDER_LOOKBACK_CANDLES = 60
# Минимальное КОЛИЧЕСТВО СВЕЧЕЙ в фазе роста (от долины до пика)
LADDER_MIN_RISE_DURATION = 15 # Минимум 15 свечей роста
# Минимальный ОБЩИЙ % роста от долины до пика
LADDER_MIN_RISE_PERCENT = 3.0
# Макс. допустимая доля "медвежьих" или "откатных" свечей в фазе роста
LADDER_MAX_BEARISH_CANDLE_RATIO = 0.30 # Не более 30% свечей могут быть красными
LADDER_MAX_PULLBACK_CANDLE_RATIO = 0.35 # Не более 35% свечей могут закрыться ниже предыдущей
# ---- Настройки для падения (как в v2) ----
LADDER_DROP_MATCH_RATIO_MIN = 0.60
LADDER_DROP_MATCH_RATIO_MAX = 1.50
DROP_PRICE_TYPE = 'low' # 'low' или 'close'
# -----------------------------------------

def check_ladder_pattern(ohlcv_data: list):
    """
    Проверяет наличие паттерна 'Лесенка' (v3 - последовательный рост OHLCV).
    Возвращает: (bool, dict)
    """
    # Требуется lookback + 1 свеча (для падения)
    required_length = LADDER_LOOKBACK_CANDLES + 1
    if len(ohlcv_data) < required_length:
        return False, {}

    analysis_ohlcv = ohlcv_data[-required_length:]

    try:
        # Извлекаем данные
        timestamps = np.array([int(candle[0]) for candle in analysis_ohlcv])
        open_prices = np.array([float(candle[1]) for candle in analysis_ohlcv])
        high_prices = np.array([float(candle[2]) for candle in analysis_ohlcv])
        low_prices = np.array([float(candle[3]) for candle in analysis_ohlcv])
        close_prices = np.array([float(candle[4]) for candle in analysis_ohlcv])

        if not (len(timestamps) == len(open_prices) == len(high_prices) == len(low_prices) == len(close_prices) == required_length):
            # print("Debug Ladder v3: Ошибка извлечения данных нужной длины.")
            return False, {}

    except (ValueError, TypeError, IndexError) as e:
        print(f"Ошибка извлечения данных из OHLCV: {e}")
        return False, {}

    try:
        # --- Поиск пика (в lookback-периоде) ---
        lookback_highs = high_prices[:LADDER_LOOKBACK_CANDLES]
        if len(lookback_highs) == 0: return False, {} # Проверка на пустой массив
        peak_index_in_lookback = np.argmax(lookback_highs)
        peak_price = lookback_highs[peak_index_in_lookback]

        # --- Поиск долины (перед пиком) ---
        prices_before_peak_low = low_prices[:peak_index_in_lookback + 1]
        if len(prices_before_peak_low) < LADDER_MIN_RISE_DURATION: # Долина должна быть достаточно далеко
            return False, {}
        valley_index = np.argmin(prices_before_peak_low)
        valley_price = prices_before_peak_low[valley_index]

        # Рассчитываем длительность и общий рост
        rise_duration = peak_index_in_lookback - valley_index
        if valley_price <= 1e-10: return False, {}
        total_rise_percent = ((peak_price - valley_price) / valley_price) * 100

        # Проверка 1: Достаточный ли рост по длительности и проценту?
        if rise_duration < LADDER_MIN_RISE_DURATION or total_rise_percent < LADDER_MIN_RISE_PERCENT:
            return False, {}

        # --- Проверка характера роста ---
        rise_phase_indices = range(valley_index + 1, peak_index_in_lookback + 1)
        if not rise_phase_indices: return False, {} # Нет свечей в фазе роста

        bearish_candle_count = 0
        pullback_candle_count = 0
        rise_candles_count = len(rise_phase_indices)

        for i in rise_phase_indices:
            if close_prices[i] < open_prices[i]: bearish_candle_count += 1
            # Используем i-1, поэтому проверяем i > valley_index
            if i > valley_index and close_prices[i] < close_prices[i-1]:
                 pullback_candle_count += 1 # Считаем только откаты внутри фазы

        # Предотвращаем деление на ноль, если rise_candles_count = 0 (хотя выше проверка)
        bearish_ratio = bearish_candle_count / rise_candles_count if rise_candles_count > 0 else 0
        pullback_ratio = pullback_candle_count / rise_candles_count if rise_candles_count > 0 else 0


        # Проверка 2: Не слишком ли много откатных/медвежьих свечей?
        if bearish_ratio > LADDER_MAX_BEARISH_CANDLE_RATIO or pullback_ratio > LADDER_MAX_PULLBACK_CANDLE_RATIO:
            return False, {}

        # --- Фаза падения (по первой свече после пика) ---
        drop_candle_index = peak_index_in_lookback + 1
        # Проверка индекса остается, т.к. анализ идет по analysis_ohlcv
        if drop_candle_index >= len(analysis_ohlcv): return False, {}

        if DROP_PRICE_TYPE == 'low': drop_price = low_prices[drop_candle_index]
        else: drop_price = close_prices[drop_candle_index]

        if peak_price <= 1e-10: return False, {}
        drop_percent = ((peak_price - drop_price) / peak_price) * 100

        # --- Финальная проверка ---
        if total_rise_percent <= 1e-10: return False, {}
        drop_to_rise_ratio = drop_percent / total_rise_percent

        is_ladder_v3 = (
            drop_percent > 0 and
            LADDER_DROP_MATCH_RATIO_MIN <= drop_to_rise_ratio <= LADDER_DROP_MATCH_RATIO_MAX
        )

        if is_ladder_v3:
            details = {
                "rise_pct": round(total_rise_percent, 2),
                "rise_duration_candles": rise_duration,
                "drop_pct_1st_candle": round(drop_percent, 2),
                "ratio": round(drop_to_rise_ratio, 2),
                "peak_price": peak_price,
                "valley_price": valley_price,
                f"drop_price_{DROP_PRICE_TYPE}": drop_price,
                "bearish_candle_ratio": round(bearish_ratio, 2),
                "pullback_candle_ratio": round(pullback_ratio, 2),
                "lookback_candles": LADDER_LOOKBACK_CANDLES
            }
            return True, details
        else:
            return False, {}

    except Exception as e:
        print(f"Ошибка в check_ladder_pattern v3: {e}")
        traceback.print_exc()
        return False, {}