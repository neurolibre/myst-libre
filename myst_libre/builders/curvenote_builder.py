"""
curvenote_builder.py

High-level builder for Curvenote projects with JupyterHub integration.
"""

from typing import Optional, Tuple

from ..tools import JupyterHubLocalSpawner, Curvenote
from ..abstract_class import AbstractClass


class CurvenoteBuilder(AbstractClass):
    """
    High-level builder for Curvenote projects.

    Provides simplified interface for building, deploying, and exporting
    Curvenote projects with optional JupyterHub integration.
    """

    def __init__(
        self,
        hub: Optional[JupyterHubLocalSpawner] = None,
        build_dir: Optional[str] = None,
        dotenvloc: str = '.'
    ):
        """
        Initialize Curvenote builder.

        Args:
            hub: JupyterHub spawner for containerized execution (optional)
            build_dir: Directory for standalone build (required if hub is None)
            dotenvloc: Path to .env file for credentials

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
            # Use dotenvloc from REES if available
            dotenvloc = getattr(self.hub.rees.config, 'dotenv', dotenvloc)
        else:
            if build_dir is None:
                raise ValueError("If 'hub' is None, 'build_dir' must be provided")
            self.build_dir = build_dir
            self.env_vars = {}
            self.hub = None

        super().__init__()
        self.curvenote_client = Curvenote(self.build_dir, self.env_vars, dotenvloc=dotenvloc)

    def set_env(self, key: str, value: str):
        """
        Set an environment variable for Curvenote operations.

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
        group: Optional[str] = None
    ) -> str:
        """
        Build the Curvenote project.

        Args:
            *args: Arguments to pass to curvenote build command
            user: Optional username to run as
            group: Optional group to run as

        Returns:
            Build output logs
        """
        if self.hub is not None:
            self.cprint(f'Starting Curvenote build {self.hub.jh_url}', 'yellow')
        else:
            self.cprint('Starting Curvenote build (no execution)', 'yellow')

        logs = self.curvenote_client.build(*args, user=user, group=group)

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

    def start(
        self,
        *args: str,
        user: Optional[str] = None,
        group: Optional[str] = None
    ) -> str:
        """
        Start the Curvenote development server.

        Args:
            *args: Arguments to pass to curvenote start command
            user: Optional username to run as
            group: Optional group to run as

        Returns:
            Server output logs
        """
        if self.hub is not None:
            self.cprint(f'Starting Curvenote dev server {self.hub.jh_url}', 'yellow')
        else:
            self.cprint('Starting Curvenote dev server (no execution)', 'yellow')

        logs = self.curvenote_client.start(*args, user=user, group=group)
        return logs

    def deploy(
        self,
        *args: str,
        user: Optional[str] = None,
        group: Optional[str] = None
    ) -> str:
        """
        Deploy the Curvenote project.

        Args:
            *args: Arguments to pass to curvenote deploy command
            user: Optional username to run as
            group: Optional group to run as

        Returns:
            Deployment output logs
        """
        if self.hub is not None:
            self.cprint(f'Deploying Curvenote project {self.hub.jh_url}', 'yellow')
        else:
            self.cprint('Deploying Curvenote project (no execution)', 'yellow')

        logs = self.curvenote_client.deploy(*args, user=user, group=group)
        return logs

    def export_pdf(
        self,
        link: Optional[str] = None,
        target: Optional[str] = None,
        template: Optional[str] = None,
        user: Optional[str] = None,
        group: Optional[str] = None
    ) -> str:
        """
        Export content to PDF.

        Args:
            link: Link to the content to export
            target: Target output directory
            template: LaTeX template to use
            user: Optional username to run as
            group: Optional group to run as

        Returns:
            Export output logs
        """
        if self.hub is not None:
            self.cprint(f'Exporting PDF from Curvenote {self.hub.jh_url}', 'yellow')
        else:
            self.cprint('Exporting PDF from Curvenote (no execution)', 'yellow')

        stdout_log, stderr_log = self.curvenote_client.export_pdf(
            link, target, template, user, group
        )

        combined_log = stdout_log
        if stderr_log:
            combined_log += "\n" + stderr_log
        return combined_log

    def export_jupyter_book(
        self,
        link: Optional[str] = None,
        user: Optional[str] = None,
        group: Optional[str] = None
    ) -> str:
        """
        Export content to Jupyter Book format.

        Args:
            link: Link to the content to export
            user: Optional username to run as
            group: Optional group to run as

        Returns:
            Export output logs
        """
        if self.hub is not None:
            self.cprint(f'Exporting Jupyter Book from Curvenote {self.hub.jh_url}', 'yellow')
        else:
            self.cprint('Exporting Jupyter Book from Curvenote (no execution)', 'yellow')

        stdout_log, stderr_log = self.curvenote_client.export_jupyter_book(link, user, group)

        combined_log = stdout_log
        if stderr_log:
            combined_log += "\n" + stderr_log
        return combined_log

    def init(
        self,
        *args: str,
        user: Optional[str] = None,
        group: Optional[str] = None
    ) -> str:
        """
        Initialize a Curvenote project.

        Args:
            *args: Arguments to pass to curvenote init command
            user: Optional username to run as
            group: Optional group to run as

        Returns:
            Initialization output logs
        """
        if self.hub is not None:
            self.cprint(f'Initializing Curvenote project {self.hub.jh_url}', 'yellow')
        else:
            self.cprint('Initializing Curvenote project (no execution)', 'yellow')

        logs = self.curvenote_client.init(*args, user=user, group=group)
        return logs

    def pull(
        self,
        path: Optional[str] = None,
        user: Optional[str] = None,
        group: Optional[str] = None
    ) -> str:
        """
        Pull content from Curvenote.

        Args:
            path: Specific path to pull content from
            user: Optional username to run as
            group: Optional group to run as

        Returns:
            Pull output logs
        """
        if self.hub is not None:
            self.cprint(f'Pulling Curvenote content {self.hub.jh_url}', 'yellow')
        else:
            self.cprint('Pulling Curvenote content (no execution)', 'yellow')

        logs = self.curvenote_client.pull(path, user=user, group=group)
        return logs

    def submit_draft(
        self,
        *args: str,
        user: Optional[str] = None,
        group: Optional[str] = None
    ) -> str:
        """
        Submit a draft to Curvenote.

        Args:
            *args: Arguments to pass to curvenote submit command
            user: Optional username to run as
            group: Optional group to run as

        Returns:
            Submit output logs
        """
        if self.hub is not None:
            self.cprint(f'Submitting draft to Curvenote {self.hub.jh_url}', 'yellow')
        else:
            self.cprint('Submitting draft to Curvenote (no execution)', 'yellow')

        logs = self.curvenote_client.submit_draft(*args, user=user, group=group)
        return logs
