"""Working tests for RAG functionality - written by someone who doesn't suck."""

import os
import pytest
from unittest.mock import MagicMock, patch

from rag.rag_qa import (
    extract_evidence_context,
    format_evidence_for_prompt,
    answer_question,
    get_value,
)
from rag.rag_summarize import (
    summarize_results,
    extract_text_fields,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def sample_document_results():
    """Sample document query results in UI format."""
    return {
        "columns": ["symbol", "title", "date", "body_text"],
        "rows": [
            {
                "symbol": {"full": "A/RES/78/220", "display": "A/RES/78/220", "truncated": False},
                "title": {"full": "Situation in Middle East", "display": "Situation...", "truncated": True},
                "date": {"full": "2023-12-19", "display": "2023-12-19", "truncated": False},
                "body_text": {"full": "The General Assembly decides...", "display": "The General...", "truncated": True}
            }
        ],
        "row_count": 1,
        "truncated": False
    }


@pytest.fixture
def sample_vote_results():
    """Sample vote query results."""
    return {
        "columns": ["symbol", "vote_type", "name"],
        "rows": [
            {
                "symbol": {"full": "A/RES/78/220", "display": "A/RES/78/220", "truncated": False},
                "vote_type": {"full": "against", "display": "against", "truncated": False},
                "name": {"full": "United States", "display": "United States", "truncated": False}
            }
        ],
        "row_count": 1,
        "truncated": False
    }


# =============================================================================
# UTILITY FUNCTION TESTS
# =============================================================================

def test_get_value_with_ui_format():
    """Test get_value extracts from UI format."""
    assert get_value({"full": "test", "display": "...", "truncated": True}) == "test"


def test_get_value_with_raw_string():
    """Test get_value handles raw strings."""
    assert get_value("raw string") == "raw string"


def test_get_value_with_none():
    """Test get_value handles None."""
    assert get_value(None) is None


def test_get_value_with_number():
    """Test get_value handles numbers."""
    assert get_value(42) == 42


# =============================================================================
# EVIDENCE EXTRACTION TESTS
# =============================================================================

def test_extract_evidence_from_documents(sample_document_results):
    """Test extracting evidence from document results."""
    evidence = extract_evidence_context(sample_document_results)

    assert len(evidence) == 1
    assert evidence[0]["type"] == "document"
    assert evidence[0]["symbol"] == "A/RES/78/220"
    assert evidence[0]["data"]["title"] == "Situation in Middle East"
    assert evidence[0]["data"]["date"] == "2023-12-19"
    assert evidence[0]["text"] == "The General Assembly decides..."


def test_extract_evidence_from_votes(sample_vote_results):
    """Test extracting evidence from vote results."""
    evidence = extract_evidence_context(sample_vote_results)

    assert len(evidence) == 1
    assert evidence[0]["type"] == "vote"
    assert evidence[0]["symbol"] == "A/RES/78/220"
    assert evidence[0]["data"]["vote_type"] == "against"
    assert evidence[0]["data"]["actor"] == "United States"


def test_extract_evidence_from_empty_results():
    """Test extracting from empty results."""
    empty = {"columns": [], "rows": [], "row_count": 0, "truncated": False}
    evidence = extract_evidence_context(empty)
    assert len(evidence) == 0


def test_extract_evidence_respects_max_limit():
    """Test that extraction respects max_results limit."""
    many_rows = {
        "columns": ["symbol"],
        "rows": [{"symbol": {"full": f"A/RES/78/{i}", "display": f"A/RES/78/{i}", "truncated": False}}
                 for i in range(100)],
        "row_count": 100,
        "truncated": False
    }

    evidence = extract_evidence_context(many_rows, max_results=5)
    assert len(evidence) == 5


# =============================================================================
# FORMATTING TESTS
# =============================================================================

def test_format_evidence_for_documents():
    """Test formatting document evidence for prompts."""
    evidence = [{
        "type": "document",
        "symbol": "A/RES/78/220",
        "data": {"title": "Test", "date": "2023-12-19"},
        "text": "Document text..."
    }]

    formatted = format_evidence_for_prompt(evidence)
    assert "A/RES/78/220" in formatted
    assert "Test" in formatted
    assert "2023-12-19" in formatted
    assert "Document text" in formatted


def test_format_evidence_for_votes():
    """Test formatting vote evidence for prompts."""
    evidence = [{
        "type": "vote",
        "symbol": "A/RES/78/220",
        "data": {"vote_type": "against", "actor": "USA"},
        "text": None
    }]

    formatted = format_evidence_for_prompt(evidence)
    assert "A/RES/78/220" in formatted
    assert "against" in formatted
    assert "USA" in formatted


def test_format_evidence_empty():
    """Test formatting empty evidence."""
    formatted = format_evidence_for_prompt([])
    assert "No evidence found" in formatted


def test_format_evidence_truncates_long_text():
    """Test that long text is truncated."""
    evidence = [{
        "type": "document",
        "symbol": "A/RES/78/220",
        "data": {},
        "text": "A" * 3000  # Very long text
    }]

    formatted = format_evidence_for_prompt(evidence)
    assert "[truncated]" in formatted
    assert len(formatted) < 3500  # Should be truncated


# =============================================================================
# ANSWER QUESTION TESTS
# =============================================================================

def test_answer_question_with_empty_results():
    """Test answering with no data returns insufficient data message."""
    empty = {"columns": [], "rows": [], "row_count": 0, "truncated": False}

    result = answer_question(empty, "What is this about?")

    assert "Insufficient data" in result["answer"]
    assert len(result["sources"]) == 0
    assert len(result["evidence"]) == 0


@patch('rag.rag_qa.get_client')
def test_answer_question_with_mocked_api(mock_get_client, sample_document_results):
    """Test answer_question with mocked OpenAI API."""
    # Mock the OpenAI client
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_message = MagicMock()
    mock_message.content = "According to A/RES/78/220, this resolution addresses the Middle East situation."
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response
    mock_get_client.return_value = mock_client

    result = answer_question(sample_document_results, "What is this about?", "SELECT * FROM documents")

    assert "answer" in result
    assert "evidence" in result
    assert "sources" in result
    assert len(result["answer"]) > 0
    assert "A/RES/78/220" in result["sources"]

    # Verify OpenAI was called with correct API
    mock_client.chat.completions.create.assert_called_once()
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4o-mini"
    assert "messages" in call_kwargs
    assert len(call_kwargs["messages"]) == 1
    assert call_kwargs["messages"][0]["role"] == "user"


@patch('rag.rag_qa.get_client')
def test_answer_question_extracts_sources(mock_get_client, sample_document_results):
    """Test that answer_question extracts document symbols as sources."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_message = MagicMock()
    mock_message.content = "Test answer"
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response
    mock_get_client.return_value = mock_client

    result = answer_question(sample_document_results, "Test")

    assert "A/RES/78/220" in result["sources"]


# =============================================================================
# SUMMARIZATION TESTS
# =============================================================================

def test_extract_text_fields_from_documents(sample_document_results):
    """Test extracting text fields from document results."""
    texts = extract_text_fields(sample_document_results)

    assert len(texts) == 1
    assert texts[0] == "The General Assembly decides..."


def test_extract_text_fields_from_empty():
    """Test extracting from empty results."""
    empty = {"columns": [], "rows": [], "row_count": 0, "truncated": False}
    texts = extract_text_fields(empty)
    assert len(texts) == 0


def test_extract_text_fields_respects_limit():
    """Test that text extraction respects MAX_RESULTS limit."""
    from rag.rag_summarize import MAX_RESULTS_FOR_SUMMARIZATION

    many_rows = {
        "columns": ["body_text"],
        "rows": [{"body_text": {"full": f"Text {i}", "display": f"Text {i}", "truncated": False}}
                 for i in range(20)],
        "row_count": 20,
        "truncated": False
    }

    texts = extract_text_fields(many_rows)
    assert len(texts) == MAX_RESULTS_FOR_SUMMARIZATION


@patch('rag.rag_summarize.get_client')
def test_summarize_results_with_mocked_api(mock_get_client, sample_document_results):
    """Test summarize_results with mocked OpenAI API."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_message = MagicMock()
    mock_message.content = "This resolution addresses the Middle East situation."
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response
    mock_get_client.return_value = mock_client

    summary = summarize_results(sample_document_results, "What is this about?")

    assert len(summary) > 0
    assert "Middle East" in summary

    # Verify correct API was used
    mock_client.chat.completions.create.assert_called_once()
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4o-mini"
    assert "messages" in call_kwargs


def test_summarize_results_with_no_text():
    """Test summarization when no text is found."""
    no_text = {
        "columns": ["id"],
        "rows": [{"id": {"full": 1, "display": "1", "truncated": False}}],
        "row_count": 1,
        "truncated": False
    }

    summary = summarize_results(no_text, "Test")
    assert "No results" in summary


# =============================================================================
# INTEGRATION-LIKE TESTS (still mocked but closer to real workflow)
# =============================================================================

@patch('rag.rag_qa.get_client')
def test_full_qa_workflow(mock_get_client):
    """Test complete Q&A workflow from query results to answer."""
    # Setup mock
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_message = MagicMock()
    mock_message.content = "The USA voted against resolution A/RES/78/220 in the plenary."
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response
    mock_get_client.return_value = mock_client

    # Simulate query results from a vote query
    query_results = {
        "columns": ["symbol", "vote_type", "name", "vote_context"],
        "rows": [{
            "symbol": {"full": "A/RES/78/220", "display": "A/RES/78/220", "truncated": False},
            "vote_type": {"full": "against", "display": "against", "truncated": False},
            "name": {"full": "United States", "display": "United States", "truncated": False},
            "vote_context": {"full": "plenary", "display": "plenary", "truncated": False}
        }],
        "row_count": 1,
        "truncated": False
    }

    question = "How did the USA vote on A/RES/78/220?"
    sql = "SELECT symbol, vote_type, name, vote_context FROM votes..."

    result = answer_question(query_results, question, sql)

    # Verify structure
    assert "answer" in result
    assert "evidence" in result
    assert "sources" in result

    # Verify content
    assert "USA" in result["answer"] or "United States" in result["answer"]
    assert "A/RES/78/220" in result["sources"]
    assert len(result["evidence"]) > 0
    assert result["evidence"][0]["type"] == "vote"
