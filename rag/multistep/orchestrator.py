from typing import Dict, Any, List, Optional, Set
from collections import defaultdict
import json
import logging
import os
import time
from pathlib import Path
from openai import OpenAI, APIConnectionError, APIError, APITimeoutError

from rag.multistep.tools import (
    get_related_documents_tool, execute_get_related_documents,
    get_votes_tool, execute_get_votes,
    get_vote_events_tool, execute_get_vote_events,
    get_utterances_tool, execute_get_utterances,
    get_related_utterances_tool, execute_get_related_utterances,
    get_chain_utterances_tool, execute_get_chain_utterances,
    get_document_details_tool, execute_get_document_details,
    execute_sql_query_tool, execute_execute_sql_query,
    answer_with_evidence_tool,
    get_full_text_context_tool, execute_get_full_text_context,
    analyze_with_python_tool, execute_analyze_with_python,
)
from rag.prompt_registry import get_prompt
from rag.prompt_config import get_default_model

# Set up logging
from utils.logging_config import get_logger
logger = get_logger(__name__, log_file="multistep_tools.log")


class MultiStepOrchestrator:
    """Orchestrate multi-step RAG queries using OpenAI tool calling."""

    def __init__(self, model: Optional[str] = None, max_steps: int = 6, verbose: bool = False):
        if model is None:
            model = get_default_model()
        self.model = model
        self.max_steps = max_steps
        self.verbose = verbose

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
            # get_vote_events_tool(),
            # get_utterances_tool(),
            get_related_utterances_tool(),
            # get_chain_utterances_tool(),
            # get_full_text_context_tool(),
            analyze_with_python_tool(),
            answer_with_evidence_tool(),
        ]

        # Tool executors
        self.executors = {
            "execute_sql_query": execute_execute_sql_query,
            # "get_related_documents": execute_get_related_documents,
            "get_document_details": execute_get_document_details,
            "get_votes": execute_get_votes,
            # "get_vote_events": execute_get_vote_events,
            # "get_utterances": execute_get_utterances,
            "get_related_utterances": execute_get_related_utterances,
            # "get_chain_utterances": execute_get_chain_utterances,
            # "get_full_text_context": execute_get_full_text_context,
            "analyze_with_python": execute_analyze_with_python,
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
        simple_turns: Optional[List] = None
    ) -> Dict[str, Any]:
        """
        Answer complex question using multi-step tool calling.

        Args:
            question: The user's question.
            mode: "deep" (default) for agentic loop, "fast" for direct SQL->Answer.
            conversation_history: Previous conversation input_list for multi-turn (deep mode).
            simple_turns: Previous SimpleTurn objects for context (fast mode).

        Returns: {
            "answer": str,
            "evidence": List[Dict],
            "sources": List[str],
            "steps": List[Dict],  # Tool calls made
            "input_list": List[Dict],  # Full conversation for storage
            "accumulated_evidence": Dict[str, List]  # Evidence for storage
        }
        """
        # Set up request-specific logging
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        traj_log_file = log_dir / f"trajectory_{timestamp}.log"

        file_handler = logging.FileHandler(traj_log_file)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

        # Attach handler to the module logger
        logger.addHandler(file_handler)

        try:
            if mode == "fast":
                # Format conversation history from simple turns
                formatted_history = None
                if simple_turns:
                    logger.info(f"Formatting conversation history from {len(simple_turns)} previous turns")
                    history_lines = []
                    for i, turn in enumerate(simple_turns[-3:], 1):  # Last 3 turns for context
                        logger.info(f"  Turn {i}: Q='{turn.question[:100]}...' A='{turn.answer[:100]}...'")
                        history_lines.append(f"Q: {turn.question}")
                        history_lines.append(f"A: {turn.answer}")
                    formatted_history = "\n".join(history_lines)
                    logger.info(f"FORMATTED CONVERSATION HISTORY (length: {len(formatted_history)} chars):")
                    logger.info(f"{'='*80}")
                    logger.info(formatted_history)
                    logger.info(f"{'='*80}")
                else:
                    logger.info("No previous turns - starting new conversation")

                return self._answer_fast(question, conversation_history=formatted_history)

            logger.info(f"\n\n{'#'*60}")
            logger.info(f"🚀 STARTING MULTI-STEP QUERY (Deep Mode)")
            logger.info(f"❓ Question: {question}")
            if conversation_history:
                logger.info(f"📜 Continuing conversation with {len(conversation_history)} previous messages")
            logger.info(f"{'#'*60}\n")

            # Initialize conversation - continue from history or start fresh
            if conversation_history:
                # Continue from existing conversation
                input_list = conversation_history.copy()
                input_list.append({"role": "user", "content": question})
            else:
                # New conversation
                multistep_prompt = get_prompt("multistep")
                input_list = [
                    {"role": "system", "content": multistep_prompt},
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
                    
                    # Log OAI input - verbose mode shows full payload, quiet mode just char count
                    if self.verbose:
                        logger.info(
                            "OAI input (chars=%s): %s",
                            self._estimate_input_chars(input_list),
                            self._serialize_input_list(input_list)
                        )
                    else:
                        logger.info("OAI call (input: %s chars)", self._estimate_input_chars(input_list))

                    response = self.client.responses.create(
                        model=self.model,
                        tools=self.tools,
                        input=input_list,
                            reasoning={
                                "effort": "medium"
                            }
                    )

                    if hasattr(response, "output"):
                        if self.verbose:
                            logger.info(
                                "OAI response output: %s",
                                self._serialize_response_output(response.output)
                            )
                        # Quiet mode: logged below per tool call
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
                                    # Special handling for analyze_with_python - pass accumulated evidence
                                    if tool_name == "analyze_with_python":
                                        result = self.executors[tool_name](
                                            accumulated_evidence=dict(accumulated_evidence),
                                            **arguments
                                        )
                                    else:
                                        result = self.executors[tool_name](**arguments)
                                    execution_time = time.time() - start_time

                                    # Log success with result summary
                                    logger.info(f"✅ Tool executed successfully in {execution_time:.2f}s")
                                    logger.info(f"📤 Result summary: {self._summarize_result(tool_name, result, arguments)}")

                                    # Only log full tool output in verbose mode
                                    if self.verbose:
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

                                # Add function result to conversation (truncated for LLM context)
                                truncated_result = self._truncate_result_for_context(tool_name, result)
                                input_list.append({
                                    "type": "function_call_output",
                                    "call_id": item.call_id,
                                    "output": json.dumps(truncated_result)
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
                                "source_links": [],
                                "steps": steps_taken,
                                "input_list": input_list,
                                "accumulated_evidence": accumulated_evidence
                            }
                        logger.info("No function call in response, stopping.")
                        break

                except APIConnectionError as e:
                    logger.error(f"API Connection Error: {e}", exc_info=True)
                    return {
                        "answer": "Unable to connect to the AI service. Please check your internet connection and try again.",
                        "evidence": [],
                        "sources": [],
                        "source_links": [],
                        "steps": steps_taken,
                        "error": "connection_error",
                        "error_details": str(e),
                        "input_list": input_list,
                        "accumulated_evidence": dict(accumulated_evidence)
                    }
                except APITimeoutError as e:
                    logger.error(f"API Timeout Error: {e}", exc_info=True)
                    return {
                        "answer": "The request timed out. The service may be overloaded. Please try again.",
                        "evidence": [],
                        "sources": [],
                        "source_links": [],
                        "steps": steps_taken,
                        "error": "timeout_error",
                        "error_details": str(e),
                        "input_list": input_list,
                        "accumulated_evidence": dict(accumulated_evidence)
                    }
                except APIError as e:
                    logger.error(f"API Error: {e}", exc_info=True)
                    return {
                        "answer": f"AI service error: {str(e)}",
                        "evidence": [],
                        "sources": [],
                        "source_links": [],
                        "steps": steps_taken,
                        "error": "api_error",
                        "error_details": str(e),
                        "input_list": input_list,
                        "accumulated_evidence": dict(accumulated_evidence)
                    }
                except Exception as e:
                    logger.error(f"Unexpected error in multi-step loop: {e}", exc_info=True)
                    return {
                        "answer": f"An unexpected error occurred: {str(e)}",
                        "evidence": [],
                        "sources": [],
                        "source_links": [],
                        "steps": steps_taken,
                        "error": "unexpected_error",
                        "error_details": str(e),
                        "input_list": input_list,
                        "accumulated_evidence": dict(accumulated_evidence)
                    }

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

            # Debug: log evidence summary
            logger.info(f"Evidence for synthesis: {len(formatted_evidence.get('rows', []))} rows")
            python_analysis_rows = [r for r in formatted_evidence.get('rows', []) if r.get('_type') == 'python_analysis']
            if python_analysis_rows:
                logger.info(f"  - {len(python_analysis_rows)} Python analysis rows included")
                logger.info(f"  - First analysis row: {python_analysis_rows[0].get('summary', 'N/A')}")
            
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
                    "source_links": final_result.get("source_links", []),
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
                logger.info(f"   Final Answer: {result['answer'][:500]}..." if len(result['answer']) > 500 else f"   Final Answer: {result['answer']}")
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
                    "source_links": [],
                    "steps": steps_taken,
                    "error": str(e)
                }
        finally:
            # Clean up handler to avoid memory leaks or duplicate logging
            file_handler.close()
            logger.removeHandler(file_handler)

    def _truncate_result_for_context(self, tool_name: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """Truncate large results before adding to LLM context.

        Full results are stored in accumulated_evidence for Python tool access.
        This returns a preview for the LLM to understand what was returned.

        Args:
            tool_name: Name of the tool
            result: Full result dict

        Returns:
            Truncated result dict suitable for LLM context
        """
        if "error" in result:
            return result  # Keep errors as-is

        if tool_name == "execute_sql_query":
            # For SQL: keep metadata, but show diverse sample rows
            rows = result.get("rows", [])
            row_count = len(rows)

            # Sample rows: first few, middle, and end to show diversity
            if row_count <= 50:
                sample_rows = rows
            else:
                # Show first 10, middle 5, last 5 = 20 rows showing data diversity
                sample_rows = (
                    rows[:10] +  # Beginning
                    rows[row_count // 2 - 2:row_count // 2 + 3] +  # Middle 5
                    rows[-5:]  # End
                )

            truncated = result.copy()
            truncated["rows"] = sample_rows
            truncated["row_count"] = row_count
            truncated["truncated_for_context"] = row_count > 50

            if row_count > 20:
                # Help LLM understand data diversity
                # Check if this is voting data with multiple resolutions
                if rows and 'resolution_symbol' in rows[0]:
                    # Count unique resolutions in full data
                    unique_resolutions = len(set(row.get('resolution_symbol') for row in rows))
                    # Also sample some resolution symbols from later in the dataset
                    sample_mid = rows[row_count // 2].get('resolution_symbol') if row_count > 100 else None
                    sample_end = rows[-1].get('resolution_symbol')

                    truncated["context_note"] = (
                        f"⚠️ PREVIEW ONLY - DO NOT analyze just these 20 rows! ⚠️\n"
                        f"This preview shows rows 1-20 from a dataset of {row_count} total rows.\n"
                        f"The FULL dataset contains {unique_resolutions} DIFFERENT resolutions:\n"
                        f"  - First: {rows[0].get('resolution_symbol')}\n"
                        f"  - Middle: {sample_mid}\n"
                        f"  - Last: {sample_end}\n"
                        f"The analyze_with_python tool receives ALL {row_count} rows across all {unique_resolutions} resolutions.\n"
                        f"For coalition analysis, you MUST use the full data, not just this preview!"
                    )
                else:
                    truncated["context_note"] = f"Showing first 20 of {row_count} rows. Full data available to analyze_with_python tool."

            return truncated

        elif tool_name == "analyze_with_python":
            # Python results are usually small dicts/lists, keep as-is
            # But truncate if result is huge
            result_data = result.get("result")
            if isinstance(result_data, list) and len(result_data) > 50:
                truncated = result.copy()
                truncated["result"] = result_data[:50]
                truncated["truncated_for_context"] = True
                truncated["context_note"] = f"Showing first 50 of {len(result_data)} items"
                return truncated
            return result

        else:
            # Other tools: keep as-is for now
            return result

    def _summarize_result(self, tool_name: str, result: Dict[str, Any], arguments: Optional[Dict[str, Any]] = None) -> str:
        """Create a rich summary of tool result for logging.

        Args:
            tool_name: Name of the tool executed
            result: Result dict from tool execution
            arguments: Optional arguments dict passed to the tool
        """
        if "error" in result:
            return f"ERROR: {result['error']}"

        if tool_name == "execute_sql_query":
            row_count = result.get("row_count", 0)
            truncated = result.get("truncated", False)
            sql = result.get("sql_query", "")
            nl_query = arguments.get("natural_language_query", "") if arguments else ""

            # Sample first 2 rows for preview
            rows = result.get("rows", [])
            sample = ""
            if rows:
                first_row = rows[0]
                sample = f"\n     First row sample: {str(first_row)[:150]}..."

            summary = f"SQL Query\n     NL: {nl_query}\n     SQL: {sql[:200]}{'...' if len(sql) > 200 else ''}\n     Rows: {row_count}{' (truncated to 20k)' if truncated else ''}{sample}"
            return summary

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

        elif tool_name == "get_related_utterances":
            count = result.get("count", 0)
            referenced = ", ".join(result.get("referenced_symbols", [])) or "documents"
            return f"Found {count} utterances referencing {referenced}"

        elif tool_name == "get_full_text_context":
            d_count = len(result.get("drafts", []))
            m_count = len(result.get("meetings", []))
            r_count = len(result.get("committee_reports", []))
            return f"Context for {result.get('symbol')}: {d_count} drafts, {r_count} reports, {m_count} meetings"

        elif tool_name == "analyze_with_python":
            result_type = result.get("result_type", "unknown")
            if result.get("error"):
                return f"ERROR: {result['error']}"

            code = arguments.get("code", "") if arguments else ""
            code_preview = code[:150].replace("\n", " ") if code else ""

            result_data = result.get("result")
            result_preview = ""
            data_sample = ""

            if result_type == "dataframe":
                shape = result.get("shape", [0, 0])
                cols = result.get("columns", [])
                result_preview = f"{shape[0]} rows x {shape[1]} cols, columns: {cols[:5]}{'...' if len(cols) > 5 else ''}"
                # Show first 2 rows as sample
                if result_data and len(result_data) > 0:
                    sample_rows = result_data[:2]
                    data_sample = "\n     Sample rows:\n"
                    for i, row in enumerate(sample_rows):
                        row_str = str(row)[:200]
                        data_sample += f"       [{i}] {row_str}{'...' if len(str(row)) > 200 else ''}\n"
            elif result_type == "dict":
                if isinstance(result_data, dict):
                    keys = list(result_data.keys())
                    result_preview = f"dict with {len(keys)} keys: {keys[:5]}{'...' if len(keys) > 5 else ''}"
                    # Show a sample of values
                    data_sample = "\n     Sample values:\n"
                    for k in keys[:3]:
                        v = result_data[k]
                        v_str = str(v)[:150]
                        data_sample += f"       {k}: {v_str}{'...' if len(str(v)) > 150 else ''}\n"
                else:
                    result_preview = f"dict (unexpected structure)"
            elif result_type == "list":
                if isinstance(result_data, list):
                    result_preview = f"list with {len(result_data)} items"
                    # Show first 2 items
                    if len(result_data) > 0:
                        data_sample = "\n     Sample items:\n"
                        for i, item in enumerate(result_data[:2]):
                            item_str = str(item)[:200]
                            data_sample += f"       [{i}] {item_str}{'...' if len(str(item)) > 200 else ''}\n"
                else:
                    result_preview = f"list (unexpected structure)"
            elif result_type == "array":
                shape = result.get("shape", [])
                result_preview = f"numpy array, shape: {shape}"
                if result_data:
                    data_sample = f"\n     First values: {result_data[:10]}{'...' if len(result_data) > 10 else ''}\n"
            else:
                result_preview = f"type: {result_type}"
                if result_data:
                    data_sample = f"\n     Value: {str(result_data)[:300]}{'...' if len(str(result_data)) > 300 else ''}\n"

            summary = f"Python Analysis\n     Code: {code_preview}...\n     Result: {result_preview}{data_sample}"
            return summary

        else:
            # Generic summary
            return f"Keys: {list(result.keys())}"

    def _format_evidence_for_answer(self, evidence: Dict[str, Any]) -> Dict[str, Any]:
        """Convert tool outputs to query_results format expected by rag_qa."""
        rows = []
        python_analysis_rows = []  # Collect these to prepend later

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

        # Add Python analysis results as structured evidence (PREPEND so they're in first 100 rows)
        if "analyze_with_python" in evidence:
            for py_result in evidence["analyze_with_python"]:
                if "error" in py_result:
                    continue

                # Extract the actual analysis result
                analysis = py_result.get("result")
                if isinstance(analysis, dict):
                    # Format as a special row type for the synthesizer
                    python_analysis_rows.append({
                        "_type": "python_analysis",
                        "_analysis_type": "coalition",
                        "analysis_data": json.dumps(analysis)[:5000],  # Truncate if huge
                        "summary": f"Coalition analysis: {analysis.get('n_countries', '?')} countries across {analysis.get('n_resolutions', '?')} resolutions"
                    })
                elif isinstance(analysis, list):
                    # List of coalition pairs - add as multiple rows
                    for item in analysis[:50]:  # Limit to top 50
                        python_analysis_rows.append({
                            "_type": "python_analysis",
                            "_analysis_type": "coalition_pair",
                            **item  # Spread the dict (country1, country2, correlation, etc.)
                        })

        # Add full text context evidence
        if "get_full_text_context" in evidence:
            for ctx in evidence["get_full_text_context"]:
                if "error" in ctx:
                    continue
                
                # Add resolution
                if ctx.get("resolution"):
                    res = ctx["resolution"]
                    rows.append({
                        "symbol": res.get("symbol"),
                        "doc_type": "resolution",
                        "text": res.get("text"),
                        "title": res.get("title"),
                        "date": res.get("date")
                    })
                
                # Add drafts
                for doc in ctx.get("drafts", []):
                    rows.append({
                        "symbol": doc.get("symbol"),
                        "doc_type": "draft",
                        "text": doc.get("text"),
                        "title": doc.get("title"),
                        "date": doc.get("date"),
                        "relationship_type": "draft_of",
                        "target_symbol": ctx.get("symbol")
                    })
                
                # Add reports
                for doc in ctx.get("committee_reports", []):
                    rows.append({
                        "symbol": doc.get("symbol"),
                        "doc_type": "committee_report",
                        "text": doc.get("text"),
                        "title": doc.get("title"),
                        "date": doc.get("date"),
                        "relationship_type": "committee_report_for",
                        "target_symbol": ctx.get("symbol")
                    })
                
                # Add meetings
                for doc in ctx.get("meetings", []):
                    rows.append({
                        "symbol": doc.get("symbol"),
                        "doc_type": "meeting",
                        "text": doc.get("text"), # Full text!
                        "title": doc.get("title"),
                        "date": doc.get("date"),
                        "relationship_type": "meeting_record_for",
                        "target_symbol": ctx.get("symbol")
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
                    meeting_symbol = utt.get("meeting_symbol")
                    if not meeting_symbol and isinstance(utt.get("meeting"), list) and utt.get("meeting"):
                        meeting_symbol = utt.get("meeting")[0]
                    rows.append({
                        "text": utt.get("text"),
                        "speaker_affiliation": utt.get("speaker_affiliation"),
                        "speaker_name": utt.get("speaker_name"),
                        "meeting_symbol": meeting_symbol,
                        "agenda_item_number": utt.get("agenda_item")
                    })

        # Add related utterance evidence
        if "get_related_utterances" in evidence:
            for utt_data in evidence["get_related_utterances"]:
                if "error" in utt_data:
                    logger.warning(f"Skipping related utterances result with error: {utt_data['error']}")
                    continue

                for utt in utt_data.get("utterances", []):
                    rows.append({
                        "symbol": utt.get("referenced_symbol"),
                        "doc_type": "utterance",
                        "text": utt.get("text"),
                        "speaker_affiliation": utt.get("speaker_affiliation"),
                        "speaker_name": utt.get("speaker_name"),
                        "meeting_symbol": utt.get("meeting_symbol"),
                        "agenda_item_number": utt.get("agenda_item"),
                        "reference_type": utt.get("reference_type")
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

        # Python analysis was already handled above and added to python_analysis_rows

        # PREPEND Python analysis rows so they're in the first 100 that rag_qa sees
        all_rows = python_analysis_rows + rows

        return {
            "columns": list(all_rows[0].keys()) if all_rows else [],
            "rows": all_rows,
            "row_count": len(all_rows),
            "truncated": False
        }

    def _answer_fast(
        self,
        question: str,
        conversation_history: Optional[str] = None
    ) -> Dict[str, Any]:
        """Fast mode: Direct NL -> SQL -> Answer pipeline."""
        logger.info(f"\n\n{'#'*60}")
        logger.info(f"🚀 STARTING FAST QUERY (Direct SQL)")
        logger.info(f"❓ Question: {question}")
        if conversation_history:
            logger.info(f"📜 With conversation history")
        logger.info(f"{'#'*60}\n")

        start_time = time.time()
        steps_taken = []

        # Step 1: Execute SQL (with conversation context if available)
        tool_name = "execute_sql_query"
        logger.info(f"Executing {tool_name} directly...")

        try:
            # We use the executor directly
            # Pass conversation history for context-aware SQL generation
            result = self.executors[tool_name](
                natural_language_query=question,
                conversation_context=conversation_history
            )
            execution_time = time.time() - start_time

            steps_taken.append({
                "tool": tool_name,
                "arguments": {"natural_language_query": question},
                "result": result,
                "execution_time": execution_time
            })

            logger.info(f"✅ SQL execution completed in {execution_time:.2f}s")

        except APIConnectionError as e:
            logger.error(f"API Connection Error in fast mode: {e}", exc_info=True)
            return {
                "answer": "Unable to connect to the AI service. Please check your internet connection and try again.",
                "evidence": [],
                "sources": [],
                "source_links": [],
                "steps": steps_taken,
                "error": "connection_error",
                "error_details": str(e),
                "input_list": [],
                "accumulated_evidence": {}
            }
        except APITimeoutError as e:
            logger.error(f"API Timeout Error in fast mode: {e}", exc_info=True)
            return {
                "answer": "The request timed out. The service may be overloaded. Please try again.",
                "evidence": [],
                "sources": [],
                "source_links": [],
                "steps": steps_taken,
                "error": "timeout_error",
                "error_details": str(e),
                "input_list": [],
                "accumulated_evidence": {}
            }
        except APIError as e:
            logger.error(f"API Error in fast mode: {e}", exc_info=True)
            return {
                "answer": f"AI service error: {str(e)}",
                "evidence": [],
                "sources": [],
                "source_links": [],
                "steps": steps_taken,
                "error": "api_error",
                "error_details": str(e),
                "input_list": [],
                "accumulated_evidence": {}
            }
        except Exception as e:
            logger.error(f"Fast mode SQL failed: {e}", exc_info=True)
            return {
                "answer": f"Failed to execute the query: {str(e)}",
                "evidence": [],
                "sources": [],
                "source_links": [],
                "steps": steps_taken,
                "error": "execution_error",
                "error_details": str(e),
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
                "source_links": final_result.get("source_links", []),
                "steps": steps_taken,
                "row_count": result.get("row_count", 0),
                # Include empty conversation state for consistency
                "input_list": [],
                "accumulated_evidence": {"execute_sql_query": [result]}
            }

        except APIConnectionError as e:
            logger.error(f"API Connection Error during synthesis: {e}", exc_info=True)
            return {
                "answer": "Unable to connect to the AI service while generating the answer. Please check your internet connection and try again.",
                "evidence": [],
                "sources": [],
                "source_links": [],
                "steps": steps_taken,
                "error": "connection_error",
                "error_details": str(e),
                "input_list": [],
                "accumulated_evidence": {}
            }
        except APITimeoutError as e:
            logger.error(f"API Timeout during synthesis: {e}", exc_info=True)
            return {
                "answer": "The request timed out while generating the answer. Please try again.",
                "evidence": [],
                "sources": [],
                "source_links": [],
                "steps": steps_taken,
                "error": "timeout_error",
                "error_details": str(e),
                "input_list": [],
                "accumulated_evidence": {}
            }
        except Exception as e:
            logger.error(f"Fast mode synthesis failed: {e}", exc_info=True)
            return {
                "answer": f"Found data but failed to generate an answer: {str(e)}",
                "evidence": [],
                "sources": [],
                "source_links": [],
                "steps": steps_taken,
                "error": "synthesis_error",
                "error_details": str(e),
                "input_list": [],
                "accumulated_evidence": {}
            }
