import random
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

# Import handlers and utility functions
from handlers.progress import show_progress, show_rating
from handlers.daily import handle_daily_task
from handlers.badges import show_badges, BADGES_LIST # Import BADGES_LIST for emoji lookup if needed elsewhere
from handlers.materials import MATERIALS
from handlers.scoring import calc_points
from handlers.utils import (
    build_main_menu,
    build_category_keyboard,
    build_back_to_menu_keyboard,
    build_topics_keyboard,
    CATEGORIES,
    LEVELS,
)

# Import database functions
from db import (
    get_all_topics,
    get_all_tasks_by_topic,
    get_user_field,
    get_random_task,
    update_user, # Specific import
    all_tasks_completed,
    mark_task_completed,
    add_score,
    add_feedback,
    get_available_levels_for_topic,
    get_all_topics_by_category,
    get_completed_task_ids,
    update_streak_and_reward, # Specific import
    get_user_completed_count,
    get_topic_streak, set_topic_streak, inc_topic_streak, reset_topic_streak,
    has_topic_streak_award, mark_topic_streak_award,
    get_task_by_id
)

# --- Logging Setup ---
logger = logging.getLogger(__name__)
# Ensure basicConfig is called only once, preferably in bot.py
# If not configured in bot.py, uncomment the following lines:
# if not logger.hasHandlers():
#     logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# --- End Logging Setup ---


# --- Sticker IDs (REPLACE WITH YOUR IDs!) ---
CORRECT_ANSWER_STICKERS = [
    'CAACAgIAAxkBAAE8-mho_hXgh17wWlhWeous-iyLoT5aHgACQFEAAmzrEUnELY0xrlcN9jYE', # Example ID
    # Add more correct sticker file_ids here
]

INCORRECT_ANSWER_STICKERS = [
    'CAACAgIAAxkBAAE8-qpo_h2pUHpZ_6n71bovF1-47kenYQAC9V8AAupQEUkloO6Sc3Q4bTYE', # Example ID
    # Add more incorrect sticker file_ids here
]
# --------------------

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

# --- Keyboard Builders ---
def build_task_keyboard():
    """Builds the keyboard with 'Don't know' and 'Menu' buttons."""
    return ReplyKeyboardMarkup(
        [[KeyboardButton("↩️ Меню"), KeyboardButton("❓ Не знаю")]],
        resize_keyboard=True
    )

def build_level_keyboard(levels):
    """Builds the keyboard for selecting difficulty levels, including a back button."""
    buttons = [[KeyboardButton(lvl)] for lvl in levels]
    return ReplyKeyboardMarkup(buttons + [[KeyboardButton("↩️ Назад до тем")]], resize_keyboard=True)
# --- End Keyboard Builders ---

