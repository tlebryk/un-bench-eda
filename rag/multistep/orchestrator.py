from typing import Dict, Any, List, Optional, Set
from collections import defaultdict
import json
import logging
import os
import time
from pathlib import Path
from openai import OpenAI

from rag.multistep.tools import (
    get_related_documents_tool, execute_get_related_documents,
    get_votes_tool, execute_get_votes,
    get_vote_events_tool, execute_get_vote_events,
    get_utterances_tool, execute_get_utterances,
    get_related_utterances_tool, execute_get_related_utterances,
    get_chain_utterances_tool, execute_get_chain_utterances,
    get_document_details_tool, execute_get_document_details,
    execute_sql_query_tool, execute_execute_sql_query,
    answer_with_evidence_tool
)
from rag.multistep.prompts import MULTISTEP_SYSTEM_PROMPT
from rag.prompt_config import get_default_model

# Set up logging
from utils.logging_config import get_logger
logger = get_logger(__name__, log_file="multistep_tools.log")


class MultiStepOrchestrator:
    """Orchestrate multi-step RAG queries using OpenAI tool calling."""

    def __init__(self, model: Optional[str] = None, max_steps: int = 6):
        if model is None:
            model = get_default_model()
        self.model = model
        self.max_steps = max_steps
        
        # Initialize client lazily or check env var
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not found. Orchestrator may fail.")
        self.client = OpenAI(api_key=api_key)

        # Tool definitions
        self.tools = [
            execute_sql_query_tool(),
            # get_related_documents_tool(),
            get_document_details_tool(),
            get_votes_tool(),
            get_vote_events_tool(),
            # get_utterances_tool(),
            # get_related_utterances_tool(),
            get_chain_utterances_tool(),
            answer_with_evidence_tool(),
        ]

        # Tool executors
        self.executors = {
            "execute_sql_query": execute_execute_sql_query,
            "get_related_documents": execute_get_related_documents,
            "get_document_details": execute_get_document_details,
            "get_votes": execute_get_votes,
            "get_vote_events": execute_get_vote_events,
            "get_utterances": execute_get_utterances,
            "get_related_utterances": execute_get_related_utterances,
            "get_chain_utterances": execute_get_chain_utterances,
        }

    @staticmethod
    def _serialize_response_output(response_output: Any) -> str:
        if response_output is None:
            return "null"
        payload = []
        for item in response_output:
            if hasattr(item, "model_dump"):
                payload.append(item.model_dump())
            elif hasattr(item, "__dict__"):
                payload.append(item.__dict__)
            else:
                payload.append(str(item))
        return json.dumps(payload, ensure_ascii=True)

    @staticmethod
    def _serialize_input_list(input_list: List[Dict[str, Any]], max_chars: int = 8000) -> str:
        try:
            raw = json.dumps(input_list, ensure_ascii=True)
        except Exception:
            raw = str(input_list)
        if len(raw) > max_chars:
            return raw[:max_chars] + "...[truncated]"
        return raw

    @staticmethod
    def _estimate_input_chars(input_list: List[Dict[str, Any]]) -> int:
        try:
            return len(json.dumps(input_list, ensure_ascii=True))
        except Exception:
            return len(str(input_list))

    def answer_multistep(
        self,
        question: str,
        mode: str = "deep",
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        previous_symbols: Optional[Set[str]] = None
    ) -> Dict[str, Any]:
        """
        Answer complex question using multi-step tool calling.

        Args:
            question: The user's question.
            mode: "deep" (default) for agentic loop, "fast" for direct SQL->Answer.
            conversation_history: Previous conversation input_list for multi-turn.
            previous_symbols: Document symbols from previous turns for context.

        Returns: {
            "answer": str,
            "evidence": List[Dict],
            "sources": List[str],
            "steps": List[Dict],  # Tool calls made
            "input_list": List[Dict],  # Full conversation for storage
            "accumulated_evidence": Dict[str, List]  # Evidence for storage
        }
        """
        if mode == "fast":
            return self._answer_fast(question, previous_symbols=previous_symbols)

        logger.info(f"\n\n{'#'*60}")
        logger.info(f"🚀 STARTING MULTI-STEP QUERY (Deep Mode)")
        logger.info(f"❓ Question: {question}")
        if conversation_history:
            logger.info(f"📜 Continuing conversation with {len(conversation_history)} previous messages")
        if previous_symbols:
            logger.info(f"📎 Previous symbols: {previous_symbols}")
        logger.info(f"{'#'*60}\n")

        # Initialize conversation - continue from history or start fresh
        if conversation_history:
            # Continue from existing conversation
            input_list = conversation_history.copy()
            input_list.append({"role": "user", "content": question})
        else:
            # New conversation
            input_list = [
                {"role": "system", "content": MULTISTEP_SYSTEM_PROMPT},
                {"role": "user", "content": question}
            ]

        steps_taken = []
        accumulated_evidence = defaultdict(list)

        # Loop until answer is ready or max steps reached
        for step_num in range(self.max_steps):
            logger.info(f"Step {step_num + 1}/{self.max_steps}")

            try:
                # Ask model to select tool
                # Note: using client.responses.create (beta) or standard chat completions depending on version
                # The offboarding doc explicitly says: Use client.responses.create() API (NOT chat.completions.create)
                # and references sample_oai_function_call.py
                
                logger.info(
                    "OAI input (chars=%s): %s",
                    self._estimate_input_chars(input_list),
                    self._serialize_input_list(input_list)
                )

                response = self.client.responses.create(
                    model=self.model,
                    tools=self.tools,
                    input=input_list,
                )

                if hasattr(response, "output"):
                    logger.info(
                        "OAI response output: %s",
                        self._serialize_response_output(response.output)
                    )
                else:
                    logger.warning("OAI response missing output attribute for logging.")

                # Add model's output to conversation
                if hasattr(response, 'output'):
                    input_list += response.output
                else:
                    logger.error("Response object missing 'output' attribute")
                    break

                # Check for function calls
                has_function_call = False
                assistant_text = None

                # Iterate through output items to find function calls
                # response.output is a list of items (Message, FunctionCall, etc.)
                for item in response.output:
                    if hasattr(item, 'type') and item.type == "function_call":
                        has_function_call = True
                        tool_name = item.name
                        arguments = json.loads(item.arguments)

                        logger.info(f"\n{'='*60}")
                        logger.info(f"🔧 TOOL CALL: {tool_name}")
                        logger.info(f"📥 Arguments: {json.dumps(arguments, indent=2)}")

                        # Check if ready to answer
                        if tool_name == "answer_with_evidence":
                            logger.info("✅ Model indicated ready to synthesize answer")
                            # Add dummy output to satisfy API requirements
                            input_list.append({
                                "type": "function_call_output",
                                "call_id": item.call_id,
                                "output": json.dumps({"ready": True})
                            })
                            logger.info(f"{'='*60}\n")
                            # Break immediately - we're done gathering evidence
                            break

                        if tool_name in self.executors:
                            # Execute tool
                            start_time = time.time()
                            try:
                                result = self.executors[tool_name](**arguments)
                                execution_time = time.time() - start_time

                                # Log success with result summary
                                logger.info(f"✅ Tool executed successfully in {execution_time:.2f}s")
                                logger.info(f"📤 Result summary: {self._summarize_result(tool_name, result)}")
                                logger.info(
                                    "📦 Tool output (chars=%s): %s",
                                    len(json.dumps(result, ensure_ascii=True)),
                                    json.dumps(result, ensure_ascii=True)[:8000] + "...[truncated]" if len(json.dumps(result, ensure_ascii=True)) > 8000 else json.dumps(result, ensure_ascii=True)
                                )

                            except Exception as e:
                                execution_time = time.time() - start_time
                                logger.error(f"❌ Tool execution failed after {execution_time:.2f}s: {e}", exc_info=True)
                                result = {"error": str(e)}

                            steps_taken.append({
                                "tool": tool_name,
                                "arguments": arguments,
                                "result": result,
                                "execution_time": execution_time
                            })

                            # Store evidence
                            accumulated_evidence[tool_name].append(result)

                            # Add function result to conversation
                            input_list.append({
                                "type": "function_call_output",
                                "call_id": item.call_id,
                                "output": json.dumps(result)
                            })

                        logger.info(f"{'='*60}\n")
                    elif hasattr(item, 'type') and item.type == "message":
                        for content_item in getattr(item, "content", []) or []:
                            if isinstance(content_item, dict) and content_item.get("type") == "output_text":
                                assistant_text = content_item.get("text")
                            elif hasattr(content_item, "type") and getattr(content_item, "type") == "output_text":
                                assistant_text = getattr(content_item, "text", None)

                # Check if we should exit the outer loop
                # If the last output item processed was answer_with_evidence, we're done
                if has_function_call:
                    # Check if any function call was answer_with_evidence
                    for item in response.output:
                        if hasattr(item, 'type') and item.type == "function_call":
                            if item.name == "answer_with_evidence":
                                logger.info("🏁 Exiting orchestrator loop - ready to synthesize")
                                break
                    else:
                        # No answer_with_evidence found, continue
                        continue
                    # If we didn't continue, we break the outer loop
                    break

                # If model didn't call any function, it might be confused or trying to talk
                # In responses API, if it returns text message, it's also in output
                if not has_function_call:
                    if assistant_text:
                        logger.info("No function call; returning assistant clarification.")
                        return {
                            "answer": assistant_text,
                            "evidence": [],
                            "sources": [],
                            "steps": steps_taken,
                            "input_list": input_list,
                            "accumulated_evidence": accumulated_evidence
                        }
                    logger.info("No function call in response, stopping.")
                    break

            except Exception as e:
                logger.error(f"Error in multi-step loop: {e}", exc_info=True)
                break

        # Synthesize final answer using rag_qa.py
        logger.info(f"\n{'='*60}")
        logger.info(f"🔄 SYNTHESIZING FINAL ANSWER")
        logger.info(f"   Tools used: {[step['tool'] for step in steps_taken]}")

        # Log accumulation summary
        for tool_name, results in accumulated_evidence.items():
            total_calls = len(results)
            successful_calls = sum(1 for r in results if "error" not in r)
            logger.info(f"   {tool_name}: {successful_calls}/{total_calls} successful calls")

        logger.info(f"{'='*60}\n")
        
        # Format evidence for rag_qa.answer_question
        formatted_evidence = self._format_evidence_for_answer(accumulated_evidence)
        
        # We also want to include the question in the formatted evidence context somehow
        # or rely on rag_qa to use the original question.
        
        # Using lazy import to avoid circular dependency if any
        from rag.rag_qa import answer_question

        try:
            final_result = answer_question(
                query_results=formatted_evidence,
                original_question=question,
                sql_query=None,
                model=self.model
            )

            result = {
                "answer": final_result["answer"],
                "evidence": final_result["evidence"],
                "sources": final_result["sources"],
                "steps": steps_taken,
                "row_count": formatted_evidence.get("row_count", 0),
                # Include conversation state for storage
                "input_list": input_list,
                "accumulated_evidence": dict(accumulated_evidence)
            }

            logger.info(f"\n{'#'*60}")
            logger.info(f"✅ MULTI-STEP QUERY COMPLETED SUCCESSFULLY")
            logger.info(f"   Steps taken: {len(steps_taken)}")
            logger.info(f"   Answer length: {len(result['answer'])} chars")
            logger.info(f"   Sources: {len(result['sources'])}")
            logger.info(f"{'#'*60}\n\n")

            return result

        except Exception as e:
            logger.error(f"\n{'#'*60}")
            logger.error(f"❌ MULTI-STEP QUERY FAILED")
            logger.error(f"   Error: {e}")
            logger.error(f"   Steps completed: {len(steps_taken)}")
            logger.error(f"{'#'*60}\n\n", exc_info=True)

            return {
                "answer": "I gathered some information but failed to synthesize a final answer.",
                "evidence": [],
                "sources": [],
                "steps": steps_taken,
                "error": str(e)
            }

    def _summarize_result(self, tool_name: str, result: Dict[str, Any]) -> str:
        """Create a concise summary of tool result for logging."""
        if "error" in result:
            return f"ERROR: {result['error']}"

        if tool_name == "execute_sql_query":
            row_count = result.get("row_count", 0)
            truncated = result.get("truncated", False)
            return f"Found {row_count} rows{' (truncated to 100)' if truncated else ''}"

        elif tool_name == "get_related_documents":
            return (f"Found {len(result.get('meetings', []))} meetings, "
                   f"{len(result.get('drafts', []))} drafts, "
                   f"{len(result.get('committee_reports', []))} reports, "
                   f"{len(result.get('agenda_items', []))} agenda items")

        elif tool_name == "get_votes":
            total = result.get("total_countries", 0)
            votes = result.get("votes", {})
            return (f"Total: {total} countries - "
                   f"In favour: {len(votes.get('in_favour', []))}, "
                   f"Against: {len(votes.get('against', []))}, "
                   f"Abstaining: {len(votes.get('abstaining', []))}")

        elif tool_name == "get_utterances":
            count = result.get("count", 0)
            return f"Found {count} utterances"

        else:
            # Generic summary
            return f"Keys: {list(result.keys())}"

    def _format_evidence_for_answer(self, evidence: Dict[str, Any]) -> Dict[str, Any]:
        """Convert tool outputs to query_results format expected by rag_qa."""
        rows = []

        # Add SQL query results (already in rows format)
        if "execute_sql_query" in evidence:
            # evidence["execute_sql_query"] is now a LIST of results
            for sql_result in evidence["execute_sql_query"]:
                # Skip results with errors
                if "error" in sql_result:
                    logger.warning(f"Skipping SQL result with error: {sql_result['error']}")
                    continue

                # SQL results are already in the right format
                for row in sql_result.get("rows", []):
                    rows.append(row)

        # Add vote evidence
        if "get_votes" in evidence:
            # evidence["get_votes"] is now a LIST of results
            for votes_data in evidence["get_votes"]:
                # Skip results with errors
                if "error" in votes_data:
                    logger.warning(f"Skipping votes result with error: {votes_data['error']}")
                    continue

                # votes_data structure: {"symbol": ..., "votes": {"against": ["Country", ...]}, "total_countries": ...}
                symbol = votes_data.get("symbol")
                for vote_type, countries in votes_data.get("votes", {}).items():
                    for country in countries:
                        rows.append({
                            "symbol": symbol,
                            "vote_type": vote_type,
                            "actor_name": country, # rag_qa looks for 'name', 'actor_name', 'speaker_affiliation', 'country'
                            "vote_context": "plenary" # assumption for now, or could come from tool
                        })

        # Add utterance evidence
        if "get_utterances" in evidence:
            # evidence["get_utterances"] is now a LIST of results
            for utt_data in evidence["get_utterances"]:
                # Skip results with errors
                if "error" in utt_data:
                    logger.warning(f"Skipping utterances result with error: {utt_data['error']}")
                    continue

                # utterances structure: {"utterances": [{"speaker_name": ..., "text": ...}, ...]}
                for utt in utt_data.get("utterances", []):
                    rows.append({
                        "text": utt.get("text"),
                        "speaker_affiliation": utt.get("speaker_affiliation"),
                        "speaker_name": utt.get("speaker_name"),
                        "meeting_symbol": utt.get("meeting", [])[0] if isinstance(utt.get("meeting"), list) and utt.get("meeting") else None,
                        "agenda_item_number": utt.get("agenda_item")
                    })

        # Add related documents metadata
        if "get_related_documents" in evidence:
            # evidence["get_related_documents"] is now a LIST of results
            for related in evidence["get_related_documents"]:
                # Skip results with errors
                if "error" in related:
                    logger.warning(f"Skipping related docs result with error: {related['error']}")
                    continue

                # related structure: {"symbol": ..., "meetings": [...], "drafts": [...], "committee_reports": [...], "agenda_items": [...]}

                # We add this as a "document" type or "relationship" type implicitly via fields
                rows.append({
                    "symbol": related.get("symbol"),
                    "doc_type": "resolution", # inferred
                    "doc_metadata": json.dumps({
                        "meetings": related.get("meetings"),
                        "drafts": related.get("drafts"),
                        "committee_reports": related.get("committee_reports"),
                        "agenda_items": related.get("agenda_items")
                    })
                })

                # Also add rows for related docs to be picked up as evidence
                for meeting in related.get("meetings", []):
                    rows.append({
                        "symbol": meeting,
                        "doc_type": "meeting",
                        "relationship_type": "meeting_for",
                        "target_symbol": related.get("symbol")
                    })

                for draft in related.get("drafts", []):
                    rows.append({
                        "symbol": draft,
                        "doc_type": "draft",
                        "relationship_type": "draft_of",
                        "target_symbol": related.get("symbol")
                    })

                for agenda_item in related.get("agenda_items", []):
                    rows.append({
                        "symbol": agenda_item,
                        "doc_type": "agenda",
                        "relationship_type": "agenda_item",
                        "target_symbol": related.get("symbol")
                    })

        return {
            "columns": list(rows[0].keys()) if rows else [],
            "rows": rows,
            "row_count": len(rows),
            "truncated": False
        }

    def _answer_fast(
        self,
        question: str,
        previous_symbols: Optional[Set[str]] = None
    ) -> Dict[str, Any]:
        """Fast mode: Direct NL -> SQL -> Answer pipeline."""
        logger.info(f"\n\n{'#'*60}")
        logger.info(f"🚀 STARTING FAST QUERY (Direct SQL)")
        logger.info(f"❓ Question: {question}")
        if previous_symbols:
            logger.info(f"📎 Previous symbols for context: {previous_symbols}")
        logger.info(f"{'#'*60}\n")

        start_time = time.time()
        steps_taken = []

        # Step 1: Execute SQL (with previous_symbols context if available)
        tool_name = "execute_sql_query"
        logger.info(f"Executing {tool_name} directly...")

        try:
            # We use the executor directly
            # Pass previous_symbols for context-aware SQL generation
            result = self.executors[tool_name](
                natural_language_query=question,
                previous_symbols=list(previous_symbols) if previous_symbols else None
            )
            execution_time = time.time() - start_time

            steps_taken.append({
                "tool": tool_name,
                "arguments": {"natural_language_query": question},
                "result": result,
                "execution_time": execution_time
            })

            logger.info(f"✅ SQL execution completed in {execution_time:.2f}s")

        except Exception as e:
            logger.error(f"Fast mode SQL failed: {e}", exc_info=True)
            return {
                "answer": f"I failed to execute the query. Error: {str(e)}",
                "evidence": [],
                "sources": [],
                "steps": steps_taken,
                "error": str(e),
                "input_list": [],
                "accumulated_evidence": {}
            }

        # Step 2: Synthesize Answer
        logger.info("🔄 Synthesizing answer...")
        
        # Lazy import
        from rag.rag_qa import answer_question
        
        try:
            # result from execute_sql_query matches the structure needed for rag_qa
            # (it has columns, rows, sql_query)
            final_result = answer_question(
                query_results=result,
                original_question=question,
                sql_query=result.get("sql_query"),
                model=self.model
            )

            return {
                "answer": final_result["answer"],
                "evidence": final_result["evidence"],
                "sources": final_result["sources"],
                "steps": steps_taken,
                "row_count": result.get("row_count", 0),
                # Include empty conversation state for consistency
                "input_list": [],
                "accumulated_evidence": {"execute_sql_query": [result]}
            }

        except Exception as e:
            logger.error(f"Fast mode synthesis failed: {e}", exc_info=True)
            return {
                "answer": "I found data but failed to generate an answer.",
                "evidence": [],
                "sources": [],
                "steps": steps_taken,
                "error": str(e),
                "input_list": [],
                "accumulated_evidence": {}
            }
