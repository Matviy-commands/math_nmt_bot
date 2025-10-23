from telegram import Update, ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
import json
import csv
import io

from handlers.utils import (
    build_admin_menu,
    build_cancel_keyboard,
    build_main_menu,
    build_tasks_pagination_keyboard,
    build_topics_keyboard,
    build_tasks_pagination_inline_keyboard,
    build_feedback_pagination_inline_keyboard,
    skip_cancel_keyboard,
    build_category_keyboard,  
    CATEGORIES,                
    LEVELS,                    
    admin_ids,
    build_type_keyboard,         
    TYPE_BUTTONS,                  
)

from db import (
    get_all_feedback,
    get_all_topics_by_category,
    get_all_topics,
    get_all_tasks_by_topic,
    get_task_by_id,
    delete_task,
    update_task_field,
    add_task,
    get_all_users_for_export,
)

# from handlers.state import feedback_state # <-- ВИДАЛЕНО

TASKS_PER_PAGE = 5
FEEDBACKS_PER_PAGE = 5

async def admin_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # user_id = update.effective_user.id # <-- Більше не потрібен тут
    text = update.message.text

    # <-- user_id не передається у функції, вони тепер беруть стан з context
    if await handle_admin_menu(update, context, text):
        return
    if await handle_add_task(update, context, text):
        return
    if await handle_delete_task(update, context, text):
        return
    if await handle_edit_task(update, context, text):
        return

async def addtask_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # user_id = update.effective_user.id # <-- Більше не потрібен тут
    text = "➕ Додати задачу"
    await handle_admin_menu(update, context, text) # <-- user_id не передається

