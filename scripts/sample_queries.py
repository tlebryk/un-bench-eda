#!/usr/bin/env python3
"""
Sample queries to demonstrate database capabilities.

This script shows how to query the database for various analyses.

Usage:
    uv run python scripts/sample_queries.py
    OR
    uv run python -m scripts.sample_queries
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from db.config import get_session
from db.models import Document, Actor, Vote
from sqlalchemy import func


def main():
    session = get_session()

    print("="*60)
    print("Sample Queries")
    print("="*60)

    # Query 1: How did USA vote on Iran resolution?
    print("\n1. How did USA vote on A/RES/78/220?")
    result = session.query(
        Document.symbol,
        Document.title,
        Vote.vote_type
    ).join(Vote).join(Actor).filter(
        Document.symbol == 'A/RES/78/220',
        Actor.name.ilike('%united states%')
    ).first()

    if result:
        print(f"   Resolution: {result.symbol}")
        print(f"   Title: {result.title[:60]}...")
        print(f"   Vote: {result.vote_type}")
    else:
        print("   No results found")

    # Query 2: All resolutions about Iran
    print("\n2. Resolutions containing 'Iran' in title:")
    results = session.query(
        Document.symbol,
        Document.title,
        Document.date
    ).filter(
        Document.doc_type == 'resolution',
        Document.title.ilike('%iran%')
    ).order_by(Document.date).limit(5).all()

    for symbol, title, date in results:
        print(f"   {symbol} ({date}): {title[:60]}...")

    # Query 3: Vote distribution on a resolution
    print("\n3. Vote distribution on A/RES/78/220:")
    results = session.query(
        Vote.vote_type,
        func.count(Vote.id)
    ).join(Document).filter(
        Document.symbol == 'A/RES/78/220'
    ).group_by(Vote.vote_type).all()

    for vote_type, count in results:
        print(f"   {vote_type}: {count}")

    # Query 4: Resolutions by session
    print("\n4. Resolutions by session:")
    results = session.query(
        Document.session,
        func.count(Document.id)
    ).filter(
        Document.doc_type == 'resolution'
    ).group_by(Document.session).order_by(Document.session).all()

    for session_num, count in results:
        if session_num:
            print(f"   Session {session_num}: {count} resolutions")

    # Query 5: Countries that always vote together
    print("\n5. Sample of countries that voted 'in_favour':")
    results = session.query(
        Actor.name
    ).join(Vote).filter(
        Vote.vote_type == 'in_favour'
    ).distinct().limit(10).all()

    for (name,) in results:
        print(f"   {name}")

    session.close()
    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()
