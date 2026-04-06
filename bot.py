import os
import datetime
import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
# from dotenv import load_dotenv

# load_dotenv()

from handlers.start import start_handler
from handlers.admin import (
    admin_message_handler,
    addtask_handler,
    handle_task_pagination_callback,
    handle_feedback_pagination_callback,
    handle_admin_photo,
    notify_admin_promotion,
)
from handlers.task import main_message_handler, handle_contact, handle_task_option_callback
from db import init_db, get_users_for_reengagement 
from handlers.utils import MAIN_MENU_BUTTONS, canonical_button_text

TOKEN = os.getenv("TELEGRAM_TOKEN")
logger = logging.getLogger(__name__)

async def router(update, context):
    raw_text = update.message.text or ""
    text = canonical_button_text(raw_text)
    logger.info("router raw_text=%r canonical=%r user_id=%s", raw_text, text, getattr(update.effective_user, "id", None))
    if text in MAIN_MENU_BUTTONS:
        context.user_data.pop('admin_menu_state', None)
        context.user_data.pop('add_task_state', None)
        context.user_data.pop('delete_task_state', None)
        context.user_data.pop('edit_task_state', None)
        if isinstance(context.user_data.get('feedback_state'), dict):
            context.user_data.pop('feedback_state', None)

    handled = await admin_message_handler(update, context)
    if handled:
        logger.info("router handled by admin_message_handler canonical=%r", text)
        return
    logger.info("router forwarding to main_message_handler canonical=%r", text)
    await main_message_handler(update, context)


async def check_inactive_users(context: ContextTypes.DEFAULT_TYPE):
    print(f"[{datetime.datetime.now()}] Job 'check_inactive_users': Запущено перевірку...")
    
    # --- Повідомлення через 3 дні ---
    try:
        # Шукаємо тих, хто був активний рівно 3 дні тому
        inactive_users = get_users_for_reengagement(days_ago=3)
        print(f"  > Знайдено {len(inactive_users)} користувачів (неактивні 3 дні).")
        
        message_text = (
            "👋 Привіт! Помітили, що ти давно не заходив.\n\n"
            "Твої математичні навички вже сумують! 🧠 Задачі самі себе не вирішать.\n\n"
            "Натисни /start, щоб повернутись у меню, або, "
            "якщо щось не так чи бракує тем, напиши нам через '❓ Допомога / Зв’язок'."
        )
            
        for (user_id,) in inactive_users:
            try:
                await context.bot.send_message(chat_id=user_id, text=message_text)
                print(f"    > Надіслано нагадування юзеру {user_id}")
            except Exception as e:

                print(f"    > ПОМИЛКА відправки юзеру {user_id}: {e}")

        inactive_users_7 = get_users_for_reengagement(days_ago=7)
        print(f"  > Знайдено {len(inactive_users_7)} користувачів (неактивні 7 днів).")
        
        message_text_7 = (
            "😥 Ми сумуємо без тебе... Можливо, щось не так?\n\n"
            "Ми активно додаємо нові задачі та теми. "
            "Дай нам знати, чого тобі не вистачає для підготовки до НМТ!"
        )

        for (user_id,) in inactive_users_7:
            try:
                await context.bot.send_message(chat_id=user_id, text=message_text_7)
                print(f"    > Надіслано 7-денне нагадування юзеру {user_id}")
            except Exception as e:
                print(f"    > ПОМИЛКА відправки 7-денного юзеру {user_id}: {e}")

                
    except Exception as e:
        print(f"[ПОМИЛКА] Збій у завданні check_inactive_users: {e}")
    
    print(f"[{datetime.datetime.now()}] Job 'check_inactive_users': Завершено.")


def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    
    job_queue = app.job_queue
    
    run_time = datetime.time(hour=10, minute=0, second=0)
    
    job_queue.run_daily(
        check_inactive_users,
        time=run_time,
        name="daily_check_inactive"
    )
    
    print(f"Завдання 'check_inactive_users' заплановано на {run_time} UTC щодня.")
    
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("promote", notify_admin_promotion))
    app.add_handler(MessageHandler(filters.PHOTO, handle_admin_photo))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(CallbackQueryHandler(handle_task_option_callback, pattern="^taskopt:"))
    app.add_handler(CallbackQueryHandler(handle_feedback_pagination_callback, pattern="^feedback_"))
    app.add_handler(CallbackQueryHandler(handle_task_pagination_callback, pattern=r"^(prev_|next_|back$|noop$)"))
    app.add_handler(CommandHandler("addtask", addtask_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, router))
    
    print("Бот запущено...")
    app.run_polling()

if __name__ == "__main__":
    main()
