from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_main_keyboard() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔎 Запустить сканирование")], # <-- Надпись
            [KeyboardButton(text="📈 Получить график")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )
    return kb
# --- Inline клавиатура (кнопки в сообщении - пока не используем, но может пригодиться) ---
# Пример:
# def get_some_inline_keyboard():
#     ikb = InlineKeyboardMarkup(inline_keyboard=[
#         [InlineKeyboardButton(text="Кнопка 1", callback_data="cb_button1")],
#     ])
#     return ikb