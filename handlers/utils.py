from telegram import ReplyKeyboardMarkup, KeyboardButton

admin_ids = [1070282751, 981761965]
TOPICS = ["Квадратні рівняння", "Відсотки"]
LEVELS = ["легкий", "середній", "важкий"]

def build_main_menu(user_id):
    keyboard = [
        [KeyboardButton("🧠 Почати задачу")],
        [KeyboardButton("📊 Мій прогрес")],
        [KeyboardButton("🔁 Щоденна задача")],
        [KeyboardButton("❓ Допомога / Зв’язок")]
    ]
    if user_id in admin_ids:
        keyboard.append([KeyboardButton("🔐 Адмінка")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def build_admin_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("➕ Додати задачу")],
        [KeyboardButton("📋 Переглянути задачі")],
        [KeyboardButton("💬 Звернення користувачів")],
        [KeyboardButton("↩️ Назад")]
    ], resize_keyboard=True)


def build_cancel_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("❌ Скасувати")]], resize_keyboard=True)

from telegram import ReplyKeyboardMarkup, KeyboardButton

def build_tasks_pagination_keyboard(page, *_):
    return ReplyKeyboardMarkup([
        [KeyboardButton("✏️ Редагувати задачу"), KeyboardButton("🗑 Видалити задачу")],
        [KeyboardButton("↩️ Назад")]
    ], resize_keyboard=True)

def build_topics_keyboard(topics):
    return ReplyKeyboardMarkup(
        [[KeyboardButton(topic)] for topic in topics],
        resize_keyboard=True
    )

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def build_tasks_pagination_inline_keyboard(page, has_prev, has_next):
    buttons = []
    # Тільки одна кнопка на сторінці
    if has_prev and not has_next:
        buttons.append([InlineKeyboardButton("⬅️ Попередня", callback_data=f"prev_{page}")])
    elif has_next and not has_prev:
        buttons.append([InlineKeyboardButton("Наступна ➡️", callback_data=f"next_{page}")])
    elif has_prev and has_next:
        # Якщо треба показати обидві (найбільш юзер-френдлі варіант)
        buttons.append([
            InlineKeyboardButton("⬅️ Попередня", callback_data=f"prev_{page}"),
            InlineKeyboardButton("Наступна ➡️", callback_data=f"next_{page}")
        ])
    # Кнопку "↩️ Назад" (до тем) можна додати окремо, якщо треба.
    return InlineKeyboardMarkup(buttons)

def build_feedback_pagination_inline_keyboard(page, has_prev, has_next):
    buttons = []

    # Навігаційні кнопки окремо, як у задачах
    if has_prev and not has_next:
        buttons.append([InlineKeyboardButton("⬅️ Попередня", callback_data=f"feedback_prev_{page}")])
    elif has_next and not has_prev:
        buttons.append([InlineKeyboardButton("Наступна ➡️", callback_data=f"feedback_next_{page}")])
    elif has_prev and has_next:
        buttons.append([
            InlineKeyboardButton("⬅️ Попередня", callback_data=f"feedback_prev_{page}"),
            InlineKeyboardButton("Наступна ➡️", callback_data=f"feedback_next_{page}")
        ])
    return InlineKeyboardMarkup(buttons)

def skip_cancel_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("Пропустити")], [KeyboardButton("❌ Скасувати")]],
        resize_keyboard=True
    )