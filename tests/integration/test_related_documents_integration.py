"""
Integration tests for get_related_documents using dev database.

Prerequisites:
1. Start dev database: docker-compose up postgres_dev
2. Set USE_DEV_DB=true in .env
3. Seed database: uv run python scripts/seed_dev_db.py

Run with: uv run pytest tests/integration/test_related_documents_integration.py -v
"""

import pytest
import os
from rag.multistep.tools import execute_get_related_documents, execute_get_utterances, execute_get_votes

# Test data constants (must match seed_dev_db.py)
TEST_RESOLUTION = "A/RES/78/300"
TEST_DRAFT = "A/C.3/78/L.41"
TEST_COMMITTEE_REPORT = "A/78/481"
TEST_MEETINGS = ["A/78/PV.99", "A/78/PV.100"]
TEST_AGENDA_ITEM = "A/78/251"


@pytest.fixture(scope="module", autouse=True)
def check_dev_db():
    """Ensure we're using dev database."""
    if os.getenv('USE_DEV_DB', 'false').lower() != 'true':
        pytest.skip("USE_DEV_DB not set - run against dev database only")


@pytest.mark.integration
class TestGetRelatedDocuments:
    """Test suite for get_related_documents function."""

    def test_get_related_documents_for_resolution(self):
        """Test getting related documents for a resolution."""
        result = execute_get_related_documents(TEST_RESOLUTION)

        assert result["symbol"] == TEST_RESOLUTION
        assert "error" not in result or not result["error"]

        # Should find the draft
        assert TEST_DRAFT in result["drafts"], f"Expected draft {TEST_DRAFT} in {result['drafts']}"

        # Should find committee report
        assert TEST_COMMITTEE_REPORT in result["committee_reports"], \
            f"Expected committee report {TEST_COMMITTEE_REPORT} in {result['committee_reports']}"

        # Should find meetings
        for meeting in TEST_MEETINGS:
            assert meeting in result["meetings"], \
                f"Expected meeting {meeting} in {result['meetings']}"

        print(f"\n✅ Found related documents:")
        print(f"   Drafts: {len(result['drafts'])}")
        print(f"   Committee Reports: {len(result['committee_reports'])}")
        print(f"   Meetings: {len(result['meetings'])}")
        print(f"   Agenda Items: {len(result['agenda_items'])}")

    def test_get_related_documents_for_draft(self):
        """Test getting related documents for a draft."""
        result = execute_get_related_documents(TEST_DRAFT)

        assert result["symbol"] == TEST_DRAFT
        assert "error" not in result or not result["error"]

        # Should find the resolution it became
        assert TEST_RESOLUTION in result["drafts"] or TEST_RESOLUTION in result.get("committee_reports", []) or \
               any(TEST_RESOLUTION in v for v in result.values() if isinstance(v, list)), \
            f"Expected to find resolution {TEST_RESOLUTION} somewhere in relationships"

        # Should find agenda item
        assert TEST_AGENDA_ITEM in result["agenda_items"], \
            f"Expected agenda item {TEST_AGENDA_ITEM} in {result['agenda_items']}"

    def test_recursive_traversal(self):
        """Test that recursive CTE traverses multiple levels."""
        # Query from draft should find both the resolution AND the meetings
        # (draft -> resolution -> meetings)
        result = execute_get_related_documents(TEST_DRAFT)

        # The recursive query should traverse:
        # Draft -> Resolution -> Meetings
        # We should find meetings in the result (either directly or through resolution)
        all_docs = (result.get("meetings", []) +
                    result.get("drafts", []) +
                    result.get("committee_reports", []) +
                    result.get("agenda_items", []))

        # Should have found multiple related documents through traversal
        assert len(all_docs) > 1, \
            f"Expected multiple related documents through recursive traversal, found: {all_docs}"

    def test_nonexistent_document(self):
        """Test querying for non-existent document."""
        result = execute_get_related_documents("A/RES/99/999")

        assert result["symbol"] == "A/RES/99/999"
        assert "error" in result
        assert result["error"] == "Document not found"
        assert result["meetings"] == []
        assert result["drafts"] == []

    def test_document_with_no_relationships(self):
        """Test document that exists but has no relationships."""
        from db.config import get_session
        from db.models import Document

        session = get_session()
        try:
            # Create a standalone document
            standalone = Document(
                symbol="A/RES/78/999",
                doc_type="resolution",
                title="Standalone test resolution",
                session=78
            )
            session.add(standalone)
            session.commit()

            # Query it
            result = execute_get_related_documents("A/RES/78/999")

            assert result["symbol"] == "A/RES/78/999"
            assert result["meetings"] == []
            assert result["drafts"] == []
            assert result["committee_reports"] == []
            assert result["agenda_items"] == []

            # Clean up
            session.delete(standalone)
            session.commit()
        finally:
            session.close()


