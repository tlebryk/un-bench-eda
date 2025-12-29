#!/usr/bin/env python3
"""
Initialize database schema.

This script creates all database tables defined in db/models.py.

Usage:
    uv run python scripts/setup_db.py
    OR
    uv run python -m scripts.setup_db
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from db.utils import create_tables

if __name__ == "__main__":
    print("="*60)
    print("UN Documents Database - Schema Setup")
    print("="*60)
    print("\nCreating database tables...")

    try:
        create_tables()
        print("\n✅ Database setup complete!")
        print("\nYou can now run the ETL script to load data:")
        print("  uv run python -m etl.run_etl --reset")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure PostgreSQL is running:")
        print("  docker-compose up -d")
