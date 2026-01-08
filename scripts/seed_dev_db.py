#!/usr/bin/env python
"""
Seed development database with known test data.

This script creates a complete document hierarchy with relationships:
- Resolution A/RES/78/300
- Draft A/C.3/78/L.41 (draft_of resolution)
- Committee report A/78/481 (committee_report_for resolution)
- Meetings A/78/PV.99, A/78/PV.100 (meeting_for resolution)
- Agenda item A/78/251 (agenda_item for draft)
- Utterances in meetings
- Votes on resolution

Can be run multiple times - drops existing test data first.
"""

import os
import argparse
from sqlalchemy import text
from db.config import get_session
from db.models import Document, Vote, Actor, Utterance, DocumentRelationship, UtteranceDocument

# Test data constants
TEST_RESOLUTION = "A/RES/78/300"
TEST_DRAFT = "A/C.3/78/L.41"
TEST_COMMITTEE_REPORT = "A/78/481"
TEST_MEETINGS = ["A/78/PV.99", "A/78/PV.100"]
TEST_AGENDA_ITEM = "A/78/251"

TEST_COUNTRIES = [
    "United States", "France", "China", "Russian Federation",
    "United Kingdom", "Germany", "Japan", "Brazil", "India", "South Africa"
]


def drop_test_data(session):
    """Drop all test data (idempotent)."""
    print("🗑️  Dropping existing test data...")

    # Get all test document IDs
    test_symbols = [TEST_RESOLUTION, TEST_DRAFT, TEST_COMMITTEE_REPORT, TEST_AGENDA_ITEM] + TEST_MEETINGS
    docs = session.query(Document).filter(Document.symbol.in_(test_symbols)).all()
    doc_ids = [d.id for d in docs]

    if doc_ids:
        # Delete in order due to foreign keys (cascade should handle most)
        session.query(UtteranceDocument).filter(UtteranceDocument.document_id.in_(doc_ids)).delete(synchronize_session=False)
        session.query(Utterance).filter(Utterance.meeting_id.in_(doc_ids)).delete(synchronize_session=False)
        session.query(Vote).filter(Vote.document_id.in_(doc_ids)).delete(synchronize_session=False)
        session.query(DocumentRelationship).filter(
            (DocumentRelationship.source_id.in_(doc_ids)) |
            (DocumentRelationship.target_id.in_(doc_ids))
        ).delete(synchronize_session=False)
        session.query(Document).filter(Document.symbol.in_(test_symbols)).delete(synchronize_session=False)
        session.commit()
        print(f"   Deleted {len(doc_ids)} test documents and related data")
    else:
        print("   No existing test data found")


def create_actors(session):
    """Create or get test actors (countries)."""
    print("👥 Creating actors...")
    actors = []
    for name in TEST_COUNTRIES:
        actor = session.query(Actor).filter(Actor.name == name).first()
        if not actor:
            actor = Actor(name=name, actor_type="country")
            session.add(actor)
        actors.append(actor)
    session.commit()
    print(f"   Created/found {len(actors)} actors")
    return actors


def create_documents(session):
    """Create test documents."""
    print("📄 Creating documents...")

    # 1. Resolution
    resolution = Document(
        symbol=TEST_RESOLUTION,
        doc_type="resolution",
        title="Situation of human rights in the Democratic People's Republic of Korea",
        date="2024-04-04",
        session=78,
        body_text="The General Assembly, ... [resolution text] ..."
    )
    session.add(resolution)
    session.flush()

    # 2. Draft
    draft = Document(
        symbol=TEST_DRAFT,
        doc_type="draft",
        title="Draft resolution on situation of human rights in DPRK",
        date="2024-03-15",
        session=78,
        body_text="Draft resolution text..."
    )
    session.add(draft)
    session.flush()

    # 3. Committee Report
    committee_report = Document(
        symbol=TEST_COMMITTEE_REPORT,
        doc_type="committee_report",
        title="Report of the Third Committee",
        date="2024-03-28",
        session=78,
        body_text="Committee report text..."
    )
    session.add(committee_report)
    session.flush()

    # 4. Agenda Item
    agenda_item = Document(
        symbol=TEST_AGENDA_ITEM,
        doc_type="agenda",
        title="Promotion and protection of human rights",
        date="2024-01-15",
        session=78,
        body_text="Agenda item description..."
    )
    session.add(agenda_item)
    session.flush()

    # 5. Meetings
    meetings = []
    for i, meeting_symbol in enumerate(TEST_MEETINGS):
        meeting = Document(
            symbol=meeting_symbol,
            doc_type="meeting",
            title=f"Plenary meeting {99 + i}",
            date=f"2024-04-0{3 + i}",
            session=78,
            body_text=f"Meeting {meeting_symbol} verbatim record..."
        )
        session.add(meeting)
        session.flush()
        meetings.append(meeting)

    session.commit()
    print(f"   Created 7 documents")

    return {
        "resolution": resolution,
        "draft": draft,
        "committee_report": committee_report,
        "agenda_item": agenda_item,
        "meetings": meetings
    }


