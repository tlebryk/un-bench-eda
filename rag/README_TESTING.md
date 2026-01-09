# RAG Q&A Testing Infrastructure

End-to-end testing for RAG queries with configurable prompt styles.

## Setup

The test infrastructure includes:

1. **Configurable prompts** (`prompt_config.yaml`) - Define different answer styles
2. **Single query testing** (`test_rag_queries.py`) - Test individual queries
3. **Batch testing** (`batch_test.py`) - Run multiple queries from YAML file
4. **Test queries** (`test_queries.yaml`) - Predefined test queries

## Prerequisites

**Database must be accessible locally:**

1. Start Docker database (if not already running):
   ```bash
   make docker-up
   ```

2. Set DATABASE_URL for local testing:
   ```bash
   # Add to your .env file:
   DATABASE_URL=postgresql://un_user:un_password@localhost:5433/un_documents

   # Or export it:
   export DATABASE_URL="postgresql://un_user:un_password@localhost:5433/un_documents"
   ```

   Note: Port 5433 is the Docker-mapped port on localhost (postgres service uses 5432 inside Docker)

## Usage

### Test Single Query

```bash
# Test with analytical style (default)
uv run python -m rag.test_rag_queries "What was said about climate change?"

# Test with strict style
uv run python -m rag.test_rag_queries "What was said about climate change?" --style strict

# Test with conversational style
uv run python -m rag.test_rag_queries "What was said about climate change?" --style conversational

# Compare all styles
uv run python -m rag.test_rag_queries "What was said about climate change?" --style compare -o ./test_results

# Save results to file
uv run python -m rag.test_rag_queries "What was said about climate change?" -o ./test_results
```

### Batch Testing

```bash
# Run all test queries with analytical style
uv run python -m rag.batch_test

# Compare all prompt styles for all queries
uv run python -m rag.batch_test --compare

# Specify custom queries file
uv run python -m rag.batch_test -q ./my_queries.yaml

# Specify output directory
uv run python -m rag.batch_test -o ./my_test_results
```

## Prompt Styles

Edit `rag/prompt_config.yaml` to customize or add new prompt styles:

### `strict`
- Conservative approach
- Explicit source citations
- Separates known vs unknown information
- Lists what data explicitly states vs what can be inferred
- **Use when:** Need defensive, verifiable answers

### `analytical` (recommended)
- Memo-style (1-2 paragraphs)
- Identifies patterns and themes
- Organized, synthesized findings
- Natural citations
- **Use when:** Need concise analysis for decision-making

### `conversational`
- Natural, flowing narrative
- Organic citations
- Less rigid structure
- **Use when:** Need accessible, readable briefings

## Test Queries Format

Create test queries in YAML (`test_queries.yaml`):

```yaml
queries:
  - id: climate_plenary
    question: "What was said about climate change in plenary meetings?"
    expected_themes:
      - "Nature-based solutions"
      - "Sea level rise"

  - id: voting_pattern
    question: "Which countries voted against A/RES/78/220?"
    expected_type: "List of countries"
```

## Output Format

Results are saved as JSON:

```json
{
  "question": "What was said about climate change?",
  "prompt_style": "analytical",
  "model": "gpt-5-mini-2025-08-07",
  "sql_query": "SELECT ...",
  "row_count": 23,
  "answer": "Plenary discussions highlighted three main themes...",
  "sources": ["A/78/PV.102", "A/78/PV.80"],
  "evidence_count": 23
}
```

## Comparing Before/After

To test prompt changes:

1. Run with current prompt:
   ```bash
   uv run python -m rag.test_rag_queries "Your question" -o ./results_before
   ```

2. Edit `prompt_config.yaml` to adjust the prompt

3. Run again:
   ```bash
   uv run python -m rag.test_rag_queries "Your question" -o ./results_after
   ```

4. Compare:
   ```bash
   diff results_before/result.json results_after/result.json
   # Or just read the answer field from each JSON file
   ```

## Adding New Prompt Styles

Edit `prompt_config.yaml`:

```yaml
my_custom_style:
  name: "My Custom Style"
  description: "Brief description"
  system_instructions: |
    Your custom system instructions here...

    Guidelines:
    1. First guideline
    2. Second guideline
```

Then use it:

```bash
uv run python -m rag.test_rag_queries "Question" --style my_custom_style
```

## Tips

- **Start with `analytical`** - Best balance of conciseness and analysis
- **Use `compare`** - See how all styles handle the same query
- **Batch test** - Regression testing when changing prompts
- **Save outputs** - Compare before/after when refining prompts