@pytest.mark.integration
class TestChainedToolCalls:
    """Test chaining multiple tools together (orchestrator pattern)."""

    def test_resolution_to_utterances_chain(self):
        """Test: get_related_documents -> get_utterances chain."""
        # Step 1: Get related documents
        related = execute_get_related_documents(TEST_RESOLUTION)

        assert len(related["meetings"]) > 0, "Expected to find meetings"

        # Step 2: Use meeting symbols to get utterances
        utterances_result = execute_get_utterances(
            meeting_symbols=related["meetings"]
        )

        assert utterances_result["count"] > 0, "Expected to find utterances"
        assert len(utterances_result["utterances"]) > 0

        # Verify utterances have expected structure
        first_utt = utterances_result["utterances"][0]
        assert "speaker_affiliation" in first_utt
        assert "text" in first_utt
        assert "full_text" in first_utt

        print(f"\n✅ Chain test successful:")
        print(f"   Resolution: {TEST_RESOLUTION}")
        print(f"   -> Found {len(related['meetings'])} meetings")
        print(f"   -> Found {utterances_result['count']} utterances")
        print(f"   -> Sample speaker: {first_utt['speaker_affiliation']}")

    def test_resolution_to_votes_chain(self):
        """Test: get_related_documents -> get_votes chain."""
        # Step 1: Get related documents (to verify document exists)
        related = execute_get_related_documents(TEST_RESOLUTION)
        assert related["symbol"] == TEST_RESOLUTION

        # Step 2: Get votes directly on resolution
        votes_result = execute_get_votes(TEST_RESOLUTION)

        assert votes_result["symbol"] == TEST_RESOLUTION
        assert votes_result["total_countries"] > 0
        assert len(votes_result["votes"]) > 0

        # Should have multiple vote types
        vote_types = list(votes_result["votes"].keys())
        assert "in_favour" in vote_types or "against" in vote_types or "abstaining" in vote_types

        print(f"\n✅ Votes chain test successful:")
        print(f"   Resolution: {TEST_RESOLUTION}")
        print(f"   -> Total votes: {votes_result['total_countries']}")
        for vote_type, countries in votes_result["votes"].items():
            print(f"   -> {vote_type}: {len(countries)}")

    def test_full_orchestrator_pattern(self):
        """Test full pattern: resolution -> related docs -> meetings -> utterances + votes."""
        print(f"\n🔍 Full orchestrator pattern test for {TEST_RESOLUTION}:")

        # Step 1: Get related documents
        related = execute_get_related_documents(TEST_RESOLUTION)
        print(f"\n   Step 1 - Related documents:")
        print(f"     Drafts: {related['drafts']}")
        print(f"     Meetings: {related['meetings']}")
        print(f"     Committee Reports: {related['committee_reports']}")

        # Step 2: Get utterances from meetings
        if related["meetings"]:
            utterances = execute_get_utterances(meeting_symbols=related["meetings"])
            print(f"\n   Step 2 - Utterances from meetings:")
            print(f"     Count: {utterances['count']}")
            if utterances["count"] > 0:
                for i, utt in enumerate(utterances["utterances"][:3], 1):
                    print(f"     {i}. {utt['speaker_affiliation']}: {utt['text'][:80]}...")

        # Step 3: Get votes on resolution
        votes = execute_get_votes(TEST_RESOLUTION)
        print(f"\n   Step 3 - Votes:")
        print(f"     Total countries: {votes['total_countries']}")
        for vote_type, countries in votes["votes"].items():
            print(f"     {vote_type}: {countries[:3]}... ({len(countries)} total)")

        # Assertions
        assert len(related["drafts"]) > 0, "Expected to find drafts"
        assert len(related["meetings"]) > 0, "Expected to find meetings"
        assert utterances["count"] > 0, "Expected to find utterances"
        assert votes["total_countries"] > 0, "Expected to find votes"

        print(f"\n✅ Full orchestrator pattern successful!")


@pytest.mark.integration
class TestUtteranceDocumentPrecision:
    """Test precision of utterance-to-document relationships."""

    def test_utterances_linked_to_resolution(self):
        """Test that we can find utterances specifically about the resolution."""
        from db.config import get_session
        from db.models import Utterance, UtteranceDocument, Document

        session = get_session()
        try:
            # Find resolution
            resolution = session.query(Document).filter(
                Document.symbol == TEST_RESOLUTION
            ).first()
            assert resolution is not None

            # Find utterances linked to this resolution
            utterances = session.query(Utterance).join(
                UtteranceDocument,
                UtteranceDocument.utterance_id == Utterance.id
            ).filter(
                UtteranceDocument.document_id == resolution.id
            ).all()

            assert len(utterances) > 0, \
                f"Expected to find utterances linked to {TEST_RESOLUTION}"

            print(f"\n✅ Found {len(utterances)} utterances linked to {TEST_RESOLUTION}")
            for utt in utterances[:3]:
                print(f"   - {utt.speaker_name}: {utt.text[:60]}...")

        finally:
            session.close()

    def test_voting_utterances_precision(self):
        """Test that voting utterances are marked with reference_type='voting_on'."""
        from db.config import get_session
        from db.models import Utterance, UtteranceDocument, Document

        session = get_session()
        try:
            resolution = session.query(Document).filter(
                Document.symbol == TEST_RESOLUTION
            ).first()

            # Find voting utterances
            voting_utterances = session.query(Utterance).join(
                UtteranceDocument,
                UtteranceDocument.utterance_id == Utterance.id
            ).filter(
                UtteranceDocument.document_id == resolution.id,
                UtteranceDocument.reference_type == "voting_on"
            ).all()

            # Should have at least some voting utterances
            assert len(voting_utterances) > 0, \
                "Expected to find utterances with reference_type='voting_on'"

            print(f"\n✅ Found {len(voting_utterances)} voting utterances for {TEST_RESOLUTION}")
            for utt in voting_utterances:
                print(f"   - {utt.speaker_name}: {utt.text[:60]}...")

        finally:
            session.close()
