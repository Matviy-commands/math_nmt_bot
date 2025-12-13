import random
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

# --- Imports from other handlers ---
from handlers.progress import show_progress, show_rating
from handlers.daily import handle_daily_task
from handlers.badges import show_badges, BADGES_LIST
from handlers.materials import MATERIALS
from handlers.scoring import calc_points
from handlers.utils import (
    build_main_menu,
    build_category_keyboard,
    build_back_to_menu_keyboard,
    build_topics_keyboard,
    CATEGORIES,
    LEVELS,
)

# --- Database Imports ---
from db import (
    get_all_topics,
    get_all_tasks_by_topic,
    get_user_field,
    get_random_task,
    update_user,
    all_tasks_completed,
    mark_task_completed,
    add_score,
    add_feedback,
    get_available_levels_for_topic,
    get_all_topics_by_category,
    get_completed_task_ids,
    update_streak_and_reward,
    get_user_completed_count,
    get_topic_streak, set_topic_streak, inc_topic_streak, reset_topic_streak,
    has_topic_streak_award, mark_topic_streak_award,
    get_task_by_id
)

logger = logging.getLogger(__name__)

# --- Stickers ---
CORRECT_ANSWER_STICKERS = ['CAACAgIAAxkBAAE8-mho_hXgh17wWlhWeous-iyLoT5aHgACQFEAAmzrEUnELY0xrlcN9jYE']
INCORRECT_ANSWER_STICKERS = ['CAACAgIAAxkBAAE8-qpo_h2pUHpZ_6n71bovF1-47kenYQAC9V8AAupQEUkloO6Sc3Q4bTYE']

HELP_TEXT = """
🆘 <b>Допомога та зв'язок</b>
<b>FAQ:</b>
— <b>Що це за бот?</b>
Це навчальний бот для практики задач НМТ з математики.
— <b>Як користуватись?</b>
Обирай тему, вирішуй задачі, отримуй бали, перевіряй прогрес та проходь щоденні задачі.
"""

# --- Keyboards ---
def build_task_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("↩️ Меню"), KeyboardButton("❓ Не знаю")]],
        resize_keyboard=True
    )

def build_level_keyboard(levels):
    buttons = [[KeyboardButton(lvl)] for lvl in levels]
    return ReplyKeyboardMarkup(buttons + [[KeyboardButton("↩️ Назад до тем")]], resize_keyboard=True)

# --- Helper Functions (Defined FIRST) ---

