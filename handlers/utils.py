from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup

admin_ids = [1070282751, 981761965, 622895283, 536875267, 799115167, 816846097, 542897073, 1008277167]
CATEGORIES = ["Алгебра", "Геометрія"]
LEVELS = ["легкий", "середній", "важкий"]

TYPE_BUTTONS = {
    "Тест (1 відповідь)": "single",
    "Відповідності (часткові бали)": "match",
    "Відкрита відповідь": "open",
    "BOSS/«гробик»": "boss",
    "Лайтове (0 балів)": "light",
}

# --------- helpers

def _grid(button_texts, cols=2, extra_rows=None):
    buttons = [KeyboardButton(t) for t in button_texts]
    rows = [buttons[i:i+cols] for i in range(0, len(buttons), cols)]
    if extra_rows:
        rows.extend([[KeyboardButton(t) for t in row] for row in extra_rows])
    return rows

def _reply(rows, placeholder=None, one_time=False):
    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
        one_time_keyboard=one_time,
        input_field_placeholder=placeholder
    )

# --------- public builders

def build_type_keyboard():
    rows = _grid(list(TYPE_BUTTONS.keys()), cols=2, extra_rows=[["❌ Скасувати"]])
    return _reply(rows, placeholder="Оберіть тип задачі…")

def build_main_menu(user_id):
    # 1) велика головна кнопка окремим рядом
    row_big = [KeyboardButton("🧠 Почати задачу")]
    # 2) сітка з рештою
    grid_rows = _grid(
        ["📚 Матеріали", "📊 Мій прогрес", "🔁 Щоденна задача", "❓ Допомога / Зв’язок"],
        cols=2
    )
    rows = [row_big] + grid_rows
    if user_id in admin_ids:
        rows += _grid(["🔐 Адмінка"], cols=1)
    return _reply(rows, placeholder="Виберіть дію з меню…")

def build_admin_menu():
    # згрупували по сенсу і зробили 2-колонки
    rows = _grid(
        ["➕ Додати задачу", "➕ Додати щоденну задачу",
         "📋 Переглянути задачі", "📋 Переглянути щоденні задачі",
         "💬 Звернення користувачів"],
        cols=2,
        extra_rows=[["↩️ Назад"]]
    )
    return _reply(rows, placeholder="Адмін-дії…")

def build_cancel_keyboard():
    return _reply([[KeyboardButton("❌ Скасувати")]], one_time=True)

def skip_cancel_keyboard():
    rows = _grid(["Пропустити", "❌ Скасувати"], cols=2)
    return _reply(rows, one_time=True)

def build_tasks_pagination_keyboard(page, *_):
    rows = _grid(["✏️ Редагувати задачу", "🗑 Видалити задачу"], cols=2, extra_rows=[["↩️ Назад"]])
    return _reply(rows)

def build_topics_keyboard(topics):
    # 2-колонки + (за потреби) кнопка Назад останнім рядом
    has_back = topics and topics[-1] == "↩️ Назад"
    if has_back:
        topics_core = topics[:-1]
    else:
        topics_core = topics
    rows = _grid(topics_core, cols=2)
    if has_back:
        rows.append([KeyboardButton("↩️ Назад")])
    return _reply(rows, placeholder="Оберіть тему…")

def build_category_keyboard():
    rows = _grid(CATEGORIES, cols=2, extra_rows=[["↩️ Назад"]])
    return _reply(rows, placeholder="Оберіть категорію…")

def build_back_to_menu_keyboard():
    return _reply([[KeyboardButton("↩️ Меню")]])

# ---------- inline paginations

def build_tasks_pagination_inline_keyboard(page, has_prev, has_next, total_pages=None):
    """
    Пагінація зі стрілками та індикатором сторінки по центру.
    total_pages можна передати для «1/5».
    """
    indicator = f"• {page + 1}" + (f"/{total_pages} •" if total_pages else " •")
    row = []
    if has_prev:
        row.append(InlineKeyboardButton("⬅️", callback_data=f"prev_{page}"))
    row.append(InlineKeyboardButton(indicator, callback_data="noop"))
    if has_next:
        row.append(InlineKeyboardButton("➡️", callback_data=f"next_{page}"))
    return InlineKeyboardMarkup([row])

def build_feedback_pagination_inline_keyboard(page, has_prev, has_next, total_pages=None):
    indicator = f"• {page + 1}" + (f"/{total_pages} •" if total_pages else " •")
    row = []
    if has_prev:
        row.append(InlineKeyboardButton("⬅️", callback_data=f"feedback_prev_{page}"))
    row.append(InlineKeyboardButton(indicator, callback_data="noop"))
    if has_next:
        row.append(InlineKeyboardButton("➡️", callback_data=f"feedback_next_{page}"))
    return InlineKeyboardMarkup([row])
