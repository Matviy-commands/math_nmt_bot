from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from db import (
    get_user_field, get_level_by_score,
    get_all_topics, get_all_tasks_by_topic,
    get_user_completed_count, get_top_users, get_user_rank
)

LEVELS = ["легкий", "середній", "важкий"]

async def show_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    from handlers.state import user_last_menu
    user_last_menu[user_id] = "progress"
    score = get_user_field(user_id, "score") or 0
    level = get_level_by_score(score)
    topics = get_all_topics()
    msg = f"📊 <b>Мій рейтинг і прогрес</b>\n\n"
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
        [KeyboardButton("🏆 Рейтинг")],
        [KeyboardButton("↩️ Назад")]
    ]
    await update.message.reply_text(
        msg,
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def show_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    from handlers.state import user_last_menu
    user_last_menu[user_id] = "rating"
    top_users = get_top_users(10)
    msg = "<b>🏆 Топ-10 учасників:</b>\n\n"
    for idx, (uid, u_score) in enumerate(top_users, start=1):
        try:
            user = await context.bot.get_chat(uid)
            uname = "@" + user.username if user.username else f"Користувач {uid}"
        except Exception:
            uname = f"Користувач {uid}"
        medal = ""
        if idx == 1: medal = "🥇"
        elif idx == 2: medal = "🥈"
        elif idx == 3: medal = "🥉"
        msg += f"{medal} {idx}. {uname} — <b>{u_score}</b> балів\n"

    rank, my_score, total_users = get_user_rank(user_id)
    if rank:
        msg += f"\n<b>Твоє місце:</b> {rank} із {total_users}, бали: <b>{my_score}</b>"
    else:
        msg += f"\n<b>Твоє місце:</b> — (немає балів)"

    keyboard = [
        [KeyboardButton("↩️ Назад")]
    ]
    await update.message.reply_text(
        msg,
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
