"""
jupyter_hub_local_spawner.py

Refactored JupyterHubLocalSpawner for managing containerized JupyterHub instances.
"""

import os
import logging
import socket
from hashlib import blake2b
from typing import Optional, List, Dict, TYPE_CHECKING
from pathlib import Path

import docker.errors

from ..abstract_class import AbstractClass
from ..models import ContainerConfig
from ..exceptions import ContainerError, PortAllocationError
from .path_utils import translate_container_path_to_host, should_translate_paths

# Use TYPE_CHECKING to avoid circular import
if TYPE_CHECKING:
    from ..rees import REES
from ..constants import (
    DEFAULT_PORT_RANGE,
    DEFAULT_CONTAINER_STOP_TIMEOUT,
    TOKEN_DIGEST_SIZE,
    DATA_DIR,
)


class JupyterHubLocalSpawner(AbstractClass):
    """
    Spawner for managing JupyterHub instances in Docker containers.

    Implements context manager protocol for proper resource cleanup.
    Provides port allocation, volume mounting, and container lifecycle management.
    """

    def __init__(self, rees: 'REES', **kwargs):
        """
        Initialize JupyterHub spawner.

        Args:
            rees: REES instance with Docker and source management
            **kwargs: Container configuration parameters

        Required kwargs:
            - container_data_mount_dir: Mount point in container for data
            - container_build_source_mount_dir: Mount point in container for build sources
            - host_data_parent_dir: Parent directory on host for data
            - host_build_source_parent_dir: Parent directory on host for build sources

        Optional kwargs (for Docker-in-Docker scenarios):
            - host_path_prefix: Host path prefix for path translation. When myst-libre
              runs in a container and needs to spawn sibling containers, this should be
              set to the host path corresponding to the container_path_prefix.
              Example: if container has /workspace → /home/user/workspace mounted,
              set host_path_prefix="/home/user/workspace" and container_path_prefix="/workspace"
            - container_path_prefix: Container path prefix to replace. Default: "/"
            - enable_dind: Enable Docker-in-Docker networking fix. When True, uses the
              spawned container's name instead of localhost for Jupyter connections.
              Required for proper networking when myst-libre runs inside a container
              and spawns sibling Jupyter containers. Default: False

        Raises:
            TypeError: If rees is not a REES instance
            ValueError: If required kwargs are missing
        """
        # Import here to avoid circular import at module load time
        from ..rees import REES

        if not isinstance(rees, REES):
            raise TypeError(f"Expected 'rees' to be an instance of REES, got {type(rees).__name__}")

        super().__init__()
        self.rees = rees

        # Validate and set required inputs
        self._validate_and_set_config(kwargs)

        # Container state
        self.container: Optional = None
        self.port: Optional[int] = None
        self.jh_token: Optional[str] = None
        self.jh_url: Optional[str] = None
        self._cleanup_needed: bool = False

    def _validate_and_set_config(self, kwargs: Dict):
        """
        Validate and set container configuration.

        Args:
            kwargs: Configuration parameters

        Raises:
            ValueError: If required parameters are missing
        """
        required_inputs = [
            'container_data_mount_dir',
            'container_build_source_mount_dir',
            'host_data_parent_dir',
            'host_build_source_parent_dir'
        ]

        for inp in required_inputs:
            if inp not in kwargs:
                raise ValueError(f"Required parameter '{inp}' not provided for JupyterHubLocalSpawner")
            setattr(self, inp, kwargs[inp])

        # Docker-in-Docker support: path translation and networking
        self.host_path_prefix: Optional[str] = kwargs.get('host_path_prefix')
        self.container_path_prefix: str = kwargs.get('container_path_prefix', '/')
        self.enable_dind: bool = kwargs.get('enable_dind', False)

        # Create ContainerConfig for structured access
        self.container_config = ContainerConfig(
            host_build_source_parent_dir=self.host_build_source_parent_dir,
            container_build_source_mount_dir=self.container_build_source_mount_dir,
            host_data_parent_dir=self.host_data_parent_dir,
            container_data_mount_dir=self.container_data_mount_dir,
            port_range=kwargs.get('port_range', DEFAULT_PORT_RANGE),
            host_path_prefix=self.host_path_prefix,
            container_path_prefix=self.container_path_prefix
        )

    def find_open_port(self) -> int:
        """
        Find an open port within the configured port range.

        Returns:
            Available port number

        Raises:
            PortAllocationError: If no open ports are available
        """
        min_port, max_port = self.container_config.port_range

        for port in range(min_port, max_port + 1):
            if not self._is_port_in_use(port):
                return port

        raise PortAllocationError(
            f"No open ports available in range {min_port}-{max_port}"
        )

    def _is_port_in_use(self, port: int) -> bool:
        """
        Check if a port is in use.

        Args:
            port: Port number to check

        Returns:
            True if port is in use, False otherwise
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('127.0.0.1', port)) == 0

    def _generate_token(self) -> str:
        """
        Generate a secure random token for JupyterHub.

        Returns:
            Hex-encoded token
        """
        h = blake2b(digest_size=TOKEN_DIGEST_SIZE)
        h.update(os.urandom(TOKEN_DIGEST_SIZE))
        return h.hexdigest()

    def __enter__(self):
        """Context manager entry point."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit point - ensures cleanup."""
        self.cleanup()
        return False  # Don't suppress exceptions

    def cleanup(self):
        """
        Clean up all resources (container, etc.).

        Ensures complete cleanup of Docker containers and network resources.
        Verifies cleanup succeeded before clearing references.
        """
        if self.container:
            container_id = self.container.short_id
            try:
                self.logger.info(f"Cleaning up container {container_id}")
                self.container.stop(timeout=DEFAULT_CONTAINER_STOP_TIMEOUT)
                self.container.remove(force=True)

                # Verify container is actually removed
                try:
                    self.container.reload()
                    # If we get here, container still exists
                    self.logger.warning(f"Container {container_id} still exists after removal attempt")
                except docker.errors.NotFound:
                    # Container successfully removed
                    self.logger.info(f"Container {container_id} successfully removed")

            except (docker.errors.APIError, docker.errors.DockerException) as e:
                self.logger.error(f"Error during container cleanup: {e}")
            finally:
                # Always clear reference to avoid leaking memory
                self.container = None
                # Clear port to allow reuse
                if self.port:
                    self.logger.debug(f"Released port {self.port}")
                    self.port = None

        self._cleanup_needed = False

    def spawn_jupyter_hub(self, jb_build_command: Optional[bool] = None) -> List[str]:
        """
        Spawn a JupyterHub instance in a Docker container.

        Args:
            jb_build_command: If True, run jupyter-book build instead of server

        Returns:
            List of log messages

        Raises:
            ContainerError: If container spawn fails
        """
        output_logs = []

        try:
            # Allocate port and generate token
            self.port = self.find_open_port()
            self.jh_token = self._generate_token()

            # Set initial jh_url (may be updated after container spawn for DIND mode)
            # Use localhost for non-DIND mode (default), which works for local execution
            self.jh_url = f"http://localhost:{self.port}"

            # Determine entrypoint
            entrypoint = self._build_entrypoint(jb_build_command)

            # Prepare repository
            self._prepare_repository()

            # Pre-create data directory to avoid permission issues
            self._prepare_data_directory()

            # Download data if needed
            if self.rees.dataset_name:
                self.rees.repo2data_download(self.host_data_parent_dir)

            # Build volume mounts
            volumes = self._build_volume_mounts()

            # Pull image
            self.rees.pull_image()

            # Spawn container
            self._spawn_container(entrypoint, volumes)

            # For Docker-in-Docker mode: update jh_url to use container IP for proper networking
            # When myst-libre runs inside a container and spawns sibling Jupyter containers,
            # using localhost from the myst container doesn't reach the sibling.
            # Instead, use the container's IP address on the Docker network.
            if self.enable_dind:
                # Reload container state to get updated network settings
                self.container.reload()
                # Get the container's IP address on the default bridge network
                container_ip = self.container.attrs['NetworkSettings']['IPAddress']
                if not container_ip:
                    raise ContainerError(
                        f"Failed to get IP address for container {self.container.short_id}. "
                        f"Container may not be properly connected to Docker network."
                    )
                self.jh_url = f"http://{container_ip}:{self.port}"
                self.logger.info(f"🐳❤️🐳 Docker-in-Docker mode (DinD): Using Jupyter URL: {self.jh_url}")

                # Wait for Jupyter server to be ready
                self._wait_for_jupyter_ready(container_ip)

            # Log status information
            output_logs.extend(self._log_spawn_status())

        except (docker.errors.APIError, docker.errors.DockerException, OSError, ValueError, AttributeError) as e:
            self.logger.error(f"Could not spawn JupyterHub: {e}")
            output_logs.append(f"Error: {e}")
            self.cleanup()
            raise ContainerError(f"Failed to spawn JupyterHub: {e}") from e

        return output_logs

    def _build_entrypoint(self, jb_build_command: Optional[bool] = None) -> str:
        """
        Build the container entrypoint command.

        Args:
            jb_build_command: If True, use jupyter-book build command

        Returns:
            Entrypoint command string
        """
        if jb_build_command:
            return (
                f"/bin/sh -c 'jupyter-book build --all --verbose "
                f"--path-output {self.container_build_source_mount_dir} content "
                f"2>&1 | tee -a jupyter_book_build.log'"
            )
        else:
            return (
                f'jupyter server --allow-root --ip 0.0.0.0 --log-level=DEBUG '
                f'--IdentityProvider.token="{self.jh_token}" '
                f'--ServerApp.port="{self.port}"'
            )

    def _prepare_repository(self):
        """Clone and checkout repository."""
        self.rees.git_clone_repo(self.host_build_source_parent_dir)
        self.rees.git_checkout_commit()

        if not self.rees.dataset_name:
            self.rees.get_project_name()

    def _prepare_data_directory(self):
        """
        Pre-create data directory to prevent Docker from creating it as root.

        This must be done after checkout to avoid interfering with git operations.
        """
        if not self.rees.build_dir:
            return

        data_dir_in_build = self.rees.build_dir / DATA_DIR
        data_dir_in_build.mkdir(exist_ok=True)
        logging.debug(f"Pre-created data directory: {data_dir_in_build}")

    def _build_volume_mounts(self) -> Dict[str, Dict]:
        """
        Build volume mount configuration.

        When running in Docker-in-Docker mode (host_path_prefix is set), translates
        container paths to host paths for volume mounts. This is necessary because
        the Docker daemon always interprets volume mount paths relative to the host,
        not the myst-libre container.

        Returns:
            Dictionary of volume mounts
        """
        # Translate build directory path if needed
        build_dir_host_path = str(self.rees.build_dir)
        if should_translate_paths(self.host_path_prefix):
            build_dir_host_path = str(
                translate_container_path_to_host(
                    self.rees.build_dir,
                    self.host_path_prefix,
                    self.container_path_prefix
                )
            )

        volumes = {
            build_dir_host_path: {
                'bind': self.container_build_source_mount_dir,
                'mode': 'rw'
            }
        }

        # Add data volume if dataset exists
        if self.rees.dataset_name:
            host_data_path = Path(self.host_data_parent_dir) / self.rees.dataset_name

            # Translate data directory path if needed
            if should_translate_paths(self.host_path_prefix):
                host_data_path = translate_container_path_to_host(
                    host_data_path,
                    self.host_path_prefix,
                    self.container_path_prefix
                )

            container_data_path = f"{self.container_data_mount_dir}/{self.rees.dataset_name}"

            volumes[str(host_data_path)] = {
                'bind': container_data_path,
                'mode': 'ro'
            }

        return volumes

    def _spawn_container(self, entrypoint: str, volumes: Dict[str, Dict]):
        """
        Spawn the Docker container.

        Args:
            entrypoint: Container entrypoint command
            volumes: Volume mount configuration

        Raises:
            ContainerError: If container spawn fails
        """
        try:
            # Run as current host user to avoid permission issues
            run_user = f"{os.getuid()}:{os.getgid()}"
            logging.debug(f"Running container as user {run_user}")

            self.container = self.rees.docker_client.containers.run(
                self.rees.docker_image,
                ports={f'{self.port}/tcp': self.port},
                environment={
                    "JUPYTER_TOKEN": self.jh_token,
                    "port": str(self.port),
                    "JUPYTER_BASE_URL": self.jh_url
                },
                entrypoint=entrypoint,
                volumes=volumes,
                user=run_user,
                detach=True
            )

            self._cleanup_needed = True
            logging.info(f"Jupyter hub is {self.container.status}")

        except Exception as e:
            raise ContainerError(f"Failed to spawn container: {e}") from e

    def _log_spawn_status(self) -> List[str]:
        """
        Log spawn status information.

        Returns:
            List of log messages
        """
        output_logs = []

        def log(message: str, color: Optional[str] = None):
            """Helper to log and collect messages."""
            output_logs.append(f"\n {message}")
            if color:
                self.cprint(message, color)
            else:
                print(message)

        # Status section
        log('␤[Status]', 'light_grey')
        log(' ├─────── ⏺ running', 'green')
        log(f' └─────── Container {self.container.short_id} {self.container.name}', 'green')

        # Debug info
        log(' ℹ Run the following commands in the terminal if you are debugging locally:', 'yellow')
        log(f' port="{self.port}"', 'cyan')
        log(f' export JUPYTER_BASE_URL="{self.jh_url}"', 'cyan')
        log(f' export JUPYTER_TOKEN="{self.jh_token}"', 'cyan')

        # Resources section
        log('␤[Resources]', 'light_grey')
        log(' ├── MyST repository', 'magenta')
        log(f' │   ├───────── ✸ {self.rees.gh_user_repo_name}', 'light_blue')
        log(f' │   ├───────── ⎌ {self.rees.gh_repo_commit_hash}', 'light_blue')

        repo_info = self.rees.repo_commit_info
        if repo_info:
            log(
                f" │   └───────── ⏲ {repo_info['datetime']}: {repo_info['message']}".replace('\n', ''),
                'light_blue'
            )

        log(' └── Docker container', 'magenta')
        log(f'     ├───────── ✸ {self.rees.pull_image_name}', 'light_blue')
        log(f'     ├───────── ⎌ {self.rees.binder_image_tag}', 'light_blue')

        binder_info = self.rees.binder_commit_info
        if binder_info:
            log(
                f"     ├───────── ⏲ {binder_info['datetime']}: {binder_info['message']}".replace('\n', ''),
                'light_blue'
            )

        if self.rees.binder_image_name_override:
            log(
                f'     └───────── ℹ Using NeuroLibre base image {self.rees.binder_image_name_override}',
                'yellow'
            )
        else:
            log(
                f'     └───────── ℹ This image was built from REES-compliant '
                f'{self.rees.gh_user_repo_name} repository at the commit above',
                'yellow'
            )

        return output_logs

    def delete_stopped_containers(self):
        """Delete all stopped Docker containers."""
        stopped_containers = self.rees.docker_client.containers.list(
            all=True,
            filters={"status": "exited"}
        )

        for container in stopped_containers:
            logging.info(f"Deleting stopped container: {container.id}")
            container.remove()

    def delete_image(self):
        """Delete the pulled Docker image."""
        if self.rees.docker_image:
            logging.info(f"Deleting image: {self.rees.docker_image.id}")
            self.rees.docker_client.images.remove(image=self.rees.docker_image.id)

    def stop_container(self):
        """Stop and remove the running container."""
        self.logger.warning("Attempting to stop and remove the running container")
        self.cleanup()

    def is_running(self) -> bool:
        """
        Check if the container is currently running.

        Returns:
            True if container exists and is running, False otherwise
        """
        if not self.container:
            return False

        try:
            self.container.reload()
            return self.container.status == 'running'
        except Exception as e:
            self.logger.error(f"Error checking container status: {e}")
            return False

    def get_container_logs(self, tail: int = 100) -> str:
        """
        Get logs from the running container.

        Args:
            tail: Number of lines to tail from the logs

        Returns:
            Container logs or empty string if container not available
        """
        if not self.container:
            return ""

        try:
            return self.container.logs(tail=tail).decode('utf-8')
        except Exception as e:
            self.logger.error(f"Error getting container logs: {e}")
            return f"Error retrieving logs: {e}"

    def _wait_for_jupyter_ready(self, container_ip: str, timeout: int = 30) -> None:
        """
        Wait for Jupyter server to be ready for connections.

        Args:
            container_ip: IP address of the Jupyter container
            timeout: Maximum seconds to wait for server to be ready

        Raises:
            ContainerError: If server doesn't become ready within timeout
        """
        import time
        import urllib.request
        import urllib.error

        jupyter_url = f"http://{container_ip}:{self.port}"
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                # Create request with authentication token
                req = urllib.request.Request(
                    f"{jupyter_url}/api/status",
                    headers={"Authorization": f"token {self.jh_token}"}
                )
                response = urllib.request.urlopen(req, timeout=2)
                if response.status == 200:
                    self.logger.info(f"🕸️🐳✅ Jupyter server at {jupyter_url} is ready")
                    return
            except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
                # Server not ready yet, wait and retry
                self.logger.info(f"Jupyter not ready yet: {e}")
                time.sleep(1)
                continue

        raise ContainerError(
            f"Jupyter server at {jupyter_url} did not become ready within {timeout} seconds"
        )
