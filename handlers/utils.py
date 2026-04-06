import unicodedata
from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup

BTN_START_TASK = "🧠 Почати задачу"
BTN_MATERIALS = "📚 Матеріали"
BTN_PROGRESS = "📊 Мій прогрес"
BTN_DAILY = "🔁 Щоденна задача"
BTN_HELP = "❓ Допомога / Зв’язок"
BTN_ADMIN = "🔐 Адмінка"
BTN_MENU = "↩️ Меню"
BTN_BACK = "↩️ Назад"
BTN_BACK_TO_TOPICS = "↩️ Назад до тем"
BTN_DONT_KNOW = "❓ Не знаю"
BTN_CHANGE_TOPIC = "Змінити тему"
BTN_BADGES = "🛒 Бонуси / Бейджі"
BTN_RATING = "🏆 Рейтинг"
BTN_CONTACT_DEV = "💬 Написати розробнику"
BTN_CANCEL = "❌ Скасувати"
BTN_CHANGE_RATING_NAME = "✏️ Змінити імʼя в рейтингу"

MAIN_MENU_BUTTONS = {
    BTN_START_TASK,
    BTN_MATERIALS,
    BTN_PROGRESS,
    BTN_DAILY,
    BTN_HELP,
    BTN_ADMIN,
}


def canonical_button_text(text: str) -> str:
    raw = unicodedata.normalize("NFKC", text or "").casefold().strip()
    simple = "".join(ch if ch.isalnum() or ch.isspace() or ch in "/’'" else " " for ch in raw)
    simple = " ".join(simple.replace("`", " ").split())

    if "почати задачу" in simple:
        return BTN_START_TASK
    if "матеріали" in simple:
        return BTN_MATERIALS
    if "мій прогрес" in simple:
        return BTN_PROGRESS
    if "щоденна задача" in simple:
        return BTN_DAILY
    if "допомога" in simple and "зв" in simple:
        return BTN_HELP
    if "адмінка" in simple:
        return BTN_ADMIN
    if "назад до тем" in simple:
        return BTN_BACK_TO_TOPICS
    if simple == "назад":
        return BTN_BACK
    if simple == "меню":
        return BTN_MENU
    if "не знаю" in simple:
        return BTN_DONT_KNOW
    if "змінити тему" in simple:
        return BTN_CHANGE_TOPIC
    if "бонуси" in simple or "бейдж" in simple:
        return BTN_BADGES
    if simple == "рейтинг" or simple.endswith(" рейтинг"):
        return BTN_RATING
    if "написати розробнику" in simple:
        return BTN_CONTACT_DEV
    if "скасувати" in simple:
        return BTN_CANCEL
    if "змінити" in simple and "ім" in simple and "рейтинг" in simple:
        return BTN_CHANGE_RATING_NAME
    return text or ""

admin_ids = [1070282751, 981761965, 622895283, 536875267, 799115167, 816846097, 542897073, 1008277167, 5215159721]
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
    """Creates a grid of KeyboardButton objects."""
    buttons = [KeyboardButton(t) for t in button_texts]
    rows = [buttons[i:i+cols] for i in range(0, len(buttons), cols)]
    if extra_rows:
        rows.extend([[KeyboardButton(t) for t in row] for row in extra_rows])
    return rows

def _reply(rows, placeholder=None, one_time=False):
    """Creates a ReplyKeyboardMarkup from rows of buttons."""
    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
        one_time_keyboard=one_time,
        input_field_placeholder=placeholder
    )

# --------- public builders

def build_type_keyboard():
    """Builds keyboard for selecting task type."""
    rows = _grid(list(TYPE_BUTTONS.keys()), cols=2, extra_rows=[[BTN_CANCEL]])
    return _reply(rows, placeholder="Оберіть тип задачі…")

def build_main_menu(user_id):
    """Builds the main menu keyboard, showing admin button if applicable."""
    row_big = [KeyboardButton(BTN_START_TASK)]
    grid_rows = _grid(
        [BTN_MATERIALS, BTN_PROGRESS, BTN_DAILY, BTN_HELP],
        cols=2
    )
    rows = [row_big] + grid_rows
    if user_id in admin_ids:
        rows += _grid([BTN_ADMIN], cols=1)
    return _reply(rows, placeholder="Виберіть дію з меню…")

