from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from handlers.progress import show_progress, show_rating
from handlers.daily import handle_daily_task
from handlers.state import feedback_state, user_last_menu, solving_state, change_name_state
from handlers.badges import show_badges
from handlers.materials import MATERIALS
from handlers.scoring import calc_points


from handlers.utils import (
    build_main_menu,
    build_category_keyboard,
    build_back_to_menu_keyboard,
    CATEGORIES,               
    LEVELS,
)

from db import (
    get_all_topics,
    get_all_tasks_by_topic,
    get_user_field,
    get_random_task,
    update_user,
    all_tasks_completed,
    mark_task_completed,
    add_score,
    add_feedback,
    get_available_levels_for_topic,
    get_all_topics_by_category,
    get_completed_task_ids,
    update_streak_and_reward,
    get_user_completed_count,
    get_topic_streak, set_topic_streak, inc_topic_streak, reset_topic_streak,
    has_topic_streak_award, mark_topic_streak_award,

)


HELP_TEXT = """
🆘 <b>Допомога та зв'язок</b>

<b>FAQ:</b>
— <b>Що це за бот?</b>
Це навчальний бот для практики задач НМТ з математики.

— <b>Як користуватись?</b>
Обирай тему, вирішуй задачі, отримуй бали, перевіряй прогрес та проходь щоденні задачі.

— <b>Я не можу знайти потрібну тему / є баг</b>
Пиши розробнику через кнопку нижче!
"""

start_task_state = {}

def build_task_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("❓ Не знаю")]], resize_keyboard=True)

def build_level_keyboard(levels):
    buttons = [[KeyboardButton(lvl)] for lvl in levels]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

async def task_entrypoint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    topics = get_all_topics()
    if not topics:
        await update.message.reply_text("❌ Зараз у базі немає жодної теми із задачами.")
        return
    await update.message.reply_text("Оберіть тему:", reply_markup=build_topic_keyboard())
    start_task_state[user_id] = {"step": "topic"}

async def handle_task_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if user_id in start_task_state:
        state = start_task_state[user_id]

        # вибір категорії
        if state["step"] == "category" and text in CATEGORIES:
            state["category"] = text
            from db import get_all_topics_by_category
            topics = get_all_topics_by_category(text)
            if not topics:
                await update.message.reply_text(
                    "❌ У цій категорії немає тем.\n\nНатисни «↩️ Меню», щоб повернутись.",
                    reply_markup=build_back_to_menu_keyboard()
                )
                return

            state["step"] = "topic"
            await update.message.reply_text("Оберіть тему:", reply_markup=build_topic_keyboard(topics))
            return
        
        # якщо натиснули назад -> повертаємось на вибір категорії
        if state["step"] == "topic" and text == "↩️ Назад":
            state["step"] = "category"
            await update.message.reply_text(
                "Оберіть категорію:",
                reply_markup=build_category_keyboard()
            )
            return


        # вибір теми
        topics = get_all_topics()  # або фільтруй по категорії, якщо треба
        if state["step"] == "topic" and text in topics:
            available_levels = set([t["level"] for t in get_all_tasks_by_topic(text)])
            if not available_levels:
                await update.message.reply_text("❌ Для цієї теми немає жодної задачі.")
                del start_task_state[user_id]
                return
            update_user(user_id, "topic", text)
            state["step"] = "level"
            buttons = [[KeyboardButton(lvl)] for lvl in LEVELS if lvl in available_levels]
            await update.message.reply_text(
                f"✅ Тема обрана: {text} ❤️\nТепер обери рівень складності:",
                reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
            )
            return

        elif state["step"] == "level" and text in LEVELS:
            topic = get_user_field(user_id, "topic")
            # --- отримуємо всі задачі цієї теми
            all_tasks = get_all_tasks_by_topic(topic)
            # --- фільтруємо задачі саме цього рівня
            level_tasks = [t for t in all_tasks if t["level"] == text]
            if not level_tasks:
                await update.message.reply_text(
                    f"❌ Для рівня «{text}» задач немає!",
                    reply_markup=build_main_menu(user_id)
                )
                del start_task_state[user_id]
                return

            # --- визначаємо невиконані задачі
            # --- беремо всі задачі рівня (ДОЗВОЛЯЄМО перепроходження)
            completed_ids = set(get_completed_task_ids(user_id, topic, text))  # збережемо, щоб знати які вже виконані
            tasks = level_tasks  # не фільтруємо

            # --- зберігаємо стан проходження рівня (додаємо completed_ids)
            solving_state[user_id] = {
                "topic": topic,
                "level": text,
                "task_ids": [t["id"] for t in tasks],
                "completed_ids": completed_ids,   # <- важливо
                "current": 0,
            }

            await send_next_task(update, context, user_id)
            del start_task_state[user_id]
            return

