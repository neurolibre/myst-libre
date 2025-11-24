"""
build_source_manager.py

Refactored BuildSourceManager for handling Git repositories and build management.
"""

import os
import json
import shutil
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime

# Silence git python warnings
os.environ["GIT_PYTHON_REFRESH"] = "quiet"
from git import Repo, GitCommandError

from ..abstract_class import AbstractClass
from ..models import REESConfig, CommitInfo, BuildContext
from ..exceptions import GitOperationError, ConfigurationError
from ..constants import (
    DEFAULT_GIT_PROVIDER,
    BUILD_CACHE_DIR,
    DATA_DIR,
    DATA_REQUIREMENT_FILE,
    GIT_EXCLUDE_FILE,
    LATEST_BUILD_MARKER,
    LATEST_DIR_NAME,
)
from repo2data.repo2data import Repo2Data


class BuildSourceManager(AbstractClass):
    """
    Manager for handling source code repositories and build operations.

    Responsibilities:
    - Git repository cloning and management
    - Build directory management with "latest" pattern
    - Build cache preservation
    - Data dependency downloads via repo2data
    - Commit information tracking
    """

    def __init__(self, config: REESConfig):
        """
        Initialize BuildSourceManager.

        Args:
            config: REES configuration
        """
        super().__init__()
        self.config = config
        self.provider = DEFAULT_GIT_PROVIDER

        # Build context (set after cloning)
        self.build_context: Optional[BuildContext] = None
        self.repo_object: Optional[Repo] = None
        self.host_build_source_parent_dir: Optional[Path] = None

    @property
    def build_dir(self) -> Optional[Path]:
        """Get current build directory."""
        return self.build_context.build_dir if self.build_context else None

    @property
    def dataset_name(self) -> Optional[str]:
        """Get dataset name from build context."""
        return self.build_context.dataset_name if self.build_context else None

    @property
    def preserve_cache(self) -> bool:
        """Check if cache preservation is enabled."""
        return self.build_context.preserve_cache if self.build_context else True

    def git_clone_repo(self, clone_parent_directory: Path) -> bool:
        """
        Clone the GitHub repository into the 'latest' directory.

        Always works in the 'latest' folder to avoid cache snowballing.
        The latest directory is reused across builds and only successful builds
        are copied to commit-specific directories.

        Args:
            clone_parent_directory: Parent directory for cloning

        Returns:
            True if cloned, False if already existed

        Raises:
            GitOperationError: If clone operation fails
        """
        if isinstance(clone_parent_directory, str):
            clone_parent_directory = Path(clone_parent_directory)

        self.host_build_source_parent_dir = clone_parent_directory

        # Always use 'latest' directory for builds
        build_dir = (
            clone_parent_directory
            / self.config.username
            / self.config.repo_name
            / LATEST_DIR_NAME
        )

        try:
            if build_dir.exists():
                self.print_warning(f"Source {build_dir} already exists, will reuse and update")
                self.repo_object = Repo(str(build_dir))

                # Fetch latest commits
                self.cprint("Fetching latest commits from origin", "cyan")
                self.repo_object.remotes.origin.fetch()
                cloned_new = False
            else:
                # Create parent directories
                build_dir.parent.mkdir(parents=True, exist_ok=True)

                # Clone repository
                self.print_success(f"Cloning into {build_dir}")
                repo_url = f"{self.provider}/{self.config.gh_user_repo_name}"
                self.repo_object = Repo.clone_from(repo_url, str(build_dir))
                cloned_new = True

            # Initialize build context
            self.build_context = BuildContext(
                build_dir=build_dir,
                preserve_cache=True,
            )

            # Set commit information
            self._set_commit_info()

            return cloned_new

        except GitCommandError as e:
            raise GitOperationError(f"Failed to clone repository: {e}") from e
        except (OSError, PermissionError, ValueError) as e:
            raise GitOperationError(f"System error during clone: {e}") from e

    def git_checkout_commit(self) -> bool:
        """
        Checkout the specified commit in the repository.

        Fetches latest changes, cleans the working directory, and checks out the commit.
        The _build folder is preserved via git exclude if preserve_cache is True.

        Returns:
            True if checked out successfully

        Raises:
            GitOperationError: If checkout operation fails
        """
        if not self.repo_object or not self.build_dir:
            raise GitOperationError("Repository not cloned. Call git_clone_repo first.")

        try:
            # Configure git exclude for cache and data preservation
            self._configure_git_exclude()

            # Fetch latest changes
            self.cprint("Fetching latest changes from origin", "cyan")
            self.repo_object.remotes.origin.fetch()

            # Clean working directory (respecting excludes)
            self._clean_working_directory()

            # Reset any local changes
            self.repo_object.git.reset('--hard')

            # Checkout specified commit
            self.print_success(f"Checking out {self.config.gh_repo_commit_hash}")
            self.repo_object.git.checkout(self.config.gh_repo_commit_hash)

            return True

        except GitCommandError as e:
            self.print_error(f"Failed to checkout {self.config.gh_repo_commit_hash}: {e}")
            raise GitOperationError(f"Checkout failed: {e}") from e
        except (OSError, PermissionError, ValueError) as e:
            raise GitOperationError(f"System error during checkout: {e}") from e

    def _configure_git_exclude(self):
        """Configure git exclude patterns to preserve cache and data directories."""
        if not self.build_dir:
            return

        git_exclude_path = self.build_dir / GIT_EXCLUDE_FILE
        patterns_to_exclude = []

        # Preserve build cache if configured
        if self.preserve_cache:
            patterns_to_exclude.append(f"{BUILD_CACHE_DIR}/")

        # Always exclude data directory to avoid permission issues
        patterns_to_exclude.append(f"{DATA_DIR}/")

        # Read existing excludes
        try:
            git_exclude_path.parent.mkdir(parents=True, exist_ok=True)
            if git_exclude_path.exists():
                exclude_content = git_exclude_path.read_text()
            else:
                exclude_content = ''
        except (OSError, PermissionError, IOError) as e:
            self.logger.warning(f"Error reading git exclude file: {e}")
            exclude_content = ''

        # Add missing patterns
        patterns_added = [p for p in patterns_to_exclude if p not in exclude_content]

        if patterns_added:
            try:
                with open(git_exclude_path, 'a') as f:
                    if exclude_content and not exclude_content.endswith('\n'):
                        f.write('\n')
                    f.write('\n'.join(patterns_added) + '\n')
                self.cprint(f"Added {', '.join(patterns_added)} to git exclude", "cyan")
            except (OSError, PermissionError, IOError) as e:
                self.logger.warning(f"Failed to update git exclude: {e}")

    def _clean_working_directory(self):
        """Clean the git working directory, respecting exclude patterns."""
        exclude_args = []

        if self.preserve_cache:
            exclude_args.extend(['-e', BUILD_CACHE_DIR])

        # Always exclude data
        exclude_args.extend(['-e', DATA_DIR])

        if self.preserve_cache:
            self.cprint(f"Cleaning working directory (preserving {BUILD_CACHE_DIR} and {DATA_DIR})", "cyan")
        else:
            self.cprint(f"Cleaning working directory (preserving {DATA_DIR})", "cyan")

        self.repo_object.git.clean('-fdx', *exclude_args)

    def get_project_name(self) -> Optional[str]:
        """
        Get the project name from the data requirement file.

        Returns:
            Project name if found in data_requirement.json, None otherwise
        """
        if not self.build_dir:
            return None

        data_config_path = self.build_dir / DATA_REQUIREMENT_FILE

        if data_config_path.exists():
            try:
                with open(data_config_path, 'r') as f:
                    data = json.load(f)

                dataset_name = data.get('projectName', self.config.repo_name)
                if self.build_context:
                    self.build_context.dataset_name = dataset_name
                return dataset_name

            except (json.JSONDecodeError, IOError) as e:
                self.logger.warning(f"Failed to read data requirement file: {e}")
                return None
        else:
            self.cprint(
                f"Data requirement file not found at {data_config_path}, using repository name",
                "yellow"
            )
            if self.build_context:
                self.build_context.dataset_name = None
            return None

    def repo2data_download(self, target_directory: Path):
        """
        Download data dependencies using repo2data.

        Args:
            target_directory: Directory to download data into

        Raises:
            ConfigurationError: If data requirement file is missing
        """
        if not self.build_dir:
            raise ConfigurationError("Build directory not set. Call git_clone_repo first.")

        if isinstance(target_directory, str):
            target_directory = Path(target_directory)

        data_req_path = self.build_dir / DATA_REQUIREMENT_FILE

        if not data_req_path.exists():
            self.print_warning("Skipping repo2data download - no data requirement file")
            return

        try:
            self.print_success("Starting repo2data download")
            repo2data = Repo2Data(str(data_req_path), server=True)
            repo2data.set_server_dst_folder(str(target_directory))
            repo2data.install()
        except (OSError, RuntimeError, ValueError, ImportError) as e:
            self.logger.error(f"repo2data download failed: {e}")
            raise

    def _set_commit_info(self):
        """Set commit information for both repo and binder image."""
        if not self.repo_object or not self.build_context:
            return

        try:
            # Repository commit info
            repo_commit = self.repo_object.commit(self.config.gh_repo_commit_hash)
            self.build_context.repo_commit_info = CommitInfo(
                datetime=repo_commit.committed_datetime,
                message=repo_commit.message,
                hash=self.config.gh_repo_commit_hash
            )

            # Binder image commit info
            if self.config.binder_image_name_override:
                # Using override image - use defaults
                from ..constants import DEFAULT_OVERRIDE_IMAGE_DATE, DEFAULT_OVERRIDE_IMAGE_MESSAGE
                self.build_context.binder_commit_info = CommitInfo(
                    datetime=datetime.fromisoformat(DEFAULT_OVERRIDE_IMAGE_DATE),
                    message=DEFAULT_OVERRIDE_IMAGE_MESSAGE
                )
            else:
                # Use actual binder tag commit
                binder_commit = self.repo_object.commit(self.config.binder_image_tag)
                self.build_context.binder_commit_info = CommitInfo(
                    datetime=binder_commit.committed_datetime,
                    message=binder_commit.message,
                    hash=self.config.binder_image_tag
                )

        except (AttributeError, ValueError, TypeError) as e:
            self.logger.warning(f"Failed to set commit info: {e}")

    def read_latest_successful_hash(self) -> Optional[str]:
        """
        Read the latest successful build commit hash from latest.txt.

        Returns:
            Commit hash of last successful build, or None if not available
        """
        if not self.host_build_source_parent_dir:
            return None

        latest_txt_path = (
            self.host_build_source_parent_dir
            / self.config.username
            / self.config.repo_name
            / LATEST_BUILD_MARKER
        )

        if latest_txt_path.exists():
            try:
                commit_hash = latest_txt_path.read_text().strip()
                self.logger.info(f"Last successful build: {commit_hash}")
                return commit_hash
            except (OSError, PermissionError, IOError) as e:
                self.logger.warning(f"Error reading {LATEST_BUILD_MARKER}: {e}")
                return None
        return None

    def save_successful_build(self) -> bool:
        """
        Save the current successful build.

        Copies 'latest' directory to a commit-specific folder and updates
        latest.txt with the commit hash.

        Returns:
            True if saved successfully

        Raises:
            GitOperationError: If save operation fails
        """
        if not self.build_dir or not self.host_build_source_parent_dir:
            raise GitOperationError("Build directory not set")

        try:
            # Define target directory for this commit
            commit_dir = (
                self.host_build_source_parent_dir
                / self.config.username
                / self.config.repo_name
                / self.config.gh_repo_commit_hash
            )

            # Remove existing commit directory if present
            if commit_dir.exists():
                self.print_warning(f"Removing existing build at {self.config.gh_repo_commit_hash}")
                shutil.rmtree(commit_dir)

            # Copy latest to commit-specific directory
            self.print_success(f"Preserving successful build to {self.config.gh_repo_commit_hash}")
            shutil.copytree(self.build_dir, commit_dir, symlinks=False)

            # Update latest.txt
            latest_txt_path = (
                self.host_build_source_parent_dir
                / self.config.username
                / self.config.repo_name
                / LATEST_BUILD_MARKER
            )
            latest_txt_path.write_text(self.config.gh_repo_commit_hash)

            self.logger.info(f"Successfully saved build for commit {self.config.gh_repo_commit_hash}")
            self.cprint(f"✓ Build preserved at {commit_dir}", "white", "on_green")
            return True

        except (OSError, PermissionError, shutil.Error) as e:
            self.print_error(f"Failed to preserve build: {e}")
            raise GitOperationError(f"Failed to save build: {e}") from e

    def clear_build_cache(self) -> bool:
        """
        Manually clear the _build cache in the latest directory.

        Useful when you want to force a clean build.

        Returns:
            True if cache cleared successfully
        """
        if not self.build_dir:
            self.print_warning("No build directory set")
            return False

        build_cache_path = self.build_dir / BUILD_CACHE_DIR

        if build_cache_path.exists():
            try:
                self.print_warning(f"Clearing build cache at {build_cache_path}")
                shutil.rmtree(build_cache_path)
                self.logger.info("Build cache cleared successfully")
                self.print_success("Build cache cleared")
                return True
            except (OSError, PermissionError, shutil.Error) as e:
                self.print_error(f"Failed to clear cache: {e}")
                return False
        else:
            self.cprint("No build cache to clear", "cyan")
            return True
