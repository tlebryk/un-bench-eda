# UN Draft Documentation

This Sphinx site aggregates the living design notes that power the UN Document Scraper, RAG stack, and Deliberation Gym. Markdown lives in `docs/` so the same source material also stays readable from the repository.

## Build the docs locally

```bash
uv run sphinx-build -b html docs/source docs/_build/html
open docs/_build/html/index.html
```

```{toctree}
:caption: Product Briefing
:maxdepth: 2

../project
../rag_enhancement_plan
../training_eval
```

```{toctree}
:caption: Pipelines & Gym
:maxdepth: 2

../etl
../gym
```

```{toctree}
:caption: Platform & Reference
:maxdepth: 2

../README_DATABASE
../TODO_UI
../un_document_structure
```

```{toctree}
:caption: API Reference
:maxdepth: 2

api
```
