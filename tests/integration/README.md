# Integration Tests

Integration tests for the UN documents database RAG system. These tests verify SQL-based functionality against a real PostgreSQL database.

## Setup

### 1. Start Development Database

```bash
docker-compose up postgres_dev -d
```

This starts a PostgreSQL database on port 5434:
- Database: `un_documents_dev`
- User: `un_user`
- Password: `un_password`
- Port: `5434`

### 2. Set Environment Variables

Add to your `.env` file:

```bash
USE_DEV_DB=true
DEV_DATABASE_URL=postgresql://un_user:un_password@localhost:5434/un_documents_dev
```

### 3. Seed Test Data

```bash
PYTHONPATH=. USE_DEV_DB=true DEV_DATABASE_URL=postgresql://un_user:un_password@localhost:5434/un_documents_dev \
  uv run python scripts/seed_dev_db.py
```

This creates known test data:
- Resolution: `A/RES/78/300`
- Draft: `A/C.3/78/L.41`
- Committee Report: `A/78/481`
- Meetings: `A/78/PV.99`, `A/78/PV.100`
- Agenda Item: `A/78/251`
- 10 countries with votes
- 5 utterances with document links

The script is idempotent - run it multiple times to reset test data.

## Running Tests

### Run All Integration Tests

```bash
USE_DEV_DB=true uv run pytest tests/integration/ -v
```

### Run Specific Test Suite

```bash
USE_DEV_DB=true uv run pytest tests/integration/test_related_documents_integration.py::TestGetRelatedDocuments -v
```

### Run With Output

```bash
USE_DEV_DB=true uv run pytest tests/integration/test_related_documents_integration.py -v -s
```

## Test Coverage

### TestGetRelatedDocuments
- ✅ `test_get_related_documents_for_resolution` - Get drafts, meetings, reports for a resolution
- ✅ `test_get_related_documents_for_draft` - Get resolution and agenda items for a draft
- ✅ `test_recursive_traversal` - Verify multi-level relationship traversal
- ✅ `test_nonexistent_document` - Handle missing documents gracefully
- ✅ `test_document_with_no_relationships` - Handle isolated documents

### TestChainedToolCalls
- ✅ `test_resolution_to_utterances_chain` - Chain: resolution → meetings → utterances
- ✅ `test_resolution_to_votes_chain` - Get votes for a resolution
- ✅ `test_full_orchestrator_pattern` - Complete workflow: resolution → related docs → utterances + votes

### TestUtteranceDocumentPrecision
- ✅ `test_utterances_linked_to_resolution` - Verify utterances are linked to specific documents
- ✅ `test_voting_utterances_precision` - Verify voting utterances have `reference_type='voting_on'`

## Resetting Test Data

To drop test data without recreating:

```bash
PYTHONPATH=. USE_DEV_DB=true uv run python scripts/seed_dev_db.py --drop-only
```

To recreate test data:

```bash
PYTHONPATH=. USE_DEV_DB=true uv run python scripts/seed_dev_db.py
```

## Troubleshooting

### Database Connection Fails

Check if postgres_dev is running:
```bash
docker ps | grep un_documents_db_dev
```

Restart if needed:
```bash
docker-compose restart postgres_dev
```

### Wrong Database Being Used

Verify environment variables:
```bash
echo $USE_DEV_DB
echo $DEV_DATABASE_URL
```

### Module Not Found Errors

Ensure `PYTHONPATH=.` is set when running scripts:
```bash
PYTHONPATH=. uv run python scripts/seed_dev_db.py
```

### Tests Fail After Schema Changes

Re-run migrations on dev database:
```bash
# Add your migration commands here
```

Then reseed:
```bash
PYTHONPATH=. USE_DEV_DB=true uv run python scripts/seed_dev_db.py
```

## Test Data Structure

```
Resolution: A/RES/78/300
├── Draft: A/C.3/78/L.41
│   └── Agenda Item: A/78/251
├── Committee Report: A/78/481
├── Meetings:
│   ├── A/78/PV.99 (3 utterances)
│   └── A/78/PV.100 (2 voting utterances)
└── Votes: 10 countries
    ├── In favour: 4
    ├── Against: 3
    └── Abstaining: 3
```

## CI/CD Integration

For CI/CD pipelines, use Docker Compose to run tests:

```yaml
# Example GitHub Actions workflow
- name: Start dev database
  run: docker-compose up postgres_dev -d

- name: Wait for database
  run: |
    timeout 30 sh -c 'until docker exec un_documents_db_dev pg_isready; do sleep 1; done'

- name: Seed test data
  run: PYTHONPATH=. USE_DEV_DB=true uv run python scripts/seed_dev_db.py

- name: Run integration tests
  run: USE_DEV_DB=true uv run pytest tests/integration/ -v
```
