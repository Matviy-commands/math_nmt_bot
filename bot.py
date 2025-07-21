import os
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from db import *
import datetime

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")

admin_ids = [1070282751]
user_states = {}
add_task_state = {}
start_task_state = {}

TOPICS = ["Квадратні рівняння", "Відсотки"]
LEVELS = ["легкий", "середній", "важкий"]

def build_main_menu(user_id):
    keyboard = [
        [KeyboardButton("🧠 Почати задачу")],
        [KeyboardButton("📊 Мій прогрес")],
        [KeyboardButton("🔁 Щоденна задача")]
    ]
    if user_id in admin_ids:
        keyboard.append([KeyboardButton("➕ Додати задачу")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def build_cancel_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("❌ Скасувати")]], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    create_or_get_user(user_id)
    greeting_text = """👋 Привіт! Це бот для підготовки до НМТ з математики 📐

📌 Як працює бот:
• Обираєш тему і рівень складності
• Отримуєш задачі й відповідаєш на них
• Накопичуєш бали за правильні відповіді

🏆 Як нараховуються бали:
• +10 балів за правильну відповідь
• Можеш переглядати свій прогрес у 📊 Мій прогрес

📚 Навчальні матеріали та підказки:
• Будуть додані скоро — стеж за оновленнями!

ℹ️ Інструкція:
• Обери тему 📚 і рівень 🎯 у головному меню
• Отримай задачу 🧠 або щоденну задачу 🔁
• Перевір свій прогрес і заробляй бейджі!

📍 Головне меню:"""
    await update.message.reply_text(greeting_text, reply_markup=build_main_menu(user_id))