async def handle_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text):
    user_id = update.effective_user.id # <-- Отримуємо user_id тут, він потрібен для admin_ids

    # <-- Перевірка стану через context.user_data
    if context.user_data.get('feedback_state') and context.user_data['feedback_state'].get("step") == "pagination":
        if text == "↩️ Назад":
            context.user_data.pop('feedback_state', None) # <-- Видалення стану з context
            await update.message.reply_text(
                "Ви повернулись в адмін-меню.",
                reply_markup=build_admin_menu()
            )
            return True
            
    # --- Перегляд звернень користувачів ---
    # <-- Перевірка стану через context.user_data
    if text == "💬 Звернення користувачів" and context.user_data.get('admin_menu_state'):
        await context.bot.send_chat_action(chat_id=user_id, action="typing")
        feedbacks = get_all_feedback()
        if not feedbacks:
            await update.message.reply_text("Немає звернень.", reply_markup=build_admin_menu())
            return True
        context.user_data['feedback_state'] = {"page": 0, "step": "pagination"} # <-- Збереження стану в context
        msg, total = show_feedback_page_msg(feedbacks, 0)
        has_prev = False
        has_next = FEEDBACKS_PER_PAGE < total
        await update.message.reply_text(
            msg,
            reply_markup=build_feedback_pagination_inline_keyboard(0, has_prev, has_next)
        )
        return True
    
    
    # Перехід в адмінку
    
    if text == "➕ Додати задачу" and context.user_data.get('admin_menu_state'):
        context.user_data['add_task_state'] = {"step": "category", "is_daily": 0} # <-- Збереження стану в context
        await update.message.reply_text(
            "Оберіть категорію задачі:",
            reply_markup=build_category_keyboard()
        )
        return True

    # <-- Перевірка стану через context.user_data
    if context.user_data.get('add_task_state') and context.user_data['add_task_state']["step"] == "category" and text in CATEGORIES:
        state = context.user_data['add_task_state'] # <-- Отримання стану з context
        data = state.get("data", {})
        data["category"] = text
        state["step"] = "topic"
        state["data"] = data
        await update.message.reply_text("Введіть тему задачі:", reply_markup=build_cancel_keyboard())
        return True



    
    if text == "➕ Додати щоденну задачу" and context.user_data.get('admin_menu_state'):
        context.user_data['add_task_state'] = {"step": "topic", "is_daily": 1} # <-- Збереження стану в context
        await update.message.reply_text(
            "📝 Введи тему ЩОДЕННОЇ задачі:",
            reply_markup=build_cancel_keyboard()
        )
        return True


    if text == "🗑 Видалити задачу" and context.user_data.get('admin_menu_state'):
        context.user_data['delete_task_state'] = {"step": "ask_id"} # <-- Збереження стану в context
        await update.message.reply_text(
            "Введи ID задачі для видалення:",
            reply_markup=build_cancel_keyboard()
        )
        return True

    if text == "✏️ Редагувати задачу" and context.user_data.get('admin_menu_state'):
        context.user_data['edit_task_state'] = {"step": "ask_id"} # <-- Збереження стану в context
        await update.message.reply_text(
            "Введи ID задачі для редагування:",
            reply_markup=build_cancel_keyboard()
        )
        return True

    if text == "🔐 Адмінка" and user_id in admin_ids:
        context.user_data['admin_menu_state'] = True # <-- Збереження стану в context
        await update.message.reply_text(
            "Вітаю в адмін-меню! Оберіть дію:",
            reply_markup=build_admin_menu()
        )
        return True

    if text == "↩️ Назад" and context.user_data.get('admin_menu_state'):
        if context.user_data['admin_menu_state'] == True:
            # Користувач у корені адмін-меню — повертаємо в головне меню
            context.user_data.pop('admin_menu_state', None) # <-- Видалення стану з context
            await update.message.reply_text(
                "Ви повернулись у головне меню.",
                reply_markup=build_main_menu(user_id) # <-- user_id тут потрібен
            )
            return True
        else:
            # Якщо в підменю — повертаємо в адмін-меню
            context.user_data['admin_menu_state'] = True # <-- Збереження стану в context
            await update.message.reply_text(
                "Ви повернулись в адмін-меню.",
                reply_markup=build_admin_menu()
            )
            return True

    # --- Крок 1: Перехід на вибір теми для перегляду задач ---
    if text == "📋 Переглянути задачі" and context.user_data.get('admin_menu_state'):
        context.user_data['admin_menu_state'] = {"step": "choose_category"} # <-- Збереження стану в context
        await update.message.reply_text(
            "Оберіть категорію для перегляду задач:",
            reply_markup=build_category_keyboard()
        )
        return True

    if context.user_data.get('admin_menu_state') and isinstance(context.user_data['admin_menu_state'], dict):
        state = context.user_data['admin_menu_state'] # <-- Отримання стану з context
        if state.get("step") == "choose_category" and text in CATEGORIES:
            await context.bot.send_chat_action(chat_id=user_id, action="typing")
            state["category"] = text
            topics = get_all_topics_by_category(text)
            if not topics:
                await update.message.reply_text("У цій категорії немає тем.", reply_markup=build_admin_menu())
                context.user_data['admin_menu_state'] = True # <-- Збереження стану в context
                return True
            state["step"] = "choose_topic"
            await update.message.reply_text(
                "Оберіть тему:",
                reply_markup=build_topics_keyboard(topics + ["↩️ Назад"])
            )
            return True
    if text == "📥 Експорт користувачів (CSV)" and context.user_data.get('admin_menu_state'):
        await context.bot.send_chat_action(chat_id=user_id, action="upload_document")
        
        try:
            users_data = get_all_users_for_export()
            
            # Створюємо файл в пам'яті
            f = io.StringIO()
            writer = csv.writer(f)
            
            # Записуємо заголовки
            writer.writerow(["Telegram ID", "Ім'я", "Username", "Бали", "Місто", "Телефон", "Остання активність"])
            
            # Записуємо дані
            for user in users_data:
                writer.writerow(user)
            
            f.seek(0) # Повертаємось на початок файлу
            
            # Конвертуємо StringIO в BytesIO для відправки
            bytes_io = io.BytesIO(f.getvalue().encode('utf-8'))
            
            await context.bot.send_document(
                chat_id=user_id,
                document=bytes_io,
                filename="users_export.csv",
                caption=f"✅ Ось експорт {len(users_data)} користувачів."
            )
            
        except Exception as e:
            await update.message.reply_text(f"❌ Не вдалося створити експорт: {e}")
            
        return True    

    if text == "📋 Переглянути щоденні задачі" and context.user_data.get('admin_menu_state'):
        topics = get_all_topics(is_daily=1)
        if not topics:
            await update.message.reply_text("У базі ще немає жодної теми.", reply_markup=build_admin_menu())
            return True
        context.user_data['admin_menu_state'] = {"step": "choose_topic_daily"} # <-- Збереження стану в context
        await update.message.reply_text(
            "Оберіть тему для перегляду щоденних задач:",
            reply_markup=build_topics_keyboard(topics + ["↩️ Назад"])
        )
        return True


    # --- Крок 2: Обрано тему — стартуємо пагінацію ---
    if context.user_data.get('admin_menu_state') and isinstance(context.user_data['admin_menu_state'], dict):
        state = context.user_data['admin_menu_state'] # <-- Отримання стану з context
        # (Виправлено: is_daily=1 якщо step == "choose_topic_daily", інакше 0)
        is_daily_check = 1 if state.get("step") == "choose_topic_daily" else 0
        topics = get_all_topics(is_daily=is_daily_check)
        
        if state.get("step") in ["choose_topic", "choose_topic_daily"] and text in topics:
            state["topic"] = text
            state["page"] = 0
            state["is_daily"] = 1 if state.get("step") == "choose_topic_daily" else 0
            state["step"] = "pagination"
            print(f"[DEBUG] Вибрана тема: {text}, state: {state}")
            # <-- user_id прибрано з виклику, він там не потрібен
            await show_tasks_page(update, state["topic"], 0, is_daily=state["is_daily"])
            return True




        # Повернення на вибір дії адмінки
        if state.get("step") == "choose_topic" and text == "↩️ Назад":
            context.user_data['admin_menu_state'] = True # <-- Збереження стану в context
            await update.message.reply_text(
                "Виберіть дію:",
                reply_markup=build_admin_menu()
            )
            return True

        # --- Листання вперед/назад вже по обраній темі ---
        if state.get("step") == "pagination":
            topic = state["topic"]
            page = state.get("page", 0)
            is_daily = state.get("is_daily", 0)
            if text == "⬅️ Попередня":
                state["page"] = max(0, page - 1)
                await show_tasks_page(update, topic, state["page"], is_daily=is_daily)
                return True
            if text == "Наступна ➡️":
                state["page"] = page + 1
                await show_tasks_page(update, topic, state["page"], is_daily=is_daily)
                return True
            
            


    return False

