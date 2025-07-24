from handlers.utils import (
    build_admin_menu,
    build_cancel_keyboard,
    build_main_menu,
    build_tasks_pagination_keyboard,
    build_topics_keyboard,
    build_tasks_pagination_inline_keyboard,
    build_feedback_pagination_inline_keyboard
)
from db import *
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from handlers.state import feedback_state

add_task_state = {}
admin_menu_state = {}
edit_task_state = {}
delete_task_state = {}

LEVELS = ["легкий", "середній", "важкий"]
admin_ids = [1070282751]
TASKS_PER_PAGE = 5
FEEDBACKS_PER_PAGE = 5

async def admin_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if await handle_admin_menu(update, context, user_id, text):
        return
    if await handle_add_task(update, context, user_id, text):
        return
    if await handle_delete_task(update, context, user_id, text):
        return
    if await handle_edit_task(update, context, user_id, text):
        return

async def addtask_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = "➕ Додати задачу"
    await handle_admin_menu(update, context, user_id, text)

async def handle_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, text):
    if user_id in feedback_state and feedback_state[user_id].get("step") == "pagination":
        if text == "↩️ Назад":
            feedback_state.pop(user_id, None)
            await update.message.reply_text(
                "Ви повернулись в адмін-меню.",
                reply_markup=build_admin_menu()
            )
            return True
    # --- Перегляд звернень користувачів ---
    if text == "💬 Звернення користувачів" and user_id in admin_menu_state:
        feedbacks = get_all_feedback()
        if not feedbacks:
            await update.message.reply_text("Немає звернень.", reply_markup=build_admin_menu())
            return True
        feedback_state[user_id] = {"page": 0, "step": "pagination"}
        msg, total = show_feedback_page_msg(feedbacks, 0)
        has_prev = False
        has_next = FEEDBACKS_PER_PAGE < total
        await update.message.reply_text(
            msg,
            reply_markup=build_feedback_pagination_inline_keyboard(0, has_prev, has_next)
        )
        return True


    # Перехід в адмінку
    if text == "➕ Додати задачу" and user_id in admin_menu_state:
        add_task_state[user_id] = {"step": "topic"}
        await update.message.reply_text(
            "📝 Введи тему задачі:",
            reply_markup=build_cancel_keyboard()
        )
        return True

    if text == "🗑 Видалити задачу" and user_id in admin_menu_state:
        delete_task_state[user_id] = {"step": "ask_id"}
        await update.message.reply_text(
            "Введи ID задачі для видалення:",
            reply_markup=build_cancel_keyboard()
        )
        return True

    if text == "✏️ Редагувати задачу" and user_id in admin_menu_state:
        edit_task_state[user_id] = {"step": "ask_id"}
        await update.message.reply_text(
            "Введи ID задачі для редагування:",
            reply_markup=build_cancel_keyboard()
        )
        return True

    if text == "🔐 Адмінка" and user_id in admin_ids:
        admin_menu_state[user_id] = True
        await update.message.reply_text(
            "Вітаю в адмін-меню! Оберіть дію:",
            reply_markup=build_admin_menu()
        )
        return True

    if text == "↩️ Назад" and user_id in admin_menu_state:
        if admin_menu_state[user_id] == True:
            # Користувач у корені адмін-меню — повертаємо в головне меню
            admin_menu_state.pop(user_id, None)
            await update.message.reply_text(
                "Ви повернулись у головне меню.",
                reply_markup=build_main_menu(user_id)
            )
            return True
        else:
            # Якщо в підменю — повертаємо в адмін-меню
            admin_menu_state[user_id] = True
            await update.message.reply_text(
                "Ви повернулись в адмін-меню.",
                reply_markup=build_admin_menu()
            )
            return True

    # --- Крок 1: Перехід на вибір теми для перегляду задач ---
    if text == "📋 Переглянути задачі" and user_id in admin_menu_state:
        admin_menu_state[user_id] = {"step": "choose_topic"}
        topics = get_all_topics()
        if not topics:
            await update.message.reply_text("У базі ще немає жодної теми.", reply_markup=build_admin_menu())
            return True
        await update.message.reply_text(
            "Оберіть тему для перегляду задач:",
            reply_markup=build_topics_keyboard(topics + ["↩️ Назад"])
        )
        return True

    # --- Крок 2: Обрано тему — стартуємо пагінацію ---
    if user_id in admin_menu_state and isinstance(admin_menu_state[user_id], dict):
        state = admin_menu_state[user_id]
        topics = get_all_topics()
        if state.get("step") == "choose_topic" and text in topics:
            state["topic"] = text
            state["page"] = 0
            state["step"] = "pagination"
            print(f"[DEBUG] Вибрана тема: {text}, state: {state}")
            await show_tasks_page(update, user_id, state["topic"], 0)
            return True



        # Повернення на вибір дії адмінки
        if state.get("step") == "choose_topic" and text == "↩️ Назад":
            admin_menu_state[user_id] = True
            await update.message.reply_text(
                "Виберіть дію:",
                reply_markup=build_admin_menu()
            )
            return True

        # --- Листання вперед/назад вже по обраній темі ---
        if state.get("step") == "pagination":
            topic = state["topic"]
            page = state.get("page", 0)
            if text == "⬅️ Попередня":
                state["page"] = max(0, page - 1)
                await show_tasks_page(update, user_id, topic, state["page"])
                return True
            if text == "Наступна ➡️":
                state["page"] = page + 1
                await show_tasks_page(update, user_id, topic, state["page"])
                return True

    return False

