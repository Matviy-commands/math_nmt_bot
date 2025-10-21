from telegram import Update
from telegram.ext import ContextTypes
from db import create_or_get_user
from handlers.utils import build_main_menu


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник команди /start — створює користувача і показує головне меню."""
    user_id = update.effective_user.id
    user = create_or_get_user(user_id)

    greeting_text = (
        "👋 <b>Привіт!</b> Це бот для підготовки до <b>НМТ з математики</b> 📐\n\n"
        "📌 <b>Як працює бот:</b>\n"
        "• Обираєш тему і рівень складності\n"
        "• Отримуєш задачі й відповідаєш на них\n"
        "• Накопичуєш бали за правильні відповіді\n\n"
        "🏆 <b>Як нараховуються бали (V2):</b>\n"
        "• <b>+1 бал</b> за 'Тест (1 відповідь)'\n"
        "• <b>+1 бал</b> за кожну правильну у 'Відповідності' (макс. 3)\n"
        "• <b>+2 бали</b> за 'Відкрита відповідь'\n"
        "• <b>+10 балів</b> за 'BOSS/«гробик»'\n"
        "• Переглядай свій прогрес у <b>📊 Мій прогрес</b>\n\n"
        "📚 <b>Навчальні матеріали:</b>\n"
        "• Підручники, довідники та відео — у розділі <b>Матеріали</b>\n\n"
        "🎯 <b>Інструкція:</b>\n"
        "1️⃣ Обери тему 📚 та рівень складності 🎯\n"
        "2️⃣ Отримай задачу 🧠 або щоденну задачу 🔁\n"
        "3️⃣ Перевір свій прогрес і заробляй бейджі 🏅\n\n"
        "📍 <b>Головне меню:</b>"
    )

    await update.message.reply_text(
        greeting_text,
        parse_mode="HTML",
        reply_markup=build_main_menu(user_id)
    )
