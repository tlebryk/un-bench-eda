"""Pytest configuration."""

import sys
from pathlib import Path

# Add workspace to path so we can import un_gym
workspace = Path(__file__).parent.parent
sys.path.insert(0, str(workspace))