def show_tasks_page_msg(topic, page):
    all_tasks = get_all_tasks_by_topic(topic)
    total = len(all_tasks)
    start = page * TASKS_PER_PAGE
    end = start + TASKS_PER_PAGE
    tasks_on_page = all_tasks[start:end]
    msg = f"Список задач з теми «{topic}» (сторінка {page+1}/{(total-1)//TASKS_PER_PAGE+1}):\n\n"
    for t in tasks_on_page:
        msg += f"ID: {t['id']}\nТема: {t['topic']}\nРівень: {t['level']}\nПитання: {t['question'][:30]}...\n\n"
    return msg, len(all_tasks)

def show_feedback_page_msg(feedbacks, page):
    total = len(feedbacks)
    start = page * FEEDBACKS_PER_PAGE
    end = start + FEEDBACKS_PER_PAGE
    page_feedbacks = feedbacks[start:end]
    msg = f"Список звернень користувачів (сторінка {page+1}/{(total-1)//FEEDBACKS_PER_PAGE+1}):\n\n"
    for fb in page_feedbacks:
        # fb: (id, user_id, username, date, text)
        msg += f"ID: {fb[0]}\nКористувач: @{fb[2]} (id:{fb[1]})\n{fb[4]}\n{fb[3]}\n\n"
    return msg, total

from telegram import ReplyKeyboardRemove

async def show_tasks_page(update, user_id, topic, page):
    msg, total = show_tasks_page_msg(topic, page)
    has_prev = page > 0
    has_next = (page + 1) * TASKS_PER_PAGE < total
    print(f"[DEBUG] show_tasks_page: topic={topic}, page={page}, has_prev={has_prev}, has_next={has_next}, total={total}")
    await update.message.reply_text(
        msg,
        reply_markup=build_tasks_pagination_inline_keyboard(page, has_prev, has_next)
    )
    # Відправ reply-клавіатуру для редагування/видалення
    await update.message.reply_text(
        "Оберіть дію з задачами:",
        reply_markup=build_tasks_pagination_keyboard(page, has_prev, has_next)
    )





async def handle_add_task(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, text):
    if user_id not in add_task_state:
        return False
    state = add_task_state[user_id]
    data = state.get("data", {})
    if text == "❌ Скасувати":
        del add_task_state[user_id]
        if user_id in admin_menu_state:
            await update.message.reply_text("Додавання задачі скасовано.", reply_markup=build_admin_menu())
        else:
            await update.message.reply_text("Додавання задачі скасовано.", reply_markup=build_main_menu(user_id))
        return True
    if state["step"] == "topic":
        data["topic"] = text
        state["step"] = "level"
        state["data"] = data
        await update.message.reply_text("🟡 Введи рівень задачі (легкий/середній/важкий):", reply_markup=build_cancel_keyboard())
        return True
    elif state["step"] == "level":
        if text not in LEVELS:
            await update.message.reply_text("❌ Невірний рівень. Введи: легкий / середній / важкий", reply_markup=build_cancel_keyboard())
            return True
        data["level"] = text
        state["step"] = "question"
        state["data"] = data
        await update.message.reply_text("🟢 Введи текст задачі:", reply_markup=build_cancel_keyboard())
        return True
    elif state["step"] == "question":
        data["question"] = text
        state["step"] = "answer"
        state["data"] = data
        await update.message.reply_text("🔷 Введи правильні відповіді через кому (наприклад: 2, -2):", reply_markup=build_cancel_keyboard())
        return True
    elif state["step"] == "answer":
        data["answer"] = [a.strip() for a in text.split(",")]
        state["step"] = "explanation"
        state["data"] = data
        await update.message.reply_text("📘 Введи пояснення до задачі:", reply_markup=build_cancel_keyboard())
        return True
    elif state["step"] == "explanation":
        data["explanation"] = text
        add_task(data)
        await update.message.reply_text("✅ Задачу додано успішно!", reply_markup=build_admin_menu() if user_id in admin_menu_state else build_main_menu(user_id))
        del add_task_state[user_id]
        return True
    return False

async def handle_delete_task(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, text):
    if user_id not in delete_task_state:
        return False
    if text == "❌ Скасувати":
        del delete_task_state[user_id]
        await update.message.reply_text("Видалення скасовано.", reply_markup=build_admin_menu())
        return True
    state = delete_task_state[user_id]
    if state["step"] == "ask_id":
        try:
            task_id = int(text)
            task = get_task_by_id(task_id)
            if not task:
                await update.message.reply_text("Задача з таким ID не знайдена. Введіть ще раз або ❌ Скасувати.")
                return True
            delete_task(task_id)
            await update.message.reply_text(f"✅ Задача {task_id} видалена.", reply_markup=build_admin_menu())
            del delete_task_state[user_id]
            return True
        except Exception:
            await update.message.reply_text("ID має бути цілим числом. Введіть ще раз або ❌ Скасувати.")
            return True
    return False

