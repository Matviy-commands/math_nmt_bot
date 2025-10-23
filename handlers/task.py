from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from handlers.progress import show_progress, show_rating
from handlers.daily import handle_daily_task
from handlers.badges import show_badges
from handlers.materials import MATERIALS
from handlers.scoring import calc_points
from db import update_streak_and_reward, update_user

from handlers.utils import (
    build_main_menu,
    build_category_keyboard,
    build_back_to_menu_keyboard,
    build_topics_keyboard,
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

def build_task_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("❓ Не знаю")]], resize_keyboard=True)

def build_level_keyboard(levels):
    buttons = [[KeyboardButton(lvl)] for lvl in levels]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

async def task_entrypoint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topics = get_all_topics()
    if not topics:
        await update.message.reply_text("❌ Зараз у базі немає жодної теми із задачами.")
        return
    # <-- ВИПРАВЛЕНО: 'build_topics_keyboard' і додано "Назад"
    await update.message.reply_text("Оберіть тему:", reply_markup=build_topics_keyboard(topics + ["↩️ Назад"]))
    context.user_data['start_task_state'] = {"step": "topic"}

async def handle_task_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if 'start_task_state' in context.user_data:
        state = context.user_data['start_task_state']

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
             # <-- ВИПРАВЛЕНО: 'build_topics_keyboard' і додано "Назад"
            await update.message.reply_text("Оберіть тему:", reply_markup=build_topics_keyboard(topics + ["↩️ Назад"]))
            return
        
        if state["step"] == "topic" and text == "↩️ Назад":
            state["step"] = "category"
            await update.message.reply_text(
                "Оберіть категорію:",
                reply_markup=build_category_keyboard()
            )
            return

        topics = get_all_topics()
        if state["step"] == "topic" and text in topics:
            available_levels = set([t["level"] for t in get_all_tasks_by_topic(text)])
            if not available_levels:
                await update.message.reply_text("❌ Для цієї теми немає жодної задачі.")
                context.user_data.pop('start_task_state', None)
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
            all_tasks = get_all_tasks_by_topic(topic)
            level_tasks = [t for t in all_tasks if t["level"] == text]
            if not level_tasks:
                await update.message.reply_text(
                    f"❌ Для рівня «{text}» задач немає!",
                    reply_markup=build_main_menu(user_id)
                )
                context.user_data.pop('start_task_state', None)
                return

            completed_ids = set(get_completed_task_ids(user_id, topic, text))
            
            uncompleted_tasks = [t for t in level_tasks if t["id"] not in completed_ids]

            tasks_to_solve = []
            reply_text = ""

            if uncompleted_tasks:
                tasks_to_solve = uncompleted_tasks
                reply_text = f"✅ Тема: {topic} ({text}). Починаємо! Задач у черзі: {len(tasks_to_solve)}"
            else:
                tasks_to_solve = level_tasks
                reply_text = f"👍 Ти вже все вирішив у цій темі! Запускаю повторне коло (без балів)."

            if not tasks_to_solve:
                await update.message.reply_text(
                    f"❌ Для рівня «{text}» дивним чином не знайшлось задач.",
                    reply_markup=build_main_menu(user_id)
                )
                context.user_data.pop('start_task_state', None)
                return

            await update.message.reply_text(reply_text) 

            context.user_data['solving_state'] = {
                "topic": topic,
                "level": text,
                "task_ids": [t["id"] for t in tasks_to_solve],
                "completed_ids": completed_ids,
                "current": 0,
            }

            await send_next_task(update, context, user_id)
            context.user_data.pop('start_task_state', None)
            return

