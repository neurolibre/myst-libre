"""
curvenote_client.py

Refactored Curvenote client for managing Curvenote CLI operations.
"""

import subprocess
import os
import sys
import grp
import pwd
from typing import Optional, Tuple, Dict

from .authenticator import Authenticator


class Curvenote(Authenticator):
    """
    Curvenote CLI client for building, deploying, and exporting content.

    Handles all Curvenote CLI operations with proper authentication and environment setup.
    """

    def __init__(
        self,
        build_dir: str,
        env_vars: Dict[str, str],
        executable: str = 'curvenote',
        dotenvloc: str = '.'
    ):
        """
        Initialize the Curvenote client.

        Args:
            build_dir: Directory where the build will take place
            env_vars: Environment variables needed for the build process
            executable: Name of the Curvenote executable (default: 'curvenote')
            dotenvloc: Path to .env file for credentials
        """
        super().__init__(dotenvloc=dotenvloc)
        self.executable = executable
        self.build_dir = build_dir
        self.env_vars = env_vars

        self.cprint("␤[Curvenote Preflight checks]", "light_grey")
        self._check_node_installed()
        self._check_curvenote_installed()

    def _check_node_installed(self):
        """
        Check if Node.js is installed and available in the system PATH.

        Raises:
            EnvironmentError: If Node.js is not installed or not found in PATH
        """
        try:
            process = subprocess.Popen(
                ['node', '--version'],
                env=os.environ,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            stdout, stderr = process.communicate()

            if process.returncode != 0:
                raise subprocess.CalledProcessError(
                    process.returncode, process.args, stdout, stderr
                )

            self.print_success(f"Node.js is installed: {stdout.strip()}")

        except subprocess.CalledProcessError as e:
            self.print_error(f"Error checking Node.js version: {e.stderr.strip()}")
            raise
        except (FileNotFoundError, OSError) as e:
            self.print_error(f"Node.js executable not found: {str(e)}")
            raise EnvironmentError("Node.js is not installed or not found in PATH") from e

    def _check_curvenote_installed(self):
        """
        Check if Curvenote CLI is installed and available in the system PATH.

        Raises:
            EnvironmentError: If Curvenote CLI is not installed or not found in PATH
        """
        try:
            process = subprocess.Popen(
                [self.executable, '--version'],
                env=os.environ,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            stdout, stderr = process.communicate()

            if process.returncode != 0:
                raise subprocess.CalledProcessError(
                    process.returncode, process.args, stdout, stderr
                )

            self.print_success(f"curvenote is installed: {stdout.strip()}")

        except subprocess.CalledProcessError as e:
            self.print_error(f"Error checking curvenote version: {e.stderr.strip()}")
            raise
        except (FileNotFoundError, OSError) as e:
            self.print_error(f"Curvenote CLI executable not found: {str(e)}")
            raise EnvironmentError("Curvenote CLI is not installed or not found in PATH") from e

    def run_command(
        self,
        *args: str,
        env_vars: Optional[Dict[str, str]] = None,
        user: Optional[str] = None,
        group: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Run a command using the Curvenote executable.

        Args:
            *args: Arguments for the Curvenote executable command
            env_vars: Environment variables to set for the command
            user: Optional username to run command as
            group: Optional group to run command as

        Returns:
            Tuple of (stdout_log, stderr_log)
        """
        if env_vars is None:
            env_vars = {}

        command = [self.executable] + list(args)

        try:
            # Combine the current environment with the provided env_vars
            env = os.environ.copy()
            env.update(env_vars)

            # Add Curvenote token to environment if available
            if self._auth.get('curvenote_token'):
                env['CURVENOTE_TOKEN'] = self._auth['curvenote_token']
                self.cprint("🔑 Using Curvenote API token for authentication", "green")

            # Debug information
            self.logger.debug(f"Running command from directory: {os.getcwd()}")
            self.logger.debug(f"Set cwd to: {self.build_dir}")
            self.logger.debug(f"Command: {' '.join(command)}")

            # Build subprocess arguments
            popen_kwargs = {
                'env': env,
                'stdout': subprocess.PIPE,
                'stderr': subprocess.PIPE,
                'text': True,
                'cwd': self.build_dir
            }

            # Add user/group if specified
            if user and group:
                uid = pwd.getpwnam(user).pw_uid
                gid = grp.getgrnam(group).gr_gid
                popen_kwargs['preexec_fn'] = lambda: os.setgid(gid) or os.setuid(uid)

            # Start process
            process = subprocess.Popen(command, **popen_kwargs)

            # Stream output in real-time
            stdout_log = self._stream_output(process.stdout, "light_grey")
            stderr_log = self._stream_output(process.stderr, "red")

            process.wait()
            return stdout_log, stderr_log

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error running command: {e}")
            self.logger.error(f"Command output: {e.output}")
            self.logger.error(f"Error output: {e.stderr}")
            return "Error", e.stderr or ""
        except (OSError, PermissionError, FileNotFoundError) as e:
            self.logger.error(f"System error running curvenote command: {e}")
            return "Error", str(e)

    def _stream_output(self, stream, color: str) -> str:
        """
        Stream output from a pipe in real-time.

        Args:
            stream: Output stream to read from
            color: Color to print output in

        Returns:
            Complete output as string
        """
        output_log = ""
        for line in stream:
            if line:
                output_log += line
                self.cprint(line.rstrip(), color)
        return output_log

    def _combine_logs(self, stdout_log: str, stderr_log: str) -> str:
        """
        Combine stdout and stderr logs.

        Args:
            stdout_log: Standard output log
            stderr_log: Standard error log

        Returns:
            Combined log string
        """
        combined_log = stdout_log
        if stderr_log:
            combined_log += "\n" + stderr_log
        return combined_log

    def build(
        self,
        *args: str,
        user: Optional[str] = None,
        group: Optional[str] = None
    ) -> str:
        """
        Build the Curvenote project with specified arguments.

        Args:
            *args: Variable length argument list for the curvenote build command
            user: Optional username to run command as
            group: Optional group to run command as

        Returns:
            Combined stdout and stderr output
        """
        stdout_log, stderr_log = self.run_command(
            'build', *args,
            env_vars=self.env_vars,
            user=user,
            group=group
        )
        return self._combine_logs(stdout_log, stderr_log)

    def start(
        self,
        *args: str,
        user: Optional[str] = None,
        group: Optional[str] = None
    ) -> str:
        """
        Start the Curvenote development server with specified arguments.

        Args:
            *args: Variable length argument list for the curvenote start command
            user: Optional username to run command as
            group: Optional group to run command as

        Returns:
            Combined stdout and stderr output
        """
        stdout_log, stderr_log = self.run_command(
            'start', *args,
            env_vars=self.env_vars,
            user=user,
            group=group
        )
        return self._combine_logs(stdout_log, stderr_log)

    def deploy(
        self,
        *args: str,
        user: Optional[str] = None,
        group: Optional[str] = None
    ) -> str:
        """
        Deploy the Curvenote project with specified arguments.

        Args:
            *args: Variable length argument list for the curvenote deploy command
            user: Optional username to run command as
            group: Optional group to run command as

        Returns:
            Combined stdout and stderr output
        """
        stdout_log, stderr_log = self.run_command(
            'deploy', *args,
            env_vars=self.env_vars,
            user=user,
            group=group
        )
        return self._combine_logs(stdout_log, stderr_log)

    def export_pdf(
        self,
        link: Optional[str] = None,
        target: Optional[str] = None,
        template: Optional[str] = None,
        user: Optional[str] = None,
        group: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Export content to PDF using Curvenote CLI.

        Args:
            link: Link to the content to export
            target: Target output directory
            template: LaTeX template to use
            user: Optional username to run command as
            group: Optional group to run command as

        Returns:
            Tuple of (stdout_log, stderr_log)
        """
        args = ['export', 'pdf']
        if link:
            args.append(link)
        if target:
            args.append(target)
        if template:
            args.extend(['-t', template])

        return self.run_command(*args, env_vars=self.env_vars, user=user, group=group)

    def export_jupyter_book(
        self,
        link: Optional[str] = None,
        user: Optional[str] = None,
        group: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Export content to Jupyter Book format using Curvenote CLI.

        Args:
            link: Link to the content to export
            user: Optional username to run command as
            group: Optional group to run command as

        Returns:
            Tuple of (stdout_log, stderr_log)
        """
        args = ['export', 'jb']
        if link:
            args.append(link)

        return self.run_command(*args, env_vars=self.env_vars, user=user, group=group)

    def init(
        self,
        *args: str,
        user: Optional[str] = None,
        group: Optional[str] = None
    ) -> str:
        """
        Initialize a Curvenote project.

        Args:
            *args: Variable length argument list for the curvenote init command
            user: Optional username to run command as
            group: Optional group to run command as

        Returns:
            Combined stdout and stderr output
        """
        stdout_log, stderr_log = self.run_command(
            'init', *args,
            env_vars=self.env_vars,
            user=user,
            group=group
        )
        return self._combine_logs(stdout_log, stderr_log)

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
            user: Optional username to run command as
            group: Optional group to run command as

        Returns:
            Combined stdout and stderr output
        """
        args = ['pull']
        if path:
            args.append(path)

        stdout_log, stderr_log = self.run_command(
            *args,
            env_vars=self.env_vars,
            user=user,
            group=group
        )
        return self._combine_logs(stdout_log, stderr_log)

    def submit_draft(
        self,
        *args: str,
        user: Optional[str] = None,
        group: Optional[str] = None
    ) -> str:
        """
        Submit a draft to Curvenote with specified arguments.

        Args:
            *args: Variable length argument list for the curvenote submit command
            user: Optional username to run command as
            group: Optional group to run command as

        Returns:
            Combined stdout and stderr output
        """
        stdout_log, stderr_log = self.run_command(
            'submit', *args,
            env_vars=self.env_vars,
            user=user,
            group=group
        )
        return self._combine_logs(stdout_log, stderr_log)


# Backward compatibility aliases
check_node_installed = Curvenote._check_node_installed
check_curvenote_installed = Curvenote._check_curvenote_installed