def show_tasks_page_msg(topic, page, is_daily=0):
    all_tasks = get_all_tasks_by_topic(topic, is_daily)
    print(f"DEBUG show_tasks_page_msg: all_tasks={all_tasks}")

    total = len(all_tasks)
    start = page * TASKS_PER_PAGE
    end = start + TASKS_PER_PAGE
    tasks_on_page = all_tasks[start:end]
    msg = f"Список задач з теми «{topic}» (сторінка {page+1}/{(total-1)//TASKS_PER_PAGE+1}):\n\n"
    for t in tasks_on_page:
        tt = t.get('task_type') or '—'
        msg += (
            f"ID: {t['id']}\n"
            f"Тема: {t['topic']}\n"
            f"Рівень: {t['level']}\n"
            f"Тип: {tt}\n"
            f"Питання: {t['question'][:30]}...\n\n"
        )
    return msg, len(all_tasks)

def show_feedback_page_msg(feedbacks, page):
    total = len(feedbacks)
    start = page * FEEDBACKS_PER_PAGE
    end = start + FEEDBACKS_PER_PAGE
    page_feedbacks = feedbacks[start:end]
    msg = f"Список звернень користувачів (сторінка {page+1}/{(total-1)//FEEDBACKS_PER_PAGE+1}):\n\n"
    for fb in page_feedbacks:
        # fb: (id, user_id, username, date, text)
        msg += f"ID: {fb[0]}\nКористувач: @{fb[2]} (id:{fb[1]})\n{fb[3]}\n{fb[4]}\n\n"
    return msg, total