async def handle_registration_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    state = context.user_data['registration_state']

    if text == "❌ Скасувати":
        context.user_data.pop('registration_state', None)
        await update.message.reply_text("Реєстрацію скасовано.", reply_markup=build_main_menu(user_id))
        return

    if state.get("step") == "name":
        if not (2 <= len(text.strip()) <= 20):
            await update.message.reply_text("Імʼя повинно бути від 2 до 20 символів.")
            return
        update_user(user_id, "display_name", text.strip())
        state["step"] = "city"
        await update.message.reply_text("✅ Чудово! Тепер вкажіть ваше місто:", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Скасувати")]], resize_keyboard=True))

    elif state.get("step") == "city":
        if not (2 <= len(text.strip()) <= 30):
             await update.message.reply_text("Назва міста має бути від 2 до 30 символів.")
             return
        update_user(user_id, "city", text.strip())
        state["step"] = "phone"
        kb = ReplyKeyboardMarkup([[KeyboardButton("📱 Поділитись контактом", request_contact=True)], [KeyboardButton("❌ Скасувати")]], resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("✅ Майже готово! Поділіться контактом або введіть номер:", reply_markup=kb)

    elif state.get("step") == "phone":
        if not (text.strip().startswith('+') and len(text.strip()) >= 10 and text.strip()[1:].isdigit()):
             await update.message.reply_text("Некоректний формат (+380...).")
             return
        update_user(user_id, "phone_number", text.strip())
        context.user_data.pop('registration_state', None)
        await update.message.reply_text("🎉 <b>Дякуємо за реєстрацію!</b>", parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove())
        await show_rating(update, context)

async def handle_change_name_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    if text == "❌ Скасувати":
        context.user_data.pop('change_name_state', None)
        await update.message.reply_text("Скасовано.", reply_markup=build_main_menu(user_id))
        return
    if not (2 <= len(text.strip()) <= 20):
        await update.message.reply_text("Імʼя: 2-20 символів.")
        return
    update_user(user_id, "display_name", text.strip())
    context.user_data.pop('change_name_state', None)
    await update.message.reply_text(f"✅ Імʼя оновлено: <b>{text.strip()}</b>", parse_mode=ParseMode.HTML)
    await show_rating(update, context)

async def handle_feedback_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    if text == "❌ Скасувати":
        context.user_data.pop('feedback_state', None)
        await update.message.reply_text("Скасовано.", reply_markup=build_main_menu(user_id))
        return
    add_feedback(user_id, update.effective_user.username or f"id_{user_id}", text)
    context.user_data.pop('feedback_state', None)
    await update.message.reply_text("✅ Дякуємо! Ваше повідомлення відправлено.", reply_markup=build_main_menu(user_id))

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if context.user_data.get('registration_state') and context.user_data['registration_state'].get("step") == "phone":
        phone = update.message.contact.phone_number
        if not phone.startswith('+'): phone = '+' + phone
        update_user(user_id, "phone_number", phone)
        context.user_data.pop('registration_state', None)
        await update.message.reply_text("🎉 <b>Дякуємо за реєстрацію!</b>", parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove())
        await show_rating(update, context)
    else:
        await update.message.reply_text("Дякую, але зараз контакт не потрібен.", reply_markup=build_main_menu(user_id))

# --- Task Logic ---

async def task_entrypoint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📁 Оберіть категорію (Алгебра чи Геометрія):", reply_markup=build_category_keyboard())
    context.user_data['start_task_state'] = {"step": "category"}

async def handle_task_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # 🔥 ВИПРАВЛЕННЯ: Дозволяємо вийти в меню на будь-якому етапі вибору
    if text == "↩️ Меню":
        context.user_data.pop('start_task_state', None)
        await update.message.reply_text("📍 Головне меню:", reply_markup=build_main_menu(user_id))
        return

    if 'start_task_state' in context.user_data:
        state = context.user_data['start_task_state']
        category = state.get("category")

        if state["step"] == "category" and text in CATEGORIES:
            state["category"] = text
            topics = get_all_topics_by_category(text)
            if not topics:
                await update.message.reply_text(f"📂 У категорії '{text}' поки що немає тем.", reply_markup=build_back_to_menu_keyboard())
                return
            state["step"] = "topic"
            await update.message.reply_text(f"📖 Оберіть тему:", reply_markup=build_topics_keyboard(topics + ["↩️ Назад"]))
            return

        if state["step"] == "topic" and text == "↩️ Назад":
            state["step"] = "category"
            await update.message.reply_text("📁 Оберіть категорію:", reply_markup=build_category_keyboard())
            return

        current_topics = get_all_topics_by_category(category) if category else get_all_topics()
        if state["step"] == "topic" and text in current_topics:
            tasks_in_topic = get_all_tasks_by_topic(text)
            available_levels = {t["level"] for t in tasks_in_topic if t.get("level")}
            state["available_levels"] = sorted(list(available_levels))
            if not available_levels:
                await update.message.reply_text("❌ Немає задач у цій темі.", reply_markup=build_topics_keyboard(current_topics + ["↩️ Назад"]))
                return
            update_user(user_id, "topic", text)
            state["step"] = "level"
            await update.message.reply_text(f"✅ Тема <b>{text}</b>! Оберіть рівень:", reply_markup=build_level_keyboard(state["available_levels"]), parse_mode=ParseMode.HTML)
            return

        if state["step"] == "level" and text == "↩️ Назад до тем":
            state["step"] = "topic"
            topics = get_all_topics_by_category(category) if category else get_all_topics()
            await update.message.reply_text("📖 Оберіть тему:", reply_markup=build_topics_keyboard(topics + ["↩️ Назад"]))
            return

        elif state["step"] == "level" and text in LEVELS:
            topic = get_user_field(user_id, "topic")
            all_tasks = get_all_tasks_by_topic(topic)
            level_tasks = [t for t in all_tasks if t.get("level") == text]
            if not level_tasks:
                await update.message.reply_text("🤷‍♂️ Задач цього рівня немає.", reply_markup=build_level_keyboard(state["available_levels"]))
                return
            
            completed_ids = set(get_completed_task_ids(user_id, topic, text))
            uncompleted = [t for t in level_tasks if t["id"] not in completed_ids]
            to_solve = uncompleted if uncompleted else level_tasks
            is_repeat = not uncompleted
            
            msg = f"🚀 Поїхали! <b>{topic} ({text})</b>. Нових: {len(to_solve)}" if uncompleted else f"👍 Повторне проходження <b>{topic} ({text})</b>."
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

            context.user_data['solving_state'] = {
                "topic": topic, "level": text, "task_ids": [t["id"] for t in to_solve],
                "completed_ids": completed_ids, "current": 0, "total_tasks": len(to_solve), "is_repeat": is_repeat
            }
            context.user_data.pop('start_task_state', None)
            await send_next_task(update, context, user_id)
            return

async def send_next_task(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id):
    if 'solving_state' not in context.user_data: return
    state = context.user_data['solving_state']
    idx = state["current"]

    if idx >= len(state["task_ids"]):
        await update.message.reply_text("Завдання скінчилися.", reply_markup=build_main_menu(user_id))
        context.user_data.pop('solving_state', None)
        return

    try:
        task = get_task_by_id(state["task_ids"][idx])
    except Exception:
        await update.message.reply_text("Помилка БД.", reply_markup=build_main_menu(user_id))
        context.user_data.pop('solving_state', None)
        return

    if not task:
        await update.message.reply_text("Задачу не знайдено, пропускаємо...")
        state["current"] += 1
        await send_next_task(update, context, user_id)
        return

    state["current_task"] = task
    already_done = task["id"] in state.get("completed_ids", set())
    
    header = f"🧠 <b>Тема: {task.get('topic')} ({task.get('level')})</b>"
    info = f"Завдання {idx+1} з {state.get('total_tasks')}"
    streak_info = ""
    
    if not state.get("is_daily") and not already_done:
        s = get_topic_streak(user_id, state.get("topic"))
        if s > 0: streak_info = f"🔥 Стрік: {s}"
    if already_done: streak_info = "🔁 Повтор (без балів)"

    txt = f"{header}\n<i>{info}</i>\n\n📝 <b>Завдання:</b>\n{task.get('question')}\n\n<i>{streak_info}</i>"
    kb = build_task_keyboard()

    try:
        if task.get("photo"):
            await update.message.reply_photo(task["photo"], caption=txt, reply_markup=kb, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(txt, reply_markup=kb, parse_mode=ParseMode.HTML)
    except Exception:
        await update.message.reply_text("Помилка відправки.", reply_markup=build_main_menu(user_id))
        context.user_data.pop('solving_state', None)

async def handle_task_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    if 'solving_state' not in context.user_data: return
    state = context.user_data['solving_state']
    task = state.get("current_task")

    if not task: return

    if text == "↩️ Меню":
        context.user_data.pop('solving_state', None)
        await update.message.reply_text("📍 Головне меню:", reply_markup=build_main_menu(user_id))
        return

    explanation = task.get("explanation", "Пояснення відсутнє.")
    user_ans = [a.strip() for a in text.replace(';', ',').split(',') if a.strip()]
    correct_ans = [str(a).strip() for a in task.get("answer", [])]
    
    is_correct = False
    match_correct = 0
    try:
        if task.get("task_type") == "match":
            match_correct = len(set(user_ans) & set(correct_ans))
            is_correct = (match_correct == len(correct_ans) and len(user_ans) == len(correct_ans))
        else:
            is_correct = (set(user_ans) == set(correct_ans))
    except Exception: pass

    already = task["id"] in state.get("completed_ids", set())
    is_daily = state.get("is_daily", False)
    delta = 0

    if not already:
        delta = calc_points(task, is_correct=is_correct, match_correct=match_correct)
        if delta > 0: add_score(user_id, delta)

    msg = "✅ <b>Правильно!</b>" if is_correct else "❌ <b>Неправильно.</b>"
    if not is_correct: msg += f"\nПравильна: <code>{', '.join(correct_ans)}</code>"
    if delta > 0: msg += f"\n💰 +{delta} балів"
    msg += f"\n\n📖 <b>Пояснення:</b>\n{explanation}"
    
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    
    # Sticker
    sticker = random.choice(CORRECT_ANSWER_STICKERS if is_correct else INCORRECT_ANSWER_STICKERS)
    try: await context.bot.send_sticker(user_id, sticker)
    except: pass

    if mark_task_completed(user_id, task["id"]):
        state.get("completed_ids", set()).add(task["id"])

    # Topic Streaks
    if is_correct and not already and not is_daily:
        topic = state.get("topic")
        s = inc_topic_streak(user_id, topic)
        if s in [5, 10, 15, 20]:
             add_score(user_id, s)
             await update.message.reply_text(f"🏅 Стрік {s} у темі «{topic}»! +{s} балів")
    elif not is_correct and not already and not is_daily:
        reset_topic_streak(user_id, state.get("topic"))

    # Daily Streak
    s, b = update_streak_and_reward(user_id)
    if b > 0: await update.message.reply_text(f"🔥 Щоденний стрік: {s}! +{b} балів.")

    state["current"] += 1
    if state["current"] < state.get("total_tasks"):
        if is_daily:
            context.user_data.pop('solving_state', None)
            await update.message.reply_text("✅ Щоденна задача виконана!", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("↩️ Меню")]], resize_keyboard=True))
        else:
            await send_next_task(update, context, user_id)
    else:
        topic = state.get("topic"); lvl = state.get("level")
        is_rep = state.get("is_repeat")
        context.user_data.pop('solving_state', None)
        
        if is_daily:
            await update.message.reply_text("🎉 Щоденна задача завершена!", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("↩️ Меню")]], resize_keyboard=True))
        else:
            kb = []
            avl = get_available_levels_for_topic(topic, exclude_level=lvl)
            if avl: kb.append([KeyboardButton(l) for l in avl])
            kb.append([KeyboardButton("Змінити тему"), KeyboardButton("↩️ Меню")])
            
            txt = f"👍 Повтор завершено." if is_rep else f"🎉 Рівень «{lvl}» завершено!"
            await update.message.reply_text(txt, reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

async def handle_dont_know(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if 'solving_state' not in context.user_data: return
    state = context.user_data['solving_state']
    task = state.get("current_task")

    if not task: return

    ans = ', '.join([str(a).strip() for a in task.get("answer", [])])
    expl = task.get("explanation", "")
    await update.message.reply_text(f"🤔 Правильна: <code>{ans}</code>\n\n📖 {expl}", parse_mode=ParseMode.HTML)

    if mark_task_completed(user_id, task["id"]):
        state.get("completed_ids", set()).add(task["id"])

    if not state.get("is_daily"):
        reset_topic_streak(user_id, state.get("topic"))

    state["current"] += 1
    if state["current"] < state.get("total_tasks"):
        if state.get("is_daily"):
            context.user_data.pop('solving_state', None)
            await update.message.reply_text("Задача завершена.", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("↩️ Меню")]], resize_keyboard=True))
        else:
            await send_next_task(update, context, user_id)
    else:
        context.user_data.pop('solving_state', None)
        await update.message.reply_text("Всі задачі завершено.", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("↩️ Меню")]], resize_keyboard=True))


