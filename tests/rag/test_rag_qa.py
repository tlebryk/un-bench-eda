"""Tests for RAG Q&A functionality."""

import os
import pytest
from unittest.mock import MagicMock, patch

from rag.rag_qa import (
    extract_evidence_context,
    fetch_missing_text,
    format_evidence_for_prompt,
    answer_question,
    get_value,
    MAX_RESULTS_FOR_EVIDENCE,
)


@pytest.fixture
def sample_document_results():
    """Sample document query results."""
    return {
        "columns": ["symbol", "title", "date", "doc_type", "session", "body_text"],
        "rows": [
            {
                "symbol": {"full": "A/RES/78/220", "display": "A/RES/78/220", "truncated": False},
                "title": {"full": "The situation in the Middle East", "display": "The situation...", "truncated": True},
                "date": {"full": "2023-12-19", "display": "2023-12-19", "truncated": False},
                "doc_type": {"full": "resolution", "display": "resolution", "truncated": False},
                "session": {"full": 78, "display": "78", "truncated": False},
                "body_text": {"full": "The General Assembly decides to address the situation in the Middle East...", "display": "The General Assembly...", "truncated": True}
            },
            {
                "symbol": {"full": "A/RES/78/221", "display": "A/RES/78/221", "truncated": False},
                "title": {"full": "Another resolution", "display": "Another resolution", "truncated": False},
                "date": {"full": "2023-12-20", "display": "2023-12-20", "truncated": False},
                "doc_type": {"full": "resolution", "display": "resolution", "truncated": False},
                "session": {"full": 78, "display": "78", "truncated": False},
                "body_text": {"full": "Another resolution text content...", "display": "Another resolution...", "truncated": True}
            }
        ],
        "row_count": 2,
        "truncated": False
    }


@pytest.fixture
def sample_vote_results():
    """Sample vote query results."""
    return {
        "columns": ["symbol", "vote_type", "vote_context", "name"],
        "rows": [
            {
                "symbol": {"full": "A/RES/78/220", "display": "A/RES/78/220", "truncated": False},
                "vote_type": {"full": "against", "display": "against", "truncated": False},
                "vote_context": {"full": "plenary", "display": "plenary", "truncated": False},
                "name": {"full": "United States", "display": "United States", "truncated": False}
            },
            {
                "symbol": {"full": "A/RES/78/220", "display": "A/RES/78/220", "truncated": False},
                "vote_type": {"full": "in_favour", "display": "in_favour", "truncated": False},
                "vote_context": {"full": "plenary", "display": "plenary", "truncated": False},
                "name": {"full": "France", "display": "France", "truncated": False}
            }
        ],
        "row_count": 2,
        "truncated": False
    }


@pytest.fixture
def sample_utterance_results():
    """Sample utterance query results."""
    return {
        "columns": ["id", "text", "speaker_affiliation", "speaker_name", "meeting_id", "agenda_item_number"],
        "rows": [
            {
                "id": {"full": 1, "display": "1", "truncated": False},
                "text": {"full": "We support this resolution because it addresses important issues.", "display": "We support...", "truncated": True},
                "speaker_affiliation": {"full": "Libya", "display": "Libya", "truncated": False},
                "speaker_name": {"full": "El-Sonni", "display": "El-Sonni", "truncated": False},
                "meeting_id": {"full": 100, "display": "100", "truncated": False},
                "agenda_item_number": {"full": "11", "display": "11", "truncated": False}
            }
        ],
        "row_count": 1,
        "truncated": False
    }


def test_get_value_ui_formatted():
    """Test get_value with UI-formatted data."""
    cell_data = {"full": "test value", "display": "test...", "truncated": False}
    result = get_value(cell_data)
    assert result == "test value"


def test_get_value_raw_string():
    """Test get_value with raw string."""
    result = get_value("raw string")
    assert result == "raw string"


def test_get_value_none():
    """Test get_value with None."""
    result = get_value(None)
    assert result is None


def test_extract_evidence_context_documents(sample_document_results):
    """Test extracting evidence from document results."""
    evidence = extract_evidence_context(sample_document_results)
    
    assert isinstance(evidence, list)
    assert len(evidence) == 2
    
    # Check first document
    doc1 = evidence[0]
    assert doc1["type"] == "document"
    assert doc1["symbol"] == "A/RES/78/220"
    assert "title" in doc1["data"]
    assert "date" in doc1["data"]
    assert "doc_type" in doc1["data"]
    assert "session" in doc1["data"]
    assert doc1["text"] is not None


