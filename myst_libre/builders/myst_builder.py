"""
myst_builder.py

High-level builder for MyST projects with JupyterHub integration.
"""

from typing import Optional
from pathlib import Path

from ..tools import JupyterHubLocalSpawner, MystMD
from ..abstract_class import AbstractClass


class MystBuilder(AbstractClass):
    """
    High-level builder for MyST markdown projects.

    Provides simplified interface for building MyST projects with optional
    JupyterHub integration for execution.
    """

    def __init__(
        self,
        hub: Optional[JupyterHubLocalSpawner] = None,
        build_dir: Optional[str] = None
    ):
        """
        Initialize MyST builder.

        Args:
            hub: JupyterHub spawner for containerized execution (optional)
            build_dir: Directory for standalone build (required if hub is None)

        Raises:
            TypeError: If hub is not a JupyterHubLocalSpawner instance
            ValueError: If both hub and build_dir are None
        """
        if hub is not None:
            if not isinstance(hub, JupyterHubLocalSpawner):
                raise TypeError(
                    f"Expected 'hub' to be an instance of JupyterHubLocalSpawner, "
                    f"got {type(hub).__name__} instead"
                )
            self.hub = hub
            self.env_vars = {
                "JUPYTER_BASE_URL": f"{self.hub.jh_url}",
                "JUPYTER_TOKEN": f"{self.hub.jh_token}",
                "port": f"{self.hub.port}"
            }
            self.build_dir = str(self.hub.rees.build_dir)
        else:
            if build_dir is None:
                raise ValueError("If 'hub' is None, 'build_dir' must be provided")
            self.build_dir = build_dir
            self.env_vars = {}
            self.hub = None

        super().__init__()
        self.myst_client = MystMD(self.build_dir, self.env_vars)

    def set_env(self, key: str, value: str):
        """
        Set an environment variable for MyST builds.

        Args:
            key: Environment variable name
            value: Environment variable value
        """
        self.env_vars[key] = value

    # Deprecated alias for backward compatibility
    def setenv(self, key: str, value: str):
        """Deprecated: Use set_env instead."""
        self.logger.warning("setenv is deprecated, use set_env instead")
        return self.set_env(key, value)

    def build(
        self,
        *args: str,
        user: Optional[str] = None,
        group: Optional[str] = None,
        timeout: Optional[int] = None
    ) -> str:
        """
        Build the MyST project.

        The theme server port is left to mystmd. Pinning it with ``--port``
        meant reserving a port here and mystmd binding it only after
        ``buildSite`` finishes - the whole execution phase later, up to hours on
        a heavy paper. By then the reservation is stale and another build may
        hold the port; before mystmd 1.10 a pinned port has no fallback, so the
        collision is fatal. Letting mystmd allocate at bind time shrinks that
        window to nothing.

        Teardown does not need the port: the process group is killed as a whole
        (see MystMD.cleanup and MystMD.reap_orphans).

        Args:
            *args: Arguments to pass to myst build command
            user: Optional username to run as
            group: Optional group to run as
            timeout: Optional timeout in seconds for the build process

        Returns:
            Build output logs
        """
        if self.hub is not None:
            self.cprint(f'Starting MyST build {self.hub.jh_url}', 'yellow')
        else:
            self.cprint('Starting MyST build (no execution)', 'yellow')

        build_args = ('build',) + args
        logs = self.myst_client.build(
            *build_args, user=user, group=group, timeout=timeout
        )

        # Check if build was successful
        build_failed = logs and (
            'Error' in logs or
            'error:' in logs.lower() or
            'failed' in logs.lower()
        )

        if not build_failed and self.hub is not None:
            # Save the successful build
            self.print_success('Build completed successfully, preserving...')
            self.hub.rees.save_successful_build()

        return logs

    def cleanup(self):
        """Kill the myst process tree and release all resources.

        Safe to call multiple times, after success or failure, or even
        when no build was started.
        """
        self.myst_client.cleanup()
