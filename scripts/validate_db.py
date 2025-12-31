#!/usr/bin/env python3
"""
Validate database contents.

This script checks that data was loaded correctly and shows summary statistics.

Usage:
    uv run python scripts/validate_db.py
    OR
    uv run python -m scripts.validate_db
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from db.config import get_session
from db.models import Document, Actor, Vote, DocumentRelationship
from sqlalchemy import func


def main():
    session = get_session()

    print("="*60)
    print("Database Validation")
    print("="*60)

    # Count documents
    doc_count = session.query(Document).filter_by(doc_type='resolution').count()
    print(f"\n✓ Resolutions: {doc_count}")

    # Count actors
    actor_count = session.query(Actor).count()
    print(f"✓ Actors: {actor_count}")

    # Count votes
    vote_count = session.query(Vote).count()
    print(f"✓ Votes: {vote_count}")

    # Count relationships
    rel_count = session.query(DocumentRelationship).count()
    print(f"✓ Relationships: {rel_count}")

    # Sample resolutions
    print(f"\n{'='*60}")
    print("Sample Resolutions:")
    print(f"{'='*60}")

    sample_docs = session.query(Document).filter_by(doc_type='resolution').limit(5).all()
    for doc in sample_docs:
        print(f"  {doc.symbol}: {doc.title[:60]}...")

    # Top voters
    print(f"\n{'='*60}")
    print("Top 5 Most Active Voters:")
    print(f"{'='*60}")

    top_voters = session.query(
        Actor.name,
        func.count(Vote.id).label('vote_count')
    ).join(Vote).group_by(Actor.id).order_by(func.count(Vote.id).desc()).limit(5).all()

    for name, count in top_voters:
        print(f"  {name}: {count} votes")

    session.close()
    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()