async def task_entrypoint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the start of the task selection process (shows categories)."""
    await update.message.reply_text("📁 Оберіть категорію (Алгебра чи Геометрія):", reply_markup=build_category_keyboard())
    context.user_data['start_task_state'] = {"step": "category"}


async def handle_task_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the multi-step process of selecting a task (category -> topic -> level)."""
    user_id = update.effective_user.id
    text = update.message.text

    if 'start_task_state' in context.user_data:
        state = context.user_data['start_task_state']
        category = state.get("category")

        # --- Step: Category Selection ---
        if state["step"] == "category" and text in CATEGORIES:
            state["category"] = text
            topics = get_all_topics_by_category(text)
            if not topics:
                await update.message.reply_text(
                    f"📂 У категорії '{text}' поки що немає тем. Оберіть іншу або поверніться в меню.",
                    reply_markup=build_back_to_menu_keyboard()
                )
                return
            state["step"] = "topic"
            await update.message.reply_text(f"📖 Чудово! Тепер обери конкретну тему з розділу '{text}':", reply_markup=build_topics_keyboard(topics + ["↩️ Назад"]))
            return

        # --- Step: Back from Topic to Category ---
        if state["step"] == "topic" and text == "↩️ Назад":
            state["step"] = "category"
            await update.message.reply_text(
                "📁 Оберіть категорію (Алгебра чи Геометрія):",
                reply_markup=build_category_keyboard()
            )
            return

        # --- Step: Topic Selection ---
        current_topics = get_all_topics_by_category(category) if category else get_all_topics()
        if state["step"] == "topic" and text in current_topics:
            tasks_in_topic = get_all_tasks_by_topic(text) # Check if tasks exist first
            available_levels = {t["level"] for t in tasks_in_topic if t.get("level")}
            state["available_levels"] = sorted(list(available_levels)) # Store levels

            if not available_levels: # Check if levels were found
                await update.message.reply_text(f"❌ Для теми '{text}' ще немає задач з рівнями складності. Спробуйте іншу.")
                await update.message.reply_text("📚 Вибери іншу тему:", reply_markup=build_topics_keyboard(current_topics + ["↩️ Назад"]))
                return

            update_user(user_id, "topic", text)
            state["step"] = "level"
            await update.message.reply_text(
                f"✅ Тема <b>{text}</b> обрана!\n🎯 Тепер визнач рівень складності:",
                reply_markup=build_level_keyboard(state["available_levels"]),
                parse_mode=ParseMode.HTML
            )
            return

        # --- Step: Back from Level to Topic ---
        if state["step"] == "level" and text == "↩️ Назад до тем":
            state["step"] = "topic"
            topics_for_back = get_all_topics_by_category(category) if category else get_all_topics()
            await update.message.reply_text(f"📖 Обери тему з розділу '{category or 'всіх тем'}':", reply_markup=build_topics_keyboard(topics_for_back + ["↩️ Назад"]))
            return

        # --- Step: Level Selection & Start Task Session ---
        elif state["step"] == "level" and text in LEVELS:
            topic = get_user_field(user_id, "topic")
            if not topic:
                logger.error(f"User {user_id}: Topic not found when selecting level '{text}'.")
                await update.message.reply_text("Помилка: не вдалося знайти обрану тему. Почніть спочатку.", reply_markup=build_main_menu(user_id))
                context.user_data.pop('start_task_state', None)
                return

            all_tasks_in_topic = get_all_tasks_by_topic(topic) # Get all tasks for the topic
            level_tasks = [t for t in all_tasks_in_topic if t.get("level") == text]

            if not level_tasks:
                await update.message.reply_text(
                    f"🤷‍♂️ На рівні «{text}» для теми «{topic}» ще немає задач. Спробуй інший рівень.",
                    reply_markup=build_level_keyboard(state.get("available_levels", [])) # Offer other levels from state
                )
                return # Stay on level selection

            # Determine tasks to solve (new ones first)
            completed_ids = set(get_completed_task_ids(user_id, topic, text))
            uncompleted_tasks = [t for t in level_tasks if t["id"] not in completed_ids]
            tasks_to_solve = uncompleted_tasks if uncompleted_tasks else level_tasks # Repeat if no new tasks
            reply_text = (f"🚀 Поїхали! Тема: <b>{topic}</b> ({text}).\nНових задач у черзі: {len(tasks_to_solve)}"
                          if uncompleted_tasks else
                          f"👍 Ти вже профі у темі <b>{topic}</b> ({text})!\nЗапускаю <b>повторне коло</b> ({len(tasks_to_solve)} задач, без балів).")

            if not tasks_to_solve:
                await update.message.reply_text(f"❌ Не знайдено задач для теми '{topic}' рівня '{text}'.", reply_markup=build_main_menu(user_id))
                context.user_data.pop('start_task_state', None)
                return
            
            is_repeat_session = not uncompleted_tasks

            await update.message.reply_text(reply_text, parse_mode=ParseMode.HTML)

            # Store solving state
            context.user_data['solving_state'] = {
                "topic": topic,
                "level": text,
                "task_ids": [t["id"] for t in tasks_to_solve],
                "completed_ids": completed_ids,
                "current": 0,
                "total_tasks": len(tasks_to_solve),
                "is_repeat": is_repeat_session
            }

            await send_next_task(update, context, user_id)
            context.user_data.pop('start_task_state', None) # Clean up start state
            return

