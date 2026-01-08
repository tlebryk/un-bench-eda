#!/usr/bin/env python3
"""
Test script for text-to-SQL functionality.

This test can run in two modes:
1. Mock mode (default): Tests the logic without calling OpenAI API
2. Live mode: Tests with real OpenAI API (requires OPENAI_API_KEY in .env)

Usage:
    # Run with mocks (no API key needed)
    uv run test_text_to_sql.py
    
    # Run with real API (requires OPENAI_API_KEY)
    uv run test_text_to_sql.py --live
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from text_to_sql import generate_sql, SCHEMA_DESCRIPTION, SYSTEM_PROMPT


class TestTextToSQL(unittest.TestCase):
    """Tests for text-to-SQL functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_queries = [
            "Show me all resolutions where USA voted against",
            "Find all documents from session 78",
            "What did Libya say about resolution A/RES/78/220?",
            "List all votes for resolution A/RES/78/220",
        ]
    
    def test_schema_description_exists(self):
        """Test that schema description is properly formatted."""
        self.assertIsInstance(SCHEMA_DESCRIPTION, str)
        self.assertIn("documents", SCHEMA_DESCRIPTION.lower())
        self.assertIn("votes", SCHEMA_DESCRIPTION.lower())
        self.assertIn("actors", SCHEMA_DESCRIPTION.lower())
        self.assertGreater(len(SCHEMA_DESCRIPTION), 100)
    
    def test_system_prompt_exists(self):
        """Test that system prompt is properly formatted."""
        self.assertIsInstance(SYSTEM_PROMPT, str)
        self.assertIn("PostgreSQL", SYSTEM_PROMPT)
        self.assertIn("SELECT", SYSTEM_PROMPT)
        self.assertGreater(len(SYSTEM_PROMPT), 50)
    
    @patch('text_to_sql.get_client')
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
    def test_generate_sql_basic(self, mock_get_client):
        """Test basic SQL generation with mocked OpenAI response."""
        # Mock OpenAI client and response
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "SELECT * FROM documents WHERE doc_type = 'resolution';"
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        result = generate_sql("Show me all resolutions")
        
        self.assertIsInstance(result, str)
        self.assertIn("SELECT", result.upper())
        # Verify OpenAI was called
        mock_client.chat.completions.create.assert_called_once()
        call_args = mock_client.chat.completions.create.call_args
        self.assertEqual(call_args.kwargs['model'], 'gpt-5-mini-2025-08-07')
        # self.assertEqual(call_args.kwargs['temperature'], 0.1)
    
    @patch('text_to_sql.get_client')
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
    def test_generate_sql_removes_markdown(self, mock_get_client):
        """Test that markdown code blocks are removed from response."""
        test_cases = [
            ("```sql\nSELECT * FROM documents;\n```", "SELECT * FROM documents;"),
            ("```\nSELECT * FROM documents;\n```", "SELECT * FROM documents;"),
            ("SELECT * FROM documents;", "SELECT * FROM documents;"),
        ]
        
        for input_sql, expected_output in test_cases:
            with self.subTest(input_sql=input_sql):
                mock_client = MagicMock()
                mock_response = MagicMock()
                mock_response.choices = [MagicMock()]
                mock_response.choices[0].message.content = input_sql
                mock_client.chat.completions.create.return_value = mock_response
                mock_get_client.return_value = mock_client
                
                result = generate_sql("test query")
                self.assertEqual(result.strip(), expected_output.strip())
    
    @patch.dict(os.environ, {}, clear=True)
    def test_generate_sql_no_api_key(self):
        """Test that missing API key raises appropriate error."""
        with self.assertRaises(ValueError) as context:
            generate_sql("test query")
        
        self.assertIn("OPENAI_API_KEY", str(context.exception))
    
    @patch('text_to_sql.get_client')
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
    def test_generate_sql_api_error(self, mock_get_client):
        """Test handling of API errors."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API Error")
        mock_get_client.return_value = mock_client
        
        with self.assertRaises(RuntimeError) as context:
            generate_sql("test query")
        
        self.assertIn("Failed to generate SQL", str(context.exception))
    
    @patch('text_to_sql.get_client')
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
    def test_generate_sql_custom_model(self, mock_get_client):
        """Test that custom model can be specified."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "SELECT 1;"
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        generate_sql("test", model="gpt-4")
        
        call_args = mock_client.chat.completions.create.call_args
        self.assertEqual(call_args.kwargs['model'], 'gpt-4')
    
    @patch('text_to_sql.get_client')
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
    def test_generate_sql_prompt_structure(self, mock_get_client):
        """Test that prompts are structured correctly."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "SELECT 1;"
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        generate_sql("Show me all resolutions")
        
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs['messages']
        
        # Check message structure
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]['role'], 'system')
        self.assertEqual(messages[1]['role'], 'user')
        self.assertIn("Show me all resolutions", messages[1]['content'])
        self.assertIn(SCHEMA_DESCRIPTION, messages[0]['content'])


class TestTextToSQLLive(unittest.TestCase):
    """Live tests that require actual OpenAI API key."""
    
    @unittest.skipUnless(
        os.getenv("OPENAI_API_KEY") and os.getenv("RUN_LIVE_TESTS") == "1",
        "Skipping live test. Set OPENAI_API_KEY and RUN_LIVE_TESTS=1 to run."
    )
    def test_live_generate_sql(self):
        """Test SQL generation with real OpenAI API."""
        query = "Show me all resolutions from session 78"
        result = generate_sql(query)
        
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 10)
        # Should be valid SQL (starts with SELECT, WITH, or EXPLAIN)
        result_upper = result.strip().upper()
        self.assertTrue(
            result_upper.startswith("SELECT") or 
            result_upper.startswith("WITH") or 
            result_upper.startswith("EXPLAIN"),
            f"Generated SQL doesn't start with SELECT/WITH/EXPLAIN: {result}"
        )
        # Should not contain markdown
        self.assertNotIn("```", result)
    
    @unittest.skipUnless(
        os.getenv("OPENAI_API_KEY") and os.getenv("RUN_LIVE_TESTS") == "1",
        "Skipping live test. Set OPENAI_API_KEY and RUN_LIVE_TESTS=1 to run."
    )
    def test_live_multiple_queries(self):
        """Test multiple queries to ensure consistency."""
        queries = [
            "Find all resolutions",
            "Show votes for resolution A/RES/78/220",
            "List all actors",
        ]
        
        results = []
        for query in queries:
            result = generate_sql(query)
            results.append(result)
            self.assertIsInstance(result, str)
            self.assertGreater(len(result), 10)
        
        # All results should be different
        self.assertEqual(len(set(results)), len(results), "All queries should generate different SQL")


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
    suite.addTests(loader.loadTestsFromTestCase(TestTextToSQL))
    
    # Add live tests if requested
    if live:
        suite.addTests(loader.loadTestsFromTestCase(TestTextToSQLLive))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test text-to-SQL functionality")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run live tests with real OpenAI API (requires OPENAI_API_KEY)"
    )
    args = parser.parse_args()
    
    success = run_tests(live=args.live)
    sys.exit(0 if success else 1)