def create_relationships(session, docs):
    """Create document relationships."""
    print("🔗 Creating document relationships...")

    relationships = [
        # Draft -> Resolution
        DocumentRelationship(
            source_id=docs["draft"].id,
            target_id=docs["resolution"].id,
            relationship_type="draft_of"
        ),
        # Committee Report -> Resolution
        DocumentRelationship(
            source_id=docs["committee_report"].id,
            target_id=docs["resolution"].id,
            relationship_type="committee_report_for"
        ),
        # Agenda Item -> Draft
        DocumentRelationship(
            source_id=docs["agenda_item"].id,
            target_id=docs["draft"].id,
            relationship_type="agenda_item"
        ),
    ]

    # Meetings -> Resolution
    for meeting in docs["meetings"]:
        relationships.append(
            DocumentRelationship(
                source_id=meeting.id,
                target_id=docs["resolution"].id,
                relationship_type="meeting_for"
            )
        )

    for rel in relationships:
        session.add(rel)

    session.commit()
    print(f"   Created {len(relationships)} relationships")


def create_votes(session, docs, actors):
    """Create votes on the resolution."""
    print("🗳️  Creating votes...")

    votes = []
    for i, actor in enumerate(actors):
        # Mix of vote types
        if i % 3 == 0:
            vote_type = "in_favour"
        elif i % 3 == 1:
            vote_type = "against"
        else:
            vote_type = "abstaining"

        vote = Vote(
            document_id=docs["resolution"].id,
            actor_id=actor.id,
            vote_type=vote_type,
            vote_context="plenary"
        )
        votes.append(vote)
        session.add(vote)

    session.commit()
    print(f"   Created {len(votes)} votes")

    # Count by type
    in_favour = sum(1 for v in votes if v.vote_type == "in_favour")
    against = sum(1 for v in votes if v.vote_type == "against")
    abstaining = sum(1 for v in votes if v.vote_type == "abstaining")
    print(f"     In favour: {in_favour}, Against: {against}, Abstaining: {abstaining}")


