"""Load model configuration for RAG system.

Note: Prompt text is now managed by rag/prompt_registry.py using versioned .txt files.
This module only handles model configuration (which model to use by default).
"""

import yaml
import os
from pathlib import Path
from typing import Dict, Any
from jinja2 import Template

# Default model config file location
DEFAULT_CONFIG_FILE = Path(__file__).parent / "model_config.yaml"


def load_model_config(config_file: Path = DEFAULT_CONFIG_FILE) -> Dict[str, Any]:
    """
    Load model configuration from YAML file with Jinja2 support.

    Args:
        config_file: Path to YAML config file

    Returns:
        Dictionary of model configurations
    """
    with open(config_file, 'r') as f:
        content = f.read()

    # Render with Jinja2 using environment variables
    template = Template(content)
    rendered_content = template.render(env=os.environ)

    return yaml.safe_load(rendered_content)


def get_default_model(config_file: Path = DEFAULT_CONFIG_FILE) -> str:
    """Get the default model from configuration."""
    config = load_model_config(config_file)
    return config.get("default_model", "gpt-5-mini-2025-08-07")


# Backward compatibility alias (deprecated)
def load_prompt_config(config_file: Path = DEFAULT_CONFIG_FILE) -> Dict[str, Any]:
    """
    Deprecated: Use load_model_config() instead.
    Kept for backward compatibility.
    """
    return load_model_config(config_file)
