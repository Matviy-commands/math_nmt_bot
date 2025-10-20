import os
import psycopg2
import json
from datetime import date, timedelta
# from dotenv import load_dotenv
# load_dotenv()

# -----------------------------
# Connection
# -----------------------------
def connect():
    return psycopg2.connect(
        dbname=os.getenv("PG_DBNAME"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
        sslmode="require",
    )

# -----------------------------
# Schema init (safe idempotent)
# -----------------------------
def init_db():
    with connect() as con:
        cur = con.cursor()

        # 1) базові таблиці
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                username TEXT,
                display_name TEXT,
                score INTEGER DEFAULT 0,
                topic TEXT,
                last_daily TEXT,
                feedbacks INTEGER DEFAULT 0,
                all_tasks_completed INTEGER DEFAULT 0,
                topics_total INTEGER DEFAULT 0,
                topics_completed INTEGER DEFAULT 0
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
                answer TEXT NOT NULL,
                explanation TEXT,
                photo TEXT,
                is_daily INTEGER DEFAULT 0
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS completed_tasks (
                user_id BIGINT NOT NULL,
                task_id INTEGER NOT NULL,
                PRIMARY KEY (user_id, task_id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                username TEXT,
                message TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS badges (
                user_id BIGINT NOT NULL,
                badge TEXT NOT NULL,
                PRIMARY KEY (user_id, badge)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_topic_streaks (
                user_id BIGINT NOT NULL,
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
                PRIMARY KEY (user_id, topic, milestone)
            )
        """)

        # 2) додаткові поля в users (якщо ще не створені)
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_activity DATE")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS streak_days INTEGER DEFAULT 0")

        # 3) індекси
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_topic_level_daily ON tasks (topic, level, is_daily)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_is_daily ON tasks (is_daily)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_category ON tasks (category)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_completed_user ON completed_tasks (user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_completed_task ON completed_tasks (task_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_feedback_user_time ON feedback (user_id, timestamp)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_streaks_user_topic ON user_topic_streaks (user_id, topic)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_streak_awards_user_topic ON user_topic_streak_awards (user_id, topic)")

        con.commit()

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
    with connect() as con:
        cur = con.cursor()
        cur.execute(f"SELECT {field} FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        return row[0] if row else None

def get_level_by_score(score):
    if score < 30:
        return "Новачок"
    elif score < 100:
        return "Середній"
    else:
        return "Математичний гуру"

# -----------------------------
# Tasks
# -----------------------------
def get_random_task(topic=None, level=None, user_id=None):
    with connect() as con:
        cur = con.cursor()
        base = """
            SELECT t.id, t.category, t.topic, t.level, t.task_type, t.question,
                   t.answer, t.explanation, t.photo, t.is_daily
            FROM tasks t
            {anti}
            WHERE 1=1
        """
        params = []
        anti = ""
        if user_id:
            anti = "LEFT JOIN completed_tasks c ON c.task_id = t.id AND c.user_id = %s"
            params.append(user_id)
        q = base.format(anti=anti)
        if topic:
            q += " AND t.topic = %s"; params.append(topic)
        if level:
            q += " AND t.level = %s"; params.append(level)
        if user_id:
            q += " AND c.task_id IS NULL"
        q += " ORDER BY RANDOM() LIMIT 1"

        cur.execute(q, tuple(params))
        row = cur.fetchone()
        if row:
            return {
                "id": row[0],
                "category": row[1],
                "topic": row[2],
                "level": row[3],
                "task_type": row[4],
                "question": row[5],
                "answer": json.loads(row[6]),
                "explanation": row[7],
                "photo": row[8],
                "is_daily": row[9],
            }
    return None

def add_task(data):
    category = data.get("category")
    with connect() as con:
        con.cursor().execute("""
            INSERT INTO tasks (category, topic, level, task_type, question, answer, explanation, photo, is_daily)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            category,
            data["topic"],
            data.get("level") or "",      # для daily можна "" як зараз
            data.get("task_type"),
            data["question"],
            json.dumps(data["answer"]),
            data["explanation"],
            data.get("photo"),
            data.get("is_daily", 0),
        ))

def get_all_tasks_by_topic(topic, is_daily=0):
    with connect() as con:
        cur = con.cursor()
        cur.execute("""
            SELECT id, category, topic, level, task_type, question, answer, explanation, photo, is_daily
            FROM tasks
            WHERE topic = %s AND is_daily = %s
            ORDER BY id
        """, (topic, is_daily))
        rows = cur.fetchall()
        tasks = []
        for row in rows:
            tasks.append({
                "id": row[0],
                "category": row[1],
                "topic": row[2],
                "level": row[3],
                "task_type": row[4],
                "question": row[5],
                "answer": json.loads(row[6]),
                "explanation": row[7],
                "photo": row[8],
                "is_daily": row[9],
            })
        return tasks

def all_tasks_completed(user_id, topic, level):
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT id FROM tasks WHERE topic=%s AND level=%s", (topic, level))
        all_ids = set(r[0] for r in cur.fetchall())
        cur.execute("""
            SELECT task_id
            FROM completed_tasks
            WHERE user_id=%s AND task_id IN (SELECT id FROM tasks WHERE topic=%s AND level=%s)
        """, (user_id, topic, level))
        done_ids = set(r[0] for r in cur.fetchall())
        return all_ids == done_ids and len(all_ids) > 0

def get_task_by_id(task_id):
    with connect() as con:
        cur = con.cursor()
        cur.execute("""
            SELECT id, category, topic, level, task_type, question, answer, explanation, photo, is_daily
            FROM tasks WHERE id = %s
        """, (task_id,))
        row = cur.fetchone()
        if row:
            return {
                "id": row[0],
                "category": row[1],
                "topic": row[2],
                "level": row[3],
                "task_type": row[4],
                "question": row[5],
                "answer": json.loads(row[6]),
                "explanation": row[7],
                "photo": row[8],
                "is_daily": row[9],
            }
    return None

def delete_task(task_id):
    with connect() as con:
        con.cursor().execute("DELETE FROM tasks WHERE id = %s", (task_id,))

def update_task_field(task_id, field, value):
    with connect() as con:
        con.cursor().execute(
            f"UPDATE tasks SET {field} = %s WHERE id = %s",
            (value, task_id),
        )

def get_all_topics(is_daily=0):
    with connect() as con:
        cur = con.cursor()
        cur.execute(
            "SELECT DISTINCT topic FROM tasks WHERE is_daily=%s",
            (int(is_daily),),
        )
        topics = [row[0] for row in cur.fetchall()]
        forbidden = {"🧠 Почати задачу", "Рандомна тема", "❌ Немає тем"}
        clean_topics = [t for t in topics if t not in forbidden and len(t) > 1]
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
        return cur.fetchall()

def get_user_completed_count(user_id, topic, level):
    with connect() as con:
        cur = con.cursor()
        cur.execute("""
            SELECT COUNT(*)
            FROM completed_tasks
            WHERE user_id = %s AND task_id IN (
                SELECT id FROM tasks WHERE topic=%s AND level=%s
            )
        """, (user_id, topic, level))
        return cur.fetchone()[0]

def get_top_users(limit=10):
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT id, score FROM users ORDER BY score DESC LIMIT %s", (limit,))
        return cur.fetchall()

def get_user_rank(user_id):
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT id, score FROM users ORDER BY score DESC")
        rows = cur.fetchall()
        for rank, (uid, score) in enumerate(rows, start=1):
            if uid == user_id:
                return rank, score, len(rows)
        return None, None, len(rows)

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
            if reward:
                cur.execute(
                    "UPDATE users SET score = score + %s WHERE id = %s",
                    (reward, user_id),
                )
            return True
    return False

def get_user_badges(user_id):
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT badge FROM badges WHERE user_id = %s", (user_id,))
        return [row[0] for row in cur.fetchall()]

def count_user_tasks(user_id):
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM completed_tasks WHERE user_id = %s", (user_id,))
        return cur.fetchone()[0]

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
        cur.execute("SELECT COUNT(*) FROM tasks")
        total_tasks = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM completed_tasks WHERE user_id = %s", (user_id,))
        completed = cur.fetchone()[0]
        completed_flag = 1 if total_tasks > 0 and completed == total_tasks else 0
        cur.execute(
            "UPDATE users SET all_tasks_completed = %s WHERE id = %s",
            (completed_flag, user_id),
        )

def update_topics_progress(user_id):
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT DISTINCT topic FROM tasks")
        all_topics = set(row[0] for row in cur.fetchall())
        topics_total = len(all_topics)

        cur.execute("""
            SELECT DISTINCT t.topic
            FROM completed_tasks c
            JOIN tasks t ON c.task_id = t.id
            WHERE c.user_id = %s
        """, (user_id,))
        completed_topics = set(row[0] for row in cur.fetchall())
        topics_completed = len(completed_topics)

        cur.execute("""
            UPDATE users SET topics_total = %s, topics_completed = %s
            WHERE id = %s
        """, (topics_total, topics_completed, user_id))

def mark_task_completed(user_id, task_id):
    with connect() as con:
        cur = con.cursor()
        cur.execute("""
            INSERT INTO completed_tasks (user_id, task_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
        """, (user_id, task_id))
        update_all_tasks_completed_flag(user_id)
        update_topics_progress(user_id)

def get_available_levels_for_topic(topic, exclude_level=None):
    tasks = get_all_tasks_by_topic(topic)
    available = set(t['level'] for t in tasks)
    if exclude_level:
        try:
            available.remove(exclude_level)
        except KeyError:
            pass
    return sorted(available)

def get_all_topics_by_category(category, is_daily=0):
    with connect() as con:
        cur = con.cursor()
        cur.execute("""
            SELECT DISTINCT topic FROM tasks
            WHERE category=%s AND is_daily=%s
        """, (category, int(is_daily)))
        return [row[0] for row in cur.fetchall()]

def get_completed_task_ids(user_id, topic=None, level=None):
    with connect() as con:
        cur = con.cursor()
        if topic and level:
            cur.execute("""
                SELECT c.task_id
                FROM completed_tasks c
                JOIN tasks t ON t.id = c.task_id
                WHERE c.user_id = %s AND t.topic = %s AND t.level = %s
            """, (user_id, topic, level))
        elif topic:
            cur.execute("""
                SELECT c.task_id
                FROM completed_tasks c
                JOIN tasks t ON t.id = c.task_id
                WHERE c.user_id = %s AND t.topic = %s
            """, (user_id, topic))
        else:
            cur.execute("SELECT task_id FROM completed_tasks WHERE user_id = %s", (user_id,))
        return {row[0] for row in cur.fetchall()}

# -----------------------------
# Streaks (days) and per-topic
# -----------------------------
def update_streak_and_reward(user_id):
    today = date.today()
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT last_activity, streak_days FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        last_activity, streak_days = (row if row else (None, 0))

        if last_activity == today:
            return streak_days, 0

        if last_activity == (today - timedelta(days=1)):
            new_streak = (streak_days or 0) + 1
        else:
            new_streak = 1

        cur.execute(
            "UPDATE users SET last_activity=%s, streak_days=%s WHERE id=%s",
            (today, new_streak, user_id),
        )

        reward_map = {3: 5, 7: 10, 14: 20, 30: 50}
        reward = reward_map.get(new_streak, 0)
        if reward:
            cur.execute(
                "UPDATE users SET score = score + %s WHERE id=%s",
                (reward, user_id),
            )

        return new_streak, reward

def get_topic_streak(user_id: int, topic: str) -> int:
    with connect() as con:
        cur = con.cursor()
        cur.execute("""
            SELECT streak
            FROM user_topic_streaks
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
            SELECT 1
            FROM user_topic_streak_awards
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
    """
    totals[(topic, level)] = загальна кількість задач (звичайних, не daily)
    done[(topic, level)]   = скільки користувач виконав у цій парі (topic, level)
    """
    with connect() as con:
        cur = con.cursor()
        cur.execute("""
            SELECT topic, level, COUNT(*)
            FROM tasks
            WHERE is_daily = 0
            GROUP BY topic, level
        """)
        totals = {(t, l): n for (t, l, n) in cur.fetchall()}

        cur.execute("""
            SELECT t.topic, t.level, COUNT(*)
            FROM completed_tasks c
            JOIN tasks t ON t.id = c.task_id
            WHERE c.user_id = %s AND t.is_daily = 0
            GROUP BY t.topic, t.level
        """, (user_id,))
        done = {(t, l): n for (t, l, n) in cur.fetchall()}

        return totals, done