def create_utterances(session, docs, actors):
    """Create utterances in meetings with links to documents."""
    print("💬 Creating utterances...")

    utterance_count = 0

    # Meeting 1 utterances
    meeting1 = docs["meetings"][0]
    utterances_m1 = [
        {
            "speaker": actors[0],  # United States
            "text": f"We support the draft resolution {TEST_DRAFT} and urge all member states to vote in favor.",
            "agenda_item": "74(b)",
            "references": [docs["draft"], docs["resolution"]]
        },
        {
            "speaker": actors[2],  # China
            "text": f"We have concerns about this resolution and will vote against it.",
            "agenda_item": "74(b)",
            "references": [docs["resolution"]]
        },
        {
            "speaker": actors[1],  # France
            "text": f"The committee report {TEST_COMMITTEE_REPORT} clearly outlines the human rights situation.",
            "agenda_item": "74(b)",
            "references": [docs["committee_report"]]
        },
    ]

    for i, utt_data in enumerate(utterances_m1):
        utt = Utterance(
            meeting_id=meeting1.id,
            speaker_actor_id=utt_data["speaker"].id,
            speaker_name=utt_data["speaker"].name,
            speaker_affiliation=utt_data["speaker"].name,
            text=utt_data["text"],
            position_in_meeting=i + 1,
            agenda_item_number=utt_data["agenda_item"]
        )
        session.add(utt)
        session.flush()

        # Link to referenced documents
        for doc in utt_data["references"]:
            utt_doc = UtteranceDocument(
                utterance_id=utt.id,
                document_id=doc.id,
                reference_type="mentioned",
                context=utt_data["text"][:200]
            )
            session.add(utt_doc)

        utterance_count += 1

    # Meeting 2 utterances (voting)
    meeting2 = docs["meetings"][1]
    utterances_m2 = [
        {
            "speaker": actors[4],  # United Kingdom
            "text": f"We vote in favour of resolution {TEST_RESOLUTION}.",
            "agenda_item": "74(b)",
            "references": [docs["resolution"]],
            "reference_type": "voting_on"
        },
        {
            "speaker": actors[7],  # Brazil
            "text": "We abstain on this resolution.",
            "agenda_item": "74(b)",
            "references": [docs["resolution"]],
            "reference_type": "voting_on"
        },
    ]

    for i, utt_data in enumerate(utterances_m2):
        utt = Utterance(
            meeting_id=meeting2.id,
            speaker_actor_id=utt_data["speaker"].id,
            speaker_name=utt_data["speaker"].name,
            speaker_affiliation=utt_data["speaker"].name,
            text=utt_data["text"],
            position_in_meeting=i + 1,
            agenda_item_number=utt_data["agenda_item"]
        )
        session.add(utt)
        session.flush()

        # Link to referenced documents
        for doc in utt_data["references"]:
            utt_doc = UtteranceDocument(
                utterance_id=utt.id,
                document_id=doc.id,
                reference_type=utt_data.get("reference_type", "mentioned"),
                context=utt_data["text"][:200]
            )
            session.add(utt_doc)

        utterance_count += 1

    session.commit()
    print(f"   Created {utterance_count} utterances across {len(docs['meetings'])} meetings")


def verify_data(session):
    """Verify seeded data."""
    print("\n✅ Verification:")

    # Check resolution exists
    res = session.query(Document).filter(Document.symbol == TEST_RESOLUTION).first()
    print(f"   Resolution: {res.symbol} (ID: {res.id})")

    # Check relationships
    rel_count = session.query(DocumentRelationship).filter(
        (DocumentRelationship.target_id == res.id) |
        (DocumentRelationship.source_id == res.id)
    ).count()
    print(f"   Relationships: {rel_count}")

    # Check votes
    vote_count = session.query(Vote).filter(Vote.document_id == res.id).count()
    print(f"   Votes: {vote_count}")

    # Check utterances
    meetings = session.query(Document).filter(Document.symbol.in_(TEST_MEETINGS)).all()
    meeting_ids = [m.id for m in meetings]
    utt_count = session.query(Utterance).filter(Utterance.meeting_id.in_(meeting_ids)).count()
    print(f"   Utterances: {utt_count}")

    # Check utterance-document links
    utt_doc_count = session.query(UtteranceDocument).join(
        Utterance
    ).filter(Utterance.meeting_id.in_(meeting_ids)).count()
    print(f"   Utterance-Document links: {utt_doc_count}")


def main():
    parser = argparse.ArgumentParser(description="Seed dev database with test data")
    parser.add_argument(
        "--drop-only",
        action="store_true",
        help="Only drop test data, don't recreate"
    )
    args = parser.parse_args()

    # Check env
    if os.getenv('USE_DEV_DB', 'false').lower() != 'true':
        print("⚠️  Warning: USE_DEV_DB is not set to 'true'")
        print("   Set USE_DEV_DB=true in your .env file to use the dev database")
        response = input("   Continue anyway? (y/N): ")
        if response.lower() != 'y':
            print("   Aborted")
            return

    session = get_session()

    try:
        print(f"\n{'='*60}")
        print("🌱 Seeding development database")
        print(f"{'='*60}\n")

        # Always drop first (idempotent)
        drop_test_data(session)

        if args.drop_only:
            print("\n✅ Test data dropped successfully")
            return

        # Create data
        actors = create_actors(session)
        docs = create_documents(session)
        create_relationships(session, docs)
        create_votes(session, docs, actors)
        create_utterances(session, docs, actors)

        # Verify
        verify_data(session)

        print(f"\n{'='*60}")
        print("✅ Seeding complete!")
        print(f"{'='*60}\n")
        print(f"Test resolution: {TEST_RESOLUTION}")
        print(f"Test draft: {TEST_DRAFT}")
        print(f"Test meetings: {', '.join(TEST_MEETINGS)}")

    finally:
        session.close()


if __name__ == "__main__":
    main()
