import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, FSInputFile # Добавляем FSInputFile обратно
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Импорты функций и констант
import sys, os, csv, datetime, pathlib, traceback, tempfile
from datetime import timezone, timedelta # Уточним импорт timedelta

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path: sys.path.insert(0, project_root)

try:
    from utils.find_tokens import find_and_filter_symbols, OUTPUT_CSV_FILE as ALL_SYMBOLS_CSV # CSV со всеми отфильтрованными
    from utils.chart_generator import generate_mexc_chart_image, CHART_TIMEFRAME as GENERATED_CHART_TIMEFRAME # Берем ТФ из генератора
    from main import run_one_scan_cycle # Импортируем новую функцию сканера
except ImportError as e:
    print(f"Ошибка импорта в bot/handlers.py: {e}"); exit(1)

from .keyboards import get_main_keyboard

# Создаем Router
router = Router()

# --- Состояние для скриншота ---
class ScreenshotState(StatesGroup):
    waiting_for_symbol = State()

# --- Вспомогательная функция для генерации CSV ---
def create_temp_csv(data: list, base_filename: str) -> str | None:
    """Создает временный CSV файл и возвращает путь к нему."""
    if not data:
        return None
    try:
        # Создаем временный файл
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix=".csv", delete=False, encoding='utf-8', newline='')
        filename = temp_file.name
        print(f"Создание временного CSV: {filename}")

        fieldnames = list(data[0].keys())
        writer = csv.DictWriter(temp_file, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(data)
        temp_file.close() # Закрываем файл, чтобы он сохранился
        return filename
    except Exception as e:
        print(f"Ошибка создания временного CSV {base_filename}: {e}")
        if 'temp_file' in locals() and not temp_file.closed: temp_file.close()
        return None
# ----------------------------------------------------

# --- Обработчики ---

@router.message(CommandStart())
async def handle_start(message: Message):
    await message.answer("Привет! Я бот-скринер MEXC...", reply_markup=get_main_keyboard())

# --- ОБРАБОТЧИК "Запустить сканирование" ---
@router.message(F.text == "🔎 Запустить сканирование")
async def handle_scan_request(message: Message, bot: Bot):
    user_id = message.from_user.id
    print(f"[{user_id}] Получен запрос на ЗАПУСК СКАНИРОВАНИЯ")
    processing_message = await message.answer("⏳ Начинаю поиск и фильтрацию токенов...")

    try:
        # 1. Находим символы по цене
        filtered_symbols_data = await find_and_filter_symbols()
        if not filtered_symbols_data:
            await bot.edit_message_text("❌ Не найдено токенов, подходящих по цене.", chat_id=message.chat.id, message_id=processing_message.message_id)
            return

        symbols_to_scan = [item['symbol'] for item in filtered_symbols_data]
        await bot.edit_message_text(f"🔎 Найдено {len(symbols_to_scan)} ток. Запускаю анализ паттернов...", chat_id=message.chat.id, message_id=processing_message.message_id)

        # 2. Запускаем ОДИН цикл анализа паттернов
        brush_results, ladder_results = await run_one_scan_cycle(symbols_to_scan)

        # 3. Собираем уникальные символы с найденными паттернами
        found_symbols_details = {} # Словарь: {'SYMBOL': 'Тип Паттерна'}
        if brush_results:
            for item in brush_results: found_symbols_details[item['symbol']] = "Ёршик"
        if ladder_results:
            for item in ladder_results: found_symbols_details[item['symbol']] = "Лесенка" # Лесенка перезапишет Ёршик, если найдены оба

        # 4. Формируем отчет и генерируем/отправляем графики
        if found_symbols_details:
            sorted_symbols = sorted(list(found_symbols_details.keys()))
            await bot.edit_message_text(f"✅ Сканирование завершено. Найдено паттернов: {len(sorted_symbols)}. Генерирую графики...", chat_id=message.chat.id, message_id=processing_message.message_id)

            sent_count = 0
            for symbol in sorted_symbols:
                pattern_type = found_symbols_details[symbol]
                print(f"[{user_id}] Генерация графика для {symbol} ({pattern_type})...")
                filepath = await generate_mexc_chart_image(symbol) # Используем символ с '/'
                if filepath and os.path.exists(filepath):
                    try:
                        chart_image = FSInputFile(filepath)
                        await message.answer_photo(chart_image, caption=f"{symbol} - Найден паттерн: {pattern_type} (ТФ: {GENERATED_CHART_TIMEFRAME})")
                        sent_count += 1
                    except Exception as e_send:
                        print(f"Ошибка отправки графика {filepath}: {e_send}")
                        await message.answer(f"Не удалось отправить график для {symbol}")
                    finally:
                        # Удаляем временный файл в любом случае (если он был создан)
                        try: os.remove(filepath)
                        except OSError as e_del: print(f"Не удалось удалить файл графика {filepath}: {e_del}")
                else:
                    print(f"Не удалось сгенерировать график для {symbol}")
                    await message.answer(f"Не удалось сгенерировать график для {symbol}")
                await asyncio.sleep(1) # Небольшая пауза между отправками, чтобы не попасть под лимиты

            final_message = f"📊 Отправлено {sent_count} из {len(sorted_symbols)} графиков."
            # Удаляем сообщение "Генерирую графики..."
            try: await bot.delete_message(chat_id=message.chat.id, message_id=processing_message.message_id)
            except: pass
            # Отправляем финальное сообщение
            await message.answer(final_message, reply_markup=get_main_keyboard())

        else:
            await bot.edit_message_text("ℹ️ Сканирование завершено. Активных паттернов не найдено.", chat_id=message.chat.id, message_id=processing_message.message_id)
            # Возвращаем клавиатуру
            await message.answer("Используйте кнопки для новых команд.", reply_markup=get_main_keyboard())


        # --- Сохранение логов в CSV (ОПЦИОНАЛЬНО) ---
        # Можно оставить сохранение логов, но они не будут отправляться пользователю
        # if brush_results:
        #     create_temp_csv(brush_results, BRUSH_PATTERN_LOG_CSV) # Используем старые имена для записи логов
        # if ladder_results:
        #     create_temp_csv(ladder_results, LADDER_PATTERN_LOG_CSV)
        # --------------------------------------------

    except Exception as e:
        print(f"Ошибка при выполнении сканирования по запросу: {e}")
        try: # Пытаемся отредактировать сообщение об ошибке
             await bot.edit_message_text("❌ Произошла ошибка во время сканирования.", chat_id=message.chat.id, message_id=processing_message.message_id)
        except: # Если не удалось отредактировать, просто отправляем новое
            await message.answer("❌ Произошла ошибка во время сканирования.")
        traceback.print_exc()


# -----------------------------

# --- Обработчики скриншотов (без изменений) ---
@router.message(F.text == "📈 Получить график")
async def handle_screenshot_request(message: Message, state: FSMContext):
    await message.answer("Введите символ торговой пары для генерации графика (например, BTC/USDT):")
    await state.set_state(ScreenshotState.waiting_for_symbol)

@router.message(StateFilter(ScreenshotState.waiting_for_symbol))
async def handle_symbol_for_screenshot(message: Message, state: FSMContext, bot: Bot):
    symbol = message.text.strip().upper()
    user_id = message.from_user.id
    print(f"Получен символ '{symbol}' для генерации ГРАФИКА от пользователя {user_id}")

    if '/' not in symbol or len(symbol.split('/')) != 2:
        await message.answer("Неверный формат. Введите 'BASE/QUOTE':")
        return

    await state.clear()
    # Сообщение о начале генерации
    processing_message = await message.answer(f"⏳ Генерирую график для {symbol}...")

    try:
        # Вызываем новую функцию генерации графика
        filepath = await generate_mexc_chart_image(symbol)

        if filepath and os.path.exists(filepath):
            print(f"Отправка графика {filepath} пользователю {user_id}")
            chart_image = FSInputFile(filepath)
            await message.answer_photo(chart_image, caption=f"График {symbol} ({GENERATED_CHART_TIMEFRAME})")
            # Удаляем временный файл после отправки
            try: os.remove(filepath)
            except OSError as e_del: print(f"Не удалось удалить временный файл графика {filepath}: {e_del}")
        else:
            print(f"Функция generate_mexc_chart_image не вернула путь или файл не найден для {symbol}.")
            await message.answer(f"❌ Не удалось сгенерировать график для {symbol}.")

        # Удаляем сообщение "Генерирую график..."
        await bot.delete_message(chat_id=message.chat.id, message_id=processing_message.message_id)

    except Exception as e:
        print(f"Ошибка при вызове generate_mexc_chart_image для {symbol}: {e}")
        await message.answer(f"❌ Ошибка при генерации графика для {symbol}.")
        if processing_message: # Удаляем сообщение о процессе, если оно еще есть
             try: await bot.delete_message(chat_id=message.chat.id, message_id=processing_message.message_id)
             except: pass # Игнорируем ошибки удаления
        traceback.print_exc()


# --- Обработчик неизвестного текста (без изменений) ---
@router.message(F.text)
async def handle_unknown_text(message: Message):
   await message.answer("Неизвестная команда.", reply_markup=get_main_keyboard())