def test_extract_evidence_context_votes(sample_vote_results):
    """Test extracting evidence from vote results."""
    evidence = extract_evidence_context(sample_vote_results)
    
    assert isinstance(evidence, list)
    assert len(evidence) == 2
    
    # Check vote evidence
    vote1 = evidence[0]
    assert vote1["type"] == "vote"
    assert vote1["symbol"] == "A/RES/78/220"
    assert vote1["data"]["vote_type"] == "against"
    assert vote1["data"]["vote_context"] == "plenary"
    assert vote1["data"]["actor"] == "United States"


def test_extract_evidence_context_utterances(sample_utterance_results):
    """Test extracting evidence from utterance results."""
    evidence = extract_evidence_context(sample_utterance_results)
    
    assert isinstance(evidence, list)
    assert len(evidence) == 1
    
    utt = evidence[0]
    assert utt["type"] == "utterance"
    assert "text" in utt
    assert utt["data"]["speaker_affiliation"] == "Libya"
    assert utt["data"]["speaker_name"] == "El-Sonni"
    assert utt["data"]["id"] == 1  # Should extract ID


def test_extract_evidence_context_empty():
    """Test extracting from empty results."""
    empty_results = {
        "columns": ["symbol"],
        "rows": [],
        "row_count": 0,
        "truncated": False
    }
    
    evidence = extract_evidence_context(empty_results)
    assert len(evidence) == 0


def test_extract_evidence_context_limits_to_max():
    """Test that extraction limits to MAX_RESULTS_FOR_EVIDENCE."""
    large_results = {
        "columns": ["symbol", "title"],
        "rows": [
            {
                "symbol": {"full": f"A/RES/78/{i}", "display": f"A/RES/78/{i}", "truncated": False},
                "title": {"full": f"Title {i}", "display": f"Title {i}", "truncated": False}
            }
            for i in range(MAX_RESULTS_FOR_EVIDENCE + 10)
        ],
        "row_count": MAX_RESULTS_FOR_EVIDENCE + 10,
        "truncated": False
    }
    
    evidence = extract_evidence_context(large_results)
    assert len(evidence) == MAX_RESULTS_FOR_EVIDENCE


def test_extract_evidence_context_raw_format():
    """Test extracting from raw (non-UI-formatted) results."""
    raw_results = {
        "columns": ["symbol", "title"],
        "rows": [
            {
                "symbol": "A/RES/78/220",
                "title": "Test Resolution"
            }
        ],
        "row_count": 1,
        "truncated": False
    }
    
    evidence = extract_evidence_context(raw_results)
    assert len(evidence) == 1
    assert evidence[0]["symbol"] == "A/RES/78/220"
    assert evidence[0]["data"]["title"] == "Test Resolution"


@patch('rag.rag_qa.get_session')
def test_fetch_missing_text_documents(mock_get_session):
    """Test fetching missing document text."""
    # Mock database session
    mock_session = MagicMock()
    mock_get_session.return_value = mock_session
    
    # Mock document query
    mock_doc = MagicMock()
    mock_doc.symbol = "A/RES/78/220"
    mock_doc.body_text = "Full resolution text here..."
    mock_session.query.return_value.filter.return_value.all.return_value = [mock_doc]
    
    result = fetch_missing_text({"A/RES/78/220"}, None)
    
    assert "A/RES/78/220" in result["documents"]
    assert result["documents"]["A/RES/78/220"] == "Full resolution text here..."
    mock_session.close.assert_called_once()


@patch('rag.rag_qa.get_session')
def test_fetch_missing_text_utterances(mock_get_session):
    """Test fetching missing utterance text."""
    mock_session = MagicMock()
    mock_get_session.return_value = mock_session
    
    # Mock utterance query
    mock_utt = MagicMock()
    mock_utt.id = 1
    mock_utt.text = "Utterance text here..."
    mock_utt.speaker_affiliation = "Libya"
    mock_utt.speaker_name = "El-Sonni"
    mock_utt.meeting_id = 100
    mock_session.query.return_value.filter.return_value.all.return_value = [mock_utt]
    
    result = fetch_missing_text(set(), {1})
    
    assert 1 in result["utterances"]
    assert result["utterances"][1]["text"] == "Utterance text here..."
    assert result["utterances"][1]["speaker_affiliation"] == "Libya"


