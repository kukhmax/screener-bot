# chart_screenshot.py
import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import os
from datetime import datetime
import traceback

# --- НАСТРОЙКИ ---
MEXC_BASE_URL = "https://www.mexc.com/ru-RU/exchange/"
SCREENSHOT_DIR = "chart_screenshots"
PAGE_LOAD_TIMEOUT = 45000  # Увеличим немного
SELECTOR_TIMEOUT = 20000   # Увеличим немного
MAXIMIZE_BUTTON_SELECTOR = '.chartType_fullScreen___Vqav' # Оставляем этот вариант пока
WAIT_AFTER_MAXIMIZE_MS = 7000 # !!! УВЕЛИЧИМ ПАУЗУ до 7 секунд !!!
SCREENSHOT_TIMEOUT = 60000 # !!! УВЕЛИЧИМ ТАЙМАУТ СКРИНШОТА до 60 секунд !!!
# -----------------

async def take_mexc_chart_screenshot(symbol: str):
    """
    Открывает страницу MEXC, максимизирует график и делает скриншот.
    Возвращает путь к файлу или None в случае ошибки.
    """
    # ... (Код форматирования URL и имени файла) ...
    if not symbol or '/' not in symbol: print(f"Ошибка скриншота: Неверный формат символа '{symbol}'."); return None
    symbol_formatted_url = symbol.replace('/', '_').upper()
    symbol_formatted_file = symbol.replace('/', '-')
    url = f"{MEXC_BASE_URL}{symbol_formatted_url}"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{symbol_formatted_file}_{timestamp}.png"
    try: os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    except OSError as e: print(f"Ошибка создания папки '{SCREENSHOT_DIR}': {e}"); return None
    filepath = os.path.join(SCREENSHOT_DIR, filename)
    print(f"Попытка сделать скриншот для {symbol} по URL: {url} -> {filepath}")

    async with async_playwright() as p:
        browser = None
        try:
            # Попробуйте headless=False для визуальной отладки, если ошибка повторится
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()

            # Увеличиваем стандартный таймаут навигации для страницы
            page.set_default_navigation_timeout(PAGE_LOAD_TIMEOUT)
            page.set_default_timeout(SELECTOR_TIMEOUT) # Таймаут ожидания элементов

            print(f"[{symbol}] Переход на страницу...")
            # Используем 'load' или 'networkidle' для более полного ожидания
            await page.goto(url, wait_until='load') # Ждем полной загрузки ресурсов

            print(f"[{symbol}] Ожидание кнопки максимизации '{MAXIMIZE_BUTTON_SELECTOR}'...")
            maximize_button = page.locator(MAXIMIZE_BUTTON_SELECTOR)
           
            print(f"[{symbol}] Клик для максимизации...")
            await maximize_button.click()

            asyncio.sleep(2) # Небольшая пауза перед ожиданием

            m1_button = page.get_by_text("1м")
            await m1_button.click()
            print(f"[{symbol}] Ожидание кнопки '1m'...")

            asyncio.sleep(2) # Небольшая пауза перед ожиданием

            print(f"[{symbol}] Ожидание {WAIT_AFTER_MAXIMIZE_MS} мс после максимизации...")
            # Исправлено: добавлено await
            await asyncio.sleep(WAIT_AFTER_MAXIMIZE_MS / 1000) # asyncio.sleep ожидает секунды

            print(f"[{symbol}] Создание скриншота (таймаут {SCREENSHOT_TIMEOUT} мс)...")
            # Устанавливаем таймаут непосредственно для скриншота
            await page.screenshot(path=filepath, full_page=False, timeout=SCREENSHOT_TIMEOUT) # Попробуем НЕ full_page
            print(f"[{symbol}] Скриншот успешно сохранен: {filepath}")
            await browser.close()
            return filepath

        except PlaywrightTimeoutError as e:
            print(f"[{symbol}] Ошибка таймаута Playwright: {e}")
            # traceback.print_exc(limit=1) # Можно раскомментировать для краткого трейсбека
            return None
        except Exception as e:
            print(f"[{symbol}] Общая ошибка Playwright: {e}")
            traceback.print_exc()
            return None
        finally:
            if browser and browser.is_connected():
                await browser.close()

# ... (Код if __name__ == "__main__":) ...
if __name__ == "__main__":
    async def run_test():
        test_symbol = "BTC/USDT"
        print(f"Тестовый запуск для символа: {test_symbol}")
        filepath = await take_mexc_chart_screenshot(test_symbol)
        if filepath: print(f"Тестовый скриншот сохранен: {filepath}")
        else: print("Тестовый скриншот не удался.")
    asyncio.run(run_test())