async def send_next_task(update, context, user_id):
    state = context.user_data['solving_state']
    idx = state["current"]
    task_id = state["task_ids"][idx]
    from db import get_task_by_id
    task = get_task_by_id(task_id)
    already_done = task_id in (state.get("completed_ids") or set())
    state["current_task"] = task
    
    kb = ReplyKeyboardMarkup(
        [[KeyboardButton("↩️ Меню"), KeyboardButton("❓ Не знаю")]], resize_keyboard=True)
    task_text = f"📘 {task['topic']} ({task['level']})\n\n{task['question']}"

    try:
        cur_streak = get_topic_streak(user_id, state["topic"])
        if cur_streak > 0:
            task_text = f"🔥 Серія в темі: {cur_streak}\n\n" + task_text
    except Exception:
        pass

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

    if 'solving_state' in context.user_data:
        state = context.user_data['solving_state']
        task = state.get("current_task")
        if text == "↩️ Меню":
            context.user_data.pop('solving_state', None)
            await update.message.reply_text(
                "📍 Головне меню:",
                reply_markup=build_main_menu(user_id)
            )
            return
        explanation = task["explanation"].strip() if task["explanation"] else "Пояснення відсутнє!"

        user_answers = [a.strip() for a in text.replace(';', ',').split(',') if a.strip()]
        correct_answers = [a.strip() for a in task["answer"]]
        task_type = (task.get("task_type") or "").lower()

        if task_type == "match":
            match_correct = len(set(user_answers) & set(correct_answers))
            is_correct = (match_correct == len(correct_answers))
        else:
            match_correct = 0
            is_correct = (
                len(user_answers) == len(correct_answers) and
                set(user_answers) == set(correct_answers)
            )

        already_done = task["id"] in (state.get("completed_ids") or set())

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

        try:
            topic = state["topic"]
            is_daily = state.get("is_daily", False)

            if (not is_daily) and is_correct and not already_done:
                total_in_topic = len(get_all_tasks_by_topic(topic))
                completed_in_topic = sum(
                    get_user_completed_count(user_id, topic, lvl)
                    for lvl in {"легкий", "середній", "важкий"}
                )
                completed_after = completed_in_topic + 1

                if total_in_topic > 0:
                    percent_after = completed_after / total_in_topic
                    if percent_after >= 0.70 and not has_topic_streak_award(user_id, topic, 70):
                        add_score(user_id, 20)
                        mark_topic_streak_award(user_id, topic, 70)
                        await update.message.reply_text("🏆 Ти пройшов тему з результатом ≥70%! +20 балів 🎉")
        except Exception:
            pass
        
        topic = state["topic"]
        is_daily = state.get("is_daily", False)
        TOPIC_STREAK_MILESTONES = {5: 5, 10: 10, 15: 25, 20: 40, 30: 60}

        if not is_daily:
            if is_correct and not already_done:
                new_streak = inc_topic_streak(user_id, topic)
                awarded_msgs = []
                for m in sorted(TOPIC_STREAK_MILESTONES):
                    bonus = TOPIC_STREAK_MILESTONES[m]
                    if new_streak >= m and not has_topic_streak_award(user_id, topic, m):
                        add_score(user_id, bonus)
                        mark_topic_streak_award(user_id, topic, m)
                        awarded_msgs.append(f"🏅 Серія {m} правильних у темі «{topic}»! +{bonus} балів")

                if awarded_msgs:
                    await update.message.reply_text("\n".join(awarded_msgs))
            elif not is_correct:
                reset_topic_streak(user_id, topic)
        
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
                if is_correct:
                    # add_score(user_id, 5)
                    await update.message.reply_text(
                        "🎉 Вітаю! Щоденну задачу виконано!",
                        # "🎉 Вітаю! Щоденну задачу виконано! +5 бонусних балів.",
                        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("↩️ Меню")]], resize_keyboard=True)
                    )
                else:
                    await update.message.reply_text(
                        "✅ Щоденна задача зарахована. Бали не нараховано, але серію днів продовжено!",
                        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("↩️ Меню")]], resize_keyboard=True)
                    )
                context.user_data.pop('solving_state', None)
                return

            await send_next_task(update, context, user_id)
        else:
            is_daily = state.get("is_daily", False)
            if is_daily:
                if is_correct:
                    # add_score(user_id, 5)
                    await update.message.reply_text(
                        "🎉 Готово! Щоденна задача на сьогодні виконана.\n"
                        "Повернись завтра по нову 💪",
                        # "🎉 Готово! Щоденна задача на сьогодні виконана. +5 бонусних балів.\n"
                        # "Повернись завтра по нову 💪",
                        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("↩️ Меню")]], resize_keyboard=True)
                    )
                else:
                     await update.message.reply_text(
                        "✅ Готово! Щоденна задача на сьогодні виконана. Бали не нараховано.\n"
                        "Повернись завтра по нову 💪",
                        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("↩️ Меню")]], resize_keyboard=True)
                    )
                context.user_data.pop('solving_state', None)
                return

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

            context.user_data.pop('solving_state', None)

        return

