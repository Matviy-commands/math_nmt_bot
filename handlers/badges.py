from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes

async def show_badges(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "<b>🛒 Бонуси / Бейджі</b>\n\n"
        "• За кількість задач (10/50/100)\n"
        "• За щоденну активність\n"
        "• За проходження всіх тем\n"
        "• ... (незабаром)\n\n"
        "<i>Збирай бали й відкривай досягнення!</i>"
    )
    await update.message.reply_text(
        msg,
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("↩️ Назад")]], resize_keyboard=True)
    )