async def addtask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in admin_ids:
        await update.message.reply_text("⛔ У тебе немає прав додавати задачі.")
        return
    add_task_state[user_id] = {"step": "topic"}
    await update.message.reply_text("📝 Введи тему задачі:", reply_markup=build_cancel_keyboard())

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    create_or_get_user(user_id)

    # --- Скасування додавання задачі ---
    if user_id in add_task_state and text == "❌ Скасувати":
        del add_task_state[user_id]
        await update.message.reply_text("Додавання задачі скасовано.", reply_markup=build_main_menu(user_id))
        return

    # --- Додавання задачі (admin flow) ---
    if user_id in add_task_state:
        state = add_task_state[user_id]
        data = state.get("data", {})

        if state["step"] == "topic":
            data["topic"] = text
            state["step"] = "level"
            state["data"] = data
            await update.message.reply_text("🟡 Введи рівень задачі (легкий/середній/важкий):", reply_markup=build_cancel_keyboard())
            return

        elif state["step"] == "level":
            if text not in LEVELS:
                await update.message.reply_text("❌ Невірний рівень. Введи: легкий / середній / важкий", reply_markup=build_cancel_keyboard())
                return
            data["level"] = text
            state["step"] = "question"
            state["data"] = data
            await update.message.reply_text("🟢 Введи текст задачі:", reply_markup=build_cancel_keyboard())
            return

        elif state["step"] == "question":
            data["question"] = text
            state["step"] = "answer"
            state["data"] = data
            await update.message.reply_text("🔷 Введи правильні відповіді через кому (наприклад: 2, -2):", reply_markup=build_cancel_keyboard())
            return

        elif state["step"] == "answer":
            data["answer"] = [a.strip() for a in text.split(",")]
            state["step"] = "explanation"
            state["data"] = data
            await update.message.reply_text("📘 Введи пояснення до задачі:", reply_markup=build_cancel_keyboard())
            return

        elif state["step"] == "explanation":
            data["explanation"] = text
            add_task(data)
            await update.message.reply_text("✅ Задачу додано успішно!", reply_markup=build_main_menu(user_id))
            del add_task_state[user_id]
            return

    # --- Почати задачу ---
    if text == "🧠 Почати задачу":
        start_task_state[user_id] = {"step": "topic"}
        real_topics = set([t["topic"] for t in get_all_tasks_by_topic("Квадратні рівняння")] + [t["topic"] for t in get_all_tasks_by_topic("Відсотки")])
        buttons = [[KeyboardButton(topic)] for topic in TOPICS if topic in real_topics]
        if not buttons:
            await update.message.reply_text("❌ Зараз у базі немає жодної теми із задачами.", reply_markup=build_main_menu(user_id))
            return
        await update.message.reply_text("Оберіть тему:", reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True))
        return

    # --- Логіка кроків вибору задачі ---
    if user_id in start_task_state:
        state = start_task_state[user_id]
        if state["step"] == "topic" and text in TOPICS:
            available_levels = set([t["level"] for t in get_all_tasks_by_topic(text)])
            if not available_levels:
                await update.message.reply_text("❌ Для цієї теми немає жодної задачі.", reply_markup=build_main_menu(user_id))
                del start_task_state[user_id]
                return
            update_user(user_id, "topic", text)
            state["step"] = "level"
            buttons = [[KeyboardButton(lvl)] for lvl in LEVELS if lvl in available_levels]
            await update.message.reply_text(
                f"✅ Тема обрана: {text} ❤️\nТепер оберіть рівень складності:",
                reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
            )
            return
        elif state["step"] == "level" and text in LEVELS:
            topic = get_user_field(user_id, "topic")
            # Перевірка — чи всі задачі виконані:
            if all_tasks_completed(user_id, topic, text):
                await update.message.reply_text(
                    "🎉 Вітаю! Ти пройшов всі задачі цієї теми та рівня!",
                    reply_markup=build_main_menu(user_id)
                )
                del start_task_state[user_id]
                return
            task = get_random_task(topic, text, user_id)
            if task:
                update_user(user_id, "level", text)
                user_states[user_id] = task
                custom_keyboard = ReplyKeyboardMarkup([[KeyboardButton("❓ Не знаю")]], resize_keyboard=True)
                await update.message.reply_text(
                    f"📘 {task['topic']} ({task['level']})\n\n{task['question']}",
                    reply_markup=custom_keyboard
                )
                del start_task_state[user_id]
            else:
                await update.message.reply_text(
                    "🎉 Вітаю! Ти пройшов всі задачі цієї теми та рівня!",
                    reply_markup=build_main_menu(user_id)
                )
                del start_task_state[user_id]
            return

    # --- "Не знаю" — показати пояснення й повернути меню ---
    if text == "❓ Не знаю" and user_id in user_states:
        task = user_states[user_id]
        explanation = task["explanation"].strip()
        if not explanation:
            explanation = "Пояснення відсутнє!"
        msg = f"📖 Пояснення: {explanation}"
        await update.message.reply_text(msg, reply_markup=build_main_menu(user_id))
        mark_task_completed(user_id, task["id"])
        del user_states[user_id]
        return

    # --- Відповідь на задачу ---
    if user_id in user_states:
        task = user_states[user_id]
        explanation = task["explanation"].strip()
        if not explanation:
            explanation = "Пояснення відсутнє!"
        if text.strip() in task["answer"]:
            add_score(user_id, 10)
            msg = "✅ Правильно! +10 балів 🎉"
        else:
            msg = "❌ Неправильно."
        msg += f"\n📖 Пояснення: {explanation}"
        await update.message.reply_text(msg, reply_markup=build_main_menu(user_id))
        mark_task_completed(user_id, task["id"])
        del user_states[user_id]
        return

    # --- Інші функції ---
    if text == "📊 Мій прогрес":
        score = get_user_field(user_id, "score")
        level = get_level_by_score(score or 0)
        await update.message.reply_text(f"📊 Бали: {score}\n🎓 Рівень: {level}", reply_markup=build_main_menu(user_id))

    elif text == "🔁 Щоденна задача":
        today = str(datetime.date.today())
        last_daily = get_user_field(user_id, "last_daily")
        if last_daily == today:
            await update.message.reply_text("📆 Ти вже отримував щоденну задачу сьогодні.", reply_markup=build_main_menu(user_id))
        else:
            task = get_random_task(user_id=user_id)
            if task:
                update_user(user_id, "last_daily", today)
                user_states[user_id] = task
                custom_keyboard = ReplyKeyboardMarkup([[KeyboardButton("❓ Не знаю")]], resize_keyboard=True)
                await update.message.reply_text(
                    f"📅 Щоденна задача:\n\n{task['question']}",
                    reply_markup=custom_keyboard
                )
            else:
                await update.message.reply_text("❌ Задач не знайдено.", reply_markup=build_main_menu(user_id))

    elif text == "➕ Додати задачу":
        if user_id in admin_ids:
            add_task_state[user_id] = {"step": "topic"}
            await update.message.reply_text("📝 Введи тему задачі:", reply_markup=build_cancel_keyboard())
        else:
            await update.message.reply_text("⛔ Тобі недоступна ця функція.", reply_markup=build_main_menu(user_id))

def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addtask", addtask))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    print("Бот запущено...")
    app.run_polling()

if __name__ == "__main__":
    main()