def build_admin_menu():
    """Builds the admin menu keyboard."""
    rows = _grid(
        ["➕ Додати задачу", "➕ Додати щоденну задачу",
         "📋 Переглянути задачі", "📋 Переглянути щоденні задачі",
         "💬 Звернення користувачів", "📥 Експорт користувачів (CSV)"],
        cols=2,
        extra_rows=[["↩️ Назад"]]
    )
    return _reply(rows, placeholder="Адмін-дії…")

def build_cancel_keyboard():
    """Builds a simple cancel keyboard."""
    return _reply([[KeyboardButton(BTN_CANCEL)]], one_time=True)

def skip_cancel_keyboard():
    """Builds a keyboard with Skip and Cancel options."""
    rows = _grid(["Пропустити", BTN_CANCEL], cols=2)
    return _reply(rows, one_time=True)

def build_tasks_pagination_keyboard(page, *_):
    """Builds reply keyboard for task pagination actions (edit/delete)."""
    rows = _grid(["✏️ Редагувати задачу", "🗑 Видалити задачу"], cols=2, extra_rows=[["↩️ Назад"]])
    return _reply(rows)

def build_topics_keyboard(topics):
    """Builds keyboard for selecting a topic."""
    # Ensure "Назад" is always the last button if present
    has_back = topics and topics[-1] == BTN_BACK
    if has_back:
        topics_core = topics[:-1]
    else:
        topics_core = topics
    
    # Sort topics alphabetically, keeping "Назад" at the end if it was there
    topics_core.sort()
    
    rows = _grid(topics_core, cols=2)
    if has_back:
        rows.append([KeyboardButton(BTN_BACK)])
        
    return _reply(rows, placeholder="Оберіть тему…")

def build_category_keyboard():
    """Builds keyboard for selecting a category."""
    rows = _grid(CATEGORIES, cols=2, extra_rows=[[BTN_BACK]])
    return _reply(rows, placeholder="Оберіть категорію…")

def build_back_to_menu_keyboard():
    """Builds a simple keyboard with a 'Menu' button."""
    return _reply([[KeyboardButton(BTN_MENU)]])

# ---------- inline paginations ----------

def build_tasks_pagination_inline_keyboard(page, has_prev, has_next, total_pages=None):
    """Builds inline keyboard for task pagination (prev/next)."""
    indicator = f"• {page + 1}" + (f"/{total_pages} •" if total_pages else " •")
    row = []
    if has_prev:
        row.append(InlineKeyboardButton("⬅️", callback_data=f"prev_{page}"))
    # Add a non-clickable indicator
    row.append(InlineKeyboardButton(indicator, callback_data="noop")) # "noop" = no operation
    if has_next:
        row.append(InlineKeyboardButton("➡️", callback_data=f"next_{page}"))
    # Add a "Back to Admin Menu" button maybe?
    # row.append(InlineKeyboardButton("↩️ Адмінка", callback_data="admin_menu"))
    return InlineKeyboardMarkup([row])

def build_feedback_pagination_inline_keyboard(page, has_prev, has_next, total_pages=None):
    """Builds inline keyboard for feedback pagination."""
    indicator = f"• {page + 1}" + (f"/{total_pages} •" if total_pages else " •")
    row = []
    if has_prev:
        row.append(InlineKeyboardButton("⬅️", callback_data=f"feedback_prev_{page}"))
    row.append(InlineKeyboardButton(indicator, callback_data="noop"))
    if has_next:
        row.append(InlineKeyboardButton("➡️", callback_data=f"feedback_next_{page}"))
    return InlineKeyboardMarkup([row])

# ---------- NEW HELPER FUNCTION ----------
def create_progress_bar(current: int, total: int, length: int = 8) -> str:
    """
    Генерує текстовий прогрес-бар.
    Наприклад: [████░░░░]  40%
    """
    # Ensure valid inputs
    current = max(0, current)
    total = max(1, total) # Avoid division by zero
    length = max(1, length)

    percent = int((current / total) * 100)
    # Ensure percent doesn't exceed 100 if current > total somehow
    percent = min(100, percent)
    
    filled_length = int(length * current // total)
    # Ensure filled_length doesn't exceed bar length
    filled_length = min(length, filled_length)

    filled_char = '█'
    empty_char = '░'
    
    bar = filled_char * filled_length + empty_char * (length - filled_length)
    
    # Format percentage string to always take 4 characters (e.g., "  5%", " 50%", "100%")
    percent_str = f"{percent}%".rjust(4)

    return f"[{bar}] {percent_str}"
# ----------------------------------------
