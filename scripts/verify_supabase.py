#!/usr/bin/env python3
"""Verify Supabase database contents"""

from db.config import get_session
from sqlalchemy import text

session = get_session()

print("\n" + "=" * 80)
print("Supabase Database Verification")
print("=" * 80)

# Check table counts
result = session.execute(text("""
    SELECT
        doc_type,
        COUNT(*) as total,
        COUNT(body_text) FILTER (WHERE body_text IS NOT NULL AND body_text != '') as with_text
    FROM documents
    GROUP BY doc_type
    ORDER BY doc_type;
"""))

print("\n📊 Documents by Type:")
for row in result:
    print(f"  {row[0]:20} | Total: {row[1]:4} | With body_text: {row[2]:4}")

# Check actors
result = session.execute(text("SELECT COUNT(*) FROM actors;"))
actor_count = result.scalar()
print(f"\n👥 Actors: {actor_count}")

# Check votes
result = session.execute(text("SELECT COUNT(*) FROM votes;"))
vote_count = result.scalar()
print(f"🗳️  Votes: {vote_count}")

# Check relationships
result = session.execute(text("SELECT COUNT(*) FROM document_relationships;"))
rel_count = result.scalar()
print(f"🔗 Relationships: {rel_count}")

# Check utterances
result = session.execute(text("SELECT COUNT(*) FROM utterances;"))
utt_count = result.scalar()
print(f"💬 Utterances: {utt_count}")

# Sample resolution with body_text
result = session.execute(text("""
    SELECT symbol, LENGTH(body_text) as text_length
    FROM documents
    WHERE doc_type = 'resolution' AND body_text IS NOT NULL
    ORDER BY symbol
    LIMIT 1;
"""))

row = result.fetchone()
if row:
    print(f"\n✅ Sample: {row[0]} has {row[1]:,} chars of body_text")

print("\n" + "=" * 80)

session.close()
