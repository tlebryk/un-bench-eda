"""Prompt registry for managing RAG system prompts as versioned files."""

import os
from pathlib import Path
from typing import Optional, List, Dict
import logging

logger = logging.getLogger(__name__)

# Default prompts directory
PROMPTS_DIR = Path(__file__).parent / "prompts"

# Default prompt style (can be overridden by environment variable)
DEFAULT_PROMPT_STYLE = "analytical"


class PromptRegistry:
    """
    Registry for loading and managing system prompts.

    Prompts are stored as individual files in rag/prompts/:
    - analytical_v1.txt
    - strict_v1.txt
    - conversational_v1.txt

    Supports versioning: If you have analytical_v1.txt and analytical_v2.txt,
    calling load("analytical") will load the highest version.
    """

    def __init__(self, prompts_dir: Path = PROMPTS_DIR):
        self.prompts_dir = prompts_dir
        self._cache: Dict[str, str] = {}

    def load(self, style: str, version: Optional[int] = None) -> str:
        """
        Load a prompt by style name.

        Args:
            style: Prompt style name (e.g., "analytical", "strict")
            version: Optional specific version to load (e.g., 1, 2)
                    If not specified, loads the highest version available

        Returns:
            Prompt text as string

        Raises:
            FileNotFoundError: If prompt file doesn't exist
        """
        cache_key = f"{style}_v{version}" if version else style

        # Check cache
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Find prompt file
        if version:
            # Load specific version
            prompt_file = self.prompts_dir / f"{style}_v{version}.txt"
        else:
            # Load highest version
            prompt_file = self._find_latest_version(style)

        if not prompt_file or not prompt_file.exists():
            available = self.list_available()
            raise FileNotFoundError(
                f"Prompt '{style}' (version {version}) not found in {self.prompts_dir}. "
                f"Available prompts: {', '.join(available)}"
            )

        # Load and cache
        logger.info(f"Loading prompt from {prompt_file}")
        with open(prompt_file, 'r') as f:
            prompt_text = f.read().strip()

        self._cache[cache_key] = prompt_text
        return prompt_text

    def _find_latest_version(self, style: str) -> Optional[Path]:
        """Find the highest version of a prompt style."""
        pattern = f"{style}_v*.txt"
        matching_files = sorted(self.prompts_dir.glob(pattern))

        if not matching_files:
            return None

        # Return the last file (highest version) when sorted
        return matching_files[-1]

    def list_available(self) -> List[str]:
        """List all available prompt styles."""
        if not self.prompts_dir.exists():
            return []

        styles = set()
        for file in self.prompts_dir.glob("*.txt"):
            # Extract style name (before _v)
            name = file.stem
            if "_v" in name:
                style = name.split("_v")[0]
                styles.add(style)

        return sorted(styles)

    def list_versions(self, style: str) -> List[int]:
        """List all available versions for a prompt style."""
        pattern = f"{style}_v*.txt"
        matching_files = self.prompts_dir.glob(pattern)

        versions = []
        for file in matching_files:
            # Extract version number
            name = file.stem
            if "_v" in name:
                try:
                    version = int(name.split("_v")[1])
                    versions.append(version)
                except ValueError:
                    continue

        return sorted(versions)


# Global registry instance
_registry = PromptRegistry()


def get_prompt(
    style: Optional[str] = None,
    version: Optional[int] = None
) -> str:
    """
    Get a prompt by style name.

    Args:
        style: Prompt style name. If None, uses RAG_PROMPT_STYLE env var
               or defaults to "analytical"
        version: Optional specific version to load

    Returns:
        Prompt text as string
    """
    if style is None:
        # Check environment variable
        style = os.getenv("RAG_PROMPT_STYLE", DEFAULT_PROMPT_STYLE)

    return _registry.load(style, version)


def list_prompts() -> List[str]:
    """List all available prompt styles."""
    return _registry.list_available()


def list_prompt_versions(style: str) -> List[int]:
    """List all versions for a prompt style."""
    return _registry.list_versions(style)