from telegram import ReplyKeyboardRemove

# <-- user_id прибрано з аргументів
async def show_tasks_page(update, topic, page, is_daily=0):
    msg, total = show_tasks_page_msg(topic, page, is_daily)
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





async def handle_add_task(update: Update, context: ContextTypes.DEFAULT_TYPE, text):
    user_id = update.effective_user.id # <-- Отримуємо user_id
    
    # <-- Перевірка стану через context.user_data
    if 'add_task_state' not in context.user_data:
        return False
    state = context.user_data['add_task_state'] # <-- Отримання стану з context
    data = state.get("data", {})

    if text == "❌ Скасувати":
        context.user_data.pop('add_task_state', None) # <-- Видалення стану з context
        if context.user_data.get('admin_menu_state'): # <-- Перевірка стану
            await update.message.reply_text("Додавання задачі скасовано.", reply_markup=build_admin_menu())
        else:
            await update.message.reply_text("Додавання задачі скасовано.", reply_markup=build_main_menu(user_id))
        return True

    if state["step"] == "topic":
        data["topic"] = text.strip()
        state["step"] = "level"
        state["data"] = data
        # показуємо кнопки з рівнями, щоб не було помилок набору
        level_kb = [[KeyboardButton(l)] for l in LEVELS] + [[KeyboardButton("❌ Скасувати")]]
        await update.message.reply_text(
            "🟡 Оберіть рівень задачі:",
            reply_markup=ReplyKeyboardMarkup(level_kb, resize_keyboard=True)
        )
        return True

    elif state["step"] == "level":
        lvl = (text or "").strip().lower()
        allowed = {l.lower(): l for l in LEVELS}
        if lvl not in allowed:
            level_kb = [[KeyboardButton(l)] for l in LEVELS] + [[KeyboardButton("❌ Скасувати")]]
            await update.message.reply_text(
                "❌ Невірний рівень. Оберіть один із варіантів:",
                reply_markup=ReplyKeyboardMarkup(level_kb, resize_keyboard=True)
            )
            return True
        data["level"] = allowed[lvl]
        state["step"] = "type"
        state["data"] = data
        await update.message.reply_text("🧩 Оберіть тип задачі:", reply_markup=build_type_keyboard())
        return True


    elif state["step"] == "type":
        btn = (text or "").strip()
        if btn not in TYPE_BUTTONS:
            await update.message.reply_text(
                "❌ Оберіть тип із кнопок нижче:",
                reply_markup=build_type_keyboard()
            )
            return True
        data["task_type"] = TYPE_BUTTONS[btn]
        state["step"] = "question"
        state["data"] = data
        await update.message.reply_text("🟢 Введи текст задачі:", reply_markup=build_cancel_keyboard())
        return True



    elif state["step"] == "question":
        data["question"] = text
        state["step"] = "photo"
        state["data"] = data
        await update.message.reply_text(
            "🔗 Надішліть фото до умови задачі або натисніть 'Пропустити', якщо фото не потрібно.",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("Пропустити")], [KeyboardButton("❌ Скасувати")]], resize_keyboard=True)
        )
        return True

    elif state["step"] == "photo":
        if update.message.photo:
            file_id = update.message.photo[-1].file_id
            data["photo"] = file_id
        elif text == "Пропустити":
            data["photo"] = None
        else:
            await update.message.reply_text(
                "Надішли фото або натисни 'Пропустити'! 😎",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton("Пропустити")], [KeyboardButton("❌ Скасувати")]],
                    resize_keyboard=True
                )
            )
            return True
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
        data["is_daily"] = state.get("is_daily", 0)
        if data["is_daily"] == 1 and "category" not in data:
            data["category"] = "Щоденні"   
        add_task(data)
        await update.message.reply_text("✅ Задачу додано успішно!", reply_markup=build_admin_menu() if context.user_data.get('admin_menu_state') else build_main_menu(user_id))
        await update.message.reply_text("Гуд гьорл! 😎")
        context.user_data.pop('add_task_state', None) # <-- Видалення стану з context
        return True



    return False


