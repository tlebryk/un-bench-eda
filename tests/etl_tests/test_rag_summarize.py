#!/usr/bin/env python3
"""
Test script for RAG summarization functionality.

This test can run in two modes:
1. Mock mode (default): Tests the logic without calling OpenAI API
2. Live mode: Tests with real OpenAI API (requires OPENAI_API_KEY in .env)

Usage:
    # Run with mocks (no API key needed)
    uv run test_rag_summarize.py
    
    # Run with real API (requires OPENAI_API_KEY)
    uv run test_rag_summarize.py --live
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from rag_summarize import (
    summarize_results,
    extract_text_fields,
    MAX_RESULTS_FOR_SUMMARIZATION,
)


class TestRAGSummarize(unittest.TestCase):
    """Tests for RAG summarization functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.sample_resolution_results = {
            "columns": ["symbol", "title", "doc_metadata"],
            "rows": [
                {
                    "symbol": {"full": "A/RES/78/220", "display": "A/RES/78/220", "truncated": False},
                    "title": {"full": "The situation in the Middle East", "display": "The situation in the Middle East", "truncated": False},
                    "doc_metadata": {
                        "full": '{"text": "The General Assembly decides to...", "date": "2024-01-01"}',
                        "display": '{"text": "The General Assembly decides to...", "date": "2024-01-01"}',
                        "truncated": False
                    }
                },
                {
                    "symbol": {"full": "A/RES/78/221", "display": "A/RES/78/221", "truncated": False},
                    "title": {"full": "Another resolution", "display": "Another resolution", "truncated": False},
                    "doc_metadata": {
                        "full": '{"text": "Another resolution text...", "date": "2024-01-02"}',
                        "display": '{"text": "Another resolution text...", "date": "2024-01-02"}',
                        "truncated": False
                    }
                }
            ],
            "row_count": 2,
            "truncated": False
        }
        
        self.sample_utterance_results = {
            "columns": ["speaker_name", "speaker_affiliation", "text", "agenda_item_number"],
            "rows": [
                {
                    "speaker_name": {"full": "El-Sonni", "display": "El-Sonni", "truncated": False},
                    "speaker_affiliation": {"full": "Libya", "display": "Libya", "truncated": False},
                    "text": {"full": "We support this resolution because...", "display": "We support this resolution because...", "truncated": False},
                    "agenda_item_number": {"full": "11", "display": "11", "truncated": False}
                },
                {
                    "speaker_name": {"full": "Smith", "display": "Smith", "truncated": False},
                    "speaker_affiliation": {"full": "USA", "display": "USA", "truncated": False},
                    "text": {"full": "We have concerns about this resolution...", "display": "We have concerns about this resolution...", "truncated": False},
                    "agenda_item_number": {"full": "11", "display": "11", "truncated": False}
                }
            ],
            "row_count": 2,
            "truncated": False
        }
    
    def test_extract_text_fields_resolutions(self):
        """Test extracting text fields from resolution results."""
        texts = extract_text_fields(self.sample_resolution_results)
        
        self.assertIsInstance(texts, list)
        self.assertEqual(len(texts), 2)
        # Should extract text from doc_metadata JSON
        self.assertIn("The General Assembly decides to", texts[0])
        self.assertIn("Another resolution text", texts[1])
    
    def test_extract_text_fields_utterances(self):
        """Test extracting text fields from utterance results."""
        texts = extract_text_fields(self.sample_utterance_results)
        
        self.assertIsInstance(texts, list)
        self.assertEqual(len(texts), 2)
        # Should extract text from text column
        self.assertIn("We support this resolution", texts[0])
        self.assertIn("We have concerns", texts[1])
    
    def test_extract_text_fields_limits_to_max(self):
        """Test that extraction limits to MAX_RESULTS_FOR_SUMMARIZATION."""
        # Create results with more than MAX_RESULTS rows
        large_results = {
            "columns": ["text"],
            "rows": [
                {"text": {"full": f"Text {i}", "display": f"Text {i}", "truncated": False}}
                for i in range(MAX_RESULTS_FOR_SUMMARIZATION + 5)
            ],
            "row_count": MAX_RESULTS_FOR_SUMMARIZATION + 5,
            "truncated": False
        }
        
        texts = extract_text_fields(large_results)
        self.assertEqual(len(texts), MAX_RESULTS_FOR_SUMMARIZATION)
    
    def test_extract_text_fields_empty_results(self):
        """Test extracting from empty results."""
        empty_results = {
            "columns": ["text"],
            "rows": [],
            "row_count": 0,
            "truncated": False
        }
        
        texts = extract_text_fields(empty_results)
        self.assertEqual(len(texts), 0)
    
    def test_extract_text_fields_no_text_column(self):
        """Test extracting when no text column exists."""
        no_text_results = {
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
        
        texts = extract_text_fields(no_text_results)
        # Should return empty list if no text fields found
        self.assertEqual(len(texts), 0)
    
    @patch('rag_summarize.get_client')
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
    def test_summarize_results_basic(self, mock_get_client):
        """Test basic summarization with mocked OpenAI response."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.output_text = "Summary: These resolutions address Middle East issues..."
        mock_client.responses.create.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        result = summarize_results(
            self.sample_resolution_results,
            "What are these resolutions about?"
        )
        
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 10)
        # Verify OpenAI was called
        mock_client.responses.create.assert_called_once()
        call_args = mock_client.responses.create.call_args
        self.assertIn("What are these resolutions about?", call_args.kwargs['input'])
    
    @patch('rag_summarize.get_client')
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
    def test_summarize_results_utterances(self, mock_get_client):
        """Test summarization of utterance results."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.output_text = "Summary: Speakers expressed mixed views..."
        mock_client.responses.create.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        result = summarize_results(
            self.sample_utterance_results,
            "What did speakers say about this resolution?"
        )
        
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 10)
        call_args = mock_client.responses.create.call_args
        self.assertIn("What did speakers say", call_args.kwargs['input'])
        # Should include utterance texts in the prompt
        self.assertIn("We support this resolution", call_args.kwargs['input'])
    
    @patch('rag_summarize.get_client')
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
    def test_summarize_results_empty(self, mock_get_client):
        """Test summarization with empty results."""
        empty_results = {
            "columns": ["text"],
            "rows": [],
            "row_count": 0,
            "truncated": False
        }
        
        result = summarize_results(empty_results, "Test question")
        
        # Should return a message indicating no results
        self.assertIsInstance(result, str)
        self.assertIn("no results", result.lower())
        # Should not call OpenAI
        mock_get_client.assert_not_called()
    
    @patch('rag_summarize.get_client')
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
    def test_summarize_results_limits_to_max(self, mock_get_client):
        """Test that summarization limits to MAX_RESULTS_FOR_SUMMARIZATION."""
        large_results = {
            "columns": ["text"],
            "rows": [
                {"text": {"full": f"Text content {i}", "display": f"Text content {i}", "truncated": False}}
                for i in range(MAX_RESULTS_FOR_SUMMARIZATION + 10)
            ],
            "row_count": MAX_RESULTS_FOR_SUMMARIZATION + 10,
            "truncated": False
        }
        
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.output_text = "Summary"
        mock_client.responses.create.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        summarize_results(large_results, "Test question")
        
        call_args = mock_client.responses.create.call_args
        # Should only include MAX_RESULTS_FOR_SUMMARIZATION texts
        input_text = call_args.kwargs['input']
        # Count occurrences of "Text content" to verify limit
        count = input_text.count("Text content")
        self.assertLessEqual(count, MAX_RESULTS_FOR_SUMMARIZATION)
    
    @patch.dict(os.environ, {}, clear=True)
    def test_summarize_results_no_api_key(self):
        """Test that missing API key raises appropriate error."""
        with self.assertRaises(ValueError) as context:
            summarize_results(self.sample_resolution_results, "Test question")
        
        self.assertIn("OPENAI_API_KEY", str(context.exception))
    
    @patch('rag_summarize.get_client')
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
    def test_summarize_results_api_error(self, mock_get_client):
        """Test handling of API errors."""
        mock_client = MagicMock()
        mock_client.responses.create.side_effect = Exception("API Error")
        mock_get_client.return_value = mock_client
        
        with self.assertRaises(RuntimeError) as context:
            summarize_results(self.sample_resolution_results, "Test question")
        
        self.assertIn("Failed to summarize", str(context.exception))