# --- Main Handler (Router) ---
async def main_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text or ""

    try:
        update_streak_and_reward(user_id)
        if update.effective_user.username:
            update_user(user_id, "username", update.effective_user.username)
    except: pass

    # State Dispatch
    if 'registration_state' in context.user_data: await handle_registration_step(update, context); return
    if context.user_data.get('change_name_state'): await handle_change_name_step(update, context); return
    if 'feedback_state' in context.user_data: await handle_feedback_step(update, context); return
    if 'start_task_state' in context.user_data: await handle_task_step(update, context); return
    
    if 'solving_state' in context.user_data:
        if text == "❓ Не знаю": await handle_dont_know(update, context)
        elif text == "↩️ Меню": 
             context.user_data.pop('solving_state', None)
             await update.message.reply_text("📍 Головне меню:", reply_markup=build_main_menu(user_id))
        else: await handle_task_answer(update, context)
        return

    # Button Dispatch
    handlers = {
        "🧠 Почати задачу": task_entrypoint,
        "🔁 Щоденна задача": handle_daily_task,
        "📊 Мій прогрес": show_progress,
        "🛒 Бонуси / Бейджі": show_badges,
        "🏆 Рейтинг": show_rating,
        "Змінити тему": task_entrypoint,
        "↩️ Меню": lambda u, c: u.message.reply_text("📍 Головне меню:", reply_markup=build_main_menu(user_id)),
        "↩️ Назад": lambda u, c: show_progress(u, c) if c.user_data.get('user_last_menu') in ("badges", "rating") else u.message.reply_text("📍 Головне меню:", reply_markup=build_main_menu(user_id))
    }

    if text in handlers:
        await handlers[text](update, context)
    elif text == "❓ Допомога / Зв’язок":
        await update.message.reply_text(HELP_TEXT, reply_markup=ReplyKeyboardMarkup([[KeyboardButton("💬 Написати розробнику")], [KeyboardButton("↩️ Назад")]], resize_keyboard=True), parse_mode=ParseMode.HTML)
    elif text == "💬 Написати розробнику":
        context.user_data['feedback_state'] = True
        await update.message.reply_text("✉️ Напишіть ваше звернення:", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Скасувати")]], resize_keyboard=True))
    elif text == "✏️ Змінити імʼя в рейтингу":
        context.user_data['change_name_state'] = True
        await update.message.reply_text("Введіть нове імʼя:", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Скасувати")]], resize_keyboard=True))
    elif text == "📚 Матеріали":
        btns = [[InlineKeyboardButton(m.get("title","Link"), url=m.get("url", "#"))] for m in MATERIALS]
        await update.message.reply_text("Матеріали:", reply_markup=InlineKeyboardMarkup(btns))
    elif text in LEVELS:
         topic = get_user_field(user_id, "topic")
         if topic:
             context.user_data['start_task_state'] = {"step": "level", "topic": topic}
             await handle_task_step(update, context)
         else:
             await update.message.reply_text("Спочатку оберіть тему.", reply_markup=build_main_menu(user_id))
    else:
        active_states = ['registration_state', 'change_name_state', 'feedback_state', 'start_task_state', 'solving_state']
        if not any(state in context.user_data for state in active_states):
            logger.info(f"User {user_id}: Unknown command: '{text}'")
            await update.message.reply_text("Не зрозумів 🤔. Скористайтесь кнопками.", reply_markup=build_main_menu(user_id))