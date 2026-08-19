"""
myst-libre: Build MyST articles in containerized environments following REES.
"""

# Core classes
from .rees import REES
from .models import REESConfig, ContainerConfig, CommitInfo, BuildContext
from .exceptions import (
    MystLibreError,
    ConfigurationError,
    DockerError,
    DockerRegistryError,
    GitOperationError,
    BuildError,
    ContainerError,
    ImageNotFoundError,
    PortAllocationError,
)

__version__ = "dynamic"  # Set by setuptools_scm

__all__ = [
    'REES',
    'REESConfig',
    'ContainerConfig',
    'CommitInfo',
    'BuildContext',
    'MystLibreError',
    'ConfigurationError',
    'DockerError',
    'DockerRegistryError',
    'GitOperationError',
    'BuildError',
    'ContainerError',
    'ImageNotFoundError',
    'PortAllocationError',
]
