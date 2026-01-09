# RAG System Prompts

This directory contains system prompts for the RAG Q&A system, managed as versioned files.

## Current Prompts

- `analytical_v1.txt` - **Default/Recommended**: Concise memo-style analysis with patterns and findings (1-2 paragraphs)
- `strict_v1.txt` - Conservative evidence-based answers with explicit citations and clear separation of known vs unknown
- `conversational_v1.txt` - Natural, flowing narrative style for accessible briefings

## Why Separate Files?

Instead of burying prompts in YAML or code:

1. **Git-friendly** - Clear diffs when prompts change
2. **Easy to review** - Read the full prompt in plain text
3. **Versioning** - Track prompt evolution (`v1`, `v2`, etc.)
4. **Easy to edit** - No YAML escaping, just plain text
5. **Production-ready** - Prompts are configuration, not code

## Usage in Code

```python
from rag.prompt_registry import get_prompt

# Load default (analytical)
prompt = get_prompt()

# Load specific style
prompt = get_prompt("strict")

# Load specific version
prompt = get_prompt("analytical", version=1)

# List available prompts
from rag.prompt_registry import list_prompts
print(list_prompts())  # ['analytical', 'conversational', 'strict']
```

## Usage in Production

Set the `RAG_PROMPT_STYLE` environment variable:

```bash
# In .env file
RAG_PROMPT_STYLE=analytical

# Or in docker-compose.yml
environment:
  RAG_PROMPT_STYLE: analytical

# Or export it
export RAG_PROMPT_STYLE=analytical
```

If not set, defaults to `analytical`.

## Creating New Prompts

1. **Create a new file**: `my_new_style_v1.txt`

2. **Write the prompt**:
   ```
   You are a research assistant...

   GUIDELINES:
   1. First guideline
   2. Second guideline
   ```

3. **Use it**:
   ```python
   get_prompt("my_new_style")
   ```

## Versioning Prompts

When iterating on a prompt:

1. **Keep the old version**: Don't delete `analytical_v1.txt`
2. **Create new version**: `analytical_v2.txt`
3. **By default, highest version is used**: `get_prompt("analytical")` → loads v2
4. **Pin to specific version if needed**: `get_prompt("analytical", version=1)`

### Example Evolution

```
prompts/
├── analytical_v1.txt      # Original
├── analytical_v2.txt      # Iteration 1: More concise
├── analytical_v3.txt      # Iteration 2: Better citations
└── analytical_v4.txt      # Current production version
```

The system automatically loads the highest version (v4) unless you specify otherwise.

## Best Practices

1. **Test before deploying**: Use `rag/test_rag_queries.py` to test prompt changes
2. **Compare versions**: Use `--style compare` to see side-by-side results
3. **Document changes**: Add git commit messages explaining prompt changes
4. **A/B test in production**: Deploy with environment variable, easy rollback
5. **Keep old versions**: Useful for comparing or rolling back

## Prompt Comparison

Run tests to compare prompt styles:

```bash
# Compare all styles on one query
DATABASE_URL="..." uv run python -m rag.test_rag_queries \
  "What was said about climate change?" \
  --style compare \
  -o ./test_results

# View comparison
uv run python -m rag.compare_results ./test_results
```

## Production Deployment

**Docker (hot reload):**
```bash
# Set in .env
RAG_PROMPT_STYLE=analytical

# Restart to pick up changes
make docker-reload
```

**Local:**
```bash
export RAG_PROMPT_STYLE=analytical
uv run uvicorn ui.app:app --reload
```

## Monitoring

The UI logs the active prompt style on startup:

```
📝 RAG prompt style: analytical
```

Check logs to verify which prompt is being used.
