"""Tests for multi-step RAG tools - fail-to-pass approach."""

import pytest
from pathlib import Path

# Tests will fail initially until we implement the tools


@pytest.mark.integration
def test_execute_get_related_documents():
    """Test related documents tool execution - SQL-based."""
    from rag.multistep.tools import execute_get_related_documents

    result = execute_get_related_documents("A/RES/78/300")

    assert "symbol" in result
    assert result["symbol"] == "A/RES/78/300"
    assert "meetings" in result
    assert "drafts" in result
    assert "committee_reports" in result
    assert "agenda_items" in result
    assert isinstance(result["meetings"], list)
    assert isinstance(result["drafts"], list)
    assert isinstance(result["committee_reports"], list)
    assert isinstance(result["agenda_items"], list)


@pytest.mark.integration
def test_execute_get_votes():
    """Test vote tool execution."""
    from rag.multistep.tools import execute_get_votes

    result = execute_get_votes("A/RES/78/300", vote_type="against")

    assert "symbol" in result
    assert "votes" in result
    assert "against" in result["votes"]
    assert isinstance(result["votes"]["against"], list)
    assert len(result["votes"]["against"]) > 0
    assert "total_countries" in result


@pytest.mark.integration
def test_execute_get_votes_all_types():
    """Test getting all vote types without filter."""
    from rag.multistep.tools import execute_get_votes

    result = execute_get_votes("A/RES/78/300")

    assert "votes" in result
    # Should have multiple vote types
    assert len(result["votes"]) > 0


@pytest.mark.integration
def test_execute_get_utterances():
    """Test utterance tool execution."""
    from rag.multistep.tools import execute_get_utterances

    # Note: This test assumes A/78/PV.99 exists with utterances
    result = execute_get_utterances(
        meeting_symbols=["A/78/PV.99"],
        speaker_countries=["United States"]
    )

    assert "utterances" in result
    assert "count" in result
    assert isinstance(result["utterances"], list)

    if result["count"] > 0:
        # Check structure of utterances
        first_utt = result["utterances"][0]
        assert "speaker_affiliation" in first_utt
        assert "speaker_name" in first_utt
        assert "text" in first_utt
        assert "full_text" in first_utt


@pytest.mark.integration
def test_execute_get_utterances_no_country_filter():
    """Test getting all utterances from a meeting without country filter."""
    from rag.multistep.tools import execute_get_utterances

    result = execute_get_utterances(meeting_symbols=["A/78/PV.99"])

    assert "utterances" in result
    assert "count" in result


@pytest.mark.integration
def test_execute_get_related_utterances_filters_referenced_documents():
    """Ensure the related utterance tool keeps context to the requested symbol."""
    from rag.multistep.tools import execute_get_related_utterances

    symbol = "A/RES/78/190"
    result = execute_get_related_utterances(symbol)

    assert result["count"] > 0
    assert result["referenced_symbols"] == [symbol]
    assert all(utt["referenced_symbol"] == symbol for utt in result["utterances"])


@pytest.mark.integration
def test_execute_get_related_utterances_country_filter_matches_speaker_name():
    """Speaker country filter should match on either affiliation or speaker name."""
    from rag.multistep.tools import execute_get_related_utterances

    symbol = "A/RES/78/190"
    result = execute_get_related_utterances(symbol, speaker_countries=["China"], limit=25)

    assert result["count"] > 0
    assert any("China" in (utt["speaker_name"] or "") for utt in result["utterances"])


def test_tool_definitions():
    """Test that tool definitions have correct structure."""
    from rag.multistep.tools import (
        get_related_documents_tool,
        get_votes_tool,
        get_utterances_tool,
        answer_with_evidence_tool
    )

    # Check get_related_documents tool
    related_docs_tool = get_related_documents_tool()
    assert related_docs_tool["type"] == "function"
    assert related_docs_tool["name"] == "get_related_documents"
    assert "description" in related_docs_tool
    assert "parameters" in related_docs_tool
    assert "symbol" in related_docs_tool["parameters"]["properties"]

    # Check get_votes tool
    votes_tool = get_votes_tool()
    assert votes_tool["type"] == "function"
    assert votes_tool["name"] == "get_votes"
    assert "symbol" in votes_tool["parameters"]["properties"]
    assert "vote_type" in votes_tool["parameters"]["properties"]

    # Check get_utterances tool
    utt_tool = get_utterances_tool()
    assert utt_tool["type"] == "function"
    assert utt_tool["name"] == "get_utterances"
    assert "meeting_symbols" in utt_tool["parameters"]["properties"]
    assert "speaker_countries" in utt_tool["parameters"]["properties"]

    # Check answer_with_evidence tool
    answer_tool = answer_with_evidence_tool()
    assert answer_tool["type"] == "function"
    assert answer_tool["name"] == "answer_with_evidence"