async def handle_delete_task(update: Update, context: ContextTypes.DEFAULT_TYPE, text):
    # <-- Перевірка стану через context.user_data
    if 'delete_task_state' not in context.user_data:
        return False
    if text == "❌ Скасувати":
        context.user_data.pop('delete_task_state', None) # <-- Видалення стану з context
        await update.message.reply_text("Видалення скасовано.", reply_markup=build_admin_menu())
        return True
    
    state = context.user_data['delete_task_state'] # <-- Отримання стану з context
    if state["step"] == "ask_id":
        try:
            task_id = int(text)
            task = get_task_by_id(task_id)
            if not task:
                await update.message.reply_text("Задача з таким ID не знайдена. Введіть ще раз або ❌ Скасувати.")
                return True
            state['is_daily'] = task.get('is_daily', 0)
            delete_task(task_id)
            await update.message.reply_text(f"✅ Задача {task_id} видалена.", reply_markup=build_admin_menu())
            context.user_data.pop('delete_task_state', None) # <-- Видалення стану з context
            context.user_data['admin_menu_state'] = True # <-- Збереження стану в context
            return True
        except Exception:
            await update.message.reply_text("ID має бути цілим числом. Введіть ще раз або ❌ Скасувати.")
            return True
    return False

async def handle_edit_task(update: Update, context: ContextTypes.DEFAULT_TYPE, text):
    # <-- Перевірка стану через context.user_data
    if 'edit_task_state' not in context.user_data:
        return False

    state = context.user_data['edit_task_state'] # <-- Отримання стану з context

    # Скасування
    if text == "❌ Скасувати":
        context.user_data.pop('edit_task_state', None) # <-- Видалення стану з context
        await update.message.reply_text("Редагування скасовано.", reply_markup=build_admin_menu())
        return True

    # Крок 1: ID задачі
    if state.get("step") == "ask_id":
        try:
            task_id = int(text)
            task = get_task_by_id(task_id)
            if not task:
                await update.message.reply_text(
                    "Задача з таким ID не знайдена. Введіть ще раз або ❌ Скасувати."
                )
                return True

            state["task_id"] = task_id
            state["is_daily"] = task.get("is_daily", 0)
            if state["is_daily"]:
                # Щоденна: одразу питаємо питання
                state["step"] = "edit_question"
                await update.message.reply_text(
                    f"Поточне питання: {task['question']}\nВведіть новий текст задачі або натисніть 'Пропустити':",
                    reply_markup=skip_cancel_keyboard()
                )
            else:
                # Звичайна: питаємо тему
                state["step"] = "edit_topic"
                await update.message.reply_text(
                    f"Поточна тема: {task['topic']}\nВведіть нову тему або натисніть 'Пропустити':",
                    reply_markup=skip_cancel_keyboard()
                )
            return True

        except ValueError:
            await update.message.reply_text(
                "ID має бути цілим числом. Введіть ще раз або ❌ Скасувати."
            )
            return True

    # Крок 2: (Лише для звичайної) Тема
    if state.get("step") == "edit_topic" and not state.get("is_daily"):
        task_id = state["task_id"]
        if text != "Пропустити" and text != "❌ Скасувати":
            if len(text.strip()) == 0:
                await update.message.reply_text(
                    "Тема не може бути порожньою. Введіть нову тему або натисніть 'Пропустити':",
                    reply_markup=skip_cancel_keyboard()
                )
                return True
            update_task_field(task_id, "topic", text.strip())

        state["step"] = "edit_question"
        task = get_task_by_id(task_id)
        await update.message.reply_text(
            f"Поточне питання: {task['question']}\nВведіть новий текст задачі або натисніть 'Пропустити':",
            reply_markup=skip_cancel_keyboard()
        )
        return True

    # Крок 3: Питання
    if state.get("step") == "edit_question":
        task_id = state["task_id"]
        if text != "Пропустити" and text.strip():
            update_task_field(task_id, "question", text.strip())
        # Для звичайної — наступний крок рівень, для daily — одразу відповідь
        if state.get("is_daily"):
            state["step"] = "edit_answer"
            task = get_task_by_id(task_id)
            ans_str = ', '.join(task['answer'])
            await update.message.reply_text(
                f"Поточна відповідь: {ans_str}\nВведіть нову відповідь через кому або натисніть 'Пропустити':",
                reply_markup=skip_cancel_keyboard()
            )
        else:
            state["step"] = "edit_level"
            task = get_task_by_id(task_id)
            await update.message.reply_text(
                f"Поточний рівень: {task['level']}\nВведіть новий рівень (легкий/середній/важкий) або натисніть 'Пропустити':",
                reply_markup=skip_cancel_keyboard()
            )
        return True

    # Крок 4: (Лише для звичайної) Рівень
    if state.get("step") == "edit_level" and not state.get("is_daily"):
        task_id = state["task_id"]
        level = text.strip()
        norm = (level or "").strip().lower()
        allowed = {l.lower(): l for l in LEVELS}
        if level and norm != "пропустити" and norm not in allowed:
            await update.message.reply_text("❌ Невірний рівень. Можливі: легкий / середній / важкий / Пропустити.")
            return True
        if level and norm != "пропустити":
            update_task_field(task_id, "level", allowed[norm])

        # ---> тепер питаємо тип
        state["step"] = "edit_type"
        task = get_task_by_id(task_id)
        current_type = task.get("task_type") or "—"
        await update.message.reply_text(
            f"Поточний тип: {current_type}\n"
            f"Оберіть новий тип або натисніть 'Пропустити':",
            reply_markup=build_type_keyboard()
        )
        return True

    
    if state.get("step") == "edit_type":
        task_id = state["task_id"]
        if text != "Пропустити":
            btn = (text or "").strip()
            if btn not in TYPE_BUTTONS:
                await update.message.reply_text(
                    "❌ Оберіть тип із кнопок, або натисніть 'Пропустити'.",
                    reply_markup=build_type_keyboard()
                )
                return True
            update_task_field(task_id, "task_type", TYPE_BUTTONS[btn])
        state["step"] = "edit_answer"
        task = get_task_by_id(task_id)
        ans_str = ', '.join(task['answer'])
        await update.message.reply_text(
            f"Поточна відповідь: {ans_str}\nВведіть нову відповідь через кому або натисніть 'Пропустити':",
            reply_markup=skip_cancel_keyboard()
        )
        return True


    # Крок 5: Відповідь
    if state.get("step") == "edit_answer":
        task_id = state["task_id"]
        if text != "Пропустити" and text.strip():
            ans_list = [a.strip() for a in text.split(",")]
            update_task_field(task_id, "answer", json.dumps(ans_list))
        state["step"] = "edit_explanation"
        task = get_task_by_id(task_id)
        await update.message.reply_text(
            f"Поточне пояснення: {task['explanation']}\nВведіть нове пояснення або натисніть 'Пропустити':",
            reply_markup=skip_cancel_keyboard()
        )
        return True

    # Крок 6: Пояснення
    if state.get("step") == "edit_explanation":
        task_id = state["task_id"]
        if text != "Пропустити" and text.strip():
            update_task_field(task_id, "explanation", text.strip())
        # Додаємо крок редагування фото
        state["step"] = "edit_photo"
        await update.message.reply_text(
            "Надішліть нове фото до задачі, якщо потрібно змінити. Або натисніть 'Пропустити', щоб залишити старе.",
            reply_markup=skip_cancel_keyboard()
        )
        return True

    # Крок 7: Фото
    if state.get("step") == "edit_photo":
        if text == "Пропустити":
            await update.message.reply_text("✅ Задачу оновлено.", reply_markup=build_admin_menu())
            context.user_data.pop('edit_task_state', None) # <-- Видалення стану з context
            context.user_data['admin_menu_state'] = True # <-- Збереження стану в context
            return True
        # Фото обробляється окремо в handle_edit_task_photo
        if update.message.photo:
            return False
        else:
            await update.message.reply_text(
                "Надішліть саме фото, або натисніть 'Пропустити'.",
                reply_markup=skip_cancel_keyboard()
            )
            return True

    return False

