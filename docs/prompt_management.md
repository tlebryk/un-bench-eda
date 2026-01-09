# Prompt Management Guide

## Overview

RAG system prompts are managed as **versioned files** in `rag/prompts/`, not embedded in code or YAML. This follows industry best practices for prompt engineering in production systems.

## Architecture

```
rag/
├── prompts/
│   ├── analytical_v1.txt       # Memo-style analysis (default)
│   ├── strict_v1.txt           # Evidence-based citations
│   ├── conversational_v1.txt   # Natural narrative
│   └── README.md
├── prompt_registry.py          # Loader with versioning
└── rag_qa.py                   # Uses registry
```

## Why This Approach?

### 1. Separate Files (Not YAML)
- **Git-friendly**: Clear diffs when prompts change
- **Easy to review**: Read full prompt without escaping
- **No parsing**: Just plain text
- **IDE support**: Syntax highlighting, spell check

### 2. Versioning
- Track evolution: `analytical_v1.txt` → `analytical_v2.txt`
- A/B testing: Compare versions easily
- Safe rollback: Keep old versions
- Automatic loading: `get_prompt("analytical")` loads highest version

### 3. Environment Configuration
- Production control: `RAG_PROMPT_STYLE=analytical`
- No code changes: Just env var
- Per-deployment: Different prompts in staging/prod
- Easy rollback: Change env var, restart

## Production Usage

### Setting the Prompt Style

**In .env file:**
```bash
RAG_PROMPT_STYLE=analytical
```

**In docker-compose.yml:**
```yaml
environment:
  RAG_PROMPT_STYLE: ${RAG_PROMPT_STYLE:-analytical}
```

**Export for local testing:**
```bash
export RAG_PROMPT_STYLE=analytical
uv run uvicorn ui.app:app --reload
```

### Verification

Check logs on startup:
```
📝 RAG prompt style: analytical
```

## Prompt Development Workflow

### 1. Create New Version

When improving a prompt, **don't modify the existing file**. Create a new version:

```bash
# Don't do this:
# Edit analytical_v1.txt

# Do this:
cp rag/prompts/analytical_v1.txt rag/prompts/analytical_v2.txt
# Edit analytical_v2.txt
```

### 2. Test Locally

```bash
DATABASE_URL="..." uv run python -m rag.test_rag_queries \
  "Your test question" \
  --style analytical

# Compare v1 vs v2
get_prompt("analytical", version=1)  # Old
get_prompt("analytical", version=2)  # New (auto-loaded)
```

### 3. A/B Test

Run batch tests comparing versions:

```bash
# Test all queries with both versions
DATABASE_URL="..." uv run python -m rag.batch_test --compare -o ./test_results
```

### 4. Review Metrics

- **Answer length**: Shorter is often better (aim for 1-2 paragraphs)
- **Citation quality**: Natural vs defensive
- **Relevance**: Addresses question directly
- **Readability**: Clear organization

### 5. Deploy

```bash
# Update .env (or set in deployment system)
RAG_PROMPT_STYLE=analytical

# For Docker
make docker-reload
```

### 6. Rollback if Needed

```bash
# Roll back to v1
RAG_PROMPT_STYLE=analytical
# Then pin version in code temporarily:
get_prompt("analytical", version=1)
```

## Best Practices

### Version Naming

```
{style}_v{number}.txt

Examples:
- analytical_v1.txt
- analytical_v2.txt
- analytical_v3.txt
```

### Git Commits

```bash
git add rag/prompts/analytical_v2.txt
git commit -m "prompts: analytical v2 - more concise, better citations

- Reduced from ~2000 to ~1500 chars average
- Cleaner pattern identification
- Less defensive hedging
- Tested on climate change queries"
```

### Documentation

Each new version should document changes:

```
analytical_v2.txt
-----------------
Changes from v1:
- More concise guidelines (removed redundant points)
- Emphasis on synthesis over listing
- Added "Think memo, not report" guideline
- Tested: 15% shorter answers, same coverage
```

