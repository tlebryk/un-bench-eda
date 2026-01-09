"""Centralized logging configuration for the UN Draft project.

All logs go to the project root logs/ directory.
Usage:
    from utils.logging_config import get_logger
    logger = get_logger(__name__)
"""

import logging
from pathlib import Path
from typing import Optional


def get_logger(
    name: str,
    log_file: Optional[str] = None,
    level: int = logging.INFO
) -> logging.Logger:
    """
    Get a configured logger instance.

    Args:
        name: Logger name (typically __name__ from calling module)
        log_file: Optional specific log file name (defaults to module-based name)
        level: Logging level (default: INFO)

    Returns:
        Configured logger with file and console handlers
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Only add handlers if they haven't been added yet (avoid duplicates on reload)
    if not logger.handlers:
        # Determine log file path
        log_dir = Path(__file__).parent.parent / "logs"
        log_dir.mkdir(exist_ok=True)

        if log_file:
            log_path = log_dir / log_file
        else:
            # Default: use module name as log file (e.g., "ui.app" -> "ui_app.log")
            safe_name = name.replace(".", "_")
            log_path = log_dir / f"{safe_name}.log"

        # File handler
        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    return logger
