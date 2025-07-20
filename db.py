import sqlite3
import json

DB_NAME = "database.db"

def connect():
    return sqlite3.connect(DB_NAME)

def init_db():
    with connect() as con:
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                score INTEGER DEFAULT 0,
                topic TEXT,
                level TEXT,
                last_daily TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                level TEXT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                explanation TEXT
            )
        """)

def get_user(user_id):
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        return cur.fetchone()

def create_or_get_user(user_id):
    if not get_user(user_id):
        with connect() as con:
            con.execute("INSERT INTO users (id) VALUES (?)", (user_id,))
    return get_user(user_id)

def update_user(user_id, field, value):
    with connect() as con:
        con.execute(f"UPDATE users SET {field} = ? WHERE id = ?", (value, user_id))

def add_score(user_id, delta):
    with connect() as con:
        con.execute("UPDATE users SET score = score + ? WHERE id = ?", (delta, user_id))

def get_user_field(user_id, field):
    with connect() as con:
        cur = con.cursor()
        cur.execute(f"SELECT {field} FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        return row[0] if row else None

def get_level_by_score(score):
    if score < 30:
        return "Новачок"
    elif score < 100:
        return "Середній"
    else:
        return "Математичний гуру"

def get_random_task(topic=None, level=None):
    with connect() as con:
        cur = con.cursor()
        query = "SELECT * FROM tasks WHERE 1=1"
        params = []
        if topic:
            query += " AND topic = ?"
            params.append(topic)
        if level:
            query += " AND level = ?"
            params.append(level)
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
                "explanation": row[5]
            }
    return None

def add_task(data):
    with connect() as con:
        con.execute("""
            INSERT INTO tasks (topic, level, question, answer, explanation)
            VALUES (?, ?, ?, ?, ?)
        """, (
            data["topic"],
            data["level"],
            data["question"],
            json.dumps(data["answer"]),
            data["explanation"]
        ))
