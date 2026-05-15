"""SQLite database connection and schema initialization."""

import sqlite3
from pathlib import Path

from app.core.config import settings


def get_connection() -> sqlite3.Connection:
    """
    Create a new SQLite connection with row_factory set to sqlite3.Row.
    The caller is responsible for closing the connection.
    """
    db_path = settings.task_db_file
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    return connection


def init_database() -> None:
    """
    Create tables and indexes if they do not already exist.
    
    Also performs a lightweight migration: if the tasks table was created
    before the payload_hash column existed, it adds the column now.
    """
    Path(settings.storage_dir).mkdir(parents=True, exist_ok=True)
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_hash TEXT,
                params TEXT NOT NULL,
                result TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                finished_at TEXT
            )
            """
        )
        # Lightweight migration: add payload_hash column if missing
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(tasks)").fetchall()
        }
        if "payload_hash" not in columns:
            connection.execute("ALTER TABLE tasks ADD COLUMN payload_hash TEXT")
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tasks_type_hash_status
            ON tasks (task_type, payload_hash, status)
            """
        )
        connection.commit()
