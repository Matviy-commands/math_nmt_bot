from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from handlers.progress import show_progress, show_rating
from handlers.daily import handle_daily_task
from handlers.state import feedback_state, user_last_menu, solving_state
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from handlers.badges import show_badges
from db import add_feedback

from db import (
    get_all_topics,
    get_all_tasks_by_topic,
    get_user_field,
    get_random_task,
    update_user,
    all_tasks_completed,
    mark_task_completed,
    add_score,
)
from handlers.utils import build_main_menu

LEVELS = ["легкий", "середній", "важкий"]

HELP_TEXT = """
🆘 <b>Допомога та зв'язок</b>

<b>FAQ:</b>
— <b>Що це за бот?</b>
Це навчальний бот для практики задач НМТ з математики.

— <b>Як користуватись?</b>
Обирай тему, вирішуй задачі, отримуй бали, перевіряй прогрес та проходь щоденні задачі.

— <b>Я не можу знайти потрібну тему / є баг</b>
Пиши розробнику через кнопку нижче!
"""

start_task_state = {}

def build_task_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("❓ Не знаю")]], resize_keyboard=True)

def build_topic_keyboard():
    topics = get_all_topics()  # Теми з бази
    # Якщо нема жодної теми — показати інформативну кнопку
    if not topics:
        return ReplyKeyboardMarkup([[KeyboardButton("❌ Немає тем")]], resize_keyboard=True)
    buttons = [[KeyboardButton(topic)] for topic in topics]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def build_level_keyboard(levels):
    buttons = [[KeyboardButton(lvl)] for lvl in levels]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

async def task_entrypoint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    topics = get_all_topics()
    if not topics:
        await update.message.reply_text("❌ Зараз у базі немає жодної теми із задачами.")
        return
    await update.message.reply_text("Оберіть тему:", reply_markup=build_topic_keyboard())
    start_task_state[user_id] = {"step": "topic"}

async def handle_task_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    topics = get_all_topics()

    if user_id in start_task_state:
        state = start_task_state[user_id]
        # 1. Вибір теми
        if state["step"] == "topic" and text in topics:
            available_levels = set([t["level"] for t in get_all_tasks_by_topic(text)])
            if not available_levels:
                await update.message.reply_text("❌ Для цієї теми немає жодної задачі.")
                del start_task_state[user_id]
                return
            update_user(user_id, "topic", text)
            state["step"] = "level"
            buttons = [[KeyboardButton(lvl)] for lvl in LEVELS if lvl in available_levels]
            await update.message.reply_text(
                f"✅ Тема обрана: {text} ❤️\nТепер обери рівень складності:",
                reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
            )
            return

        # 2. Вибір рівня і запуск циклу задач
        elif state["step"] == "level" and text in LEVELS:
            topic = get_user_field(user_id, "topic")
            # ---- отримуємо задачі цього рівня, які ще не виконані
            all_tasks = get_all_tasks_by_topic(topic)
            completed = set([
                t["id"] for t in all_tasks
                if all_tasks_completed(user_id, topic, text)
            ])
            tasks = [t for t in all_tasks if t["level"] == text and t["id"] not in completed]
            if not tasks:
                await update.message.reply_text(
                    "🎉 Вітаю! Ти пройшов всі задачі цієї теми та рівня!",
                    reply_markup=build_main_menu(user_id)
                )
                del start_task_state[user_id]
                return

            # --- зберігаємо стан проходження рівня
            solving_state[user_id] = {
                "topic": topic,
                "level": text,
                "task_ids": [t["id"] for t in tasks],
                "current": 0,
            }
            await send_next_task(update, context, user_id)
            del start_task_state[user_id]
            return

async def send_next_task(update, context, user_id):
    state = solving_state[user_id]
    idx = state["current"]
    task_id = state["task_ids"][idx]
    from db import get_task_by_id
    task = get_task_by_id(task_id)
    state["current_task"] = task
    # Надіслати задачу (текст + фото)
    kb = ReplyKeyboardMarkup(
        [[KeyboardButton("↩️ Меню"), KeyboardButton("❓ Не знаю")]], resize_keyboard=True)
    task_text = f"📘 {task['topic']} ({task['level']})\n\n{task['question']}"
    if task.get("photo"):
        await update.message.reply_photo(
            task["photo"], caption=task_text, reply_markup=kb
        )
    else:
        await update.message.reply_text(task_text, reply_markup=kb)


async def handle_task_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if user_id in solving_state:
        state = solving_state[user_id]
        task = state.get("current_task")
        if text == "↩️ Меню":
            solving_state.pop(user_id, None)
            await update.message.reply_text(
                "📍 Головне меню:",
                reply_markup=build_main_menu(user_id)
            )
            return
        explanation = task["explanation"].strip() if task["explanation"] else "Пояснення відсутнє!"
        if text.strip() in task["answer"]:
            add_score(user_id, 10)
            msg = "✅ Правильно! +10 балів 🎉"
        else:
            msg = "❌ Неправильно."
        msg += f"\n📖 Пояснення: {explanation}"
        await update.message.reply_text(msg)
        mark_task_completed(user_id, task["id"])
        state["current"] += 1
        # якщо є ще задачі — надсилаємо наступну
        if state["current"] < len(state["task_ids"]):
            await send_next_task(update, context, user_id)
        else:
            # всі задачі рівня виконані!
            await update.message.reply_text(
                f"🎉 Вітаю! Ви завершили всі задачі рівня «{state['level']}».\n"
                "Оберіть інший рівень або змініть тему, або поверніться в меню.",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton(lvl) for lvl in LEVELS if lvl != state['level']],
                      [KeyboardButton("Змінити тему")],
                      [KeyboardButton("↩️ Меню")]],
                    resize_keyboard=True
                )
            )
            solving_state.pop(user_id, None)
        return


