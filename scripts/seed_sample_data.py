#!/usr/bin/env python3
"""
CLI utility to seed realistic sample data into the active database
(SQLite or Cloud PostgreSQL via DATABASE_URL).
Usage:
    python scripts/seed_sample_data.py
    python scripts/seed_sample_data.py --force
"""

import sys
import argparse
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from backend.app.db.models import Base
from backend.app.db.session import engine, SessionLocal
from backend.app.db.seed import seed_database


def main():
    parser = argparse.ArgumentParser(description="Seed Physics Wallah sample student leads")
    parser.add_argument("--force", action="store_true", help="Force re-seed even if students exist")
    args = parser.parse_args()

    print(f"Connecting to database via engine: {engine.url} ...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        count = seed_database(db, force=args.force)
        print(f"Successfully populated database with {count} sample student leads and call records!")
    except Exception as e:
        print(f"Error seeding database: {e}")
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