async def send_next_task(update, context, user_id):
    state = solving_state[user_id]
    idx = state["current"]
    task_id = state["task_ids"][idx]
    from db import get_task_by_id
    task = get_task_by_id(task_id)
    already_done = task_id in (solving_state[user_id].get("completed_ids") or set())
    state["current_task"] = task
    # Надіслати задачу (текст + фото)
    kb = ReplyKeyboardMarkup(
        [[KeyboardButton("↩️ Меню"), KeyboardButton("❓ Не знаю")]], resize_keyboard=True)
    task_text = f"📘 {task['topic']} ({task['level']})\n\n{task['question']}"

        # необов'язково: показати поточну серію у темі
    try:
        cur_streak = get_topic_streak(user_id, state["topic"])
        if cur_streak > 0:
            task_text = f"🔥 Серія в темі: {cur_streak}\n\n" + task_text
    except Exception:
        pass


    # ⬇️ якщо задача вже була виконана — покажемо плашку "повтор"
    if already_done:
        task_text = "🔁 (повтор, без нарахування балів)\n\n" + task_text


    if task.get("photo"):
        await update.message.reply_photo(
            task["photo"], caption=task_text, reply_markup=kb
        )
    else:
        await update.message.reply_text(task_text, reply_markup=kb)


async def handle_task_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if user_id in solving_state:
        state = solving_state[user_id]
        task = state.get("current_task")
        if text == "↩️ Меню":
            solving_state.pop(user_id, None)
            await update.message.reply_text(
                "📍 Головне меню:",
                reply_markup=build_main_menu(user_id)
            )
            return
        explanation = task["explanation"].strip() if task["explanation"] else "Пояснення відсутнє!"

        # === Перевірка відповіді + скоринг (єдиний блок) ===
        user_answers = [a.strip() for a in text.replace(';', ',').split(',') if a.strip()]
        correct_answers = [a.strip() for a in task["answer"]]
        task_type = (task.get("task_type") or "").lower()

        if task_type == "match":
            # часткові збіги — рахуємо; повна правильність, якщо вгадано всі
            match_correct = len(set(user_answers) & set(correct_answers))
            is_correct = (match_correct == len(correct_answers))
        else:
            # інші типи — повний збіг множин (порядок неважливий)
            match_correct = 0
            is_correct = (
                len(user_answers) == len(correct_answers) and
                set(user_answers) == set(correct_answers)
            )

        # чи це повторне проходження
        already_done = task["id"] in (state.get("completed_ids") or set())

        # на повторі бали не нараховуємо
        if already_done:
            delta = 0
        else:
            delta = calc_points(task, is_correct=is_correct, match_correct=match_correct)

        if delta > 0:
            add_score(user_id, delta)

        if is_correct:
            if already_done:
                msg = "✅ Правильно! (повтор) Балів не нараховано."
            else:
                msg = f"✅ Правильно! +{delta} балів 🎉" if delta > 0 else "✅ Правильно!"
        else:
            msg = "❌ Неправильна відповідь.\n⚠️ Бали за цю задачу не нараховано."


        msg += f"\n📖 Пояснення: {explanation}"
        await update.message.reply_text(msg)

        # --------------------------
        # Серія правильних у межах теми (лише перші проходження)
        topic = state["topic"]
        TOPIC_STREAK_MILESTONES = {5: 5, 10: 10, 15: 25, 20: 40, 30: 60}

        if not already_done:
            if is_correct:
                new_streak = inc_topic_streak(user_id, topic)
                awarded_msgs = []
                for m, bonus in TOPIC_STREAK_MILESTONES.items():
                    if new_streak >= m and not has_topic_streak_award(user_id, topic, m):
                        add_score(user_id, bonus)
                        mark_topic_streak_award(user_id, topic, m)
                        awarded_msgs.append(f"🏅 Серія {m} правильних у темі «{topic}»! +{bonus} балів")
                if awarded_msgs:
                    await update.message.reply_text("\n".join(awarded_msgs))
            else:
                # перша спроба на цю задачу неправильна -> скидаємо серію
                reset_topic_streak(user_id, topic)
        # якщо already_done == True (повтор), серію не чіпаємо
        # --------------------------


        # --- streak & бонуси за безперервні дні
        streak, bonus = update_streak_and_reward(user_id)
        if bonus > 0:
            await update.message.reply_text(
                f"🔥 Серія: {streak} дні(в) підряд! Бонус +{bonus} балів."
            )
        
        # якщо це перша спроба на цю задачу — скидаємо серію у темі
        already_done = task["id"] in (state.get("completed_ids") or set())
        if not already_done:
            reset_topic_streak(user_id, state["topic"])


        mark_task_completed(user_id, task["id"])
        state["current"] += 1
        if state["current"] < len(state["task_ids"]):
            is_daily = state.get("is_daily", False)
            if is_daily:
                await update.message.reply_text(
                    "🎉 Вітаю! Ви виконали щоденну задачу!",
                    reply_markup=ReplyKeyboardMarkup([[KeyboardButton("↩️ Меню")]], resize_keyboard=True)
                )
                solving_state.pop(user_id, None)
                return

            await send_next_task(update, context, user_id)
        else:
            # кінець списку задач
            is_daily = state.get("is_daily", False)
            if is_daily:
                await update.message.reply_text(
                    "🎉 Готово! Щоденна задача на сьогодні виконана.\n"
                    "Повернись завтра по нову 💪",
                    reply_markup=ReplyKeyboardMarkup([[KeyboardButton("↩️ Меню")]], resize_keyboard=True)
                )
                solving_state.pop(user_id, None)
                return

            # --- звичайні (не daily) задачі: показуємо стандартне завершення рівня ---
            topic = state["topic"]
            current_level = state["level"]
            available_levels = get_available_levels_for_topic(topic, exclude_level=current_level)

            keyboard = []
            if available_levels:
                keyboard.append([KeyboardButton(lvl) for lvl in available_levels])
            keyboard.append([KeyboardButton("Змінити тему")])
            keyboard.append([KeyboardButton("↩️ Меню")])

            await update.message.reply_text(
                f"🎉 Вітаю! Ви завершили всі задачі рівня «{current_level}».\n"
                "Оберіть інший рівень або змініть тему, або поверніться в меню.",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
            # --- Бонус за тему ≥70% (альтернатива без бейджа) ---
            try:
                # Порахувати прогрес по ВСІЙ темі (усі рівні)
                all_tasks_in_topic = get_all_tasks_by_topic(topic)  # без is_daily => звичайні задачі
                total_in_topic = len(all_tasks_in_topic)

                # Скільки задач у темі виконано користувачем по всіх рівнях
                completed_in_topic = sum(
                    get_user_completed_count(user_id, topic, lvl)
                    for lvl in {"легкий", "середній", "важкий"}
                )

                if total_in_topic > 0:
                    percent = completed_in_topic / total_in_topic
                    if percent >= 0.70:
                        # Нарахуємо +20 балів (простий варіант, без блокування повторів)
                        add_score(user_id, 20)
                        await update.message.reply_text("🏆 Ти пройшов тему з результатом ≥70%! +20 балів 🎉")
            except Exception as e:
                # Безпечний fallback, щоб не ламати потік
                # Можеш залогувати e, якщо потрібно
                pass

            solving_state.pop(user_id, None)

        return

async def handle_dont_know(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in solving_state:
        state = solving_state[user_id]
        task = state.get("current_task")
        await update.message.reply_text(
            f"🤔 Обрано варіант 'Не знаю'.\n⚠️ Бали за цю задачу не нараховано.\n\n📖 Пояснення: {task['explanation'].strip() if task['explanation'] else 'Пояснення відсутнє!'}"
        )

        # --- streak & бонуси за безперервні дні (рахуємо як активність)
        streak, bonus = update_streak_and_reward(user_id)
        if bonus > 0:
            await update.message.reply_text(
                f"🔥 Серія: {streak} дні(в) підряд! Бонус +{bonus} балів."
            )


        mark_task_completed(user_id, task["id"])
        state["current"] += 1
        if state["current"] < len(state["task_ids"]):
            is_daily = state.get("is_daily", False)
            if is_daily:
                await update.message.reply_text(
                    "🎉 Вітаю! Ви виконали щоденну задачу!",
                    reply_markup=ReplyKeyboardMarkup([[KeyboardButton("↩️ Меню")]], resize_keyboard=True)
                )
                solving_state.pop(user_id, None)
                return
            await send_next_task(update, context, user_id)
        else:
            # кінець списку задач
            is_daily = state.get("is_daily", False)
            if is_daily:
                await update.message.reply_text(
                    "🎯 Щоденна задача завершена.\n"
                    "⚠️ За цю задачу бали не нараховано.",
                    reply_markup=ReplyKeyboardMarkup([[KeyboardButton("↩️ Меню")]], resize_keyboard=True)
                )
                solving_state.pop(user_id, None)
                return

            # --- звичайні (не daily) задачі: стандартне завершення рівня ---
            topic = state["topic"]
            current_level = state["level"]
            available_levels = get_available_levels_for_topic(topic, exclude_level=current_level)

            keyboard = []
            if available_levels:
                keyboard.append([KeyboardButton(lvl) for lvl in available_levels])
            keyboard.append([KeyboardButton("Змінити тему")])
            keyboard.append([KeyboardButton("↩️ Меню")])

            await update.message.reply_text(
                f"🎉 Вітаю! Ви завершили всі задачі рівня «{current_level}».\n"
                "Оберіть інший рівень або змініть тему, або поверніться в меню.",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
            solving_state.pop(user_id, None)


        return



async def main_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    username = update.effective_user.username or ""
    if username:
        update_user(user_id, "username", username)

    if text == "🧠 Почати задачу":
        await update.message.reply_text("Оберіть категорію:", reply_markup=build_category_keyboard())
        start_task_state[user_id] = {"step": "category"}
        return


    if text == "✏️ Змінити імʼя в рейтингу":
        change_name_state[user_id] = True
        await update.message.reply_text(
            "Введіть нове імʼя (2-20 символів):",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Скасувати")]], resize_keyboard=True)
        )
        return

    if change_name_state.get(user_id):
        if text == "❌ Скасувати":
            del change_name_state[user_id]
            await update.message.reply_text(
                "Скасовано. Ви у головному меню.",
                reply_markup=build_main_menu(user_id)
            )
            return
        new_name = text.strip()
        if not (2 <= len(new_name) <= 20):
            await update.message.reply_text("Імʼя повинно бути від 2 до 20 символів. Спробуйте ще раз:")
            return
        update_user(user_id, "display_name", new_name)
        del change_name_state[user_id]
        await update.message.reply_text(
            f"✅ Ваше імʼя в рейтингу оновлено: <b>{new_name}</b>",
            parse_mode="HTML"
        )
        # Одразу показуємо рейтинг
        await show_rating(update, context)
        return

    # if text == "📚 Матеріали":
    #     msg = "<b>Матеріали для підготовки до НМТ:</b>\n\n"
    #     for m in MATERIALS:
    #         msg += f"🔗 <a href='{m['url']}'>{m['title']}</a>\n"
    #     await update.message.reply_text(
    #         msg,
    #         parse_mode="HTML",
    #         disable_web_page_preview=False
    #     )
    #     return

    if text == "📚 Матеріали":
        buttons = [
            [InlineKeyboardButton(m["title"], url=m["url"])] for m in MATERIALS
        ]
        await update.message.reply_text(
            "Оберіть матеріал для перегляду:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    if text in LEVELS and user_id not in start_task_state:
        # Хоче пройти інший рівень — запускаємо збереження стану та handle_task_step
        start_task_state[user_id] = {"step": "level"}
        await handle_task_step(update, context)
        return
    if text == "Змінити тему":
        await task_entrypoint(update, context)
        return
    
    if text == "↩️ Меню":
        solving_state.pop(user_id, None)  # На всякий випадок очищуємо стан
        await update.message.reply_text(
            "📍 Головне меню:",
            reply_markup=build_main_menu(user_id)
        )
        return


    if text == "↩️ Назад":
        last_menu = user_last_menu.get(user_id)
        if last_menu in ("badges", "rating"):
            await show_progress(update, context)
            user_last_menu[user_id] = "progress"  # повертаємось до прогресу
        else:
            await update.message.reply_text(
                "📍 Головне меню:",
                reply_markup=build_main_menu(user_id)
            )
        return

    if text == "📊 Мій прогрес":
        await show_progress(update, context)
        return

    if text == "🛒 Бонуси / Бейджі":
        await show_badges(update, context)
        return
    
    if text == "🏆 Рейтинг":
        await show_rating(update, context)
        return


    if text == "↩️ Назад":
        await update.message.reply_text(
            "📍 Головне меню:",
            reply_markup=build_main_menu(user_id)
        )
        return


    # --- 1. Допомога та FAQ ---
    if text == "❓ Допомога / Зв’язок":
        keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton("💬 Написати розробнику")], [KeyboardButton("↩️ Назад")]],
            resize_keyboard=True
        )
        await update.message.reply_text(
            HELP_TEXT,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        return

    # --- 2. Користувач натиснув "Написати розробнику" ---
    if text == "💬 Написати розробнику":
        feedback_state[user_id] = True
        await update.message.reply_text(
            "✉️ Напишіть ваше звернення чи питання. Ми отримаємо його в адмінці.\n\nЩоб скасувати — натисніть ❌ Скасувати.",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Скасувати")]], resize_keyboard=True)
        )
        return

    # --- 3. Якщо користувач у стані написання звернення ---
    if user_id in feedback_state:
        if text == "❌ Скасувати":
            del feedback_state[user_id]
            await update.message.reply_text(
                "Скасовано. Ви у головному меню.",
                reply_markup=build_main_menu(user_id)
            )
            return
        add_feedback(user_id, username, text)
        del feedback_state[user_id]
        await update.message.reply_text(
            "✅ Ваше повідомлення відправлено адміністратору!",
            reply_markup=build_main_menu(user_id)
        )
        return

    if text == "🧠 Почати задачу":
        await task_entrypoint(update, context)
        return

    if text == "📊 Мій прогрес":
        await show_progress(update, context)
        return

    if user_id in start_task_state:
        await handle_task_step(update, context)
        return

    if text == "❓ Не знаю" and user_id in solving_state:
        await handle_dont_know(update, context)
        return

    if user_id in solving_state:
        await handle_task_answer(update, context)
        return


    if text == "🔁 Щоденна задача":
        await handle_daily_task(update, context)
        return

    if text == "❓ Допомога / Зв’язок":
        # FAQ + кнопка для зв’язку
        keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton("💬 Написати розробнику")], [KeyboardButton("↩️ Назад")]],
            resize_keyboard=True
        )
        await update.message.reply_text(
            HELP_TEXT,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        return

    # Обробка кнопки "Написати розробнику"
    if text == "💬 Написати розробнику":
        await update.message.reply_text(
            "Напишіть розробнику у Telegram: @ostapsalo",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("↩️ Назад")]], resize_keyboard=True
            ),
            disable_web_page_preview=True
        )
        return

    # Повернення до головного меню
    if text == "↩️ Назад":
        await update.message.reply_text(
            "📍 Головне меню:",
            reply_markup=build_main_menu(user_id)
        )
        return
    
def build_topic_keyboard(topics=None):
    if topics is None:
        topics = get_all_topics()
    if not topics:
        return ReplyKeyboardMarkup([[KeyboardButton("❌ Немає тем")]], resize_keyboard=True)
    return ReplyKeyboardMarkup(
        [[KeyboardButton(t)] for t in topics] + [[KeyboardButton("↩️ Назад")]],
        resize_keyboard=True
    )
