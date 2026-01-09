"""Load and manage RAG prompt configurations."""

import yaml
from pathlib import Path
from typing import Dict, Any

# Default prompt config file location
DEFAULT_CONFIG_FILE = Path(__file__).parent / "prompt_config.yaml"


def load_prompt_config(config_file: Path = DEFAULT_CONFIG_FILE) -> Dict[str, Any]:
    """
    Load prompt configurations from YAML file.

    Args:
        config_file: Path to YAML config file

    Returns:
        Dictionary of prompt configurations
    """
    with open(config_file, 'r') as f:
        return yaml.safe_load(f)


def get_prompt_style(style: str = "analytical", config_file: Path = DEFAULT_CONFIG_FILE) -> str:
    """
    Get system instructions for a specific prompt style.

    Args:
        style: Prompt style name ("strict", "analytical", "conversational")
        config_file: Path to YAML config file

    Returns:
        System instructions string

    Raises:
        ValueError: If style not found in config
    """
    config = load_prompt_config(config_file)

    if style not in config:
        available_styles = ", ".join(config.keys())
        raise ValueError(
            f"Prompt style '{style}' not found. Available styles: {available_styles}"
        )

    return config[style]["system_instructions"]


def list_prompt_styles(config_file: Path = DEFAULT_CONFIG_FILE) -> Dict[str, str]:
    """
    List all available prompt styles with descriptions.

    Args:
        config_file: Path to YAML config file

    Returns:
        Dictionary mapping style names to descriptions
    """
    config = load_prompt_config(config_file)
    return {
        name: info["description"]
        for name, info in config.items()
    }
