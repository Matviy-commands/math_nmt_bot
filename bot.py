# --- Flask для Heroku (не чіпай цей блок, якщо треба веб-інтеграцію) ---
# import threading
# from flask import Flask
# flask_app = Flask(__name__)
# @flask_app.route('/')
# def index():
#     return "Бот працює!"
# def run_flask():
#     import os
#     port = int(os.environ.get("PORT", 5000))
#     flask_app.run(host="0.0.0.0", port=port)
# --- Кінець блоку Flask ---

import os
# from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler

from handlers.start import start_handler
from handlers.admin import admin_message_handler, addtask_handler, admin_menu_state, handle_task_pagination_callback, handle_feedback_pagination_callback
from handlers.task import main_message_handler
from db import init_db

# load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")

async def router(update, context):
    user_id = update.effective_user.id
    text = update.message.text
    if text == "🔐 Адмінка" or user_id in admin_menu_state:
        await admin_message_handler(update, context)
    else:
        await main_message_handler(update, context)


def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CallbackQueryHandler(handle_feedback_pagination_callback, pattern="^feedback_"))
    app.add_handler(CallbackQueryHandler(handle_task_pagination_callback))

    app.add_handler(CommandHandler("addtask", addtask_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, router))
    print("Бот запущено...")
    app.run_polling()

if __name__ == "__main__":
    main()