async def handle_task_pagination_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print('[DEBUG] callback received!')
    query = update.callback_query
    # user_id = query.from_user.id # <-- Не потрібен для перевірки стану

    # <-- Перевірка стану через context.user_data
    if not context.user_data.get('admin_menu_state') or not isinstance(context.user_data['admin_menu_state'], dict):
        await query.answer()
        return

    state = context.user_data['admin_menu_state'] # <-- Отримання стану з context
    topic = state["topic"]
    page = state["page"]
    is_daily = state.get("is_daily", 0)


    if query.data.startswith("prev_"):
        page = max(0, page - 1)
        state["page"] = page
    elif query.data.startswith("next_"):
        page = page + 1
        state["page"] = page
    elif query.data == "back":
        context.user_data['admin_menu_state'] = True # <-- Збереження стану в context
        await query.edit_message_text("Виберіть дію:", reply_markup=build_admin_menu())
        await query.answer()
        return

    msg, total = show_tasks_page_msg(topic, page, is_daily)
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

    # <-- Перевірка стану через context.user_data
    if not context.user_data.get('feedback_state') or context.user_data['feedback_state'].get("step") != "pagination":
        await query.answer()
        print(f"[DEBUG] Feedback callback IGNORED (state: {context.user_data.get('feedback_state')})")
        return


    feedbacks = get_all_feedback()
    state = context.user_data['feedback_state'] # <-- Отримання стану з context
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

