import datetime
import logging # <-- Додаємо logging
from telegram import ReplyKeyboardMarkup, KeyboardButton, Update
from telegram.ext import ContextTypes

# Імпорти з db
from db import get_user_field, update_user, get_random_task

# Налаштування логера
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

async def handle_daily_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the '/daily' command or 'Щоденна задача' button."""
    user_id = update.effective_user.id
    logger.info(f"User {user_id}: Requested daily task.")

    try:
        today_str = str(datetime.date.today())
        last_daily_str = get_user_field(user_id, "last_daily")

        # --- Check if already received today ---
        if last_daily_str == today_str:
            logger.info(f"User {user_id}: Daily task already received today.")
            await update.message.reply_text(
                "📆 Ти вже отримував(ла) щоденну задачу сьогодні! Повертайся завтра. 😉"
            )
            return
        # --- End Check ---

        # --- Get a random daily task ---
        logger.info(f"User {user_id}: Fetching a new daily task...")
        # Make sure user_id is passed if you want to exclude completed tasks
        task = get_random_task(user_id=None, is_daily=1) # Or pass user_id if needed

        if task:
            logger.info(f"User {user_id}: Daily task ID {task.get('id')} found.")
            # Update last_daily date in DB
            update_user(user_id, "last_daily", today_str)

            # --- Set up solving state for the daily task ---
            context.user_data['solving_state'] = {
                "topic": task.get("topic", "Щоденна"), # Use default topic if missing
                "level": task.get("level", ""),       # Level might be empty for daily
                "task_ids": [task["id"]],
                "current": 0,
                "current_task": task,
                "is_daily": True,
                "total_tasks": 1 # Only one task
            }
            # --- End State Setup ---

            # --- Send the task ---
            # Use formatting similar to send_next_task
            header = f"📅 <b>Щоденна Задача на Сьогодні!</b>"
            topic_info = f"Тема: {task.get('topic', 'Різне')}" # Show topic if available
            task_body = task.get('question', 'Текст завдання відсутній.')

            task_text = f"{header}\n<i>{topic_info}</i>\n\n📝 <b>Завдання:</b>\n{task_body}"

            # Keyboard for answering
            kb = ReplyKeyboardMarkup(
                   [[KeyboardButton("↩️ Меню"), KeyboardButton("❓ Не знаю")]],
                   resize_keyboard=True
               )

            if task.get("photo"):
                await update.message.reply_photo(
                    task["photo"], caption=task_text, reply_markup=kb, parse_mode="HTML"
                )
            else:
                await update.message.reply_text(task_text, reply_markup=kb, parse_mode="HTML")
            # --- End Sending Task ---

        else:
            logger.warning(f"User {user_id}: No available daily tasks found.")
            await update.message.reply_text("❌ На жаль, на сьогодні щоденних завдань немає. Зазирни пізніше!")

    except Exception as e:
        logger.error(f"Error in handle_daily_task for user {user_id}: {e}", exc_info=True)
        # Import build_main_menu if not already imported at top
        from handlers.utils import build_main_menu
        await update.message.reply_text(
            "Ой, сталася помилка при отриманні щоденної задачі. 😥 Спробуйте пізніше.",
            reply_markup=build_main_menu(user_id)
        )