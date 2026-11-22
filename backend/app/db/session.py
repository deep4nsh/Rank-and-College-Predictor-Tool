"""
Database session and SQLite WAL-mode concurrency configuration.
Optimized for high-concurrency exam-day submission spikes, connection pooling,
and non-blocking reads/writes with 64MB cache and WAL checkpoints.
"""

import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./gate_predictor.db")

connect_args = {}
engine_kwargs = {}

if DATABASE_URL.startswith("sqlite"):
    connect_args = {
        "check_same_thread": False,
        "timeout": 30.0,  # Wait up to 30 seconds for SQLite busy lock clearance
    }
    # For file-based SQLite databases, enable QueuePool for worker thread reuse
    if ":memory:" not in DATABASE_URL:
        from sqlalchemy.pool import QueuePool
        engine_kwargs["poolclass"] = QueuePool
        engine_kwargs["pool_size"] = 25
        engine_kwargs["max_overflow"] = 25
        engine_kwargs["pool_timeout"] = 30.0
        engine_kwargs["pool_recycle"] = 1800
        engine_kwargs["pool_pre_ping"] = True

engine = create_engine(DATABASE_URL, connect_args=connect_args, **engine_kwargs)

# Enable WAL (Write-Ahead Logging), fast synchronization, and in-memory caches
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=15000")       # 15s lock contention tolerance
        cursor.execute("PRAGMA cache_size=-64000")        # 64 MB RAM page cache
        cursor.execute("PRAGMA temp_store=MEMORY")        # Fast in-memory temp tables
        cursor.execute("PRAGMA mmap_size=268435456")      # 256 MB memory-mapped I/O
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def checkpoint_db_wal():
    """
    Executes a passive WAL checkpoint to keep SQLite write-ahead log files compact.
    Safe to invoke while active readers and writers are online.
    """
    if DATABASE_URL.startswith("sqlite"):
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA wal_checkpoint(PASSIVE)")

