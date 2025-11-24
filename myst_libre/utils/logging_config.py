"""
logging_config.py

Centralized logging configuration for myst-libre.
"""

import logging
import sys
from typing import Optional
from pathlib import Path


def configure_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    format_string: Optional[str] = None,
    use_rich: bool = True
) -> None:
    """
    Configure logging for the entire myst-libre package.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path to write logs to
        format_string: Custom format string for log messages
        use_rich: Whether to use rich formatting (default: True)

    Example:
        >>> from myst_libre.utils import configure_logging
        >>> configure_logging(level="DEBUG", log_file="myst.log")
    """
    # Convert string level to logging constant
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Invalid log level: {level}')

    # Default format
    if format_string is None:
        format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove existing handlers
    root_logger.handlers.clear()

    # Console handler with rich if available
    if use_rich:
        try:
            from rich.logging import RichHandler
            console_handler = RichHandler(
                level=numeric_level,
                show_time=True,
                show_path=True,
                markup=True
            )
        except ImportError:
            # Fall back to standard console handler if rich not available
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(numeric_level)
            console_formatter = logging.Formatter(format_string)
            console_handler.setFormatter(console_formatter)
    else:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        console_formatter = logging.Formatter(format_string)
        console_handler.setFormatter(console_formatter)

    root_logger.addHandler(console_handler)

    # File handler if specified
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(numeric_level)
        file_formatter = logging.Formatter(format_string)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    # Configure package logger
    package_logger = logging.getLogger('myst_libre')
    package_logger.setLevel(numeric_level)

    # Log configuration details
    package_logger.debug(
        f"Logging configured: level={level}, log_file={log_file}, use_rich={use_rich}"
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the given name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("Starting process")
    """
    return logging.getLogger(name)


def set_log_level(level: str, logger_name: Optional[str] = None) -> None:
    """
    Change the log level for a specific logger or the root logger.

    Args:
        level: New logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        logger_name: Optional specific logger name, or None for root logger

    Example:
        >>> set_log_level("DEBUG", "myst_libre.rees")
    """
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Invalid log level: {level}')

    if logger_name:
        logger = logging.getLogger(logger_name)
    else:
        logger = logging.getLogger()

    logger.setLevel(numeric_level)