class TestRAGSummarizeLive(unittest.TestCase):
    """Live tests that require actual OpenAI API key."""
    
    @unittest.skipUnless(
        os.getenv("OPENAI_API_KEY") and os.getenv("RUN_LIVE_TESTS") == "1",
        "Skipping live test. Set OPENAI_API_KEY and RUN_LIVE_TESTS=1 to run."
    )
    def test_live_summarize_resolutions(self):
        """Test summarization with real OpenAI API for resolutions."""
        results = {
            "columns": ["symbol", "title", "doc_metadata"],
            "rows": [
                {
                    "symbol": {"full": "A/RES/78/220", "display": "A/RES/78/220", "truncated": False},
                    "title": {"full": "Test Resolution", "display": "Test Resolution", "truncated": False},
                    "doc_metadata": {
                        "full": '{"text": "This is a test resolution about peace and security.", "date": "2024-01-01"}',
                        "display": '{"text": "This is a test resolution about peace and security.", "date": "2024-01-01"}',
                        "truncated": False
                    }
                }
            ],
            "row_count": 1,
            "truncated": False
        }
        
        result = summarize_results(results, "What is this resolution about?")
        
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 10)
        # Should mention something about the content
        self.assertIn("peace", result.lower() or "security" in result.lower())


def run_tests(live=False):
    """Run all tests."""
    if live:
        os.environ["RUN_LIVE_TESTS"] = "1"
        print("="*60)
        print("Running LIVE tests (requires OPENAI_API_KEY)")
        print("="*60)
    else:
        print("="*60)
        print("Running tests with MOCKED OpenAI API")
        print("(Set --live flag and OPENAI_API_KEY to test with real API)")
        print("="*60)
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Always run mock tests
    suite.addTests(loader.loadTestsFromTestCase(TestRAGSummarize))
    
    # Add live tests if requested
    if live:
        suite.addTests(loader.loadTestsFromTestCase(TestRAGSummarizeLive))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test RAG summarization functionality")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run live tests with real OpenAI API (requires OPENAI_API_KEY)"
    )
    args = parser.parse_args()
    
    success = run_tests(live=args.live)
    sys.exit(0 if success else 1)