async def handle_dont_know(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in solving_state:
        state = solving_state[user_id]
        task = state.get("current_task")
        await update.message.reply_text(
            f"📖 Пояснення: {task['explanation'].strip() if task['explanation'] else 'Пояснення відсутнє!'}"
        )
        mark_task_completed(user_id, task["id"])
        state["current"] += 1
        if state["current"] < len(state["task_ids"]):
            await send_next_task(update, context, user_id)
        else:
            await update.message.reply_text(
                f"🎉 Вітаю! Ви завершили всі задачі рівня «{state['level']}».\n"
                "Оберіть інший рівень або змініть тему, або поверніться в меню.",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton(lvl) for lvl in LEVELS if lvl != state['level']],
                      [KeyboardButton("Змінити тему")],
                      [KeyboardButton("↩️ Меню")]],
                    resize_keyboard=True
                )
            )
            solving_state.pop(user_id, None)
        return



async def main_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    username = update.effective_user.username or ""

    if text in LEVELS and user_id not in start_task_state:
        # Хоче пройти інший рівень — запускаємо збереження стану та handle_task_step
        start_task_state[user_id] = {"step": "level"}
        await handle_task_step(update, context)
        return
    if text == "Змінити тему":
        await task_entrypoint(update, context)
        return
    
    if text == "↩️ Меню":
        solving_state.pop(user_id, None)  # На всякий випадок очищуємо стан
        await update.message.reply_text(
            "📍 Головне меню:",
            reply_markup=build_main_menu(user_id)
        )
        return


    if text == "↩️ Назад":
        last_menu = user_last_menu.get(user_id)
        if last_menu in ("badges", "rating"):
            await show_progress(update, context)
            user_last_menu[user_id] = "progress"  # повертаємось до прогресу
        else:
            await update.message.reply_text(
                "📍 Головне меню:",
                reply_markup=build_main_menu(user_id)
            )
        return

    if text == "📊 Мій прогрес":
        await show_progress(update, context)
        return

    if text == "🛒 Бонуси / Бейджі":
        await show_badges(update, context)
        return
    
    if text == "🏆 Рейтинг":
        await show_rating(update, context)
        return


    if text == "↩️ Назад":
        await update.message.reply_text(
            "📍 Головне меню:",
            reply_markup=build_main_menu(user_id)
        )
        return


    # --- 1. Допомога та FAQ ---
    if text == "❓ Допомога / Зв’язок":
        keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton("💬 Написати розробнику")], [KeyboardButton("↩️ Назад")]],
            resize_keyboard=True
        )
        await update.message.reply_text(
            HELP_TEXT,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        return

    # --- 2. Користувач натиснув "Написати розробнику" ---
    if text == "💬 Написати розробнику":
        feedback_state[user_id] = True
        await update.message.reply_text(
            "✉️ Напишіть ваше звернення чи питання. Ми отримаємо його в адмінці.\n\nЩоб скасувати — натисніть ❌ Скасувати.",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Скасувати")]], resize_keyboard=True)
        )
        return

    # --- 3. Якщо користувач у стані написання звернення ---
    if user_id in feedback_state:
        if text == "❌ Скасувати":
            del feedback_state[user_id]
            await update.message.reply_text(
                "Скасовано. Ви у головному меню.",
                reply_markup=build_main_menu(user_id)
            )
            return
        add_feedback(user_id, username, text)
        del feedback_state[user_id]
        await update.message.reply_text(
            "✅ Ваше повідомлення відправлено адміністратору!",
            reply_markup=build_main_menu(user_id)
        )
        return

    if text == "🧠 Почати задачу":
        await task_entrypoint(update, context)
        return

    if text == "📊 Мій прогрес":
        await show_progress(update, context)
        return

    if user_id in start_task_state:
        await handle_task_step(update, context)
        return

    if text == "❓ Не знаю" and user_id in solving_state:
        await handle_dont_know(update, context)
        return

    if user_id in solving_state:
        await handle_task_answer(update, context)
        return


    if text == "🔁 Щоденна задача":
        await handle_daily_task(update, context)
        return

    if text == "❓ Допомога / Зв’язок":
        # FAQ + кнопка для зв’язку
        keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton("💬 Написати розробнику")], [KeyboardButton("↩️ Назад")]],
            resize_keyboard=True
        )
        await update.message.reply_text(
            HELP_TEXT,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        return

    # Обробка кнопки "Написати розробнику"
    if text == "💬 Написати розробнику":
        await update.message.reply_text(
            "Напишіть розробнику у Telegram: @ostapsalo",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("↩️ Назад")]], resize_keyboard=True
            ),
            disable_web_page_preview=True
        )
        return

    # Повернення до головного меню
    if text == "↩️ Назад":
        await update.message.reply_text(
            "📍 Головне меню:",
            reply_markup=build_main_menu(user_id)
        )
        return
