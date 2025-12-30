#!/usr/bin/env python3
"""
Initialize database schema.

This script creates all database tables defined in db/models.py.

Usage:
    # Production database
    uv run -m db.setup_db

    # Development database
    uv run -m db.setup_db --dev

    # Reset database (drop and recreate)
    uv run -m db.setup_db --reset
    uv run -m db.setup_db --dev --reset
"""

import argparse
from db.utils import create_tables, reset_database
from db.config import get_dev_engine, engine


def main():
    parser = argparse.ArgumentParser(
        description="Initialize UN Documents database schema",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Setup production database
  uv run -m db.setup_db

  # Setup dev database
  uv run -m db.setup_db --dev

  # Reset production database (drops all tables!)
  uv run -m db.setup_db --reset

  # Reset dev database
  uv run -m db.setup_db --dev --reset
        """
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Use development database (requires DEV_DATABASE_URL in .env)"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop and recreate all tables (USE WITH CAUTION)"
    )

    args = parser.parse_args()

    # Determine which database to use
    if args.dev:
        db_engine = get_dev_engine()
        if not db_engine:
            print("❌ Error: DEV_DATABASE_URL not set in .env file")
            print("\nAdd to your .env file:")
            print("  DEV_DATABASE_URL=sqlite:///dev_data/un_documents_dev.db")
            return
        db_name = "Development"
    else:
        db_engine = engine
        db_name = "Production"

    print("=" * 60)
    print(f"UN Documents Database - {db_name} Schema Setup")
    print("=" * 60)

    try:
        if args.reset:
            print(f"\n⚠️  WARNING: This will drop all tables in {db_name.lower()} database!")
            confirm = input("Type 'yes' to continue: ")
            if confirm.lower() != 'yes':
                print("❌ Cancelled")
                return
            print(f"\nResetting {db_name.lower()} database...")
            reset_database(db_engine)
        else:
            print(f"\nCreating {db_name.lower()} database tables...")
            create_tables(db_engine)

        print(f"\n✅ {db_name} database setup complete!")

        if args.dev:
            print("\nNext steps:")
            print("  1. Run ETL on dev data: (TODO - add dev ETL workflow)")
            print("  2. Test UI with dev database")
        else:
            print("\nYou can now run the ETL script to load data:")
            print("  uv run -m etl.run_etl --reset")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        if not args.dev:
            print("\nMake sure PostgreSQL is running:")
            print("  docker-compose up -d")
        else:
            print("\nCheck your DEV_DATABASE_URL in .env file")


if __name__ == "__main__":
    main()
