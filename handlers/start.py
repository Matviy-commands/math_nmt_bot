from telegram import Update
from telegram.ext import ContextTypes
from db import create_or_get_user
from handlers.utils import build_main_menu


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник команди /start — створює користувача і показує головне меню."""
    user_id = update.effective_user.id
    # Переконайся, що користувач створений або отриманий перед показом меню
    user = create_or_get_user(user_id) 

    greeting_text = (
        "👋 <b>Привіт! Вітаю у «МехМатику»!</b> 🤖\n"
        "Твій персональний помічник для підготовки до <b>НМТ з математики</b> 📐\n\n"
        "📌 <b>Як тут все влаштовано:</b>\n"
        "   📚 Обирай тему та рівень складності.\n"
        "   💡 Розв'язуй задачі та отримуй пояснення.\n"
        "   🏆 Накопичуй бали та змагайся у рейтингу!\n\n"

        "💰 <b>Система балів (V2):</b>\n"
        "   ✅ <code>+1 бал</code> - Тест (1 відповідь)\n"
        "   📊 <code>+1 бал</code> - За кожну вірну пару у 'Відповідності' (макс. 3)\n"
        "   ✏️ <code>+2 бали</code> - Відкрита відповідь\n"
        "   🤯 <code>+10 балів</code> - BOSS/«гробик»\n"
        "   👀 <i>(Лайтові задачі балів не дають)</i>\n\n"

        "🎁 <b>Бонуси та Досягнення:</b>\n"
        "   🔥 Підтримуй серію днів активності!\n"
        "   🎯 Роби серії правильних відповідей у темах!\n"
        "   🏅 Відкривай круті бейджі за свої успіхи!\n\n"

        "👇 <b>Починай з головного меню:</b>"
    )

    await update.message.reply_text(
        greeting_text,
        parse_mode="HTML",
        reply_markup=build_main_menu(user_id) # Передаємо user_id для можливої кнопки адміна
    )