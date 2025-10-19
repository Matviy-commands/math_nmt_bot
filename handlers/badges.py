from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from db import (
    get_user_field, unlock_badge, get_user_badges, count_user_tasks
)

BADGES_LIST = [
    # --- Бали / прогрес ---
    ("Сотий крок", "💯",
     "Досягни 100 балів та стань майстром математики! (+200 балів)",
     lambda user_id: (get_user_field(user_id, "score") or 0) >= 100,
     200),

    ("Всі теми!", "📚",
     "Виріши задачі хоча б з кожної теми. (+150 балів)",
     lambda user_id: (get_user_field(user_id, "topics_completed") or 0) >= (get_user_field(user_id, "topics_total") or 99),
     150),

    ("Фідбекер", "📨",
     "Надішли відгук або питання розробнику. (+30 балів)",
     lambda user_id: (get_user_field(user_id, "feedbacks") or 0) >= 1,
     30),

    ("Гуру", "🧙‍♂️",
     "Пройди всі задачі у боті. (+500 балів)",
     lambda user_id: bool(get_user_field(user_id, "all_tasks_completed")),
     500),

    # --- Серії (streak) за протяжність виконання ---
    ("3 дні підряд", "🔥",
     "Виконуй завдання 3 дні поспіль (щоденні або по темах). (+5 балів)",
     lambda user_id: (get_user_field(user_id, "streak_days") or 0) >= 3,
     5),

    ("7 днів підряд", "⚡",
     "Виконуй завдання 7 днів поспіль (щоденні або по темах). (+10 балів)",
     lambda user_id: (get_user_field(user_id, "streak_days") or 0) >= 7,
     10),

    ("14 днів підряд", "🚀",
     "Виконуй завдання 14 днів поспіль (щоденні або по темах). (+20 балів)",
     lambda user_id: (get_user_field(user_id, "streak_days") or 0) >= 14,
     20),

    ("1 місяць підряд", "🏅",
     "Виконуй завдання щодня протягом 30 днів. (+50 балів)",
     lambda user_id: (get_user_field(user_id, "streak_days") or 0) >= 30,
     50),
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
