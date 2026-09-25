import sqlite3
import os

DB_PATH = "escrow.db"

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            is_banned INTEGER DEFAULT 0,
            is_admin INTEGER DEFAULT 0,
            is_super_admin INTEGER DEFAULT 0,
            credits REAL DEFAULT 0.0,
            rank INTEGER DEFAULT 0,
            total_deals INTEGER DEFAULT 0,
            total_volume REAL DEFAULT 0.0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id TEXT UNIQUE,
            buyer_id INTEGER,
            seller_id INTEGER,
            amount REAL,
            fee REAL,
            net_release REAL,
            status TEXT DEFAULT 'pending',
            escrowed_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS vouches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            deal_id TEXT,
            message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS global_stats (
            key TEXT PRIMARY KEY,
            value REAL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            action TEXT,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("INSERT OR IGNORE INTO global_stats (key, value) VALUES ('total_deals', 0)")
    c.execute("INSERT OR IGNORE INTO global_stats (key, value) VALUES ('total_volume', 0.0)")
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
    conn.close()
    return user

def create_user(user_id, username):
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO users (telegram_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    conn.close()

def update_user(user_id, **kwargs):
    conn = get_db()
    fields = ", ".join([f"{k} = ?" for k in kwargs.keys()])
    values = list(kwargs.values()) + [user_id]
    conn.execute(f"UPDATE users SET {fields} WHERE telegram_id = ?", values)
    conn.commit()
    conn.close()

def get_global_stats():
    conn = get_db()
    deals = conn.execute("SELECT value FROM global_stats WHERE key = 'total_deals'").fetchone()
    volume = conn.execute("SELECT value FROM global_stats WHERE key = 'total_volume'").fetchone()
    conn.close()
    return (deals['value'] if deals else 0, volume['value'] if volume else 0.0)

def update_global_stats(deals_delta, volume_delta):
    conn = get_db()
    conn.execute("UPDATE global_stats SET value = value + ? WHERE key = 'total_deals'", (deals_delta,))
    conn.execute("UPDATE global_stats SET value = value + ? WHERE key = 'total_volume'", (volume_delta,))
    conn.commit()
    conn.close()

def log_activity(admin_id, action, details=""):
    conn = get_db()
    conn.execute("INSERT INTO activity_log (admin_id, action, details) VALUES (?, ?, ?)", (admin_id, action, details))
    conn.commit()
    conn.close()
