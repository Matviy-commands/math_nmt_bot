import os
import datetime
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
)
from handlers.task import main_message_handler
from db import init_db, get_users_for_reengagement

TOKEN = os.getenv("TELEGRAM_TOKEN")

async def router(update, context):
    text = update.message.text
    if text == "🔐 Адмінка" or context.user_data.get('admin_menu_state'):
        await admin_message_handler(update, context)
    else:
        await main_message_handler(update, context)


async def check_inactive_users(context: ContextTypes.DEFAULT_TYPE):
    print(f"[{datetime.datetime.now()}] Job 'check_inactive_users': Запущено перевірку...")
    
    try:
        # --- 1. ТИМЧАСОВА ЗМІНА ДЛЯ ТЕСТУ ---
        # Ми шукаємо 5 днів, бо в твоїй базі стоїть '2025-10-18' (23 - 18 = 5)
        # Поверни на 'days_ago=3' після тесту.
        inactive_users = get_users_for_reengagement(days_ago=5) 
        print(f"  > Знайдено {len(inactive_users)} користувачів (неактивні 5 днів - ТЕСТ).")
        
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

        
        # (Цей блок зараз нічого не знайде, бо 7 днів - це інша дата)
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
    
    
    # --- 2. ТИМЧАСОВІ ЗМІНИ ДЛЯ ТЕСТУ ---
    
    # run_time = datetime.time(hour=10, minute=0, second=0)
    
    # --- Коментуємо щоденний запуск ---
    # job_queue.run_daily(
    #     check_inactive_users,
    #     time=run_time,
    #     name="daily_check_inactive"
    # )
    # print(f"Завдання 'check_inactive_users' заплановано на {run_time} UTC щодня.")

    
    # --- Додаємо запуск через 10 секунд ---
    print("!!! ТЕСТОВИЙ РЕЖИМ: 'check_inactive_users' запуститься через 10 секунд.")
    job_queue.run_once(check_inactive_users, when=10)
    
    # --- Кінець тестових змін ---


    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(MessageHandler(filters.PHOTO, handle_admin_photo))
    app.add_handler(CallbackQueryHandler(handle_feedback_pagination_callback, pattern="^feedback_"))
    app.add_handler(CallbackQueryHandler(handle_task_pagination_callback))
    app.add_handler(CommandHandler("addtask", addtask_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, router))
    
    print("Бот запущено...")
    app.run_polling()

if __name__ == "__main__":
    main()