from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes

from handlers.state import change_name_state
from handlers.utils import admin_ids, CATEGORIES, LEVELS

from db import (
    get_user_field, get_level_by_score,
    get_top_users, get_user_rank,
    get_all_topics_by_category, get_user_badges,
    get_progress_aggregates,   # нова агрегація
)


async def show_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    from handlers.state import user_last_menu
    user_last_menu[user_id] = "progress"

    score = get_user_field(user_id, "score") or 0
    level = get_level_by_score(score)
    streak = get_user_field(user_id, "streak_days") or 0
    opened = len(get_user_badges(user_id))

    msg = (
        "📊 <b>Мій рейтинг і прогрес</b>\n\n"
        f"• <b>Кількість балів:</b> <code>{score}</code>\n"
        f"• <b>Поточний рівень:</b> {level}\n\n"
        f"• <b>Серія днів підряд:</b> {streak}\n\n"
        f"• <b>Відкриті бейджі:</b> {opened}\n\n"
        "<b>Прогрес по темах:</b>\n"
    )

    # одна поїздка в БД замість десятків
    totals, done = get_progress_aggregates(user_id)

    for category in CATEGORIES:
        msg += f"\n<b>{category}:</b>\n"
        topics = get_all_topics_by_category(category)
        for topic in topics:
            lines = []
            for lvl in LEVELS:
                n_total = totals.get((topic, lvl), 0)
                if n_total <= 0:
                    continue
                n_done = done.get((topic, lvl), 0)
                percent = int(n_done / n_total * 100)
                lines.append(f"— {topic} ({lvl}): {n_done}/{n_total} ({percent}%)")
            if lines:
                msg += "  " + "\n  ".join(lines) + "\n"

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

    # Якщо не вказано імʼя — просимо ввести
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
        dn = get_user_field(uid, "display_name") or "Користувач"
        username = get_user_field(uid, "username")
        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else ""

        if user_id in admin_ids:
            line = f"{medal} {idx}. {dn}"
            if username:
                line += f" (@{username})"
            line += f" — <b>{u_score}</b> балів"
        else:
            line = f"{medal} {idx}. {dn} — <b>{u_score}</b> балів"

        msg += line + "\n"

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
