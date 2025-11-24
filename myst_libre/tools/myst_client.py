"""
myst_client.py

Refactored MystMD client for managing MyST markdown operations.
"""

import subprocess
import os
import sys
import grp
import pwd
from typing import Optional, Tuple, Dict
from pathlib import Path

from ..abstract_class import AbstractClass


class MystMD(AbstractClass):
    """
    MystMD client for managing MyST markdown operations.

    Handles building and converting MyST markdown files using the myst CLI.
    """

    def __init__(self, build_dir: str, env_vars: Dict[str, str], executable: str = 'myst'):
        """
        Initialize the MystMD client.

        Args:
            build_dir: Directory where the build will take place
            env_vars: Environment variables needed for the build process
            executable: Name of the MyST executable (default: 'myst')
        """
        super().__init__()
        self.executable = executable
        self.build_dir = build_dir
        self.env_vars = env_vars
        self.run_pid: Optional[int] = None

        self.cprint("␤[Preflight checks]", "light_grey")
        self._check_node_installed()
        self._check_mystmd_installed()

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

    def _check_mystmd_installed(self):
        """
        Check if MyST markdown tool is installed and available in the system PATH.

        Raises:
            EnvironmentError: If MyST markdown tool is not installed or not found in PATH
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

            self.print_success(f"mystmd is installed: {stdout.strip()}")

        except subprocess.CalledProcessError as e:
            self.print_error(f"Error checking myst version: {e.stderr.strip()}")
            raise
        except (FileNotFoundError, OSError) as e:
            self.print_error(f"MyST CLI executable not found: {str(e)}")
            raise EnvironmentError("MyST CLI is not installed or not found in PATH") from e

    def run_command(
        self,
        *args: str,
        env_vars: Optional[Dict[str, str]] = None,
        user: Optional[str] = None,
        group: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Run a command using the MyST executable.

        Args:
            *args: Arguments for the MyST executable command
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

            # Debug information
            self.logger.debug(f"Running command from directory: {os.getcwd()}")
            self.logger.debug(f"Set cwd to: {self.build_dir}")
            self.logger.debug(f"Command: {' '.join(command)}")

            # Log the Jupyter environment variables being used
            if 'JUPYTER_BASE_URL' in env:
                self.logger.info(f"JUPYTER_BASE_URL: {env['JUPYTER_BASE_URL']}")
            if 'JUPYTER_TOKEN' in env:
                self.logger.info(f"JUPYTER_TOKEN: {env['JUPYTER_TOKEN']}")
            if 'port' in env:
                self.logger.info(f"port: {env['port']}")

            # Build subprocess arguments
            popen_kwargs = {
                'env': env,
                'stdout': subprocess.PIPE,
                'stderr': subprocess.PIPE,
                'text': True,
                'cwd': self.build_dir,
                'start_new_session': True
            }

            # Add user/group if specified
            if user and group:
                uid = pwd.getpwnam(user).pw_uid
                gid = grp.getgrnam(group).gr_gid
                popen_kwargs['preexec_fn'] = lambda: os.setgid(gid) or os.setuid(uid)

            # Start process
            process = subprocess.Popen(command, **popen_kwargs)
            self.run_pid = process.pid

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
            self.logger.error(f"System error running myst command: {e}")
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

    def build(
        self,
        *args: str,
        user: Optional[str] = None,
        group: Optional[str] = None
    ) -> str:
        """
        Build the MyST markdown project with specified arguments.

        Args:
            *args: Variable length argument list for the myst build command
            user: Optional username to run command as
            group: Optional group to run command as

        Returns:
            Combined stdout and stderr output
        """
        stdout_log, stderr_log = self.run_command(
            *args,
            env_vars=self.env_vars,
            user=user,
            group=group
        )

        combined_log = stdout_log
        if stderr_log:
            combined_log += "\n" + stderr_log
        return combined_log

    def convert(
        self,
        input_file: str,
        output_file: str,
        user: Optional[str] = None,
        group: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Convert a MyST markdown file to another format.

        Args:
            input_file: Path to the input MyST markdown file
            output_file: Path to the output file
            user: Optional username to run command as
            group: Optional group to run command as

        Returns:
            Tuple of (stdout_log, stderr_log)
        """
        return self.run_command(
            'convert', input_file, '-o', output_file,
            env_vars=self.env_vars,
            user=user,
            group=group
        )


# Deprecated aliases for backward compatibility
check_node_installed = MystMD._check_node_installed
check_mystmd_installed = MystMD._check_mystmd_installed
