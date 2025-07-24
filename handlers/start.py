from handlers.utils import build_main_menu
from db import create_or_get_user
from telegram import Update
from telegram.ext import ContextTypes

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    create_or_get_user(user_id)
    greeting_text = """👋 Привіт! Це бот для підготовки до НМТ з математики 📐

📌 Як працює бот:
• Обираєш тему і рівень складності
• Отримуєш задачі й відповідаєш на них
• Накопичуєш бали за правильні відповіді

🏆 Як нараховуються бали:
• +10 балів за правильну відповідь
• Можеш переглядати свій прогрес у 📊 Мій прогрес

📚 Навчальні матеріали та підказки:
• Будуть додані скоро — стеж за оновленнями!

ℹ️ Інструкція:
• Обери тему 📚 і рівень 🎯 у головному меню
• Отримай задачу 🧠 або щоденну задачу 🔁
• Перевір свій прогрес і заробляй бейджі!

📍 Головне меню:"""
    await update.message.reply_text(greeting_text, reply_markup=build_main_menu(user_id))