### Testing Strategy

1. **Unit test**: Test single query with new prompt
2. **Batch test**: Run test suite (`rag/test_queries.yaml`)
3. **Comparison**: Side-by-side with previous version
4. **Human eval**: Read 5-10 answers, check quality

## Industry Best Practices

### Prompt Engineering Principles

1. **Version Control**
   - Every prompt change is a git commit
   - Never modify production prompt directly
   - Tag stable versions: `git tag prompts/analytical-v2-stable`

2. **Testing**
   - Test before deploy
   - Regression tests: Ensure new version doesn't break old queries
   - Metrics: Track answer quality over time

3. **Documentation**
   - Document intent: Why this prompt style exists
   - Document changes: What changed between versions
   - Document usage: When to use each style

4. **Monitoring**
   - Log which prompt is active
   - Track user satisfaction (if available)
   - Monitor answer quality metrics

5. **Rollback Plan**
   - Keep old versions
   - Document how to rollback
   - Test rollback procedure

### Advanced Techniques

#### Parameterized Prompts

For complex use cases, consider template variables:

```python
# In prompt file:
# "Focus on {focus_area} when analyzing..."

# In code:
prompt = get_prompt("analytical")
prompt = prompt.format(focus_area="voting patterns")
```

#### Prompt Composition

Layer prompts for complex tasks:

```python
base_prompt = get_prompt("analytical")
domain_knowledge = get_prompt("un_specific_guidelines")
final_prompt = f"{base_prompt}\n\n{domain_knowledge}"
```

#### Dynamic Prompt Selection

Choose prompt based on query type:

```python
if query_type == "list":
    prompt_style = "strict"  # Just list the facts
elif query_type == "analysis":
    prompt_style = "analytical"  # Synthesize patterns
```

## Current Prompts

### analytical_v1 (Default)

**Purpose**: Concise memo-style analysis for decision-makers

**Characteristics**:
- 1-2 paragraphs typically
- Organized by themes/patterns
- Natural citations
- Direct, professional tone
- ~1500-1800 chars average

**Use when**: User wants actionable insights, briefings, summaries

### strict_v1

**Purpose**: Defensive evidence-based answers with clear attribution

**Characteristics**:
- Explicit source citations
- "What's known / inferred / unknown" structure
- Verbatim quotes
- ~2500-3000 chars average

**Use when**: Legal contexts, audits, need full attribution

### conversational_v1

**Purpose**: Natural, accessible narrative style

**Characteristics**:
- Flowing prose
- Organic citations
- Less structure
- ~1800-2200 chars average

**Use when**: Public-facing content, general audience

## Migration Notes

### Old System (YAML-based)

```yaml
# Old: rag/prompt_config.yaml
analytical:
  system_instructions: |
    Long multi-line prompt...
```

### New System (File-based)

```
# New: rag/prompts/analytical_v1.txt
Just the prompt text, no YAML
```

### Code Changes

```python
# Old
from rag.prompt_config import get_prompt_style
prompt = get_prompt_style("analytical")

# New
from rag.prompt_registry import get_prompt
prompt = get_prompt("analytical")
```

The YAML config is kept for backward compatibility but deprecated.

## Future Enhancements

### Considered for Future

1. **Prompt A/B Testing Framework**
   - Automatic random selection
   - Track performance metrics
   - Statistical comparison

2. **Prompt Performance Dashboard**
   - Answer length over time
   - User satisfaction scores
   - Common failure modes

3. **Auto-versioning**
   - Git hooks to auto-increment versions
   - Changelog generation

4. **Prompt Linting**
   - Check for common antipatterns
   - Enforce style guidelines
   - Maximum length checks

5. **Multi-language Prompts**
   - `analytical_v1_en.txt`
   - `analytical_v1_fr.txt`

## Resources

- **Testing**: See `rag/README_TESTING.md`
- **Prompt Files**: See `rag/prompts/README.md`
- **Examples**: See `rag/test_queries.yaml`
