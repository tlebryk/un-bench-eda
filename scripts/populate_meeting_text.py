#!/usr/bin/env python3
"""Populate meeting body_text with preface + all utterances"""

import os
from pathlib import Path
from db.config import get_session
from db.models import Document, Utterance
from sqlalchemy import text

session = get_session()
data_root = Path(os.getenv('DATA_ROOT', 'data'))
pdf_dir = data_root / "parsed" / "pdfs" / "meetings"

print("=" * 80)
print("Populating Meeting body_text (preface + utterances)")
print("=" * 80)

# Get all meetings
meetings = session.query(Document).filter(
    Document.doc_type == 'meeting'
).all()

print(f"\nFound {len(meetings)} meetings")

updated = 0
skipped = 0

for idx, meeting in enumerate(meetings, 1):
    if idx % 20 == 0:
        print(f"  Progress: {idx}/{len(meetings)}...")

    try:
        # Load preface from PDF
        filename = meeting.symbol.replace('/', '_').replace(' ', '_') + '.json'
        pdf_path = pdf_dir / filename

        preface = ""
        if pdf_path.exists():
            import json
            with open(pdf_path) as f:
                data = json.load(f)
                preface = data.get('preface', '')

        # Get all utterances for this meeting, ordered
        utterances = session.query(Utterance).filter(
            Utterance.meeting_id == meeting.id
        ).order_by(
            Utterance.position_in_meeting
        ).all()

        if not preface and not utterances:
            skipped += 1
            continue

        # Build full meeting text
        parts = []

        if preface:
            parts.append(preface)

        for utterance in utterances:
            # Format: Speaker (Affiliation): text
            speaker_line = f"\n{'=' * 80}\n"
            if utterance.speaker_name:
                speaker_line += f"{utterance.speaker_name}"
                if utterance.speaker_affiliation:
                    speaker_line += f" ({utterance.speaker_affiliation})"
                speaker_line += ":\n\n"
            parts.append(speaker_line + utterance.text)

        full_text = '\n\n'.join(parts)

        # Update meeting
        meeting.body_text = full_text
        updated += 1

    except Exception as e:
        print(f"  ❌ Error processing {meeting.symbol}: {e}")
        skipped += 1

# Commit
try:
    session.commit()
    print(f"\n✅ Updated: {updated}, Skipped: {skipped}")

    # Show stats
    result = session.execute(text("""
        SELECT
            COUNT(*) as total,
            COUNT(body_text) FILTER (WHERE body_text IS NOT NULL) as with_text,
            ROUND(AVG(LENGTH(body_text))) as avg_length
        FROM documents
        WHERE doc_type = 'meeting';
    """))
    row = result.fetchone()
    print(f"\nMeeting body_text stats:")
    print(f"  Total: {row[0]}, With text: {row[1]}, Avg length: {row[2]:,.0f} chars")

except Exception as e:
    session.rollback()
    print(f"\n❌ Commit failed: {e}")
    raise
finally:
    session.close()

print("\n" + "=" * 80)
