import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes

# Import database functions
from db import (
    get_user_field, unlock_badge, get_user_badges, count_user_tasks
)
# Import utility functions if needed (e.g., build_main_menu for error handling)
from handlers.utils import build_main_menu

# --- Logging Setup ---
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# --- End Logging Setup ---

# Define the list of badges and their unlock conditions/rewards
# (Ensure rewards match the balanced values discussed)
BADGES_LIST = [
    ("Сотий крок", "💯",
     "Досягни 100 балів та стань майстром математики! (+50 балів)",
     lambda user_id: (get_user_field(user_id, "score") or 0) >= 100,
     50),

    ("Всі теми!", "📚",
     "Виріши задачі хоча б з кожної теми. (+150 балів)",
     # Check if topics_completed >= topics_total (and total > 0)
     lambda user_id: (tt := get_user_field(user_id, "topics_total") or 0) > 0 and \
                     (get_user_field(user_id, "topics_completed") or 0) >= tt,
     150),

    ("Фідбекер", "📨",
     "Надішли відгук або питання розробнику. (+5 балів)",
     lambda user_id: (get_user_field(user_id, "feedbacks") or 0) >= 1,
     5),

    ("Гуру", "🧙‍♂️",
     "Пройди всі задачі у боті. (+500 балів)",
     # Checks the all_tasks_completed flag which is updated by db functions
     lambda user_id: bool(get_user_field(user_id, "all_tasks_completed")),
     500),

    # --- Daily Streaks ---
    ("3 дні підряд", "🔥",
     "Виконуй завдання 3 дні поспіль. (+5 балів)",
     lambda user_id: (get_user_field(user_id, "streak_days") or 0) >= 3,
     5),

    ("7 днів підряд", "⚡",
     "Виконуй завдання 7 днів поспіль. (+10 балів)",
     lambda user_id: (get_user_field(user_id, "streak_days") or 0) >= 7,
     10),

    ("14 днів підряд", "🚀",
     "Виконуй завдання 14 днів поспіль. (+20 балів)",
     lambda user_id: (get_user_field(user_id, "streak_days") or 0) >= 14,
     20),

    ("1 місяць підряд", "🏅",
     "Виконуй завдання щодня протягом 30 днів. (+50 балів)",
     lambda user_id: (get_user_field(user_id, "streak_days") or 0) >= 30,
     50),
    # Add potential secret badges here without clear descriptions if desired
]


async def show_badges(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Checks for new badges, unlocks them, and displays all user badges."""
    user_id = update.effective_user.id
    logger.info(f"User {user_id}: Running show_badges.")

    try:
        # Send typing action
        await context.bot.send_chat_action(chat_id=user_id, action="typing")
        context.user_data['user_last_menu'] = "badges" # For 'Back' button logic

        logger.info(f"User {user_id}: Checking for new badges...")
        current_badges = set(get_user_badges(user_id))
        got_new = False
        new_badges_msgs = []

        # --- Check and Unlock New Badges ---
        for name, emoji, descr, condition, reward in BADGES_LIST:
            # Check condition only if the badge isn't already unlocked
            if name not in current_badges:
                try:
                    if condition(user_id):
                        # Attempt to unlock the badge
                        if unlock_badge(user_id, name, reward):
                            got_new = True
                            # Format message for newly unlocked badge
                            new_badges_msgs.append(f"{emoji} <b>{name}</b> — відкрито! (+{reward} балів)")
                            current_badges.add(name) # Update current set immediately
                            logger.info(f"User {user_id}: Unlocked badge '{name}'.")
                except Exception as cond_err:
                    # Log error if condition check fails for some reason
                    logger.error(f"Error checking condition for badge '{name}' for user {user_id}: {cond_err}", exc_info=True)
        # --- End Badge Check ---

        logger.info(f"User {user_id}: Formatting badge display message...")
        # Start building the message
        msg = "🛒 <b>Твої Досягнення (Бейджі)</b>\n"

        # --- Display Newly Unlocked Badges ---
        if got_new:
            msg += "\n🎉 <b>Щойно відкрито:</b>\n" + "\n".join(new_badges_msgs) + "\n"
            msg += "--------------------\n" # Separator
        # --- End New Badges Display ---

        # --- Display All Badges (Locked and Unlocked) ---
        msg += "\n📜 <b>Усі Бейджі:</b>\n\n"

        unlocked_list_str = []
        locked_list_str = []

        for name, emoji, descr, *_ in BADGES_LIST:
            # Extract only the condition description (part before the reward)
            condition_text = descr.split("(+")[0].strip() if "(+" in descr else descr

            if name in current_badges:
                unlocked_list_str.append(f"{emoji} <b>{name}</b> (✅ Відкрито)\n   <i>{condition_text}</i>")
            else:
                locked_list_str.append(f"{emoji} {name} (🔒 Ще ні)\n   <i>{condition_text}</i>")

        if unlocked_list_str:
            msg += "<b>🔓 Відкриті:</b>\n" + "\n\n".join(unlocked_list_str) + "\n"

        if locked_list_str:
            msg += "\n<b>🔐 Ще закриті:</b>\n" + "\n\n".join(locked_list_str) + "\n"

        if not unlocked_list_str and not locked_list_str:
            msg += "<i>Список бейджів порожній або ще не завантажився.</i>\n"
        # --- End All Badges Display ---

        # Define the keyboard
        keyboard = [[KeyboardButton("↩️ Назад")]] # Back to progress screen

        logger.info(f"User {user_id}: Badge message formatted. Sending...")
        await update.message.reply_text(
            msg,
            parse_mode="HTML",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        logger.info(f"User {user_id}: Badge message sent successfully.")

    except Exception as e:
        logger.error(f"Error in show_badges for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text(
            "Ой, сталася помилка при відображенні бейджів. 😥 Спробуйте пізніше.",
            reply_markup=build_main_menu(user_id) # Go back to main menu on error
        )