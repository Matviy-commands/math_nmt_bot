import os
import psycopg2
import json
# from dotenv import load_dotenv

# load_dotenv()

def connect():
    return psycopg2.connect(
        dbname=os.getenv("PG_DBNAME"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
        sslmode="require"
    )

def init_db():
    with connect() as con:
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                score INTEGER DEFAULT 0,
                topic TEXT,
                level TEXT,
                last_daily TEXT,
                topics_completed INTEGER DEFAULT 0,
                topics_total INTEGER DEFAULT 0,
                daily_streak INTEGER DEFAULT 0,
                feedbacks INTEGER DEFAULT 0,
                all_tasks_completed INTEGER DEFAULT 0,
                display_name TEXT,
                username TEXT
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS badges (
                user_id BIGINT,
                badge TEXT,
                PRIMARY KEY (user_id, badge)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id SERIAL PRIMARY KEY,
                topic TEXT NOT NULL,
                level TEXT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                explanation TEXT,
                photo TEXT,
                is_daily INTEGER DEFAULT 0
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS completed_tasks (
                user_id BIGINT,
                task_id INTEGER,
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
        con.commit()  # Не забувай!

def get_user(user_id):
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        return cur.fetchone()

def create_or_get_user(user_id):
    if not get_user(user_id):
        with connect() as con:
            con.cursor().execute("INSERT INTO users (id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
    return get_user(user_id)

def update_user(user_id, field, value):
    with connect() as con:
        con.cursor().execute(f"UPDATE users SET {field} = %s WHERE id = %s", (value, user_id))

def add_score(user_id, delta):
    with connect() as con:
        con.cursor().execute("UPDATE users SET score = score + %s WHERE id = %s", (delta, user_id))

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

def get_random_task(topic=None, level=None, user_id=None):
    with connect() as con:
        cur = con.cursor()
        query = "SELECT * FROM tasks WHERE 1=1"
        params = []
        if topic:
            query += " AND topic = %s"
            params.append(topic)
        if level:
            query += " AND level = %s"
            params.append(level)
        if user_id:
            query += " AND id NOT IN (SELECT task_id FROM completed_tasks WHERE user_id = %s)"
            params.append(user_id)
        query += " ORDER BY RANDOM() LIMIT 1"
        cur.execute(query, tuple(params))
        row = cur.fetchone()
        if row:
            return {
                "id": row[0],
                "topic": row[1],
                "level": row[2],
                "question": row[3],
                "answer": json.loads(row[4]),
                "explanation": row[5],
                "photo": row[6]
            }
    return None

def add_task(data):
    with connect() as con:
        con.cursor().execute("""
            INSERT INTO tasks (topic, level, question, answer, explanation, photo, is_daily)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            data["topic"],
            data["level"],
            data["question"],
            json.dumps(data["answer"]),
            data["explanation"],
            data.get("photo"),
            data.get("is_daily", 0)
        ))

def get_all_tasks_by_topic(topic, is_daily=0):
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM tasks WHERE topic = %s AND is_daily = %s", (topic, is_daily))
        rows = cur.fetchall()
        tasks = []
        for row in rows:
            tasks.append({
                "id": row[0],
                "topic": row[1],
                "level": row[2],
                "question": row[3],
                "answer": json.loads(row[4]),
                "explanation": row[5],
                "photo": row[6],
            })
        return tasks

def all_tasks_completed(user_id, topic, level):
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT id FROM tasks WHERE topic=%s AND level=%s", (topic, level))
        all_ids = set(row[0] for row in cur.fetchall())
        cur.execute("SELECT task_id FROM completed_tasks WHERE user_id=%s AND task_id IN (SELECT id FROM tasks WHERE topic=%s AND level=%s)", (user_id, topic, level))
        done_ids = set(row[0] for row in cur.fetchall())
        return all_ids == done_ids and len(all_ids) > 0

def get_task_by_id(task_id):
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
        row = cur.fetchone()
        if row:
            return {
                "id": row[0],
                "topic": row[1],
                "level": row[2],
                "question": row[3],
                "answer": json.loads(row[4]),
                "explanation": row[5],
                "photo": row[6],
                "is_daily": row[7],
            }
    return None

def delete_task(task_id):
    with connect() as con:
        con.cursor().execute("DELETE FROM tasks WHERE id = %s", (task_id,))

def update_task_field(task_id, field, value):
    with connect() as con:
        con.cursor().execute(f"UPDATE tasks SET {field} = %s WHERE id = %s", (value, task_id))

def get_all_topics(is_daily=0):
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT DISTINCT topic FROM tasks WHERE is_daily=%s", (int(is_daily),))
        topics = [row[0] for row in cur.fetchall()]
        forbidden = {"🧠 Почати задачу", "Рандомна тема", "❌ Немає тем"}
        clean_topics = [t for t in topics if t not in forbidden and len(t) > 1]
        return clean_topics


def get_all_feedback():
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT id, user_id, username, message, timestamp FROM feedback ORDER BY timestamp DESC")
        return cur.fetchall()

def get_user_completed_count(user_id, topic, level):
    with connect() as con:
        cur = con.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM completed_tasks WHERE user_id = %s AND task_id IN (SELECT id FROM tasks WHERE topic=%s AND level=%s)",
            (user_id, topic, level)
        )
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
        cur.execute("SELECT 1 FROM badges WHERE user_id=%s AND badge=%s", (user_id, badge))
        if not cur.fetchone():
            cur.execute("INSERT INTO badges (user_id, badge) VALUES (%s, %s) ON CONFLICT DO NOTHING", (user_id, badge))
            if reward:
                cur.execute("UPDATE users SET score = score + %s WHERE id = %s", (reward, user_id))
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
        cur.execute(
            "INSERT INTO feedback (user_id, username, message) VALUES (%s, %s, %s)",
            (user_id, username, message)
        )
        cur.execute(
            "UPDATE users SET feedbacks = feedbacks + 1 WHERE id = %s", (user_id,)
        )

def update_all_tasks_completed_flag(user_id):
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM tasks")
        total_tasks = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM completed_tasks WHERE user_id = %s", (user_id,))
        completed = cur.fetchone()[0]
        completed_flag = 1 if total_tasks > 0 and completed == total_tasks else 0
        cur.execute("UPDATE users SET all_tasks_completed = %s WHERE id = %s", (completed_flag, user_id))

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
        cur.execute(
            "UPDATE users SET topics_total = %s, topics_completed = %s WHERE id = %s",
            (topics_total, topics_completed, user_id)
        )

def mark_task_completed(user_id, task_id):
    with connect() as con:
        cur = con.cursor()
        cur.execute(
            "INSERT INTO completed_tasks (user_id, task_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (user_id, task_id)
        )
        update_all_tasks_completed_flag(user_id)
        update_topics_progress(user_id)

def get_available_levels_for_topic(topic, exclude_level=None):
    tasks = get_all_tasks_by_topic(topic)
    available = set(t['level'] for t in tasks)
    if exclude_level:
        available.discard(exclude_level)
    return sorted(available)
