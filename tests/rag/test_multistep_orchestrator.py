import pytest
import os
import json
from unittest.mock import MagicMock, patch
from rag.multistep.orchestrator import MultiStepOrchestrator

# Mock response classes for OpenAI client mocking
class MockFunctionCall:
    def __init__(self, name, arguments):
        self.type = "function_call"
        self.name = name
        self.arguments = json.dumps(arguments)
        self.call_id = "call_123"

class MockResponse:
    def __init__(self, output):
        self.output = output
        self.output_text = ""

@pytest.fixture
def mock_client():
    with patch("rag.multistep.orchestrator.OpenAI") as mock_openai:
        client_instance = MagicMock()
        mock_openai.return_value = client_instance
        yield client_instance

def test_orchestrator_initialization(mock_client):
    """Test that orchestrator initializes correctly."""
    orchestrator = MultiStepOrchestrator()
    assert len(orchestrator.tools) == 4
    assert "get_trajectory" in orchestrator.executors
    assert "get_votes" in orchestrator.executors

@patch("rag.rag_qa.answer_question")
def test_orchestrator_flow_mock(mock_answer_question, mock_client):
    """Test the orchestration flow with mocked OpenAI responses."""
    # Setup the mock sequence of responses
    
    # Response 1: Call get_votes
    response1 = MockResponse([
        MockFunctionCall("get_votes", {"symbol": "A/RES/78/220", "vote_type": "against"})
    ])
    
    # Response 2: Call answer_with_evidence
    response2 = MockResponse([
        MockFunctionCall("answer_with_evidence", {"ready": True})
    ])
    
    # Configure client.responses.create to return these in sequence
    mock_client.responses.create.side_effect = [response1, response2]
    
    # Mock tool execution
    with patch("rag.multistep.orchestrator.execute_get_votes") as mock_votes:
        mock_votes.return_value = {
            "symbol": "A/RES/78/220",
            "votes": {"against": ["CountryA", "CountryB"]},
            "total_countries": 2
        }
        
        # Mock final synthesis
        mock_answer_question.return_value = {
            "answer": "Countries A and B voted against.",
            "evidence": [],
            "sources": ["A/RES/78/220"]
        }
        
        orchestrator = MultiStepOrchestrator()
        result = orchestrator.answer_multistep("Who voted against?")
        
        # Verify tool was called
        mock_votes.assert_called_once()
        
        # Verify synthesis was called
        mock_answer_question.assert_called_once()
        
        # Verify result structure
        assert result["answer"] == "Countries A and B voted against."
        assert len(result["steps"]) == 1
        assert result["steps"][0]["tool"] == "get_votes"

@pytest.mark.skip(reason="OpenAI library broken in this env (missing jiter)")
@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="Requires OpenAI API key")
def test_orchestrator_why_vote_query_integration():
    """
    End-to-end integration test: LLM selects tools for 'why vote' question.
    NOTE: This requires a working database with A/RES/78/220 data.
    """
    orchestrator = MultiStepOrchestrator()
    result = orchestrator.answer_multistep(
        "Why did countries vote against A/RES/78/220?"
    )

    assert "answer" in result
    assert "steps" in result
    
    # Check that tools were called (we expect at least get_votes or get_trajectory)
    tool_names = [step["tool"] for step in result["steps"]]
    
    # We can't strictly assert exact sequence as LLM might vary, 
    # but it should usually look up votes or trajectory for this question.
    assert any(t in tool_names for t in ["get_votes", "get_trajectory"])
    
    # Should eventually call answer_with_evidence (which is not stored in steps list in the loop logic 
    # if we break immediately, let's check the logic in orchestrator again.
    # Ah, in orchestrator, we append to steps_taken inside the loop. 
    # If answer_with_evidence is called, we log it but don't append it to steps_taken 
    # because it's not in self.executors (or is it?)
    
    # Let's check orchestrator logic:
    # self.executors = { "get_trajectory": ..., "get_votes": ..., "get_utterances": ... }
    # answer_with_evidence is NOT in executors.
    # So it won't be in result["steps"].
    
    assert len(result["steps"]) >= 1 

def test_orchestrator_max_steps_limit(mock_client):
    """Test that max steps prevents infinite loops."""
    # Setup infinite loop of tool calls
    response = MockResponse([
        MockFunctionCall("get_votes", {"symbol": "A/RES/78/220"})
    ])
    mock_client.responses.create.return_value = response
    
    with patch("rag.multistep.orchestrator.execute_get_votes") as mock_votes:
        mock_votes.return_value = {}
        with patch("rag.rag_qa.answer_question") as mock_answer:
            mock_answer.return_value = {"answer": "Timed out", "evidence": [], "sources": []}
            
            orchestrator = MultiStepOrchestrator(max_steps=2)
            result = orchestrator.answer_multistep("Loop query")
            
            assert len(result["steps"]) == 2 # Should stop after 2 steps

