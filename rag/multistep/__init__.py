"""Multi-step RAG query support using OpenAI tool calling."""

# All imports are lazy to avoid import-time errors (e.g., missing DB config)
__all__ = [
    "get_trajectory_tool",
    "get_votes_tool",
    "get_utterances_tool",
    "answer_with_evidence_tool",
    "execute_get_trajectory",
    "execute_get_votes",
    "execute_get_utterances",
    "MultiStepOrchestrator",
]

# Lazy imports to avoid circular dependencies and import-time errors
def __getattr__(name):
    if name == "MultiStepOrchestrator":
        from rag.multistep.orchestrator import MultiStepOrchestrator
        return MultiStepOrchestrator
    elif name in __all__:
        from rag.multistep import tools
        attr = getattr(tools, name)
        # Cache the attribute in this module's namespace
        globals()[name] = attr
        return attr
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
