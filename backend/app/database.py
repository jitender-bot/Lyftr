import os
import sqlite3
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from app.config import settings

def get_db_file_path() -> str:
    db_url = settings.DATABASE_URL
    prefix = "sqlite:///"
    if db_url.startswith(prefix):
        path = db_url[len(prefix):]
    elif db_url.startswith("sqlite://"):
        path = db_url[len("sqlite://"):]
    else:
        path = db_url
        
    # If path starts with leading slash on Windows like /C:/, handle appropriately
    if os.name == 'nt' and len(path) > 2 and path[0] == '/' and path[2] == ':':
        path = path[1:]
    return path

def get_db_connection() -> sqlite3.Connection:
    path = get_db_file_path()
    dir_name = os.path.dirname(path)
    if dir_name and not os.path.exists(dir_name):
        os.makedirs(dir_name, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL
            );
            """)
            conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages (session_id, id);
            """)
    finally:
        conn.close()

def is_db_reachable() -> bool:
    try:
        conn = get_db_connection()
        conn.execute("SELECT 1;").fetchone()
        conn.close()
        return True
    except Exception:
        return False

def session_exists(session_id: str) -> bool:
    conn = get_db_connection()
    try:
        cur = conn.execute("SELECT 1 FROM messages WHERE session_id = ? LIMIT 1;", (session_id,))
        row = cur.fetchone()
        return row is not None
    finally:
        conn.close()

def get_session_messages(session_id: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        cur = conn.execute(
            "SELECT role, content, metadata FROM messages WHERE session_id = ? ORDER BY id ASC;",
            (session_id,)
        )
        rows = cur.fetchall()
        result = []
        for row in rows:
            msg = {
                "role": row["role"],
                "content": row["content"]
            }
            if row["metadata"]:
                try:
                    msg["metadata"] = json.loads(row["metadata"])
                except Exception:
                    msg["metadata"] = None
            result.append(msg)
        return result
    finally:
        conn.close()

def add_message(session_id: str, role: str, content: str, metadata: Optional[Dict[str, Any]] = None):
    conn = get_db_connection()
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        metadata_str = json.dumps(metadata) if metadata else None
        with conn:
            conn.execute(
                """
                INSERT INTO messages (session_id, role, content, metadata, created_at)
                VALUES (?, ?, ?, ?, ?);
                """,
                (session_id, role, content, metadata_str, now_iso)
            )
    finally:
        conn.close()