async def handle_dont_know(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if 'solving_state' in context.user_data:
        state = context.user_data['solving_state']
        task = state.get("current_task")
        await update.message.reply_text(
            f"🤔 Обрано варіант 'Не знаю'.\n⚠️ Бали за цю задачу не нараховано.\n\n📖 Пояснення: {task['explanation'].strip() if task['explanation'] else 'Пояснення відсутнє!'}"
        )

        streak, bonus = update_streak_and_reward(user_id)
        if bonus > 0:
            await update.message.reply_text(
                f"🔥 Серія: {streak} дні(в) підряд! Бонус +{bonus} балів."
            )

        try:
            topic = state["topic"]
            is_daily = state.get("is_daily", False)
            if not is_daily:
                reset_topic_streak(user_id, topic)
        except Exception:
            pass


        mark_task_completed(user_id, task["id"])
        state["current"] += 1
        if state["current"] < len(state["task_ids"]):
            is_daily = state.get("is_daily", False)
            if is_daily:
                await update.message.reply_text(
                    "🎯 Щоденна задача завершена.\n"
                    "⚠️ За цю задачу бали не нараховано.",
                    reply_markup=ReplyKeyboardMarkup([[KeyboardButton("↩️ Меню")]], resize_keyboard=True)
                )
                context.user_data.pop('solving_state', None)
                return
            await send_next_task(update, context, user_id)
        else:
            is_daily = state.get("is_daily", False)
            if is_daily:
                await update.message.reply_text(
                    "🎯 Щоденна задача завершена.\n"
                    "⚠️ За цю задачу бали не нараховано.",
                    reply_markup=ReplyKeyboardMarkup([[KeyboardButton("↩️ Меню")]], resize_keyboard=True)
                )
                context.user_data.pop('solving_state', None)
                return

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
            context.user_data.pop('solving_state', None)

        return



async def main_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    username = update.effective_user.username or ""
    if username:
        update_user(user_id, "username", username)

    if text == "🧠 Почати задачу":
        await update.message.reply_text("Оберіть категорію:", reply_markup=build_category_keyboard())
        context.user_data['start_task_state'] = {"step": "category"}
        return


    if text == "✏️ Змінити імʼя в рейтингу":
        context.user_data['change_name_state'] = True
        await update.message.reply_text(
            "Введіть нове імʼя (2-20 символів):",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Скасувати")]], resize_keyboard=True)
        )
        return
    if 'registration_state' in context.user_data:
        state = context.user_data['registration_state']
        
        if text == "❌ Скасувати":
            context.user_data.pop('registration_state', None)
            await update.message.reply_text(
                "Реєстрацію скасовано.",
                reply_markup=build_main_menu(user_id)
            )
            return

        # Крок 1: Отримали ім'я
        if state.get("step") == "name":
            new_name = text.strip()
            if not (2 <= len(new_name) <= 20):
                await update.message.reply_text("Імʼя повинно бути від 2 до 20 символів. Спробуйте ще раз:")
                return
            
            update_user(user_id, "display_name", new_name)
            state["step"] = "city"
            await update.message.reply_text(
                f"✅ Чудово, {new_name}!\n\n"
                "📍 Тепер, будь ласка, вкажіть ваше місто (це допоможе нам у статистиці):",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Скасувати")]], resize_keyboard=True)
            )
            return

        # Крок 2: Отримали місто
        elif state.get("step") == "city":
            city = text.strip()
            if not (2 <= len(city) <= 30):
                 await update.message.reply_text("Назва міста має бути від 2 до 30 символів. Спробуйте ще раз:")
                 return
            
            update_user(user_id, "city", city)
            state["step"] = "phone"
            
            # Запитуємо телефон (з кнопкою "Поділитись контактом")
            keyboard = ReplyKeyboardMarkup(
                [[KeyboardButton("📱 Поділитись контактом", request_contact=True)], [KeyboardButton("❌ Скасувати")]],
                resize_keyboard=True, one_time_keyboard=True
            )
            await update.message.reply_text(
                f"✅ Місто: {city}.\n\n"
                "📞 Майже готово! Натисніть кнопку 'Поділитись контактом' або введіть номер вручну (у форматі +380...):",
                reply_markup=keyboard
            )
            return

        # Крок 3: Отримали телефон (або через кнопку, або текстом)
        elif state.get("step") == "phone":
            phone = ""
            if update.message.contact:
                phone = update.message.contact.phone_number
            else:
                phone = text.strip()
            
            # Проста перевірка формату
            if not (phone.startswith('+') and len(phone) >= 10 and phone[1:].isdigit()):
                 await update.message.reply_text("Некоректний формат. Будь ласка, натисніть кнопку або введіть номер у форматі +380...")
                 return

            update_user(user_id, "phone_number", phone)
            context.user_data.pop('registration_state', None)
            
            await update.message.reply_text(
                "🎉 <b>Дякуємо за реєстрацію!</b>\n\n"
                "Ваші дані успішно збережено. Тепер ви можете переглянути своє місце в рейтингу.",
                parse_mode="HTML"
            )
            # Одразу показуємо рейтинг, заради якого все почалось
            await show_rating(update, context)
            return
            
        return

    if context.user_data.get('change_name_state'):
        if text == "❌ Скасувати":
            context.user_data.pop('change_name_state', None)
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
        context.user_data.pop('change_name_state', None)
        await update.message.reply_text(
            f"✅ Ваше імʼя в рейтингу оновлено: <b>{new_name}</b>",
            parse_mode="HTML"
        )
        await show_rating(update, context)
        return

    if text == "📚 Матеріали":
        buttons = [
            [InlineKeyboardButton(m["title"], url=m["url"])] for m in MATERIALS
        ]
        await update.message.reply_text(
            "Оберіть матеріал для перегляду:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    if text in LEVELS and 'start_task_state' not in context.user_data:
        context.user_data['start_task_state'] = {"step": "level"}
        await handle_task_step(update, context)
        return
    
    if text == "Змінити тему":
        await task_entrypoint(update, context)
        return
    
    if text == "↩️ Меню":
        context.user_data.pop('solving_state', None)
        await update.message.reply_text(
            "📍 Головне меню:",
            reply_markup=build_main_menu(user_id)
        )
        return


    if text == "↩️ Назад":
        last_menu = context.user_data.get('user_last_menu')
        if last_menu in ("badges", "rating"):
            await show_progress(update, context)
            context.user_data['user_last_menu'] = "progress"
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

    if text == "💬 Написати розробнику":
        context.user_data['feedback_state'] = True
        await update.message.reply_text(
            "✉️ Напишіть ваше звернення чи питання. Ми отримаємо його в адмінці.\n\nЩоб скасувати — натисніть ❌ Скасувати.",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Скасувати")]], resize_keyboard=True)
        )
        return

    if 'feedback_state' in context.user_data:
        if text == "❌ Скасувати":
            context.user_data.pop('feedback_state', None)
            await update.message.reply_text(
                "Скасовано. Ви у головному меню.",
                reply_markup=build_main_menu(user_id)
            )
            return
        add_feedback(user_id, username, text)
        context.user_data.pop('feedback_state', None)
        await update.message.reply_text(
            "✅ Ваше повідомлення відправлено адміністратору!",
            reply_markup=build_main_menu(user_id)
        )
        return

    if text == "🔁 Щоденна задача":
        await handle_daily_task(update, context)
        return

    if 'start_task_state' in context.user_data:
        await handle_task_step(update, context)
        return

    if text == "❓ Не знаю" and 'solving_state' in context.user_data:
        await handle_dont_know(update, context)
        return

    if 'solving_state' in context.user_data:
        await handle_task_answer(update, context)
        return

    # Обробка невідомих команд або тексту
    await update.message.reply_text(
        "Незрозуміла команда. Використовуйте кнопки меню.",
        reply_markup=build_main_menu(user_id)
    )

    try:
        update_streak_and_reward(user_id)
    except Exception as e:
        print(f"[Помилка] Не вдалося оновити last_activity для {user_id}: {e}")
        
    username = update.effective_user.username or ""
    if username:
        update_user(user_id, "username", username)
