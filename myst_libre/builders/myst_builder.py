"""
myst_builder.py

High-level builder for MyST projects with JupyterHub integration.
"""

import hashlib
import json
import logging
import shutil
import time
from typing import Dict, List, Optional
from pathlib import Path

from ..tools import JupyterHubLocalSpawner, MystMD
from ..abstract_class import AbstractClass


# What the cached notebook outputs in _build/execute were computed with. mystmd keys its cache on the code cells
# only, so a new image or new data would otherwise leave old outputs in place. mystmd ignores this file.
EXECUTION_INPUTS_FILE = '_build/neurolibre-execution-inputs.json'


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
        # Whether the last build worked (see build); None before any build
        self.succeeded: Optional[bool] = None
        # Why the last build cleared mystmd's execution cache, or None if it kept it
        self.execution_cache_cleared: Optional[str] = None

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
        output_path: Optional[str] = None,
        fresh_execution: bool = False
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
            fresh_execution: Run every notebook, ignoring outputs cached by earlier
                builds. Without it, the cache is still cleared when the execution
                image or the data requirement changed (see _prepare_execution_cache).

        Returns:
            Build output logs
        """
        if self.hub is not None:
            self.cprint(f'Starting MyST build {self.hub.jh_url}', 'yellow')
        else:
            self.cprint('Starting MyST build (no execution)', 'yellow')

        for theme in remove_incomplete_themes(self.build_dir):
            self.cprint(f'Removed an incompletely installed theme, mystmd will install it again: {theme}', 'yellow')

        self.execution_cache_cleared = None
        if '--execute' in args:
            self.execution_cache_cleared = self._prepare_execution_cache(fresh_execution, user, group, output_path)

        build_args = ('build',) + args
        started = time.time()
        logs = self.myst_client.build(
            *build_args, user=user, group=group, timeout=timeout,
            output_path=output_path
        )

        # A build works when mystmd exits normally and, for --html, wrote the
        # site during this build. Words in the output do not decide it: a
        # notebook that raises puts "Error" there while the rest of the site is
        # built and exported, and that site must still be saved. Notebook
        # errors stay in the logs for the author to read.
        self.succeeded = self._build_succeeded(args, started)
        build_failed = not self.succeeded

        if not build_failed and self.hub is not None:
            # Save the successful build
            self.print_success('Build completed successfully, preserving...')
            self.hub.rees.save_successful_build()

        return logs

    def _execution_inputs(self) -> Dict[str, Optional[str]]:
        """The execution image's ID and a hash of binder/data_requirement.json."""
        image = getattr(getattr(self.hub, 'rees', None), 'docker_image', None) if self.hub is not None else None
        requirement = Path(self.build_dir) / 'binder' / 'data_requirement.json'
        try:
            data = hashlib.sha256(requirement.read_bytes()).hexdigest()
        except OSError:
            data = None
        image_id = getattr(image, 'id', None)
        if not isinstance(image_id, str):
            image_id = str(image) if image is not None else None
        return {'image': image_id, 'data_requirement': data}

    def _prepare_execution_cache(self, fresh: bool, user=None, group=None, output_path=None) -> Optional[str]:
        """Clear mystmd's execution cache when its outputs may not match this build, and record this build's inputs.

        Cleared, with mystmd's own `myst clean --execute --yes`, when a fresh run is asked for, when the image or
        the data requirement differs from the build that filled the cache, or when the cache has no record of its
        inputs. Returns the reason, or None if the cache was kept (or there was none).
        """
        marker = Path(self.build_dir) / EXECUTION_INPUTS_FILE
        inputs = self._execution_inputs()
        try:
            recorded = json.loads(marker.read_text())
        except (OSError, ValueError):
            recorded = None

        if fresh:
            reason = 'a fresh run of every notebook was asked for'
        elif recorded is None:
            reason = 'the image and data the cached outputs were computed with are not recorded'
        else:
            changed = [name.replace('_requirement', '') for name in inputs if recorded.get(name) != inputs[name]]
            reason = f"the {' and the '.join(changed)} changed since the cached outputs were computed" if changed else None

        execute_dir = Path(self.build_dir) / '_build' / 'execute'
        cleared = None
        if reason and execute_dir.is_dir() and any(execute_dir.iterdir()):
            self.cprint(f'Running every notebook again: {reason}.', 'yellow')
            self.myst_client.run_command('clean', '--execute', '--yes', env_vars=self.env_vars,
                                         user=user, group=group, output_path=output_path)
            if execute_dir.exists():
                self.logger.warning(f'myst clean --execute left {execute_dir} in place')
            cleared = reason

        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(json.dumps(inputs))
        except (OSError, TypeError, ValueError) as e:
            # Recording must never stop a build; the next build then clears the cache to be safe
            self.logger.warning(f'Could not record the execution inputs in {marker}: {e}')
        return cleared

    def _build_succeeded(self, args, started: float) -> bool:
        """mystmd exited with 0 and, if the build exports HTML, wrote _build/html/index.html after started."""
        if getattr(self.myst_client, 'last_returncode', None) != 0:
            return False
        if '--html' not in args:
            return True
        index = Path(self.build_dir) / '_build' / 'html' / 'index.html'
        try:
            # one second of slack for filesystems that store whole seconds
            return index.stat().st_mtime >= started - 1
        except OSError:
            return False

    def cleanup(self):
        """Kill the myst process tree and release all resources.

        Safe to call multiple times, after success or failure, or even
        when no build was started.
        """
        self.myst_client.cleanup()
