#!/usr/bin/env python3
"""
Load all resolutions and meetings into database.

Usage:
    # Production database
    uv run -m etl.run_etl
    uv run -m etl.run_etl --reset

    # Development database
    uv run -m etl.run_etl --dev
    uv run -m etl.run_etl --dev --reset

    # Specific data types
    uv run -m etl.run_etl --resolutions-only
    uv run -m etl.run_etl --meetings-only
"""

import argparse
from pathlib import Path
import os
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker

load_dotenv()

from db.config import get_session, engine, get_dev_engine
from db.utils import reset_database
from etl.load_resolutions import ResolutionLoader
from etl.load_meetings import MeetingLoader
from etl.load_documents import DocumentLoader


def main():
    parser = argparse.ArgumentParser(description='UN Documents ETL - Quick Win MVP')
    parser.add_argument('--reset', action='store_true', help='Reset database before loading')
    parser.add_argument('--resolutions-only', action='store_true', help='Load only resolutions')
    parser.add_argument('--meetings-only', action='store_true', help='Load only meetings')
    parser.add_argument('--documents-only', action='store_true', help='Load only drafts, committee reports, agenda items')
    parser.add_argument('--dev', action='store_true', help='Use development database and dev_data/')
    args = parser.parse_args()

    # Determine which database and data directory to use
    if args.dev:
        db_engine = get_dev_engine()
        if not db_engine:
            print("❌ Error: DEV_DATABASE_URL not set in .env file")
            return
        SessionLocal = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
        data_root = Path('dev_data')
        db_name = "Development"
    else:
        db_engine = engine
        SessionLocal = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
        data_root = Path(os.getenv('DATA_ROOT', 'data'))
        db_name = "Production"

    if args.reset:
        print(f"⚠️  Resetting {db_name.lower()} database...")
        reset_database(db_engine)
        print("✅ Database reset complete\n")

    session = SessionLocal()

    print("="*60)
    print(f"UN Documents ETL - {db_name} Database")
    print("="*60)
    print(f"Data directory: {data_root}")
    print()

    # Load resolutions unless meetings-only or documents-only flag is set
    if not args.meetings_only and not args.documents_only:
        print("\n📊 Loading Resolutions...")
        res_loader = ResolutionLoader(session, data_root)
        res_loader.load_all()

    # Load other documents unless resolutions-only or meetings-only flag is set
    if not args.resolutions_only and not args.meetings_only:
        print("\n📊 Loading Drafts...")
        draft_loader = DocumentLoader(session, data_root, 'draft')
        draft_loader.load_all()

        print("\n📊 Loading Committee Reports...")
        committee_loader = DocumentLoader(session, data_root, 'committee_report')
        committee_loader.load_all()

        print("\n📊 Loading Agenda Items...")
        agenda_loader = DocumentLoader(session, data_root, 'agenda_item')
        agenda_loader.load_all()

    # Load meetings unless resolutions-only or documents-only flag is set
    if not args.resolutions_only and not args.documents_only:
        print("\n📊 Loading Meetings and Votes...")
        meeting_loader = MeetingLoader(session, data_root)
        meeting_loader.load_all()

    session.close()
    print(f"\n✅ {db_name} ETL Complete!")


if __name__ == "__main__":
    main()
