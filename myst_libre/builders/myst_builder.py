"""
myst_builder.py

High-level builder for MyST projects with JupyterHub integration.
"""

import json
import logging
import shutil
from typing import List, Optional
from pathlib import Path

from ..tools import JupyterHubLocalSpawner, MystMD
from ..abstract_class import AbstractClass


def remove_incomplete_themes(build_dir: str) -> List[str]:
    """
    Remove site themes under _build/templates whose npm install is incomplete.

    mystmd downloads and installs a site theme only when the theme's folder is
    missing. _build is kept between builds so executed notebook outputs can be
    reused, and an interrupted install is kept with it: every later build then
    fails when the theme server cannot load its packages ("Cannot find module
    'express'"). A theme counts as complete when every dependency listed in its
    package.json has a package.json under node_modules. Removing an incomplete
    theme makes mystmd download and install it again. Nothing else in _build
    is touched.

    Args:
        build_dir: The MyST project folder (the one holding _build)

    Returns:
        The theme folders that were removed
    """
    removed = []
    for manifest in sorted(Path(build_dir).glob('_build/templates/site/*/*/package.json')):
        theme = manifest.parent
        try:
            dependencies = json.loads(manifest.read_text()).get('dependencies', {}) or {}
        except (OSError, ValueError) as e:
            missing = [f'(unreadable package.json: {e})']
        else:
            missing = [
                name for name in dependencies
                if not (theme / 'node_modules' / name / 'package.json').is_file()
            ]
        if missing:
            logging.warning(
                f"Theme at {theme} has an incomplete install (missing: "
                f"{', '.join(missing)}). Removing it so mystmd installs it again."
            )
            shutil.rmtree(theme)
            removed.append(str(theme))
    return removed


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
        timeout: Optional[int] = None,
        output_path: Optional[str] = None
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
            output_path: Optional file mystmd's output is also written to while
                the build runs, so it can be followed live (see MystMD.run_command)

        Returns:
            Build output logs
        """
        if self.hub is not None:
            self.cprint(f'Starting MyST build {self.hub.jh_url}', 'yellow')
        else:
            self.cprint('Starting MyST build (no execution)', 'yellow')

        for theme in remove_incomplete_themes(self.build_dir):
            self.cprint(f'Removed an incompletely installed theme, mystmd will install it again: {theme}', 'yellow')

        build_args = ('build',) + args
        logs = self.myst_client.build(
            *build_args, user=user, group=group, timeout=timeout,
            output_path=output_path
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
