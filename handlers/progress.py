import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes

# Import helper functions and constants
from handlers.utils import (
    admin_ids, CATEGORIES, LEVELS,
    create_progress_bar, # Import the new progress bar function
    build_main_menu # Import build_main_menu for error handling
)
# Import badge list to display emojis
from handlers.badges import BADGES_LIST

# Import database functions
from db import (
    get_user_field, get_level_by_score,
    get_top_users, get_user_rank,
    get_all_topics_by_category, get_user_badges,
    get_progress_aggregates,
)

# --- Logging Setup ---
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# --- End Logging Setup ---


async def show_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the user's progress, score, level, streaks, and badges."""
    user_id = update.effective_user.id
    logger.info(f"User {user_id}: Running show_progress.")

    try:
        # Send typing action for immediate feedback
        await context.bot.send_chat_action(chat_id=user_id, action="typing")
        context.user_data['user_last_menu'] = "progress" # Track last menu for 'Back' button

        logger.info(f"User {user_id}: Fetching user data for progress...")
        # Fetch user data safely using .get() or default values
        score = get_user_field(user_id, "score") or 0
        level = get_level_by_score(score) # Handles None score internally now
        streak = get_user_field(user_id, "streak_days") or 0
        user_badges = get_user_badges(user_id) # Fetch badges list
        opened_badges_count = len(user_badges)

        # Fetch progress aggregates
        totals, done = get_progress_aggregates(user_id)
        logger.info(f"User {user_id}: Data fetched. Formatting message...")

        # --- Build Progress Message ---
        msg = (
            "📊 <b>Мій Прогрес та Статистика</b>\n\n"
            f"⭐ <b>Загальний рахунок:</b> <code>{score}</code> балів\n"
            f"🏅 <b>Твій рівень:</b> {level}\n\n"
            f"🔥 <b>Серія днів підряд:</b> <code>{streak}</code>\n"
            f"🏆 <b>Відкрито бейджів:</b> <code>{opened_badges_count}</code>\n\n"
            "📚 <b>Прогрес по Темах:</b>\n"
            "--------------------\n"
        )

        has_progress_data = False
        # Iterate through categories to display progress
        for category in CATEGORIES:
            category_msg = f"\n📁 <b>{category}:</b>\n"
            category_has_topics = False
            topics = get_all_topics_by_category(category) # Get topics for this category
            topics.sort() # Sort topics alphabetically

            for topic in topics:
                topic_lines = []
                topic_has_levels = False
                # Filter and sort levels that actually have tasks in totals
                sorted_levels = sorted([lvl for lvl in LEVELS if totals.get((topic, lvl), 0) > 0])

                for lvl in sorted_levels:
                    n_total = totals.get((topic, lvl), 0)
                    n_done = done.get((topic, lvl), 0)

                    # Use the progress bar function
                    progress_bar_str = create_progress_bar(n_done, n_total, length=8) # Bar length 8
                    level_emoji = "🟢" if lvl == "легкий" else "🟡" if lvl == "середній" else "🔴" if lvl == "важкий" else "❓"
                    topic_lines.append(f"   {level_emoji} {lvl.capitalize()}: {progress_bar_str}")
                    topic_has_levels = True
                    has_progress_data = True # Mark that we have some progress to show

                if topic_has_levels:
                    # Add topic name before its levels
                    category_msg += f"  📖 <i>{topic}:</i>\n" + "\n".join(topic_lines) + "\n"
                    category_has_topics = True

            if category_has_topics:
                msg += category_msg
            else:
                 # If category has no topics with tasks (or no progress yet)
                 msg += f"\n📁 <b>{category}:</b>\n  <i>(Поки що немає прогресу)</i>\n"

        # Handle cases where there's no progress data at all
        if not has_progress_data and not any(get_all_topics_by_category(cat) for cat in CATEGORIES):
             msg += "\n<i>Розпочни розв'язувати задачі, щоб побачити свій прогрес тут!</i>\n"
        elif not has_progress_data:
             msg += "\n<i>Поки що немає прогресу по жодній темі. Вперед до знань!</i> 💪\n"

        # --- Display Unlocked Badges ---
        msg += "\n--------------------\n"
        msg += "🏅 <b>Твої Досягнення (Бейджі):</b>\n"
        if user_badges:
            badge_lines = []
            # Sort badges maybe?
            # user_badges.sort()
            for badge_name in user_badges:
                 badge_emoji = "🏆" # Default emoji
                 # Find emoji from BADGES_LIST
                 for b_name, b_emoji, *_ in BADGES_LIST:
                     if b_name == badge_name:
                         badge_emoji = b_emoji
                         break
                 badge_lines.append(f"  {badge_emoji} {badge_name}")
            msg += "\n".join(badge_lines) + "\n"
        else:
            msg += "<i>Поки що немає відкритих бейджів. Виконуй завдання, щоб їх отримати!</i>\n"
        # --- End Badges Display ---

        # Define keyboard for the progress screen
        keyboard = [
            [KeyboardButton("🛒 Бонуси / Бейджі")],
            [KeyboardButton("🏆 Рейтинг")],
            [KeyboardButton("↩️ Назад")] # Back to main menu
        ]

        logger.info(f"User {user_id}: Progress message formatted. Sending...")
        await update.message.reply_text(
            msg,
            parse_mode="HTML",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        logger.info(f"User {user_id}: Progress message sent successfully.")

    except Exception as e:
        logger.error(f"Error in show_progress for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text(
            "Ой, сталася помилка при відображенні прогресу. 😥 Спробуйте пізніше.",
            reply_markup=build_main_menu(user_id) # Go back to main menu on error
        )


async def show_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the top users leaderboard and the current user's rank."""
    user_id = update.effective_user.id
    logger.info(f"User {user_id}: Running show_rating.")

    try:
        display_name = get_user_field(user_id, "display_name")

        # --- Initiate Registration if Name is Missing ---
        if not display_name:
            logger.info(f"User {user_id}: No display name found. Initiating registration.")
            context.user_data['registration_state'] = {"step": "name"}
            await update.message.reply_text(
                "👋 Схоже, ти тут вперше! Щоб потрапити до рейтингу, давай зареєструємось.\n\n"
                "Введіть імʼя для відображення (2-20 символів):",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Скасувати")]], resize_keyboard=True, one_time_keyboard=True)
            )
            return
        # --- End Registration Check ---

        # Send typing action
        await context.bot.send_chat_action(chat_id=user_id, action="typing")
        context.user_data['user_last_menu'] = "rating" # Track for 'Back' button

        logger.info(f"User {user_id}: Fetching rating data...")
        top_users = get_top_users(10) # Fetch top 10 users with score > 0
        rank, my_score, total_users = get_user_rank(user_id) # Fetch user's rank among those with score > 0
        logger.info(f"User {user_id}: Rating data fetched. Formatting message...")

        # --- Build Rating Message ---
        msg = "🏆 <b>Рейтинг Топ-10 Гравців</b> 🏆\n\n"

        if not top_users:
            msg += "<i>Поки що ніхто не набрав балів. Будь першим!</i> 😉\n"
        else:
            for idx, (uid, u_score) in enumerate(top_users, start=1):
                # Fetch display name safely
                dn = get_user_field(uid, "display_name") or f"Гравець_{uid%1000}"
                medal = ""
                if idx == 1: medal = "🥇"
                elif idx == 2: medal = "🥈"
                elif idx == 3: medal = "🥉"
                else: medal = f"{idx}." # Use number for others

                line = f"{medal} {dn} — <code>{u_score}</code> балів"
                if uid == user_id:
                     line += " <b>(Ти!)</b> ✨"
                msg += line + "\n"

        msg += "\n--------------------\n" # Separator

        # Display user's rank info
        if rank: # User is in the ranked list (score > 0)
            msg += f"👤 <b>Твоє місце:</b> {rank} з {total_users} (серед гравців з балами)\n"
            msg += f"⭐ <b>Твої бали:</b> <code>{my_score}</code>"
        else: # User has 0 score or an error occurred
            msg += f"👤 <b>Твоє місце:</b> Поки що поза рейтингом (<code>{my_score}</code> балів)\n"
            msg += "<i>Виконуй завдання, щоб потрапити у топ!</i> 💪"
        # --- End Rating Message ---

        # Define keyboard for the rating screen
        keyboard = [
            [KeyboardButton("✏️ Змінити імʼя в рейтингу")],
            [KeyboardButton("↩️ Назад")] # Back to progress screen
        ]

        logger.info(f"User {user_id}: Rating message formatted. Sending...")
        await update.message.reply_text(
            msg,
            parse_mode="HTML",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        logger.info(f"User {user_id}: Rating message sent successfully.")

    except Exception as e:
        logger.error(f"Error in show_rating for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text(
            "Ой, сталася помилка при відображенні рейтингу. 😥 Спробуйте пізніше.",
            reply_markup=build_main_menu(user_id) # Go back to main menu on error
        )