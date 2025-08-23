from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes

from handlers.state import change_name_state
from handlers.utils import admin_ids, CATEGORIES, LEVELS 

from db import (
    get_user_field, get_level_by_score,
    get_all_topics, get_all_tasks_by_topic,
    get_user_completed_count, get_top_users, get_user_rank,
    get_all_topics_by_category
)


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
    for category in CATEGORIES:
        msg += f"\n<b>{category}:</b>\n"
        topics = get_all_topics_by_category(category)
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
    display_name = get_user_field(user_id, "display_name")
    # Якщо не вказано імʼя — просимо зареєструватися
    if not display_name:
        change_name_state[user_id] = True
        await update.message.reply_text(
            "Введіть імʼя для відображення у рейтингу (2-20 символів):",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Скасувати")]], resize_keyboard=True)
        )
        return
    from handlers.state import user_last_menu
    user_last_menu[user_id] = "rating"
    top_users = get_top_users(10)
    msg = "<b>🏆 Топ-10 учасників:</b>\n\n"
    for idx, (uid, u_score) in enumerate(top_users, start=1):
        display_name = get_user_field(uid, "display_name") or "Користувач"
        username = get_user_field(uid, "username")  # Телеграм-юзернейм
        medal = ""
        if idx == 1: medal = "🥇"
        elif idx == 2: medal = "🥈"
        elif idx == 3: medal = "🥉"

        # Для адміна — і нік, і юзернейм
        if user_id in admin_ids:
            user_line = f"{medal} {idx}. {display_name}"
            if username:
                user_line += f" (@{username})"
            user_line += f" — <b>{u_score}</b> балів"
        # Для звичайного користувача — тільки нік
        else:
            user_line = f"{medal} {idx}. {display_name} — <b>{u_score}</b> балів"
        msg += user_line + "\n"

    rank, my_score, total_users = get_user_rank(user_id)
    if rank:
        msg += f"\n<b>Твоє місце:</b> {rank} із {total_users}, бали: <b>{my_score}</b>"
    else:
        msg += f"\n<b>Твоє місце:</b> — (немає балів)"

    keyboard = [
        [KeyboardButton("✏️ Змінити імʼя в рейтингу")],
        [KeyboardButton("↩️ Назад")]
    ]
    await update.message.reply_text(
        msg,
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
