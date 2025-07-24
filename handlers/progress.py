from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from db import get_user_field, get_level_by_score, get_all_topics, get_all_tasks_by_topic, get_user_completed_count

LEVELS = ["легкий", "середній", "важкий"]

async def show_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    score = get_user_field(user_id, "score") or 0
    level = get_level_by_score(score)
    topics = get_all_topics()
    msg = f"🏆 <b>Мій рейтинг і прогрес</b>\n\n"
    msg += f"• <b>Кількість балів:</b> <code>{score}</code>\n"
    msg += f"• <b>Поточний рівень:</b> {level}\n\n"

    msg += "<b>Прогрес по темах:</b>\n"
    for topic in topics:
        for lvl in LEVELS:
            tasks = get_all_tasks_by_topic(topic)
            n_total = len([t for t in tasks if t['level'] == lvl])
            n_done = get_user_completed_count(user_id, topic, lvl)
            if n_total > 0:
                percent = int(n_done / n_total * 100)
                msg += f"  — {topic} ({lvl}): {n_done}/{n_total} ({percent}%)\n"

    msg += "\n<b>Відкриті бейджі:</b> 🔓 (незабаром)\n"

    keyboard = [
        [KeyboardButton("🛒 Бонуси / Бейджі")],
        [KeyboardButton("↩️ Назад")]
    ]
    await update.message.reply_text(
        msg,
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
