import os
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from db import *
import datetime

TOKEN = os.getenv("TOKEN")

admin_ids = [1070282751]
user_states = {}
add_task_state = {}
TOPICS = ["Квадратні рівняння", "Відсотки"]
LEVELS = ["легкий", "середній", "важкий"]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    create_or_get_user(user_id)

    keyboard = [
        [KeyboardButton("📚 Вибрати тему")],
        [KeyboardButton("🎯 Вибрати рівень")],
        [KeyboardButton("🧠 Отримати задачу")],
        [KeyboardButton("📊 Мій прогрес")],
        [KeyboardButton("🔁 Щоденна задача")],
        [KeyboardButton("➕ Додати задачу")] if user_id in admin_ids else []
    ]
    
    await update.message.reply_text(
        "Привіт! Це бот для підготовки до НМТ з математики 📐\n"
        "Обери тему та рівень, отримуй задачі й отримуй бали!",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def addtask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in admin_ids:
        await update.message.reply_text("⛔ У тебе немає прав додавати задачі.")
        return

    add_task_state[user_id] = {"step": "topic"}
    await update.message.reply_text("📝 Введи тему задачі:")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    create_or_get_user(user_id)

    if text == "📚 Вибрати тему":
        buttons = [[KeyboardButton(topic)] for topic in TOPICS]
        await update.message.reply_text("Оберіть тему:", reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True))

    elif text in TOPICS:
        update_user(user_id, "topic", text)
        await update.message.reply_text(f"✅ Тема обрана: {text}")

    elif text == "🎯 Вибрати рівень":
        buttons = [[KeyboardButton(lvl)] for lvl in LEVELS]
        await update.message.reply_text("Оберіть складність:", reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True))

    elif text in LEVELS:
        update_user(user_id, "level", text)
        await update.message.reply_text(f"✅ Рівень складності: {text}")

    elif text == "🧠 Отримати задачу":
        topic = get_user_field(user_id, "topic")
        level = get_user_field(user_id, "level")
        task = get_random_task(topic, level)
        if task:
            user_states[user_id] = task
            await update.message.reply_text(f"📘 {task['topic']} ({task['level']})\n\n{task['question']}")
        else:
            await update.message.reply_text("❌ Немає задач для цієї теми або рівня.")

    elif text == "📊 Мій прогрес":
        score = get_user_field(user_id, "score")
        level = get_level_by_score(score or 0)
        await update.message.reply_text(f"📊 Бали: {score}\n🎓 Рівень: {level}")

    elif text == "🔁 Щоденна задача":
        today = str(datetime.date.today())
        last_daily = get_user_field(user_id, "last_daily")
        if last_daily == today:
            await update.message.reply_text("📆 Ти вже отримував щоденну задачу сьогодні.")
        else:
            task = get_random_task()
            if task:
                update_user(user_id, "last_daily", today)
                user_states[user_id] = task
                await update.message.reply_text(f"📅 Щоденна задача:\n\n{task['question']}")
            else:
                await update.message.reply_text("❌ Задач не знайдено.")

    elif text == "➕ Додати задачу":
        if user_id in admin_ids:
            add_task_state[user_id] = {"step": "topic"}
            await update.message.reply_text("📝 Введи тему задачі:")
        else:
            await update.message.reply_text("⛔ Тобі недоступна ця функція.")

    # Обробка відповіді на задачу
    elif user_id in user_states:
        task = user_states[user_id]
        if text.strip() in task["answer"]:
            add_score(user_id, 10)
            msg = "✅ Правильно! +10 балів 🎉"
        else:
            msg = "❌ Неправильно."
        msg += f"\n📖 Пояснення: {task['explanation']}"
        await update.message.reply_text(msg)
        del user_states[user_id]

    # Додавання задач (admin flow)
    elif user_id in add_task_state:
        state = add_task_state[user_id]
        data = state.get("data", {})

        if state["step"] == "topic":
            data["topic"] = text
            state["step"] = "level"
            state["data"] = data
            await update.message.reply_text("🟡 Введи рівень задачі (легкий/середній/важкий):")

        elif state["step"] == "level":
            if text not in LEVELS:
                await update.message.reply_text("❌ Невірний рівень. Введи: легкий / середній / важкий")
                return
            data["level"] = text
            state["step"] = "question"
            state["data"] = data
            await update.message.reply_text("🟢 Введи текст задачі:")

        elif state["step"] == "question":
            data["question"] = text
            state["step"] = "answer"
            state["data"] = data
            await update.message.reply_text("🔷 Введи правильні відповіді через кому:")

        elif state["step"] == "answer":
            data["answer"] = [a.strip() for a in text.split(",")]
            state["step"] = "explanation"
            state["data"] = data
            await update.message.reply_text("📘 Введи пояснення до задачі:")

        elif state["step"] == "explanation":
            data["explanation"] = text
            add_task(data)
            await update.message.reply_text("✅ Задачу додано успішно!")
            del add_task_state[user_id]

def main():
    init_db()  # 🔧 Створення таблиць
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addtask", addtask))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    print("Бот запущено...")
    app.run_polling()

if __name__ == "__main__":
    main()
