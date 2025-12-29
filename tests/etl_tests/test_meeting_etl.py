#!/usr/bin/env python3
"""
Test script to verify meeting ETL with A_78_PV.80.json

This script:
1. Loads the specific meeting file
2. Verifies utterances are stored correctly
3. Verifies document links are created
4. Shows sample queries for tracing genealogy

Usage:
    uv run python test_meeting_etl.py
"""

import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

load_dotenv()

from db.config import get_session
from db.models import Document, Utterance, UtteranceDocument, Actor
from etl.load_meetings import MeetingLoader
from sqlalchemy import func


def test_meeting_etl():
    """Test loading A_78_PV.80 meeting"""
    session = get_session()
    data_root = Path(os.getenv('DATA_ROOT', 'data'))
    
    print("="*60)
    print("Testing Meeting ETL - A_78_PV.80")
    print("="*60)
    
    # Load the specific meeting
    meeting_file = data_root / "parsed" / "pdfs" / "meetings" / "A_78_PV.80.json"
    
    if not meeting_file.exists():
        print(f"❌ Meeting file not found: {meeting_file}")
        return
    
    print(f"\n📄 Loading meeting: {meeting_file.name}")
    loader = MeetingLoader(session, data_root)
    loader.load_meeting(meeting_file)
    
    try:
        session.commit()
        print("✅ Meeting loaded successfully")
    except Exception as e:
        session.rollback()
        print(f"❌ Error loading meeting: {e}")
        return
    
    # Verify data was loaded
    print("\n" + "="*60)
    print("Verification Queries")
    print("="*60)
    
    # 1. Check meeting document
    meeting_doc = session.query(Document).filter_by(symbol="A/78/PV.80").first()
    if meeting_doc:
        print(f"\n✅ Meeting document found: {meeting_doc.symbol}")
        print(f"   Type: {meeting_doc.doc_type}")
        print(f"   Title: {meeting_doc.title}")
    else:
        print("\n❌ Meeting document not found")
        return
    
    # 2. Check utterances
    utterances = session.query(Utterance).filter_by(meeting_id=meeting_doc.id).all()
    print(f"\n✅ Found {len(utterances)} utterances")
    
    # Show sample utterances
    print("\n📝 Sample utterances:")
    for i, utt in enumerate(utterances[:5], 1):
        speaker_info = f"{utt.speaker_name}"
        if utt.speaker_affiliation:
            speaker_info += f" ({utt.speaker_affiliation})"
        print(f"   {i}. {speaker_info}: {utt.text[:100]}...")
        print(f"      Agenda item: {utt.agenda_item_number}, Position: {utt.position_in_meeting}")
    
    # 3. Check document links
    doc_links = session.query(UtteranceDocument).join(Utterance).filter(
        Utterance.meeting_id == meeting_doc.id
    ).all()
    
    print(f"\n✅ Found {len(doc_links)} document links")
    
    # Group by document
    from collections import defaultdict
    doc_counts = defaultdict(int)
    for link in doc_links:
        doc = session.query(Document).filter_by(id=link.document_id).first()
        if doc:
            doc_counts[doc.symbol] += 1
    
    print("\n📎 Documents referenced in utterances:")
    for doc_symbol, count in sorted(doc_counts.items()):
        print(f"   {doc_symbol}: {count} mentions")
    
    # 4. Test genealogy query - find all utterances about A/78/L.56
    print("\n" + "="*60)
    print("Genealogy Test: Find all utterances about A/78/L.56")
    print("="*60)
    
    draft_doc = session.query(Document).filter_by(symbol="A/78/L.56").first()
    if draft_doc:
        print(f"\n✅ Found draft: {draft_doc.symbol}")
        
        # Find utterances that reference this draft
        draft_utterances = session.query(Utterance).join(UtteranceDocument).filter(
            UtteranceDocument.document_id == draft_doc.id
        ).all()
        
        print(f"\n📝 Found {len(draft_utterances)} utterances about {draft_doc.symbol}:")
        for utt in draft_utterances:
            speaker_info = f"{utt.speaker_name}"
            if utt.speaker_affiliation:
                speaker_info += f" ({utt.speaker_affiliation})"
            print(f"\n   Speaker: {speaker_info}")
            print(f"   Agenda item: {utt.agenda_item_number}")
            print(f"   Text preview: {utt.text[:200]}...")
    else:
        print(f"\n⚠️  Draft A/78/L.56 not found in database")
        print("   (You may need to load drafts first)")
    
    # 5. Test resolution link - find utterances about resolution 78/281
    print("\n" + "="*60)
    print("Genealogy Test: Find utterances about resolution 78/281")
    print("="*60)
    
    resolution_doc = session.query(Document).filter_by(symbol="A/RES/78/281").first()
    if resolution_doc:
        print(f"\n✅ Found resolution: {resolution_doc.symbol}")
        
        # Find utterances that reference this resolution
        res_utterances = session.query(Utterance).join(UtteranceDocument).filter(
            UtteranceDocument.document_id == resolution_doc.id
        ).all()
        
        print(f"\n📝 Found {len(res_utterances)} utterances about {resolution_doc.symbol}:")
        for utt in res_utterances:
            speaker_info = f"{utt.speaker_name}"
            if utt.speaker_affiliation:
                speaker_info += f" ({utt.speaker_affiliation})"
            print(f"\n   Speaker: {speaker_info}")
            print(f"   Agenda item: {utt.agenda_item_number}")
            print(f"   Text preview: {utt.text[:200]}...")
    else:
        print(f"\n⚠️  Resolution A/RES/78/281 not found in database")
        print("   (You may need to load resolutions first)")
    
    # 6. Show SQL queries for UI
    print("\n" + "="*60)
    print("Sample SQL Queries for UI")
    print("="*60)
    
    print("""
-- Find all utterances about a specific draft
SELECT 
    u.id,
    u.speaker_name,
    u.speaker_affiliation,
    u.agenda_item_number,
    u.text,
    d.symbol as referenced_document
FROM utterances u
JOIN utterance_documents ud ON ud.utterance_id = u.id
JOIN documents d ON d.id = ud.document_id
WHERE d.symbol = 'A/78/L.56'
ORDER BY u.position_in_meeting;

-- Find all utterances about a specific resolution
SELECT 
    u.id,
    u.speaker_name,
    u.speaker_affiliation,
    u.agenda_item_number,
    u.text,
    d.symbol as referenced_document
FROM utterances u
JOIN utterance_documents ud ON ud.utterance_id = u.id
JOIN documents d ON d.id = ud.document_id
WHERE d.symbol = 'A/RES/78/281'
ORDER BY u.position_in_meeting;

-- Find all utterances in a specific agenda item
SELECT 
    u.id,
    u.speaker_name,
    u.speaker_affiliation,
    u.text,
    m.symbol as meeting_symbol
FROM utterances u
JOIN documents m ON m.id = u.meeting_id
WHERE u.agenda_item_number = '11'
ORDER BY u.position_in_meeting;

-- Trace genealogy: from resolution to all related utterances
WITH resolution_tree AS (
    -- Start with the resolution
    SELECT id, symbol, doc_type
    FROM documents
    WHERE symbol = 'A/RES/78/281'
    
    UNION
    
    -- Find all related documents (drafts, etc.)
    SELECT d.id, d.symbol, d.doc_type
    FROM documents d
    JOIN document_relationships dr ON dr.target_id = d.id
    JOIN resolution_tree rt ON rt.id = dr.source_id
)
SELECT 
    u.id,
    u.speaker_name,
    u.speaker_affiliation,
    u.agenda_item_number,
    u.text,
    d.symbol as referenced_document,
    m.symbol as meeting_symbol
FROM utterances u
JOIN utterance_documents ud ON ud.utterance_id = u.id
JOIN resolution_tree rt ON rt.id = ud.document_id
JOIN documents d ON d.id = ud.document_id
JOIN documents m ON m.id = u.meeting_id
ORDER BY u.position_in_meeting;
    """)
    
    session.close()
    print("\n✅ Test complete!")


if __name__ == "__main__":
    test_meeting_etl()