async def handle_edit_task(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, text):
    if user_id not in edit_task_state:
        return False
    state = edit_task_state[user_id]
    if text == "❌ Скасувати":
        del edit_task_state[user_id]
        await update.message.reply_text("Редагування скасовано.", reply_markup=build_admin_menu())
        return True
    if state["step"] == "ask_id":
        try:
            task_id = int(text)
            task = get_task_by_id(task_id)
            if not task:
                await update.message.reply_text("Задача з таким ID не знайдена. Введіть ще раз або ❌ Скасувати.")
                return True
            state["task_id"] = task_id
            state["step"] = "edit_question"
            await update.message.reply_text(
                f"Поточне питання: {task['question']}\nВведіть новий текст задачі або залиште порожнім:",
                reply_markup=build_cancel_keyboard()
            )
            return True
        except Exception:
            await update.message.reply_text("ID має бути цілим числом. Введіть ще раз або ❌ Скасувати.")
            return True
    elif state["step"] == "edit_question":
        task_id = state["task_id"]
        task = get_task_by_id(task_id)
        if text.strip():
            update_task_field(task_id, "question", text.strip())
        state["step"] = "edit_level"
        await update.message.reply_text(
            f"Поточний рівень: {task['level']}\nВведіть новий рівень (легкий/середній/важкий) або залиште порожнім:",
            reply_markup=build_cancel_keyboard()
        )
        return True
    elif state["step"] == "edit_level":
        task_id = state["task_id"]
        task = get_task_by_id(task_id)
        level = text.strip()
        if level and level not in LEVELS:
            await update.message.reply_text("❌ Невірний рівень. Можливі: легкий / середній / важкий. Спробуйте ще раз або ❌ Скасувати.")
            return True
        if level:
            update_task_field(task_id, "level", level)
        state["step"] = "edit_answer"
        ans_str = ', '.join(task['answer'])
        await update.message.reply_text(
            f"Поточна відповідь: {ans_str}\nВведіть нову відповідь через кому або залиште порожнім:",
            reply_markup=build_cancel_keyboard()
        )
        return True
    elif state["step"] == "edit_answer":
        task_id = state["task_id"]
        task = get_task_by_id(task_id)
        if text.strip():
            ans_list = [a.strip() for a in text.split(",")]
            update_task_field(task_id, "answer", json.dumps(ans_list))
        state["step"] = "edit_explanation"
        await update.message.reply_text(
            f"Поточне пояснення: {task['explanation']}\nВведіть нове пояснення або залиште порожнім:",
            reply_markup=build_cancel_keyboard()
        )
        return True
    elif state["step"] == "edit_explanation":
        task_id = state["task_id"]
        if text.strip():
            update_task_field(task_id, "explanation", text.strip())
        await update.message.reply_text("✅ Задачу оновлено.", reply_markup=build_admin_menu())
        del edit_task_state[user_id]
        return True
    return False

async def handle_task_pagination_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print('[DEBUG] callback received!')
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in admin_menu_state or not isinstance(admin_menu_state[user_id], dict):
        await query.answer()
        return

    state = admin_menu_state[user_id]
    topic = state["topic"]
    page = state["page"]

    if query.data.startswith("prev_"):
        page = max(0, page - 1)
        state["page"] = page
    elif query.data.startswith("next_"):
        page = page + 1
        state["page"] = page
    elif query.data == "back":
        admin_menu_state[user_id] = True
        await query.edit_message_text("Виберіть дію:", reply_markup=build_admin_menu())
        await query.answer()
        return

    msg, total = show_tasks_page_msg(topic, page)
    has_prev = page > 0
    has_next = (page + 1) * TASKS_PER_PAGE < total

    await query.edit_message_text(
        msg,
        reply_markup=build_tasks_pagination_inline_keyboard(page, has_prev, has_next)
    )
    await query.answer()

async def handle_feedback_pagination_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    print(f"[DEBUG] Feedback callback: {query.data}, user_id: {user_id}")

    if user_id not in feedback_state or feedback_state[user_id].get("step") != "pagination":
        await query.answer()
        print(f"[DEBUG] Feedback callback IGNORED (state: {feedback_state.get(user_id)})")
        return


    feedbacks = get_all_feedback()
    state = feedback_state[user_id]
    page = state["page"]

    if query.data.startswith("feedback_prev_"):
        page = max(0, page - 1)
        state["page"] = page
    elif query.data.startswith("feedback_next_"):
        page = page + 1
        state["page"] = page


    msg, total = show_feedback_page_msg(feedbacks, page)
    has_prev = page > 0
    has_next = (page + 1) * FEEDBACKS_PER_PAGE < total
    await query.edit_message_text(
        msg,
        reply_markup=build_feedback_pagination_inline_keyboard(page, has_prev, has_next)
    )
    await query.answer()