# --- Sends the task card ---
async def send_next_task(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id):
    """Sends the next task in the current solving session."""
    if 'solving_state' not in context.user_data: return
    state = context.user_data['solving_state']
    idx = state["current"]

    # Check index bounds
    if idx >= len(state["task_ids"]):
        logger.warning(f"User {user_id}: Task index {idx} out of bounds ({len(state['task_ids'])}). Ending session.")
        await update.message.reply_text("Здається, завдання скінчилися. Повертаю в меню.", reply_markup=build_main_menu(user_id))
        context.user_data.pop('solving_state', None)
        return

    task_id_to_fetch = state["task_ids"][idx]
    task = get_task_by_id(task_id_to_fetch)

    # Handle case where task is not found in DB
    if not task:
        logger.error(f"User {user_id}: Task with ID {task_id_to_fetch} not found in DB. Skipping.")
        await update.message.reply_text(" przepraszam, nie mogę znaleźć tego zadania w bazie danych. pomijanie...", reply_markup=build_main_menu(user_id))
        state["current"] += 1 # Skip this task index
        # Check if there are more tasks or end session
        if state["current"] < state.get("total_tasks", 0):
            await send_next_task(update, context, user_id)
        else:
            context.user_data.pop('solving_state', None)
            await update.message.reply_text("Завдання завершено.", reply_markup=build_main_menu(user_id))
        return

    state["current_task"] = task # Store current task details in state
    already_done = task["id"] in (state.get("completed_ids") or set())

    # --- Format Task Message ---
    header = f"🧠 <b>Тема: {task.get('topic', 'N/A')} ({task.get('level', 'N/A')})</b>"
    counter = f"Завдання {idx + 1} з {state.get('total_tasks', '?')}"
    task_body = task.get('question', 'Текст завдання відсутній.')
    streak_info = ""

    if not state.get("is_daily", False): # Only show topic streak for normal tasks
        try:
            current_topic = state.get("topic", "")
            if current_topic: # Check if topic exists
                 cur_streak = get_topic_streak(user_id, current_topic)
                 if cur_streak > 0 and not already_done:
                     streak_info = f"🔥 Серія правильних в темі: <b>{cur_streak}</b>"
        except Exception as e:
            logger.warning(f"User {user_id}: Failed to get topic streak for '{state.get('topic')}': {e}")

    if already_done:
        streak_info = "🔁 Повторне проходження (без балів)"

    task_text = f"{header}\n<i>{counter}</i>\n\n📝 <b>Завдання:</b>\n{task_body}\n\n"
    if streak_info:
        task_text += f"<i>{streak_info}</i>"
    # --- End Format Task Message ---

    kb = build_task_keyboard() # Use the function

    # --- Send Task ---
    try:
        if task.get("photo"):
            await update.message.reply_photo(
                task["photo"], caption=task_text, reply_markup=kb, parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text(task_text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except Exception as send_err:
        logger.error(f"User {user_id}: Failed to send task {task.get('id')}: {send_err}", exc_info=True)
        await update.message.reply_text("Ой, сталася помилка при відправці завдання. Спробуйте /start", reply_markup=build_main_menu(user_id))
        context.user_data.pop('solving_state', None) # Clear state on send error
    # --- End Send Task ---

# --- Handles user's answer ---
async def handle_task_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the user's text answer to a task."""
    user_id = update.effective_user.id
    text = update.message.text

    if 'solving_state' in context.user_data:
        state = context.user_data['solving_state']
        task = state.get("current_task")

        if not task:
            logger.warning(f"User {user_id}: Answered when no current task in state.")
            await update.message.reply_text("Щось пішло не так зі станом задачі. Повертаю в меню.", reply_markup=build_main_menu(user_id))
            context.user_data.pop('solving_state', None)
            return

        # Handle 'Menu' button press during solving
        if text == "↩️ Меню":
            context.user_data.pop('solving_state', None)
            await update.message.reply_text("📍 Головне меню:", reply_markup=build_main_menu(user_id))
            return

        # --- Process Answer ---
        explanation = task.get("explanation", "").strip() or "<i>Пояснення відсутнє.</i>"
        user_answers = [a.strip() for a in text.replace(';', ',').split(',') if a.strip()]
        correct_answers = [str(a).strip() for a in task.get("answer", [])]
        task_type = (task.get("task_type") or "").lower()

        is_correct = False
        match_correct = 0
        try:
            user_answers_set = set(user_answers)
            correct_answers_set = set(correct_answers)
            if task_type == "match":
                 match_correct = len(user_answers_set & correct_answers_set)
                 is_correct = (match_correct == len(correct_answers_set) and len(user_answers_set) == len(correct_answers_set))
            else:
                 is_correct = (len(user_answers_set) == len(correct_answers_set) and user_answers_set == correct_answers_set)
        except Exception as e:
            logger.error(f"User {user_id}: Error comparing answers for task {task.get('id')}: {e}", exc_info=True)
            is_correct = False # Default to incorrect on error

        already_done = task["id"] in (state.get("completed_ids", set()))
        is_daily = state.get("is_daily", False)

        # Calculate score (only if not a repeat)
        delta = 0
        if not already_done:
            try:
                # Pass is_daily correctly
                delta = calc_points(task, is_correct=is_correct, match_correct=match_correct)
            except Exception as score_err:
                 logger.error(f"User {user_id}: Error in calc_points for task {task.get('id')}: {score_err}", exc_info=True)

        # Add score if earned
        if delta > 0:
            try:
                add_score(user_id, delta)
            except Exception as add_score_err:
                logger.error(f"User {user_id}: Failed to add score {delta}: {add_score_err}", exc_info=True)
        # --- End Process Answer ---

        # --- Format response message ---
        msg = ""
        user_answer_str = ', '.join(user_answers) if user_answers else "<i>(відповідь не надано)</i>"
        correct_answer_str = ', '.join(correct_answers) if correct_answers else "<i>(немає)</i>"

        if is_correct:
            if already_done:
                msg += "✅ <b>Правильно!</b> (повтор)\n<i>Бали за повторне проходження не нараховуються.</i>"
            else:
                msg += f"✅ <b>Правильно!</b>\n"
                if delta > 0:
                    msg += f"💰 Нараховано: <code>+{delta} балів</code> 🎉"
                else:
                    msg += "<i>Бали за це завдання не передбачені.</i>"
        else: # Incorrect
            msg += "❌ <b>Неправильно.</b>\n"
            msg += f"   - <i>Ваша відповідь:</i> <code>{user_answer_str}</code>\n"
            msg += f"   - <i>Правильна відповідь:</i> <code>{correct_answer_str}</code>\n"
            msg += "<i>Бали за цю задачу не нараховано.</i>"

        msg += f"\n\n📖 <b>Пояснення:</b>\n{explanation}"
        # --- End response message formatting ---

        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

        # --- Send Sticker ---
        sticker_to_send = None
        if is_correct and CORRECT_ANSWER_STICKERS:
            sticker_to_send = random.choice(CORRECT_ANSWER_STICKERS)
        elif not is_correct and INCORRECT_ANSWER_STICKERS:
            sticker_to_send = random.choice(INCORRECT_ANSWER_STICKERS)

        if sticker_to_send:
            try:
                await context.bot.send_sticker(chat_id=user_id, sticker=sticker_to_send)
            except Exception as e:
                logger.warning(f"Could not send sticker {sticker_to_send} to user {user_id}: {e}")
        # --- End Send Sticker ---

        # --- Mark task completed and update state FIRST ---
        was_inserted = mark_task_completed(user_id, task["id"])
        if was_inserted:
            state.get("completed_ids", set()).add(task["id"])
        # --- End Mark Task ---

        # --- Update Streaks and Bonuses (handle errors gracefully) ---
        try:
            topic = state.get("topic")
            # Only update topic streaks/bonuses for NEWLY completed NON-DAILY tasks
            if topic and not is_daily and was_inserted:
                if is_correct:
                    # Increment topic streak
                    new_streak = inc_topic_streak(user_id, topic)
                    # Check topic streak milestones
                    awarded_msgs = []
                    TOPIC_STREAK_MILESTONES = {5: 5, 10: 10, 15: 25, 20: 40, 30: 60}
                    for m in sorted(TOPIC_STREAK_MILESTONES):
                        bonus = TOPIC_STREAK_MILESTONES[m]
                        if new_streak >= m and not has_topic_streak_award(user_id, topic, m):
                            add_score(user_id, bonus)
                            mark_topic_streak_award(user_id, topic, m)
                            awarded_msgs.append(f"🏅 Серія {m} правильних у темі «{topic}»! +{bonus} балів")
                    if awarded_msgs:
                        await update.message.reply_text("\n".join(awarded_msgs))

                    # Check 70% topic completion bonus (now safe to recalculate)
                    total_in_topic = len(get_all_tasks_by_topic(topic)) # Recount total non-daily tasks
                    completed_in_topic = sum(get_user_completed_count(user_id, topic, lvl) for lvl in LEVELS) # Recount completed non-daily
                    if total_in_topic > 0:
                        percent_now = completed_in_topic / total_in_topic
                        if percent_now >= 0.70 and not has_topic_streak_award(user_id, topic, 70):
                            add_score(user_id, 20)
                            mark_topic_streak_award(user_id, topic, 70)
                            await update.message.reply_text("🏆 Ти пройшов(ла) тему з результатом ≥70%! +20 балів 🎉")
                else: # Incorrect answer for new non-daily task
                     reset_topic_streak(user_id, topic)

        except Exception as e:
            logger.error(f"Error updating topic streaks/bonuses for user {user_id}, task {task.get('id')}: {e}", exc_info=True)

        # Update daily streak (always happens on activity)
        try:
            streak, bonus = update_streak_and_reward(user_id)
            if bonus > 0:
                await update.message.reply_text(
                    f"🔥 Серія: {streak} дні(в) підряд! Бонус +{bonus} балів."
                )
        except Exception as e:
            logger.error(f"Error updating daily streak for user {user_id}: {e}", exc_info=True)
        # --- End Streaks/Bonuses ---

        state["current"] += 1 # Move to next task index

        # --- Proceed to next task or end session ---
        if state["current"] < state.get("total_tasks", 0):
            if is_daily: # End daily task immediately after one answer
                context.user_data.pop('solving_state', None)
                await update.message.reply_text(
                    "✅ Щоденну задачу зараховано!",
                    reply_markup=ReplyKeyboardMarkup([[KeyboardButton("↩️ Меню")]], resize_keyboard=True)
                )
                return
            else: # Go to next normal task
                await send_next_task(update, context, user_id)
        else: # End of tasks
            topic = state.get("topic", "поточну")
            current_level = state.get("level", "поточний")
            context.user_data.pop('solving_state', None) # End session state

            if is_daily:
                await update.message.reply_text(
                    "🎉 Готово! Щоденна задача на сьогодні виконана.\nПовернись завтра по нову 💪",
                    reply_markup=ReplyKeyboardMarkup([[KeyboardButton("↩️ Меню")]], resize_keyboard=True)
                )
            else: # End of normal task session
                  available_levels = get_available_levels_for_topic(topic, exclude_level=current_level)
                  keyboard = []
                  if available_levels:
                      keyboard.append([KeyboardButton(lvl) for lvl in available_levels])
                  keyboard.append([KeyboardButton("Змінити тему")])
                  keyboard.append([KeyboardButton("↩️ Меню")])

                  # --- ОНОВЛЕНИЙ БЛОК ПОВІДОМЛЕННЯ ---
                  is_repeat = state.get("is_repeat", False) # Перевіряємо, чи це був повтор
                  if is_repeat:
                      final_message = f"👍 Чудово! Ти завершив(ла) <b>повторне проходження</b> рівня «{current_level}» по темі «{topic}»."
                  else:
                      final_message = f"🎉 Вітаю! Ти завершив(ла) <b>усі нові завдання</b> рівня «{current_level}» по темі «{topic}»."
                  final_message += "\nМожеш спробувати інший рівень, змінити тему або повернутись у меню."
                  # --- КІНЕЦЬ ОНОВЛЕНОГО БЛОКУ ---

                  await update.message.reply_text(
                      final_message, # <-- Використовуємо нову змінну
                      reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
                      parse_mode=ParseMode.HTML # Додаємо parse_mode
                  )
        return # Important to return after handling

# --- Handles "Don't Know" button ---
async def handle_dont_know(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the '❓ Не знаю' button press during a task."""
    user_id = update.effective_user.id
    if 'solving_state' in context.user_data:
        state = context.user_data['solving_state']
        task = state.get("current_task")

        if not task:
            logger.warning(f"User {user_id}: Clicked 'Don't Know' with no current task.")
            await update.message.reply_text("Щось пішло не так. Повертаю в меню.", reply_markup=build_main_menu(user_id))
            context.user_data.pop('solving_state', None)
            return

        explanation = task.get("explanation", "").strip() or "<i>Пояснення відсутнє.</i>"
        correct_answer_str = ', '.join([str(a).strip() for a in task.get("answer", [])])

        # Format message
        msg = f"🤔 Обрано варіант 'Не знаю'.\n"
        msg += f"   - <i>Правильна відповідь:</i> <code>{correct_answer_str}</code>\n"
        msg += "<i>Бали за цю задачу не нараховано.</i>\n\n"
        msg += f"📖 <b>Пояснення:</b>\n{explanation}"

        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

        # Update daily streak (as it counts as activity)
        try:
            streak, bonus = update_streak_and_reward(user_id)
            if bonus > 0:
                await update.message.reply_text(f"🔥 Серія: {streak} дні(в) підряд! Бонус +{bonus} балів.")
        except Exception as e:
            logger.error(f"Error updating daily streak for user {user_id} (after 'Don't Know'): {e}", exc_info=True)

        # Reset topic streak if applicable (non-daily task)
        is_daily = state.get("is_daily", False)
        topic = state.get("topic")
        if topic and not is_daily:
            try:
                reset_topic_streak(user_id, topic)
            except Exception as e:
                logger.error(f"Error resetting topic streak for user {user_id} (after 'Don't Know'): {e}", exc_info=True)

        # Mark task completed (even though incorrect/skipped)
        was_inserted = mark_task_completed(user_id, task["id"])
        if was_inserted:
             state.get("completed_ids", set()).add(task["id"]) # Update state

        state["current"] += 1 # Move to next task index

        # --- Proceed or end session ---
        if state["current"] < state.get("total_tasks", 0):
            if is_daily: # End daily task session
                context.user_data.pop('solving_state', None)
                await update.message.reply_text(
                    "🎯 Щоденна задача завершена.\n⚠️ Бали не нараховано.",
                    reply_markup=ReplyKeyboardMarkup([[KeyboardButton("↩️ Меню")]], resize_keyboard=True)
                )
                return
            else: # Go to next normal task
                await send_next_task(update, context, user_id)
        else: # End of tasks
            topic = state.get("topic", "поточну")
            current_level = state.get("level", "поточний")
            context.user_data.pop('solving_state', None) # End session state
            if is_daily:
                await update.message.reply_text(
                    "🎯 Щоденна задача завершена.\n⚠️ Бали не нараховано.",
                    reply_markup=ReplyKeyboardMarkup([[KeyboardButton("↩️ Меню")]], resize_keyboard=True)
                )
            else: # End of normal session
                  available_levels = get_available_levels_for_topic(topic, exclude_level=current_level)
                  keyboard = []
                  if available_levels:
                      keyboard.append([KeyboardButton(lvl) for lvl in available_levels])
                  keyboard.append([KeyboardButton("Змінити тему")])
                  keyboard.append([KeyboardButton("↩️ Меню")])

                  # --- ОНОВЛЕНИЙ БЛОК ПОВІДОМЛЕННЯ ---
                  is_repeat = state.get("is_repeat", False) # Перевіряємо, чи це був повтор
                  if is_repeat:
                      final_message = f"🏁 Завершено <b>повторне проходження</b> рівня «{current_level}» по темі «{topic}»."
                  else:
                      final_message = f"🏁 Завершено <b>усі нові завдання</b> рівня «{current_level}» по темі «{topic}»."
                  final_message += "\nОбери інший рівень, тему або повернись у меню."
                  # --- КІНЕЦЬ ОНОВЛЕНОГО БЛОКУ ---

                  await update.message.reply_text(
                      final_message, # <-- Використовуємо нову змінну
                      reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
                      parse_mode=ParseMode.HTML # Додаємо parse_mode
                  )
        return

# --- Main Message Handler (Router for non-admin users) ---
async def main_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all text messages that are not commands and routes them."""
    user_id = update.effective_user.id
    text = update.message.text if update.message and update.message.text else ""

    # --- Update activity & username first ---
    try:
        update_streak_and_reward(user_id)
        username = update.effective_user.username or ""
        # Update username only if needed
        # current_username = get_user_field(user_id, "username") # Requires extra DB call
        # if username and username != current_username:
        if username : # Simpler approach
            update_user(user_id, "username", username)
    except Exception as e:
        logger.error(f"Error updating activity/username for {user_id}: {e}", exc_info=True)

    # --- State Handlers (priority order) ---
    if 'registration_state' in context.user_data:
        await handle_registration_step(update, context) # Use a dedicated function maybe? Assume it's handled here for now.
        return
    if context.user_data.get('change_name_state'):
        await handle_change_name_step(update, context) # Use a dedicated function maybe?
        return
    if 'feedback_state' in context.user_data:
        await handle_feedback_step(update, context) # Use a dedicated function maybe?
        return
    if 'start_task_state' in context.user_data:
        await handle_task_step(update, context)
        return
    if 'solving_state' in context.user_data:
        # Handle solving state actions (answer or 'don't know')
        if text == "❓ Не знаю":
            await handle_dont_know(update, context)
        elif text == "↩️ Меню": # Allow Menu exit from solving state
            context.user_data.pop('solving_state', None)
            await update.message.reply_text("📍 Головне меню:", reply_markup=build_main_menu(user_id))
        else: # Treat as answer
            await handle_task_answer(update, context)
        return

    # --- Main Menu Button Handlers ---
    if text == "🧠 Почати задачу": await task_entrypoint(update, context)
    elif text == "🔁 Щоденна задача": await handle_daily_task(update, context)
    elif text == "📊 Мій прогрес": await show_progress(update, context)
    elif text == "🛒 Бонуси / Бейджі": await show_badges(update, context)
    elif text == "🏆 Рейтинг": await show_rating(update, context)
    elif text == "📚 Матеріали":
        buttons = [[InlineKeyboardButton(m.get("title","Link"), url=m.get("url", "#"))] for m in MATERIALS]
        await update.message.reply_text("Оберіть матеріал:", reply_markup=InlineKeyboardMarkup(buttons))
    elif text == "❓ Допомога / Зв’язок":
        keyboard = ReplyKeyboardMarkup([[KeyboardButton("💬 Написати розробнику")], [KeyboardButton("↩️ Назад")]], resize_keyboard=True)
        await update.message.reply_text(HELP_TEXT, reply_markup=keyboard, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    elif text == "💬 Написати розробнику":
        context.user_data['feedback_state'] = True
        await update.message.reply_text("✉️ Напишіть ваше звернення...\n<i>(Натисніть '❌ Скасувати' для відміни)</i>",
                                        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Скасувати")]], resize_keyboard=True),
                                        parse_mode=ParseMode.HTML)
    elif text == "✏️ Змінити імʼя в рейтингу":
        context.user_data['change_name_state'] = True
        await update.message.reply_text("Введіть нове імʼя (2-20 символів):",
                                        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Скасувати")]], resize_keyboard=True))

    # --- Navigation Button Handlers ---
    elif text == "↩️ Меню": # General Menu button outside states
        context.user_data.clear() # Clear all states on explicit Menu return
        await update.message.reply_text("📍 Головне меню:", reply_markup=build_main_menu(user_id))
    elif text == "↩️ Назад":
        last_menu = context.user_data.get('user_last_menu')
        if last_menu in ("badges", "rating"): await show_progress(update, context) # Back to Progress
        else: await update.message.reply_text("📍 Головне меню:", reply_markup=build_main_menu(user_id)) # Default Back

    # --- Post-Level Completion Button Handlers ---
    elif text == "Змінити тему":
        await task_entrypoint(update, context) # Start category selection
    elif text in LEVELS: # User selected a new level after completing one
        current_topic = get_user_field(user_id, "topic")
        if current_topic:
            # Re-initiate start_task_state to jump back into handle_task_step
            # Try to restore category if possible (requires DB query or storing in state)
            # category = get_category_for_topic(current_topic) # Need this function in db.py
            context.user_data['start_task_state'] = {"step": "level", "topic": current_topic} # "category": category
            await handle_task_step(update, context)
        else:
            logger.warning(f"User {user_id} clicked level '{text}' post-completion, but no topic found.")
            await update.message.reply_text("Спочатку оберіть тему.", reply_markup=build_main_menu(user_id))

    # --- Fallback for unknown text ---
    else:
        # Only send if no state handler should have caught it
        active_states = ['registration_state', 'change_name_state', 'feedback_state', 'start_task_state', 'solving_state']
        if not any(state in context.user_data for state in active_states):
            logger.info(f"User {user_id}: Unknown command/text: '{text}'")
            await update.message.reply_text(
                "Не зовсім зрозумів команду 🤔. Скористайтесь кнопками меню.",
                reply_markup=build_main_menu(user_id)
            )

# --- Helper functions for state handling (extracted from main_message_handler for clarity) ---
async def handle_registration_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles steps for user registration."""
    user_id = update.effective_user.id
    text = update.message.text
    state = context.user_data['registration_state']

    if text == "❌ Скасувати":
        context.user_data.pop('registration_state', None)
        await update.message.reply_text("Реєстрацію скасовано.", reply_markup=build_main_menu(user_id))
        return

    if state.get("step") == "name":
        new_name = text.strip()
        if not (2 <= len(new_name) <= 20):
            await update.message.reply_text("Імʼя повинно бути від 2 до 20 символів.")
            return
        update_user(user_id, "display_name", new_name)
        state["step"] = "city"
        await update.message.reply_text(f"✅ Чудово, {new_name}!\n\n📍 Тепер вкажіть ваше місто:", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Скасувати")]], resize_keyboard=True))
        return

    elif state.get("step") == "city":
        city = text.strip()
        if not (2 <= len(city) <= 30):
             await update.message.reply_text("Назва міста: 2-30 символів.")
             return
        update_user(user_id, "city", city)
        state["step"] = "phone"
        keyboard = ReplyKeyboardMarkup([[KeyboardButton("📱 Поділитись контактом", request_contact=True)], [KeyboardButton("❌ Скасувати")]], resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(f"✅ Місто: {city}.\n\n📞 Майже готово! Поділіться контактом або введіть номер (+380...):", reply_markup=keyboard)
        return

    elif state.get("step") == "phone": # Handle text input for phone
        phone = text.strip()
        if not (phone.startswith('+') and len(phone) >= 10 and phone[1:].isdigit()):
             await update.message.reply_text("Некоректний формат (+380...).")
             return
        update_user(user_id, "phone_number", phone)
        context.user_data.pop('registration_state', None)
        await update.message.reply_text("🎉 <b>Дякуємо за реєстрацію!</b>", parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove())
        await show_rating(update, context) # Show updated rating
        return

async def handle_change_name_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles steps for changing display name."""
    user_id = update.effective_user.id
    text = update.message.text

    if text == "❌ Скасувати":
        context.user_data.pop('change_name_state', None)
        await update.message.reply_text("Скасовано.", reply_markup=build_main_menu(user_id))
        return

    new_name = text.strip()
    if not (2 <= len(new_name) <= 20):
        await update.message.reply_text("Імʼя: 2-20 символів.")
        return

    update_user(user_id, "display_name", new_name)
    context.user_data.pop('change_name_state', None)
    await update.message.reply_text(f"✅ Імʼя оновлено: <b>{new_name}</b>", parse_mode=ParseMode.HTML)
    await show_rating(update, context) # Show updated rating

async def handle_feedback_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles steps for submitting feedback."""
    user_id = update.effective_user.id
    text = update.message.text

    if text == "❌ Скасувати":
        context.user_data.pop('feedback_state', None)
        await update.message.reply_text("Скасовано.", reply_markup=build_main_menu(user_id))
        return

    username_fb = update.effective_user.username or f"id_{user_id}"
    add_feedback(user_id, username_fb, text)
    context.user_data.pop('feedback_state', None)
    await update.message.reply_text("✅ Дякуємо! Ваше повідомлення відправлено.", reply_markup=build_main_menu(user_id))

# --- Contact Handler (remains mostly the same) ---
async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles receiving a contact, usually during registration."""
    user_id = update.effective_user.id
    contact = update.message.contact if update.message else None

    if not contact:
        logger.warning(f"User {user_id}: handle_contact called without contact object.")
        return # Ignore if no contact

    # Check if we are in the registration phone step
    if context.user_data.get('registration_state') and context.user_data['registration_state'].get("step") == "phone":
        phone = contact.phone_number
        if not phone.startswith('+'): phone = '+' + phone # Ensure '+' prefix

        # Basic validation
        if not (phone.startswith('+') and len(phone) >= 10 and phone[1:].isdigit()):
            await update.message.reply_text("Ой, схоже, це некоректний номер телефону. Спробуйте ввести вручну у форматі +380...")
            # Keep user on the phone step, don't pop state
            return

        update_user(user_id, "phone_number", phone)
        context.user_data.pop('registration_state', None) # End registration

        # Remove the special keyboard after receiving contact
        await update.message.reply_text(
            "🎉 <b>Дякуємо за реєстрацію!</b>\n\nВаші дані збережено.",
            parse_mode=ParseMode.HTML,
            reply_markup=ReplyKeyboardRemove() # Remove the "Share Contact" keyboard
        )
        # Show rating immediately after successful registration
        await show_rating(update, context)
        return
    else:
        # If contact received unexpectedly
        logger.info(f"User {user_id}: Sent unexpected contact.")
        await update.message.reply_text(
            "Дякую за контакт, але зараз я його не очікував.",
            reply_markup=build_main_menu(user_id)
        )