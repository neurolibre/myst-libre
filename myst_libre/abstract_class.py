"""
abstract_class.py

This module contains the AbstractClass which provides basic logging functionality
and colored printing capabilities using Rich.
"""

import logging
from typing import Optional
from rich.console import Console
from rich.logging import RichHandler


class AbstractClass:
    """
    AbstractClass

    A base class that provides logging functionality and methods for printing colored messages.
    Uses Rich library for beautiful, modern terminal output.
    """

    # Shared console instance for consistent styling
    _console = Console()

    def __init__(self):
        """
        Initialize the AbstractClass with default logging settings.
        """
        self.logging_level = logging.INFO
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(self.logging_level)

        # Use RichHandler for beautiful logging output
        if not self.logger.handlers:
            handler = RichHandler(rich_tracebacks=True, show_path=False)
            handler.setFormatter(logging.Formatter('%(message)s'))
            self.logger.addHandler(handler)

    def set_log_level(self, level: int):
        """
        Set the logging level.

        Args:
            level: Logging level (e.g., logging.DEBUG, logging.INFO)
        """
        self.logging_level = level
        self.logger.setLevel(level)

    def cprint(self, message: str, color: Optional[str] = None, highlight: Optional[str] = None):
        """
        Print a message with optional color and background using Rich.

        Args:
            message: The message to print
            color: Color name (e.g., 'green', 'red', 'blue', 'yellow', 'cyan', 'magenta')
            highlight: Background color (use format like 'on_blue', 'on_red')

        Examples:
            >>> self.cprint("Success!", "green")
            >>> self.cprint("Error!", "white", "on_red")
            >>> self.cprint("Info", "cyan")
        """
        # Map old termcolor names to rich styles
        color_map = {
            'light_grey': 'bright_black',
            'light_blue': 'bright_blue',
            'light_red': 'bright_red',
            'black': 'black',
            'red': 'red',
            'green': 'green',
            'yellow': 'yellow',
            'blue': 'blue',
            'magenta': 'magenta',
            'cyan': 'cyan',
            'white': 'white',
        }

        # Build style string
        styles = []
        if color:
            rich_color = color_map.get(color, color)
            styles.append(rich_color)

        if highlight:
            # Convert 'on_blue' to 'on blue' for Rich
            bg_color = highlight.replace('on_', 'on ')
            styles.append(bg_color)

        style = ' '.join(styles) if styles else None
        self._console.print(message, style=style)

    def print_success(self, message: str):
        """Print a success message in green."""
        self.cprint(f"✓ {message}", "green")

    def print_error(self, message: str):
        """Print an error message in red."""
        self.cprint(f"✗ {message}", "red")

    def print_warning(self, message: str):
        """Print a warning message in yellow."""
        self.cprint(f"⚠ {message}", "yellow")

    def print_info(self, message: str):
        """Print an info message in cyan."""
        self.cprint(f"ℹ {message}", "cyan")