async def handle_add_task_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # user_id = update.effective_user.id # <-- Не потрібен для перевірки стану
    
    # <-- Перевірка стану через context.user_data
    if context.user_data.get('add_task_state'):
        state = context.user_data['add_task_state'] # <-- Отримання стану з context
        if state.get("step") == "photo":
            data = state.get("data", {})
            file_id = update.message.photo[-1].file_id
            data["photo"] = file_id
            state["data"] = data
            state["step"] = "answer"
            await update.message.reply_text(
                "🔷 Введи правильні відповіді через кому (наприклад: 2, -2):",
                reply_markup=build_cancel_keyboard()
            )
            return True
    return False

async def handle_edit_task_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # user_id = update.effective_user.id # <-- Не потрібен для перевірки стану

    # <-- Перевірка стану через context.user_data
    if context.user_data.get('edit_task_state'):
        state = context.user_data['edit_task_state'] # <-- Отримання стану з context
        if state.get("step") == "edit_photo":
            task_id = state["task_id"]
            file_id = update.message.photo[-1].file_id
            update_task_field(task_id, "photo", file_id)
            await update.message.reply_text(
                "✅ Фото задачі оновлено.",
                reply_markup=build_admin_menu()
            )
            context.user_data.pop('edit_task_state', None) # <-- Видалення стану з context
            context.user_data['admin_menu_state'] = True  # <-- Збереження стану в context
            return True
    return False

async def handle_admin_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # user_id = update.effective_user.id # <-- Не потрібен для перевірки стану

    # 1. Додаємо фото до задачі (створення)
    # <-- Перевірка стану через context.user_data
    if context.user_data.get('add_task_state') and context.user_data['add_task_state'].get("step") == "photo":
        await handle_add_task_photo(update, context)
        return

    # 2. Редагування фото
    # <-- Перевірка стану через context.user_data
    if context.user_data.get('edit_task_state') and context.user_data['edit_task_state'].get("step") == "edit_photo":
        await handle_edit_task_photo(update, context)
        return

    # 3. Якщо не в стейті — просто ігноруємо або даємо підказку
    await update.message.reply_text("Зараз фото не очікується. Спробуйте спочатку вибрати дію в меню.")