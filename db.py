import os
import psycopg2
import json
from datetime import date, timedelta
from psycopg2 import pool, InterfaceError # <-- Додано InterfaceError
import contextlib
import logging # <-- Додано logging

# from dotenv import load_dotenv
# load_dotenv()

# --- Налаштування логера ---
logger = logging.getLogger(__name__)
# Додаємо базову конфігурацію, якщо її ще немає
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# --- Кінець налаштування логера ---


# -----------------------------
# Connection Pool
# -----------------------------
try:
    db_pool = psycopg2.pool.SimpleConnectionPool(
        minconn=1,
        maxconn=10,
        dbname=os.getenv("PG_DBNAME"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
        sslmode="require",
    )
    logger.info("✅ Пул з'єднань з PostgreSQL успішно створено.")
except Exception as e:
    logger.error(f"❌ ПОМИЛКА: Не вдалося створити пул з'єднань: {e}", exc_info=True)
    db_pool = None

# -----------------------------
# Оновлена функція connect()
# -----------------------------
@contextlib.contextmanager
def connect():
    if db_pool is None:
        logger.critical("Пул з'єднань не ініціалізовано!")
        raise Exception("Пул з'єднань не ініціалізовано!")

    con = None
    retries = 1 # Дозволяємо одну повторну спробу

    while retries >= 0:
        need_retry = False
        try:
            con = db_pool.getconn() # Беремо з'єднання
            # --- ПЕРЕВІРКА З'ЄДНАННЯ ---
            con.cursor().execute("SELECT 1")
            # --- З'єднання живе ---

            yield con # Віддаємо живе з'єднання
            con.commit() # Commit, якщо 'with' блок пройшов успішно
            break # Виходимо з циклу, все гаразд

        except (psycopg2.OperationalError, InterfaceError) as e: # Ловимо помилку "мертвого" з'єднання або вже закритого
            logger.warning(f"Проблема зі з'єднанням БД ({type(e).__name__}): {e}. Спроба {1-retries}/1...")
            if con:
                try:
                    db_pool.putconn(con, close=True) # Скажемо пулу прибрати це "погане" з'єднання
                    logger.info("Погане з'єднання повернуто в пул для закриття.")
                except InterfaceError: # Якщо воно вже було закрите зовні
                    logger.warning("Спроба повернути вже закрите з'єднання.")
                except Exception as put_err: # Інші можливі помилки при putconn
                    logger.error(f"Помилка при поверненні поганого з'єднання в пул: {put_err}")
                con = None # Скидаємо змінну con

            retries -= 1
            if retries < 0:
                logger.error("Не вдалося отримати живе з'єднання з БД після повторної спроби.")
                raise ConnectionError("Не вдалося отримати живе з'єднання з БД.") from e
            need_retry = True # Потрібна нова ітерація циклу

        except Exception as e_other: # Ловимо інші помилки (наприклад, SQL-синтаксису)
            logger.error(f"Інша помилка при роботі з БД: {e_other}", exc_info=True)
            if con:
                try:
                    con.rollback() # Робимо rollback для інших помилок
                except InterfaceError: # Якщо з'єднання закрилось під час rollback
                    logger.warning("З'єднання закрилось під час rollback.")
                except Exception as rb_err:
                    logger.error(f"Помилка під час rollback: {rb_err}")
            raise # Прокидаємо помилку далі

        finally:
            # Якщо ми НЕ потребуємо повторної спроби І з'єднання все ще існує,
            # значить yield відпрацював, і треба повернути con в пул.
            # Якщо була OperationalError, con вже None або повернутий з close=True.
            if not need_retry and con:
                try:
                    db_pool.putconn(con) # Повертаємо живе, використане з'єднання в пул
                    con = None # Щоб уникнути подвійного повернення
                except InterfaceError:
                    logger.warning("Спроба повернути вже закрите з'єднання після успішної роботи.")
                except Exception as final_put_err:
                    logger.error(f"Помилка при фінальному поверненні з'єднання в пул: {final_put_err}")


# -----------------------------
# Schema init (safe idempotent)
# -----------------------------
def init_db():
    with connect() as con:
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                username TEXT,
                display_name TEXT,
                score INTEGER DEFAULT 0,
                topic TEXT,
                last_daily DATE, -- 🔄 ВИПРАВЛЕНО: TEXT -> DATE
                feedbacks INTEGER DEFAULT 0,
                all_tasks_completed INTEGER DEFAULT 0,
                topics_total INTEGER DEFAULT 0,
                topics_completed INTEGER DEFAULT 0,
                last_activity DATE,
                streak_days INTEGER DEFAULT 0,
                city TEXT,
                phone_number TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id SERIAL PRIMARY KEY,
                category TEXT,
                topic TEXT NOT NULL,
                level TEXT NOT NULL,
                task_type TEXT,
                question TEXT NOT NULL,
                answer JSONB NOT NULL, -- 🔄 ВИПРАВЛЕНО: TEXT -> JSONB
                explanation TEXT,
                photo TEXT,
                is_daily BOOLEAN DEFAULT FALSE -- 🔄 ВИПРАВЛЕНО: INTEGER -> BOOLEAN
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS completed_tasks (
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                PRIMARY KEY (user_id, task_id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
                username TEXT,
                message TEXT,
                timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP -- 🔄 ВИПРАВЛЕНО: Додано TIME ZONE
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS badges (
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                badge TEXT NOT NULL,
                PRIMARY KEY (user_id, badge)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_topic_streaks (
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                topic   TEXT    NOT NULL,
                streak  INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, topic)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_topic_streak_awards (
                user_id   BIGINT  NOT NULL,
                topic     TEXT    NOT NULL,
                milestone INTEGER NOT NULL,
                PRIMARY KEY (user_id, topic, milestone),
                -- 🔄 ВИПРАВЛЕНО: FOREIGN KEY має посилатись на user_topic_streaks для цілісності
                FOREIGN KEY (user_id, topic) REFERENCES user_topic_streaks(user_id, topic) ON DELETE CASCADE
            )
        """)

        # Індекси
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_topic_daily ON tasks (topic, is_daily)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_topic_level ON tasks (topic, level)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_category ON tasks (category)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_feedback_user_time ON feedback (user_id, timestamp DESC)")
        # "idx_completed_user" не потрібен, покривається PRIMARY KEY
        cur.execute("CREATE INDEX IF NOT EXISTS idx_completed_task ON completed_tasks (task_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_is_daily ON tasks (is_daily)")
        # "idx_streaks_user_topic" не потрібен, покривається PRIMARY KEY
        cur.execute("CREATE INDEX IF NOT EXISTS idx_streak_awards_user_topic ON user_topic_streak_awards (user_id, topic)")
        # 🔄 ДОДАНО: Індекс для JSONB
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_answer_gin ON tasks USING GIN (answer)")


        con.commit()
    logger.info("✅ Схема бази даних ініціалізована.")


# -----------------------------
# Users
# -----------------------------
def get_user(user_id):
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        return cur.fetchone()

def create_or_get_user(user_id):
    if not get_user(user_id):
        with connect() as con:
            con.cursor().execute(
                "INSERT INTO users (id) VALUES (%s) ON CONFLICT DO NOTHING",
                (user_id,),
            )
    return get_user(user_id)

def update_user(user_id, field, value):
    with connect() as con:
        # Додамо перевірку на допустимі поля, щоб уникнути SQL ін'єкцій, якщо field приходить ззовні
        allowed_fields = {"username", "display_name", "score", "topic", "last_daily", 
                          "feedbacks", "all_tasks_completed", "topics_total", 
                          "topics_completed", "last_activity", "streak_days", 
                          "city", "phone_number"}
        if field not in allowed_fields:
            logger.error(f"Спроба оновити недопустиме поле '{field}' для user {user_id}")
            raise ValueError(f"Недопустиме поле для оновлення: {field}")
            
        con.cursor().execute(
            f"UPDATE users SET {field} = %s WHERE id = %s",
            (value, user_id),
        )

def add_score(user_id, delta):
    with connect() as con:
        con.cursor().execute(
            "UPDATE users SET score = score + %s WHERE id = %s",
            (delta, user_id),
        )

def get_user_field(user_id, field):
    # Додамо перевірку на допустимі поля
    allowed_fields = {"id", "username", "display_name", "score", "topic", "last_daily", 
                      "feedbacks", "all_tasks_completed", "topics_total", 
                      "topics_completed", "last_activity", "streak_days", 
                      "city", "phone_number"}
    if field not in allowed_fields:
         logger.error(f"Спроба отримати недопустиме поле '{field}' для user {user_id}")
         raise ValueError(f"Недопустиме поле для отримання: {field}")
             
    with connect() as con:
        cur = con.cursor()
        cur.execute(f"SELECT {field} FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        return row[0] if row else None

def get_level_by_score(score):
    if score is None: score = 0 # Обробка випадку, коли score ще не встановлено
    if score < 30:
        return "Новачок"
    elif score < 100:
        return "Середній"
    else:
        return "Математичний гуру"

# -----------------------------
# Tasks
# -----------------------------
def get_random_task(topic=None, level=None, user_id=None, is_daily=None):
    with connect() as con:
        cur = con.cursor()
        query = """
            SELECT id, category, topic, level, task_type, question, answer, explanation, photo, is_daily
            FROM tasks
            WHERE 1=1
        """
        params = []
        if topic:
            query += " AND topic = %s"; params.append(topic)
        if level:
            query += " AND level = %s"; params.append(level)
        if is_daily is not None:
            # 🔄 ВИПРАВЛЕНО: int(is_daily) -> bool(is_daily)
            query += " AND is_daily = %s"; params.append(bool(is_daily)) 
        if user_id:
            # Переконаймося, що user_id не None перед додаванням підзапиту
            if user_id is not None:
                query += " AND id NOT IN (SELECT task_id FROM completed_tasks WHERE user_id = %s)"
                params.append(user_id)

        query += " ORDER BY RANDOM() LIMIT 1"
        cur.execute(query, tuple(params))
        row = cur.fetchone()
        if row:
            try:
                # 🔄 ВИПРАВЛЕНО: 'answer' тепер JSONB, psycopg2 поверне dict/list, json.loads не потрібен
                answer_list = row[6] 
                if isinstance(answer_list, str): # Про всяк випадок, якщо дані ще старі
                    answer_list = json.loads(answer_list)
            except json.JSONDecodeError:
                logger.error(f"Помилка декодування JSON для відповіді задачі ID={row[0]}: {row[6]}")
                answer_list = [] # або інше значення за замовчуванням
            return {
                "id": row[0], "category": row[1], "topic": row[2], "level": row[3],
                "task_type": row[4], "question": row[5], "answer": answer_list,
                "explanation": row[7], "photo": row[8], "is_daily": row[9],
            }
    return None

def add_task(data):
    category = data.get("category")
    # 🔄 ВИПРАВЛЕНО: psycopg2 сам перетворить dict в JSONB, json.dumps не потрібен
    answer_json_or_dict = data.get("answer", []) 
    with connect() as con:
        con.cursor().execute("""
            INSERT INTO tasks (category, topic, level, task_type, question, answer, explanation, photo, is_daily)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            category,
            data["topic"],
            data.get("level") or "",
            data.get("task_type"),
            data["question"],
            answer_json_or_dict, # 🔄 ВИПРАВЛЕНО
            data.get("explanation"), # Додамо get для безпеки
            data.get("photo"),
            data.get("is_daily", False), # 🔄 ВИПРАВЛЕНО: 0 -> False
        ))

def get_all_tasks_by_topic(topic, is_daily=False): # 🔄 ВИПРАВЛЕНО: 0 -> False
    with connect() as con:
        cur = con.cursor()
        cur.execute("""
            SELECT id, category, topic, level, task_type, question, answer, explanation, photo, is_daily
            FROM tasks
            WHERE topic = %s AND is_daily = %s
            ORDER BY id
        """, (topic, is_daily)) # 🔄 ВИПРАВЛЕНО: Параметр вже boolean
        rows = cur.fetchall()
        tasks = []
        for row in rows:
            try:
                # 🔄 ВИПРАВЛЕНО: 'answer' тепер JSONB
                answer_list = row[6]
                if isinstance(answer_list, str):
                    answer_list = json.loads(answer_list)
            except json.JSONDecodeError:
                logger.error(f"Помилка декодування JSON для відповіді задачі ID={row[0]}: {row[6]}")
                answer_list = []
            tasks.append({
                "id": row[0], "category": row[1], "topic": row[2], "level": row[3],
                "task_type": row[4], "question": row[5], "answer": answer_list,
                "explanation": row[7], "photo": row[8], "is_daily": row[9],
            })
        return tasks

def all_tasks_completed(user_id, topic, level):
    with connect() as con:
        cur = con.cursor()
        # 🔄 ВИПРАВЛЕНО: is_daily=0 -> is_daily=FALSE
        cur.execute("SELECT id FROM tasks WHERE topic=%s AND level=%s AND is_daily=FALSE", (topic, level)) 
        all_ids = set(r[0] for r in cur.fetchall())
        if not all_ids: # Якщо задач немає, то не можна вважати, що все пройдено
             return False
        cur.execute("""
            SELECT task_id
            FROM completed_tasks ct JOIN tasks t ON ct.task_id = t.id
            WHERE ct.user_id=%s AND t.topic=%s AND t.level=%s AND t.is_daily=FALSE
        """, (user_id, topic, level)) # 🔄 ВИПРАВЛЕНО: is_daily=0 -> is_daily=FALSE
        done_ids = set(r[0] for r in cur.fetchall())
        return all_ids == done_ids

def get_task_by_id(task_id):
    with connect() as con:
        cur = con.cursor()
        cur.execute("""
            SELECT id, category, topic, level, task_type, question, answer, explanation, photo, is_daily
            FROM tasks WHERE id = %s
        """, (task_id,))
        row = cur.fetchone()
        if row:
            try:
                # 🔄 ВИПРАВЛЕНО: 'answer' тепер JSONB
                answer_list = row[6]
                if isinstance(answer_list, str):
                    answer_list = json.loads(answer_list)
            except json.JSONDecodeError:
                logger.error(f"Помилка декодування JSON для відповіді задачі ID={row[0]}: {row[6]}")
                answer_list = []
            return {
                "id": row[0], "category": row[1], "topic": row[2], "level": row[3],
                "task_type": row[4], "question": row[5], "answer": answer_list,
                "explanation": row[7], "photo": row[8], "is_daily": row[9],
            }
    return None

def delete_task(task_id):
    with connect() as con:
        con.cursor().execute("DELETE FROM tasks WHERE id = %s", (task_id,))

def update_task_field(task_id, field, value):
     # Додамо перевірку на допустимі поля
    allowed_fields = {"category", "topic", "level", "task_type", "question", 
                      "answer", "explanation", "photo", "is_daily"}
    if field not in allowed_fields:
        logger.error(f"Спроба оновити недопустиме поле '{field}' для task {task_id}")
        raise ValueError(f"Недопустиме поле для оновлення задачі: {field}")
        
    # 🔄 ВИПРАВЛЕНО: Якщо оновлюємо 'answer' і це не JSONB-сумісний dict/list, 
    # спробуємо застарий варіант з json.dumps
    if field == 'answer' and not isinstance(value, (dict, list)):
         try:
            # Припустимо, що прийшов рядок, який треба перетворити на JSON
            # Або що прийшов dict/list, який треба передати як JSON
             value = json.dumps(value) 
         except TypeError:
             logger.warning(f"Незвичайний тип для поля 'answer' task {task_id}: {value}. Спроба передати як є.")
             # Якщо це вже dict/list, psycopg2 впорається
             if isinstance(value, (dict, list)):
                pass # Все ок
             else: # Якщо це рядок, але не JSON, база може видати помилку
                logger.error(f"Не вдалося конвертувати відповідь у JSON для task {task_id}: {value}")
                raise ValueError("Некоректний формат відповіді для JSON")
    
    # 🔄 ВИПРАВЛЕНО: для is_daily переконуємось, що це boolean
    if field == 'is_daily':
        value = bool(value)

    with connect() as con:
        con.cursor().execute(
            f"UPDATE tasks SET {field} = %s WHERE id = %s",
            (value, task_id),
        )

def get_all_topics(is_daily=False): # 🔄 ВИПРАВЛЕНО: 0 -> False
    with connect() as con:
        cur = con.cursor()
        cur.execute(
            "SELECT DISTINCT topic FROM tasks WHERE is_daily=%s",
            (is_daily,), # 🔄 ВИПРАВЛЕНО: прибрано int()
        )
        topics = [row[0] for row in cur.fetchall() if row[0]] # Додамо перевірку на None/порожній рядок
        forbidden = {"🧠 Почати задачу", "Рандомна тема", "❌ Немає тем", ""} # Додамо порожній рядок
        clean_topics = [t for t in topics if t and t not in forbidden and len(t) > 1]
        return clean_topics

# -----------------------------
# Feedback / rating / badges
# -----------------------------
def get_all_feedback():
    with connect() as con:
        cur = con.cursor()
        cur.execute("""
            SELECT id, user_id, username, message, timestamp
            FROM feedback
            ORDER BY timestamp DESC
        """)
        # Обережно конвертуємо timestamp у рядок, якщо треба
        return [(id, uid, uname, msg, ts.strftime('%Y-%m-%d %H:%M:%S') if ts else None) 
                for id, uid, uname, msg, ts in cur.fetchall()]


def get_user_completed_count(user_id, topic, level):
    with connect() as con:
        cur = con.cursor()
        # 🔄 ВИПРАВЛЕНО: is_daily=0 -> is_daily=FALSE
        cur.execute("""
            SELECT COUNT(ct.task_id)
            FROM completed_tasks ct JOIN tasks t ON ct.task_id = t.id
            WHERE ct.user_id = %s AND t.topic=%s AND t.level=%s AND t.is_daily=FALSE
        """, (user_id, topic, level))
        result = cur.fetchone()
        return result[0] if result else 0

def get_top_users(limit=10):
    with connect() as con:
        cur = con.cursor()
        # Додамо фільтр score > 0, щоб не показувати нульових
        cur.execute("SELECT id, score FROM users WHERE score > 0 ORDER BY score DESC LIMIT %s", (limit,))
        return cur.fetchall()

def get_user_rank(user_id):
    with connect() as con:
        cur = con.cursor()
        # Рахуємо ранг тільки серед тих, хто має бали
        cur.execute("SELECT id, score FROM users WHERE score > 0 ORDER BY score DESC")
        rows = cur.fetchall()
        total_ranked_users = len(rows)
        for rank, (uid, score) in enumerate(rows, start=1):
            if uid == user_id:
                return rank, score, total_ranked_users
        # Якщо юзера немає в рейтингу (score=0), повертаємо None
        # Але загальну кількість рахуємо по всіх юзерах
        cur.execute("SELECT COUNT(*) FROM users")
        total_users = cur.fetchone()[0]
        my_score = get_user_field(user_id, "score") or 0
        return None, my_score, total_users


def unlock_badge(user_id, badge, reward=0):
    with connect() as con:
        cur = con.cursor()
        cur.execute(
            "SELECT 1 FROM badges WHERE user_id=%s AND badge=%s",
            (user_id, badge),
        )
        exists = cur.fetchone()
        if not exists:
            cur.execute("""
                INSERT INTO badges (user_id, badge)
                VALUES (%s, %s) ON CONFLICT DO NOTHING
            """, (user_id, badge))
            # Перевіримо, чи вставка була успішною (rowcount > 0)
            was_inserted = cur.rowcount > 0
            if was_inserted and reward:
                cur.execute(
                    "UPDATE users SET score = score + %s WHERE id = %s",
                    (reward, user_id),
                )
            return was_inserted # Повертаємо True тільки якщо бейдж дійсно був розблокований
    return False

def get_user_badges(user_id):
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT badge FROM badges WHERE user_id = %s", (user_id,))
        return [row[0] for row in cur.fetchall()]

def count_user_tasks(user_id):
    with connect() as con:
        cur = con.cursor()
        # 🔄 ВИПРАВЛЕНО: is_daily=0 -> is_daily=FALSE
        cur.execute("""
            SELECT COUNT(ct.task_id) 
            FROM completed_tasks ct JOIN tasks t ON ct.task_id = t.id
            WHERE ct.user_id = %s AND t.is_daily=FALSE
            """, (user_id,)
        )
        result = cur.fetchone()
        return result[0] if result else 0

def add_feedback(user_id, username, message):
    with connect() as con:
        cur = con.cursor()
        cur.execute("""
            INSERT INTO feedback (user_id, username, message)
            VALUES (%s, %s, %s)
        """, (user_id, username, message))
        cur.execute("UPDATE users SET feedbacks = feedbacks + 1 WHERE id = %s", (user_id,))

# -----------------------------
# Progress flags / aggregates
# -----------------------------
def update_all_tasks_completed_flag(user_id):
    with connect() as con:
        cur = con.cursor()
        # 🔄 ВИПРАВЛЕНО: is_daily=0 -> is_daily=FALSE
        cur.execute("SELECT COUNT(*) FROM tasks WHERE is_daily=FALSE")
        total_tasks = cur.fetchone()[0]
        # 🔄 ВИПРАВЛЕНО: is_daily=0 -> is_daily=FALSE
        cur.execute("""
             SELECT COUNT(ct.task_id) 
             FROM completed_tasks ct JOIN tasks t ON ct.task_id = t.id
             WHERE ct.user_id = %s AND t.is_daily=FALSE
             """, (user_id,))
        completed = cur.fetchone()[0]
        
        completed_flag = 1 if total_tasks > 0 and completed >= total_tasks else 0
        cur.execute(
            "UPDATE users SET all_tasks_completed = %s WHERE id = %s",
            (completed_flag, user_id),
        )

def update_topics_progress(user_id):
    # Ця функція складна і може бути повільною. Можливо, її варто оновлювати рідше?
    # Або перенести логіку в тригери БД.
    with connect() as con:
        cur = con.cursor()
        # 🔄 ВИПРАВЛЕНО: is_daily=0 -> is_daily=FALSE
        cur.execute("SELECT DISTINCT topic FROM tasks WHERE is_daily=FALSE")
        all_topics = {row[0] for row in cur.fetchall() if row[0]}
        topics_total = len(all_topics)

        # 🔄 ВИПРАВЛЕНО: is_daily=0 -> is_daily=FALSE
        cur.execute("""
            SELECT t.topic
            FROM completed_tasks c
            JOIN tasks t ON c.task_id = t.id
            WHERE c.user_id = %s AND t.is_daily = FALSE
            GROUP BY t.topic
            HAVING COUNT(DISTINCT t.id) = (SELECT COUNT(*) FROM tasks t2 WHERE t2.topic = t.topic AND t2.is_daily = FALSE)
        """, (user_id,))
        # Попередній запит може бути не зовсім коректним, якщо нам треба рахувати теми,
        # де *хоча б одна* задача виконана. Уточни логіку.
        # Ось варіант для "хоча б одна задача виконана":
        cur.execute("""
             SELECT DISTINCT t.topic
             FROM completed_tasks c
             JOIN tasks t ON c.task_id = t.id
             WHERE c.user_id = %s AND t.is_daily = FALSE AND t.topic IS NOT NULL
         """, (user_id,)) # 🔄 ВИПРАВЛЕНО: is_daily=0 -> is_daily=FALSE
        completed_topics = {row[0] for row in cur.fetchall() if row[0]}
        # Переконаємось, що рахуємо тільки ті теми, які є в all_topics
        actual_completed_topics = completed_topics.intersection(all_topics)
        topics_completed = len(actual_completed_topics)


        cur.execute("""
            UPDATE users SET topics_total = %s, topics_completed = %s
            WHERE id = %s
        """, (topics_total, topics_completed, user_id))


def mark_task_completed(user_id, task_id):
    was_inserted = False
    with connect() as con:
        cur = con.cursor()
        cur.execute("""
            INSERT INTO completed_tasks (user_id, task_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
        """, (user_id, task_id))
        was_inserted = cur.rowcount > 0 # Перевіряємо, чи був запис доданий (чи це не повтор)

    # Оновлюємо агрегати тільки якщо це було перше виконання
    if was_inserted:
        # Перевіримо, чи це була звичайна задача, перед оновленням агрегатів
        task = get_task_by_id(task_id)
        if task and not task.get('is_daily'): # 🔄 ВИПРАВЛЕНО: 'is_daily' тепер False
             try:
                 update_all_tasks_completed_flag(user_id)
                 update_topics_progress(user_id)
             except Exception as e:
                 logger.error(f"Помилка при оновленні агрегатів для user {user_id} після task {task_id}: {e}")

    return was_inserted # Повертаємо статус, чи була задача відмічена вперше


def get_available_levels_for_topic(topic, exclude_level=None):
    # 🔄 ВИПРАВЛЕНО: is_daily=0 -> is_daily=False
    tasks = get_all_tasks_by_topic(topic, is_daily=False) # Шукаємо рівні тільки серед звичайних задач
    available = {t['level'] for t in tasks if t.get('level')} # Додамо перевірку на None
    if exclude_level:
        available.discard(exclude_level) # Використовуємо discard замість remove
    return sorted(list(available))

def get_all_topics_by_category(category, is_daily=False): # 🔄 ВИПРАВЛЕНО: 0 -> False
    with connect() as con:
        cur = con.cursor()
        cur.execute("""
            SELECT DISTINCT topic FROM tasks
            WHERE category=%s AND is_daily=%s AND topic IS NOT NULL AND topic != ''
        """, (category, is_daily)) # 🔄 ВИПРАВЛЕНО: прибрано int()
        return [row[0] for row in cur.fetchall()]

def get_completed_task_ids(user_id, topic=None, level=None):
    with connect() as con:
        cur = con.cursor()
        query = "SELECT c.task_id FROM completed_tasks c JOIN tasks t ON t.id = c.task_id WHERE c.user_id = %s"
        params = [user_id]
        
        # Додаємо is_daily=0, якщо шукаємо для звичайного процесу
        is_daily_check_needed = True 

        if topic:
            query += " AND t.topic = %s"
            params.append(topic)
        if level:
            query += " AND t.level = %s"
            params.append(level)
            
        # Якщо ми не шукаємо щоденні, додаємо is_daily=0
        # (Потрібно перевірити, чи не зламає це логіку щоденних задач)
        # Припустимо, що коли topic/level не задані, ми хочемо ВСІ id, тому is_daily не фільтруємо
        # if topic or level: 
        #    query += " AND t.is_daily = FALSE" # 🔄 ВИПРАВЛЕНО (але закоментовано)
            
        cur.execute(query, tuple(params))
        return {row[0] for row in cur.fetchall()}

# -----------------------------
# Streaks (days) and per-topic
# -----------------------------
def update_streak_and_reward(user_id):
    today = date.today()
    new_streak = 0
    reward = 0
    current_streak = 0
    
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT last_activity, streak_days FROM users WHERE id = %s FOR UPDATE", (user_id,)) # Блокуємо рядок
        row = cur.fetchone()
        last_activity, streak_days = (row if row else (None, 0))
        current_streak = streak_days or 0

        if last_activity == today:
            return current_streak, 0 # Активність сьогодні вже була, нічого не робимо

        if last_activity == (today - timedelta(days=1)):
            new_streak = current_streak + 1
        else:
            new_streak = 1 # Стрік починається заново

        cur.execute(
            "UPDATE users SET last_activity=%s, streak_days=%s WHERE id=%s",
            (today, new_streak, user_id),
        )

        reward_map = {3: 5, 7: 10, 14: 20, 30: 50}
        # Нараховуємо нагороду тільки якщо СЬОГОДНІ досягли позначки
        if new_streak in reward_map: 
             # Перевіримо, чи нагорода за цю позначку вже не була видана (потрібна нова таблиця?)
             # Поки що видаємо завжди при досягненні
            reward = reward_map[new_streak]
            if reward > 0:
                cur.execute(
                    "UPDATE users SET score = score + %s WHERE id=%s",
                    (reward, user_id),
                )
                logger.info(f"User {user_id} досяг стріку {new_streak} днів! Нараховано +{reward} балів.")

    return new_streak, reward

def get_topic_streak(user_id: int, topic: str) -> int:
    with connect() as con:
        cur = con.cursor()
        cur.execute("""
            SELECT streak FROM user_topic_streaks
            WHERE user_id=%s AND topic=%s
        """, (user_id, topic))
        row = cur.fetchone()
        return row[0] if row else 0

def set_topic_streak(user_id: int, topic: str, value: int):
    with connect() as con:
        cur = con.cursor()
        cur.execute("""
            INSERT INTO user_topic_streaks (user_id, topic, streak)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, topic) DO UPDATE SET streak=EXCLUDED.streak
        """, (user_id, topic, value))

def inc_topic_streak(user_id: int, topic: str) -> int:
    current = get_topic_streak(user_id, topic)
    new_val = current + 1
    set_topic_streak(user_id, topic, new_val)
    return new_val

def reset_topic_streak(user_id: int, topic: str):
    set_topic_streak(user_id, topic, 0)

def has_topic_streak_award(user_id: int, topic: str, milestone: int) -> bool:
    with connect() as con:
        cur = con.cursor()
        cur.execute("""
            SELECT 1 FROM user_topic_streak_awards
            WHERE user_id=%s AND topic=%s AND milestone=%s
        """, (user_id, topic, milestone))
        return bool(cur.fetchone())

def mark_topic_streak_award(user_id: int, topic: str, milestone: int):
    with connect() as con:
        cur = con.cursor()
        cur.execute("""
            INSERT INTO user_topic_streak_awards (user_id, topic, milestone)
            VALUES (%s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (user_id, topic, milestone))

# -----------------------------
# Aggregates for fast progress
# -----------------------------
def get_progress_aggregates(user_id: int):
    totals = {}
    done = {}
    try:
        with connect() as con:
            cur = con.cursor()
            # Отримуємо загальну кількість звичайних задач по темах/рівнях
            cur.execute("""
                SELECT topic, level, COUNT(*)
                FROM tasks
                WHERE is_daily = FALSE AND topic IS NOT NULL AND level IS NOT NULL AND topic != '' AND level != ''
                GROUP BY topic, level
            """) # 🔄 ВИПРАВЛЕНО: is_daily = 0 -> is_daily = FALSE
            totals = {(t, l): n for (t, l, n) in cur.fetchall()}

            # Отримуємо кількість виконаних звичайних задач користувачем по темах/рівнях
            cur.execute("""
                SELECT t.topic, t.level, COUNT(c.task_id)
                FROM completed_tasks c
                JOIN tasks t ON t.id = c.task_id
                WHERE c.user_id = %s AND t.is_daily = FALSE 
                      AND t.topic IS NOT NULL AND t.level IS NOT NULL AND t.topic != '' AND t.level != ''
                GROUP BY t.topic, t.level
            """, (user_id,)) # 🔄 ВИПРАВЛЕНО: is_daily = 0 -> is_daily = FALSE
            done = {(t, l): n for (t, l, n) in cur.fetchall()}
            
    except Exception as e:
       logger.error(f"Помилка при отриманні агрегатів прогресу для user {user_id}: {e}", exc_info=True)
       # Повертаємо порожні словники у випадку помилки
       return {}, {}
       
    return totals, done

def get_users_for_reengagement(days_ago: int):
    target_date = date.today() - timedelta(days=days_ago)
    with connect() as con:
        cur = con.cursor()
        cur.execute(
            "SELECT id FROM users WHERE last_activity = %s",
            (target_date,)
        )
        return cur.fetchall()

def get_all_users_for_export():
    with connect() as con:
        cur = con.cursor()
        cur.execute("""
            SELECT id, display_name, username, score, city, phone_number, last_activity
            FROM users
            ORDER BY score DESC, id
        """)
        # Конвертуємо дати в рядки для CSV
        results = []
        for row in cur.fetchall():
            row_list = list(row)
            if isinstance(row_list[-1], date): # Якщо останній елемент - дата
                row_list[-1] = row_list[-1].isoformat() # Конвертуємо в YYYY-MM-DD
            results.append(tuple(row_list))
        return results