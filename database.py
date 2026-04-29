import os
import psycopg2

def db():
    return psycopg2.connect(os.getenv("DATABASE_URL"))


def create_table():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT,
            email TEXT UNIQUE,
            password TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id SERIAL PRIMARY KEY,
            username TEXT,
            user_message TEXT,
            ai_message TEXT
        )
    """)

    conn.commit()
    cur.close()
    conn.close()