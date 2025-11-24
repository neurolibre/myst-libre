"""
models.py

Domain models for myst-libre using dataclasses.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Tuple
from datetime import datetime

from .constants import (
    DEFAULT_BRANCH,
    DEFAULT_BINDER_IMAGE_PREFIX,
    DEFAULT_IMAGE_TAG,
    DEFAULT_PORT_RANGE,
)
from .exceptions import ConfigurationError


@dataclass
class REESConfig:
    """
    Configuration for REES (Reproducible Execution Environment Specification).

    Attributes:
        registry_url: URL of the Docker registry (e.g., 'https://my-registry.io')
        gh_user_repo_name: GitHub repository in format 'user/repo'
        gh_repo_commit_hash: Commit hash to build (default: 'latest')
        branch: Git branch name (default: 'main')
        binder_image_tag: Docker image tag (default: 'latest')
        binder_image_name_override: Optional override for image name
        bh_image_prefix: BinderHub image prefix (default: 'binder-')
        bh_project_name: Optional BinderHub project name
        dotenv: Path to .env file for credentials (default: '.')
    """
    registry_url: str
    gh_user_repo_name: str
    gh_repo_commit_hash: str = "latest"
    branch: str = DEFAULT_BRANCH
    binder_image_tag: str = DEFAULT_IMAGE_TAG
    binder_image_name_override: Optional[str] = None
    bh_image_prefix: str = DEFAULT_BINDER_IMAGE_PREFIX
    bh_project_name: Optional[str] = None
    dotenv: str = '.'

    def __post_init__(self):
        """Validate configuration after initialization."""
        self._validate()

    def _validate(self):
        """Validate required fields and formats."""
        if not self.registry_url:
            raise ConfigurationError("registry_url is required")

        if not self.registry_url.startswith(('http://', 'https://')):
            raise ConfigurationError(
                f"registry_url must start with http:// or https://, got: {self.registry_url}"
            )

        if not self.gh_user_repo_name:
            raise ConfigurationError("gh_user_repo_name is required")

        if '/' not in self.gh_user_repo_name:
            raise ConfigurationError(
                f"gh_user_repo_name must be in format 'user/repo', got: {self.gh_user_repo_name}"
            )

        parts = self.gh_user_repo_name.split('/')
        if len(parts) != 2 or not all(parts):
            raise ConfigurationError(
                f"gh_user_repo_name must be in format 'user/repo', got: {self.gh_user_repo_name}"
            )

    @property
    def username(self) -> str:
        """Extract username from gh_user_repo_name."""
        return self.gh_user_repo_name.split('/')[0]

    @property
    def repo_name(self) -> str:
        """Extract repository name from gh_user_repo_name."""
        return self.gh_user_repo_name.split('/')[1]

    @classmethod
    def from_dict(cls, config_dict: Dict) -> 'REESConfig':
        """
        Create REESConfig from dictionary.

        Args:
            config_dict: Dictionary with configuration values

        Returns:
            REESConfig instance

        Raises:
            ConfigurationError: If required fields are missing
        """
        required_fields = {'registry_url', 'gh_user_repo_name'}
        missing = required_fields - set(config_dict.keys())
        if missing:
            raise ConfigurationError(f"Missing required configuration fields: {missing}")

        return cls(**{k: v for k, v in config_dict.items() if k in cls.__dataclass_fields__})


@dataclass
class ContainerConfig:
    """
    Configuration for Docker container spawning.

    Attributes:
        host_build_source_parent_dir: Parent directory on host for build sources
        container_build_source_mount_dir: Mount point in container for build sources
        host_data_parent_dir: Parent directory on host for data
        container_data_mount_dir: Mount point in container for data
        port_range: Tuple of (min_port, max_port) for port allocation
        host_path_prefix: (Optional) Host path prefix for Docker-in-Docker scenarios.
            When myst-libre runs in a container and spawns sibling containers,
            this translates container paths to host paths for volume mounts.
        container_path_prefix: (Optional) Container path prefix to replace.
            Default: "/" (root of container filesystem)
    """
    host_build_source_parent_dir: Path
    container_build_source_mount_dir: str
    host_data_parent_dir: Path
    container_data_mount_dir: str
    port_range: Tuple[int, int] = DEFAULT_PORT_RANGE
    host_path_prefix: Optional[str] = None
    container_path_prefix: str = "/"

    def __post_init__(self):
        """Convert string paths to Path objects."""
        if isinstance(self.host_build_source_parent_dir, str):
            self.host_build_source_parent_dir = Path(self.host_build_source_parent_dir)
        if isinstance(self.host_data_parent_dir, str):
            self.host_data_parent_dir = Path(self.host_data_parent_dir)

        self._validate()

    def _validate(self):
        """Validate configuration."""
        if not self.container_build_source_mount_dir:
            raise ConfigurationError("container_build_source_mount_dir is required")

        if not self.container_data_mount_dir:
            raise ConfigurationError("container_data_mount_dir is required")

        min_port, max_port = self.port_range
        if min_port >= max_port:
            raise ConfigurationError(
                f"Invalid port range: {self.port_range}. min_port must be < max_port"
            )
        if min_port < 1024 or max_port > 65535:
            raise ConfigurationError(
                f"Port range must be between 1024 and 65535, got: {self.port_range}"
            )


@dataclass
class CommitInfo:
    """Information about a Git commit."""
    datetime: datetime
    message: str
    hash: Optional[str] = None

    def __str__(self) -> str:
        """String representation of commit info."""
        return f"{self.datetime}: {self.message.strip()}"


@dataclass
class DockerImageInfo:
    """Information about a Docker image."""
    name: str
    tag: str
    registry: str
    full_name: str = field(init=False)

    def __post_init__(self):
        """Compute full image name."""
        self.full_name = f"{self.name}:{self.tag}"


@dataclass
class BuildContext:
    """Context information for a build operation."""
    build_dir: Path
    dataset_name: Optional[str] = None
    preserve_cache: bool = True
    repo_commit_info: Optional[CommitInfo] = None
    binder_commit_info: Optional[CommitInfo] = None

    def __post_init__(self):
        """Convert string paths to Path objects."""
        if isinstance(self.build_dir, str):
            self.build_dir = Path(self.build_dir)
