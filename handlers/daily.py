import datetime
from telegram import ReplyKeyboardMarkup, KeyboardButton, Update
from telegram.ext import ContextTypes
from db import get_user_field, update_user, get_random_task
from handlers.state import user_states


async def handle_daily_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    today = str(datetime.date.today())
    last_daily = get_user_field(user_id, "last_daily")
    if last_daily == today:
        await update.message.reply_text("📆 Ти вже отримував щоденну задачу сьогодні!")
        return
    task = get_random_task(user_id=user_id)
    if task:
        update_user(user_id, "last_daily", today)
        user_states[user_id] = task
        await update.message.reply_text(
            f"📅 Щоденна задача:\n\n{task['question']}",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❓ Не знаю")]], resize_keyboard=True)
        )
    else:
        await update.message.reply_text("❌ Задач не знайдено.")