def test_fetch_missing_text_empty():
    """Test fetching with empty sets."""
    result = fetch_missing_text(set(), None)
    assert result == {"documents": {}, "utterances": {}}


def test_format_evidence_for_prompt_documents():
    """Test formatting document evidence."""
    evidence = [
        {
            "type": "document",
            "symbol": "A/RES/78/220",
            "data": {
                "doc_type": "resolution",
                "date": "2023-12-19",
                "session": 78,
                "title": "Test Resolution"
            },
            "text": "Resolution text content..."
        }
    ]
    
    formatted = format_evidence_for_prompt(evidence)
    
    assert "A/RES/78/220" in formatted
    assert "resolution" in formatted
    assert "2023-12-19" in formatted
    assert "Test Resolution" in formatted
    assert "Resolution text content" in formatted


def test_format_evidence_for_prompt_votes():
    """Test formatting vote evidence."""
    evidence = [
        {
            "type": "vote",
            "symbol": "A/RES/78/220",
            "data": {
                "vote_type": "against",
                "vote_context": "plenary",
                "actor": "United States"
            },
            "text": None
        }
    ]
    
    formatted = format_evidence_for_prompt(evidence)
    
    assert "A/RES/78/220" in formatted
    assert "against" in formatted
    assert "plenary" in formatted
    assert "United States" in formatted


def test_format_evidence_for_prompt_utterances():
    """Test formatting utterance evidence."""
    evidence = [
        {
            "type": "utterance",
            "symbol": None,
            "data": {
                "meeting": "A/78/PV.80",
                "speaker_affiliation": "Libya",
                "speaker_name": "El-Sonni",
                "agenda_item": "11"
            },
            "text": "We support this resolution..."
        }
    ]
    
    formatted = format_evidence_for_prompt(evidence)
    
    assert "A/78/PV.80" in formatted
    assert "Libya" in formatted
    assert "El-Sonni" in formatted
    assert "We support this resolution" in formatted


def test_format_evidence_for_prompt_empty():
    """Test formatting empty evidence."""
    formatted = format_evidence_for_prompt([])
    assert "No evidence found" in formatted


def test_format_evidence_truncates_long_text():
    """Test that long text is truncated in formatting."""
    long_text = "A" * 2000
    evidence = [
        {
            "type": "document",
            "symbol": "A/RES/78/220",
            "data": {"title": "Test"},
            "text": long_text
        }
    ]
    
    formatted = format_evidence_for_prompt(evidence)
    # Should truncate and show [truncated]
    assert "[truncated]" in formatted
    assert len(formatted) < len(long_text) + 1000


@patch('rag.rag_qa.get_client')
@patch('rag.rag_qa.fetch_missing_text')
@patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
def test_answer_question_basic(mock_fetch_text, mock_get_client, sample_document_results):
    """Test basic Q&A with mocked OpenAI response."""
    # Mock fetch_missing_text to return empty (no missing text)
    mock_fetch_text.return_value = {"documents": {}, "utterances": {}}
    
    # Mock OpenAI client
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.output_text = "According to A/RES/78/220, the resolution addresses Middle East issues..."
    mock_client.responses.create.return_value = mock_response
    mock_get_client.return_value = mock_client
    
    result = answer_question(
        sample_document_results,
        "What is resolution A/RES/78/220 about?",
        "SELECT * FROM documents WHERE symbol = 'A/RES/78/220'"
    )
    
    assert isinstance(result, dict)
    assert "answer" in result
    assert "evidence" in result
    assert "sources" in result
    assert len(result["answer"]) > 10
    assert isinstance(result["evidence"], list)
    assert isinstance(result["sources"], list)
    
    # Verify OpenAI was called
    mock_client.responses.create.assert_called_once()
    call_args = mock_client.responses.create.call_args
    assert "What is resolution" in call_args.kwargs['input']
    assert "A/RES/78/220" in call_args.kwargs['input']


