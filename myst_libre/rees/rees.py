"""
rees.py

Refactored REES (Reproducible Execution Environment Specification) orchestrator.

Uses composition pattern instead of multiple inheritance for better modularity.
"""

import subprocess
import os
from typing import Optional, Dict
from pathlib import Path

import docker
from docker.models.images import Image

from ..abstract_class import AbstractClass
from ..models import REESConfig, CommitInfo
from ..exceptions import DockerError, ConfigurationError
from ..utils.retry import retry_github_api
from ..tools.docker_registry_client import DockerRegistryClient
from ..tools.build_source_manager import BuildSourceManager


class REES(AbstractClass):
    """
    REES orchestrator for managing reproducible execution environments.

    Coordinates Docker registry operations and Git source management
    to provide a complete REES-compliant workflow.

    Uses composition instead of inheritance for better separation of concerns.
    """

    def __init__(self, rees_dict: Dict):
        """
        Initialize REES orchestrator.

        Args:
            rees_dict: Configuration dictionary with REES parameters

        Raises:
            ConfigurationError: If required configuration is missing or invalid
        """
        super().__init__()

        # Parse and validate configuration
        self.config = REESConfig.from_dict(rees_dict)

        # Initialize composed components
        self.registry_client = DockerRegistryClient(self.config, self.config.dotenv)
        self.source_manager = BuildSourceManager(self.config)

        # Docker state
        self.docker_client: Optional[docker.DockerClient] = None
        self.docker_image: Optional[Image] = None
        self.pull_image_name: str = ""
        self.use_public_registry: bool = False

        # Run preflight checks
        self.cprint("␤[Preflight checks]", "light_grey")
        self._check_docker_installed()

        # Discover image and resolve commit hash
        self._discover_image()
        self._resolve_commit_hash()

        # Initialize Docker client
        self.docker_client = docker.from_env()

    def _check_docker_installed(self):
        """
        Check if Docker is installed and available.

        First tries docker CLI. If that fails (e.g., in containers without CLI),
        verifies the Docker daemon is accessible via the Python Docker library.

        Raises:
            EnvironmentError: If Docker daemon is not accessible
        """
        cli_available = False
        try:
            result = subprocess.run(
                ['docker', '--version'],
                env=os.environ,
                capture_output=True,
                text=True,
                check=True
            )
            self.print_success(f"Docker is installed: {result.stdout.strip()}")
            cli_available = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Docker CLI not available (common in containers)
            # Try to verify daemon access via Python library
            try:
                import docker
                client = docker.from_env()
                client.ping()  # Test connection
                self.print_success("Docker daemon is accessible (via Python library)")
            except Exception as daemon_error:
                raise EnvironmentError(
                    "Docker daemon is not accessible. Ensure /var/run/docker.sock is mounted "
                    "in Docker-in-Docker scenarios."
                ) from daemon_error

    @retry_github_api
    def _resolve_commit_hash(self):
        """
        Resolve 'latest' commit hash to actual SHA from GitHub API.

        Retries on network failures with exponential backoff.
        """
        if self.config.gh_repo_commit_hash == "latest":
            self.cprint("🔎 Searching for latest commit hash in GitHub", "light_blue")

            api_url = f"https://api.github.com/repos/{self.config.gh_user_repo_name}/commits/{self.config.branch}"
            response = self.registry_client.rest_client.get(api_url)

            if response.status_code == 200:
                latest_commit_hash = response.json()['sha']
                self.config.gh_repo_commit_hash = latest_commit_hash
                self.cprint(
                    f"🎉 Found latest commit hash: {self.config.gh_repo_commit_hash}",
                    "white",
                    "on_blue"
                )
            else:
                self.logger.warning(
                    f"Failed to fetch latest commit: {response.status_code}. "
                    f"Using 'latest' as-is."
                )

    def _discover_image(self):
        """
        Discover Docker image in registry.

        Raises:
            ImageNotFoundError: If no matching image is found
        """
        if self.registry_client.search_image_by_repo_name():
            if self.config.binder_image_tag == "latest":
                self.cprint("🔎 Searching for latest image tag in registry", "light_blue")

                if self.registry_client.get_tags_sorted_by_date():
                    self.cprint(
                        f"🎉 Found latest tag in {self.config.registry_url}",
                        "light_blue"
                    )
                    latest_tag = self.registry_client.found_image_tags_sorted[0]
                    self.cprint(
                        f"🏷️  Latest runtime tag {latest_tag} for {self.registry_client.found_image_name}",
                        "white",
                        "on_blue"
                    )
                    self.config.binder_image_tag = latest_tag

    def login_to_registry(self):
        """
        Login to private Docker registry.

        Raises:
            DockerError: If login fails
        """
        if not self.docker_client:
            raise DockerError("Docker client not initialized")

        auth = self.registry_client.rest_client._auth

        try:
            self.docker_client.login(
                username=auth['username'],
                password=auth['password'],
                registry=self.config.registry_url
            )
            self.logger.info(f"Logged into {self.config.registry_url}")
        except docker.errors.APIError as e:
            raise DockerError(f"Failed to login to registry: {e}") from e

    def pull_image(self):
        """
        Pull the Docker image from the registry.

        Raises:
            DockerError: If image pull fails
        """
        if not self.docker_client:
            raise DockerError("Docker client not initialized")

        # Login if using private registry or auth is available
        auth = self.registry_client.rest_client._auth
        if auth or not self.use_public_registry:
            self.login_to_registry()

        found_image_name = self.registry_client.found_image_name
        if not found_image_name:
            raise DockerError("No image name found. Run discovery first.")

        try:
            # Try with project prefix first
            if self.config.bh_project_name:
                self.pull_image_name = f"{self.config.bh_project_name}/{found_image_name}"
            else:
                self.pull_image_name = found_image_name

            self.logger.info(
                f"Pulling image {self.pull_image_name}:{self.config.binder_image_tag} "
                f"from {self.config.registry_url}"
            )

            self.docker_image = self.docker_client.images.pull(
                self.pull_image_name,
                tag=self.config.binder_image_tag
            )

        except (docker.errors.ImageNotFound, docker.errors.APIError) as e:
            self.logger.warning(f"Failed to pull with project prefix: {e}. Trying without prefix.")

            try:
                # Fallback: try without project prefix
                self.pull_image_name = found_image_name
                self.logger.info(
                    f"Pulling image {found_image_name}:{self.config.binder_image_tag} "
                    f"from {self.config.registry_url}"
                )

                self.docker_image = self.docker_client.images.pull(
                    found_image_name,
                    tag=self.config.binder_image_tag
                )

            except docker.errors.DockerException as fallback_error:
                raise DockerError(
                    f"Failed to pull Docker image '{found_image_name}:{self.config.binder_image_tag}' "
                    f"from {self.config.registry_url}. "
                    f"Original error: {e}. Fallback error: {fallback_error}"
                ) from fallback_error

    # Delegate Git operations to source_manager
    def git_clone_repo(self, clone_parent_directory: Path) -> bool:
        """Clone repository. Delegates to BuildSourceManager."""
        return self.source_manager.git_clone_repo(clone_parent_directory)

    def git_checkout_commit(self) -> bool:
        """Checkout commit. Delegates to BuildSourceManager."""
        return self.source_manager.git_checkout_commit()

    def get_project_name(self) -> Optional[str]:
        """Get project name. Delegates to BuildSourceManager."""
        return self.source_manager.get_project_name()

    def repo2data_download(self, target_directory: Path):
        """Download data. Delegates to BuildSourceManager."""
        return self.source_manager.repo2data_download(target_directory)

    def save_successful_build(self) -> bool:
        """Save successful build. Delegates to BuildSourceManager."""
        return self.source_manager.save_successful_build()

    # Properties for backward compatibility
    @property
    def gh_user_repo_name(self) -> str:
        """GitHub user/repo name."""
        return self.config.gh_user_repo_name

    @property
    def gh_repo_commit_hash(self) -> str:
        """Commit hash to build."""
        return self.config.gh_repo_commit_hash

    @property
    def binder_image_tag(self) -> str:
        """Binder image tag."""
        return self.config.binder_image_tag

    @property
    def binder_image_name_override(self) -> Optional[str]:
        """Binder image name override."""
        return self.config.binder_image_name_override

    @property
    def branch(self) -> str:
        """Git branch name."""
        return self.config.branch

    @property
    def build_dir(self) -> Optional[Path]:
        """Current build directory."""
        return self.source_manager.build_dir

    @property
    def dataset_name(self) -> Optional[str]:
        """Dataset name from build context."""
        return self.source_manager.dataset_name

    @property
    def found_image_name(self) -> Optional[str]:
        """Found Docker image name."""
        return self.registry_client.found_image_name

    @property
    def repo_commit_info(self) -> Optional[Dict]:
        """Repository commit information."""
        if self.source_manager.build_context and self.source_manager.build_context.repo_commit_info:
            info = self.source_manager.build_context.repo_commit_info
            return {
                'datetime': info.datetime,
                'message': info.message
            }
        return {}

    @property
    def binder_commit_info(self) -> Optional[Dict]:
        """Binder image commit information."""
        if self.source_manager.build_context and self.source_manager.build_context.binder_commit_info:
            info = self.source_manager.build_context.binder_commit_info
            return {
                'datetime': info.datetime,
                'message': info.message
            }
        return {}
