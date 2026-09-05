"""DatabaseManager: SQLite connection management with WAL mode and schema initialization."""

import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Generator, Optional


SCHEMA_PATH = Path(__file__).parent / "schema.sql"
CURRENT_SCHEMA_VERSION = 1


class DatabaseManager:
    """Manages SQLite connections, pragmas, and schema initialization."""

    def __init__(self, database_path: str = ":memory:"):
        self.database_path = database_path
        self._is_memory = database_path == ":memory:"
        # Keep an open connection if in-memory so database does not vanish between calls
        self._memory_conn: Optional[sqlite3.Connection] = None
        if self._is_memory:
            self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._memory_conn.row_factory = sqlite3.Row
            self._configure_connection(self._memory_conn)
            self._init_schema_sync(self._memory_conn)
        else:
            # Ensure parent directory exists for file-based DB
            path = Path(database_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with self.get_connection() as conn:
                self._init_schema_sync(conn)

    def _configure_connection(self, conn: sqlite3.Connection) -> None:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        if not self._is_memory:
            conn.execute("PRAGMA journal_mode = WAL;")

    def _init_schema_sync(self, conn: sqlite3.Connection) -> None:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        conn.executescript(schema_sql)

        # Record schema version
        cursor = conn.execute("SELECT version FROM runtime_schema_version WHERE version = ?", (CURRENT_SCHEMA_VERSION,))
        if not cursor.fetchone():
            conn.execute(
                "INSERT INTO runtime_schema_version (version, applied_at) VALUES (?, ?)",
                (CURRENT_SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()),
            )
        conn.commit()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Provides a managed connection."""
        if self._is_memory and self._memory_conn:
            yield self._memory_conn
        else:
            conn = sqlite3.connect(self.database_path, timeout=30.0)
            self._configure_connection(conn)
            try:
                yield conn
            finally:
                conn.close()

    async def run_async(self, func, *args, **kwargs):
        """Runs a synchronous database operation on a thread."""
        return await asyncio.to_thread(func, *args, **kwargs)

    def close(self) -> None:
        if self._memory_conn:
            self._memory_conn.close()
            self._memory_conn = None
