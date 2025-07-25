from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from db import (
    get_user_field, unlock_badge, get_user_badges, count_user_tasks
)

BADGES_LIST = [
    ("Сотий крок", "💯", "Досягни 100 балів та стань майстром математики! (+200 балів)", lambda user_id: (get_user_field(user_id, "score") or 0) >= 100, 200),
    ("Всі теми!", "📚", "Виріши задачі хоча б з кожної теми. (+150 балів)", lambda user_id: (get_user_field(user_id, "topics_completed") or 0) >= (get_user_field(user_id, "topics_total") or 99), 150),
    ("Тижневий герой", "🗓️", "Пройди щоденні задачі 7 днів поспіль! (+100 балів)", lambda user_id: (get_user_field(user_id, "daily_streak") or 0) >= 7, 100),
    ("Фідбекер", "📨", "Надішли відгук або питання розробнику. (+30 балів)", lambda user_id: (get_user_field(user_id, "feedbacks") or 0) >= 1, 30),
    ("Гуру", "🧙‍♂️", "Пройди всі задачі у боті. (+500 балів)", lambda user_id: (get_user_field(user_id, "all_tasks_completed") or False), 500),
]

async def show_badges(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    from handlers.state import user_last_menu
    user_last_menu[user_id] = "badges"
    badges = set(get_user_badges(user_id))
    got_new = False
    new_badges_msgs = []

    # Автоматичне відкриття бейджів (якщо досягнуто умови)
    for name, emoji, descr, condition, reward in BADGES_LIST:
        if name not in badges and condition(user_id):
            if unlock_badge(user_id, name, reward):
                got_new = True
                new_badges_msgs.append(f"{emoji} <b>{name}</b> — відкрито! (+{reward} балів)")

    # Оновити список після можливого відкриття
    badges = set(get_user_badges(user_id))

    msg = "<b>🛒 Бонуси / Бейджі</b>\n\n"
    if got_new:
        msg += "🎉 <b>Відкрито нові бейджі:</b>\n" + "\n".join(new_badges_msgs) + "\n\n"

    for name, emoji, descr, *_ in BADGES_LIST:
        status = "✅" if name in badges else "🔒"
        msg += f"{emoji} <b>{name}</b> {status}\n<i>{descr}</i>\n\n"

    keyboard = [[KeyboardButton("↩️ Назад")]]
    await update.message.reply_text(
        msg,
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
