"""
exceptions.py

Custom exception hierarchy for myst-libre.
"""


class MystLibreError(Exception):
    """Base exception for all myst-libre errors."""
    pass


class ConfigurationError(MystLibreError):
    """Raised when configuration validation fails."""
    pass


class DockerRegistryError(MystLibreError):
    """Raised when Docker registry operations fail."""
    pass


class DockerError(MystLibreError):
    """Raised when Docker operations fail."""
    pass


class GitOperationError(MystLibreError):
    """Raised when Git operations fail."""
    pass


class BuildError(MystLibreError):
    """Raised when build operations fail."""
    pass


class ContainerError(MystLibreError):
    """Raised when container operations fail."""
    pass


class AuthenticationError(MystLibreError):
    """Raised when authentication fails."""
    pass


class ImageNotFoundError(DockerRegistryError):
    """Raised when Docker image is not found in registry."""
    pass


class PortAllocationError(ContainerError):
    """Raised when no available ports can be found."""
    pass