@patch('rag.rag_qa.get_client')
@patch('rag.rag_qa.fetch_missing_text')
@patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
def test_answer_question_fetches_missing_text(mock_fetch_text, mock_get_client):
    """Test that missing text is fetched when needed."""
    # Create results without body_text
    results_no_text = {
        "columns": ["symbol", "title"],
        "rows": [
            {
                "symbol": {"full": "A/RES/78/220", "display": "A/RES/78/220", "truncated": False},
                "title": {"full": "Test", "display": "Test", "truncated": False}
            }
        ],
        "row_count": 1,
        "truncated": False
    }
    
    # Mock fetch to return text
    mock_fetch_text.return_value = {
        "documents": {"A/RES/78/220": "Fetched text content"},
        "utterances": {}
    }
    
    # Mock OpenAI
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.output_text = "Answer"
    mock_client.responses.create.return_value = mock_response
    mock_get_client.return_value = mock_client
    
    answer_question(results_no_text, "Test question")
    
    # Should have called fetch_missing_text
    mock_fetch_text.assert_called_once()
    call_args = mock_fetch_text.call_args
    assert "A/RES/78/220" in call_args[0][0]


@patch('rag.rag_qa.get_client')
@patch('rag.rag_qa.fetch_missing_text')
@patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
def test_answer_question_empty_results(mock_fetch_text, mock_get_client):
    """Test Q&A with empty results."""
    empty_results = {
        "columns": ["symbol"],
        "rows": [],
        "row_count": 0,
        "truncated": False
    }
    
    mock_fetch_text.return_value = {"documents": {}, "utterances": {}}
    
    result = answer_question(empty_results, "Test question")
    
    assert "Insufficient data" in result["answer"]
    assert len(result["sources"]) == 0
    assert len(result["evidence"]) == 0
    # Should not call OpenAI
    mock_get_client.assert_not_called()


@patch('rag.rag_qa.get_client')
@patch('rag.rag_qa.fetch_missing_text')
@patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
def test_answer_question_extracts_sources(mock_fetch_text, mock_get_client, sample_document_results):
    """Test that sources are extracted from evidence."""
    mock_fetch_text.return_value = {"documents": {}, "utterances": {}}
    
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.output_text = "Answer"
    mock_client.responses.create.return_value = mock_response
    mock_get_client.return_value = mock_client
    
    result = answer_question(sample_document_results, "Test question")
    
    # Should extract document symbols as sources
    assert len(result["sources"]) > 0
    assert "A/RES/78/220" in result["sources"]
    assert "A/RES/78/221" in result["sources"]


@patch('rag.rag_qa.get_client')
@patch('rag.rag_qa.fetch_missing_text')
@patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
def test_answer_question_api_error(mock_fetch_text, mock_get_client, sample_document_results):
    """Test handling of API errors."""
    mock_fetch_text.return_value = {"documents": {}, "utterances": {}}
    
    mock_client = MagicMock()
    mock_client.responses.create.side_effect = Exception("API Error")
    mock_get_client.return_value = mock_client
    
    with pytest.raises(RuntimeError) as exc_info:
        answer_question(sample_document_results, "Test question")
    
    assert "Failed to answer question" in str(exc_info.value)


def test_answer_question_no_api_key(sample_document_results):
    """Test that missing API key raises appropriate error."""
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError) as exc_info:
            answer_question(sample_document_results, "Test question")
        
        assert "OPENAI_API_KEY" in str(exc_info.value)


@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY") or os.getenv("RUN_LIVE_TESTS") != "1",
    reason="Requires OPENAI_API_KEY and RUN_LIVE_TESTS=1"
)
def test_live_answer_question():
    """Test Q&A with real OpenAI API."""
    results = {
        "columns": ["symbol", "title", "body_text"],
        "rows": [
            {
                "symbol": {"full": "A/RES/78/220", "display": "A/RES/78/220", "truncated": False},
                "title": {"full": "Test Resolution", "display": "Test Resolution", "truncated": False},
                "body_text": {"full": "This is a test resolution about peace and security.", "display": "This is...", "truncated": True}
            }
        ],
        "row_count": 1,
        "truncated": False
    }
    
    result = answer_question(results, "What is this resolution about?")
    
    assert isinstance(result, dict)
    assert "answer" in result
    assert len(result["answer"]) > 10
    assert "sources" in result
    assert "A/RES/78/220" in result["sources"]

