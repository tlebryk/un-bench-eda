#!/usr/bin/env python3
"""
Load all resolutions and meetings into database.

Usage:
    uv run python -m etl.run_etl
    uv run python -m etl.run_etl --reset
    uv run python -m etl.run_etl --resolutions-only
    uv run python -m etl.run_etl --meetings-only
"""

import argparse
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

from db.config import get_session
from db.utils import reset_database
from etl.load_resolutions import ResolutionLoader
from etl.load_meetings import MeetingLoader


def main():
    parser = argparse.ArgumentParser(description='UN Documents ETL - Quick Win MVP')
    parser.add_argument('--reset', action='store_true', help='Reset database before loading')
    parser.add_argument('--resolutions-only', action='store_true', help='Load only resolutions')
    parser.add_argument('--meetings-only', action='store_true', help='Load only meetings')
    args = parser.parse_args()

    if args.reset:
        print("⚠️  Resetting database...")
        reset_database()
        print("✅ Database reset complete\n")

    session = get_session()
    data_root = Path(os.getenv('DATA_ROOT'))

    print("="*60)
    print("UN Documents ETL - Quick Win MVP")
    print("="*60)

    # Load resolutions unless meetings-only flag is set
    if not args.meetings_only:
        print("\n📊 Loading Resolutions...")
        res_loader = ResolutionLoader(session, data_root)
        res_loader.load_all()

    # Load meetings unless resolutions-only flag is set
    if not args.resolutions_only:
        print("\n📊 Loading Meetings and Votes...")
        meeting_loader = MeetingLoader(session, data_root)
        meeting_loader.load_all()

    session.close()
    print("\n✅ ETL Complete!")


if __name__ == "__main__":
    main()
