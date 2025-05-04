# bot/handlers.py
from aiogram import Router, F, Bot
from aiogram.types import Message, FSInputFile # Добавляем FSInputFile обратно
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Импорты функций и констант
import sys
import os
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path: sys.path.insert(0, project_root)

try:
    from utils.find_tokens import find_and_filter_symbols, OUTPUT_CSV_FILE as ALL_SYMBOLS_CSV # CSV со всеми отфильтрованными
    from utils.chart_screenshot import take_mexc_chart_screenshot, SCREENSHOT_DIR
    from main import run_one_scan_cycle # Импортируем новую функцию сканера
except ImportError as e: print(f"Ошибка импорта в bot/handlers.py: {e}"); exit(1)

from .keyboards import get_main_keyboard
import csv
from datetime import datetime, timezone
import pathlib
import traceback
import tempfile # Для создания временных CSV файлов

# Создаем Router
router = Router()

# --- Состояние для скриншота ---
class ScreenshotState(StatesGroup): waiting_for_symbol = State()

# --- Вспомогательная функция для генерации CSV ---
def create_temp_csv(data: list, base_filename: str) -> str | None:
    """Создает временный CSV файл и возвращает путь к нему."""
    if not data: return None
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

# --- ИЗМЕНЕН ОБРАБОТЧИК ---
@router.message(F.text == "🔎 Запустить сканирование") # <-- Новая/старая надпись
async def handle_scan_request(message: Message, bot: Bot):
    user_id = message.from_user.id
    print(f"[{user_id}] Получен запрос на ЗАПУСК СКАНИРОВАНИЯ")
    await message.answer("⏳ Начинаю поиск и фильтрацию токенов по цене...")

    try:
        # 1. Находим символы по цене
        filtered_symbols_data = await find_and_filter_symbols()
        if not filtered_symbols_data:
            await message.answer("❌ Не найдено токенов, подходящих по цене для сканирования.")
            return

        symbols_to_scan = [item['symbol'] for item in filtered_symbols_data]
        await message.answer(f"🔎 Найдено {len(symbols_to_scan)} токенов. Запускаю анализ паттернов (1 цикл)...")

        # 2. Запускаем ОДИН цикл анализа паттернов
        brush_results, ladder_results = await run_one_scan_cycle(symbols_to_scan)

        # 3. Формируем отчет
        found_symbols = set()
        if brush_results: found_symbols.update([item['symbol'] for item in brush_results])
        if ladder_results: found_symbols.update([item['symbol'] for item in ladder_results])

        report_files = [] # Список путей к CSV файлам для отправки

        if found_symbols:
            sorted_symbols = sorted(list(found_symbols))
            response_text = f"✅ Сканирование завершено.\nПаттерны ('Ёршик' или 'Лесенка') найдены на следующих токенах:\n\n"
            response_text += "\n".join(f"- {s}" for s in sorted_symbols)

            # Создаем CSV для результатов сканирования
            if brush_results:
                 brush_csv_path = create_temp_csv(brush_results, "brush_scan")
                 if brush_csv_path: report_files.append(("Результаты 'Ёршик'", brush_csv_path))
            if ladder_results:
                 ladder_csv_path = create_temp_csv(ladder_results, "ladder_scan")
                 if ladder_csv_path: report_files.append(("Результаты 'Лесенка'", ladder_csv_path))

        else:
            response_text = "ℹ️ Сканирование завершено. Активных паттернов 'Ёршик' или 'Лесенка' не найдено в этом цикле."

        await message.answer(response_text)

        # Отправляем CSV файлы, если они создались
        for caption, filepath in report_files:
            try:
                 csv_doc = FSInputFile(filepath)
                 await message.answer_document(csv_doc, caption=caption)
                 # Удаляем временный файл после отправки
                 try: os.remove(filepath)
                 except OSError as e_del: print(f"Не удалось удалить временный файл {filepath}: {e_del}")
            except Exception as e_send:
                 print(f"Ошибка отправки файла {filepath}: {e_send}")
                 await message.answer(f"Не удалось отправить файл: {caption}.csv")

    except Exception as e:
        print(f"Ошибка при выполнении сканирования по запросу: {e}")
        await message.answer("❌ Произошла ошибка во время сканирования.")
        traceback.print_exc()

# -----------------------------

# --- Обработчики скриншотов (без изменений) ---
@router.message(F.text == "📸 Получить скриншот")
async def handle_screenshot_request(message: Message, state: FSMContext):
   # ...(код)
   pass # Как в пред. шаге

@router.message(StateFilter(ScreenshotState.waiting_for_symbol))
async def handle_symbol_for_screenshot(message: Message, state: FSMContext, bot: Bot):
   # ...(код)
   pass # Как в пред. шаге


# --- Обработчик неизвестного текста (без изменений) ---
@router.message(F.text)
async def handle_unknown_text(message: Message):
   # ...(код)
    pass # Как в пред. шаге