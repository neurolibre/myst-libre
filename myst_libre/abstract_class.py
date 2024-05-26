"""
abstract_class.py

This module contains the AbstractClass which provides basic logging functionality 
and colored printing capabilities.
"""

import logging
from termcolor import colored

class AbstractClass:
    """
    AbstractClass

    A base class that provides logging functionality and methods for printing colored messages.
    """
    def __init__(self):
        """
        Initialize the AbstractClass with default logging settings.
        """
        self.logging_level = logging.INFO
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(self.logging_level)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        if not self.logger.handlers:  # Avoid adding multiple handlers if already set
            self.logger.addHandler(handler)

    def set_log_level(self, level):
        """
        Set the logging level.
        
        Args:
            level (str): Logging level.
        """
        self.logging_level = level
        self.logger = logging.basicConfig(level=self.logging_level, format='%(asctime)s - %(levelname)s - %(message)s')
    
    def cprint(self, message, color):
        """
        Print a message in a specified color using termcolor.
        
        Args:
            message (str): The message to print.
            color (str): The color to use for printing the message.
        """
        print(colored(message, color))