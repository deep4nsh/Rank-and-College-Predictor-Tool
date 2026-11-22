"""
Database session and SQLite WAL-mode concurrency configuration.
Optimized for high-concurrency exam-day submission spikes, connection pooling,
and non-blocking reads/writes with 64MB cache and WAL checkpoints.
"""

import os
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

# Automatically load .env file if present in workspace root
_env_path = Path(__file__).resolve().parents[3] / ".env"
if _env_path.exists():
    with open(_env_path, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                _val = _v.strip().strip("'\"")
                os.environ.setdefault(_k.strip(), _val)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./gate_predictor.db")

# Normalize cloud Postgres URLs (Render/Heroku sometimes use postgres:// which SQLAlchemy 2.0 rejects)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

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
else:
    # Production Cloud PostgreSQL connection pooling
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20
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

