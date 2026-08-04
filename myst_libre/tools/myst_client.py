"""
myst_client.py

Refactored MystMD client for managing MyST markdown operations.
"""

import fcntl
import json
import logging
import os
import grp
import pwd
import re
import signal
import socket
import subprocess
import tempfile
import time
from typing import Optional, Tuple, Dict, List
from pathlib import Path

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')

from ..abstract_class import AbstractClass
from ..constants import PROCESS_STATE_FILE


def _process_start_key(pid: int) -> Optional[str]:
    """
    Read a stable per-process start identifier, used to detect PID reuse.

    A recorded PID alone is not safe to signal later: the OS recycles PIDs, so
    by the time a stale record is reconciled that number may belong to something
    unrelated. Pairing it with the process start time makes the record
    self-validating.

    No psutil dependency - /proc on Linux, ps(1) elsewhere.

    Args:
        pid: Process ID

    Returns:
        Opaque start-time string, or None if it could not be determined
    """
    # Linux: field 22 of /proc/<pid>/stat is starttime. Split on the last ')'
    # because the comm field can itself contain spaces and parentheses.
    try:
        with open(f'/proc/{pid}/stat') as f:
            return f.read().rsplit(')', 1)[1].split()[19]
    except (OSError, IndexError):
        pass

    # macOS/BSD fallback
    try:
        result = subprocess.run(
            ['ps', '-o', 'lstart=', '-p', str(pid)],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass

    return None


class MystMD(AbstractClass):
    """
    MystMD client for managing MyST markdown operations.

    Handles building and converting MyST markdown files using the myst CLI.
    """

    def __init__(
        self,
        build_dir: str,
        env_vars: Dict[str, str],
        executable: str = 'myst',
        state_file: Optional[str] = None
    ):
        """
        Initialize the MystMD client.

        Args:
            build_dir: Directory where the build will take place
            env_vars: Environment variables needed for the build process
            executable: Name of the MyST executable (default: 'myst')
            state_file: Path to the process state file used for orphan recovery
                (default: PROCESS_STATE_FILE). See reap_orphans.
        """
        super().__init__()
        self.state_file = Path(state_file or PROCESS_STATE_FILE)
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
        group: Optional[str] = None,
        timeout: Optional[int] = None
    ) -> Tuple[str, str]:
        """
        Run a command using the MyST executable.

        Args:
            *args: Arguments for the MyST executable command
            env_vars: Environment variables to set for the command
            user: Optional username to run command as
            group: Optional group to run command as
            timeout: Optional timeout in seconds. If the process does not
                     complete within this time, the entire process tree is
                     killed and a subprocess.TimeoutExpired is raised.

        Returns:
            Tuple of (stdout_log, stderr_log)
        """
        if env_vars is None:
            env_vars = {}

        command = [self.executable] + list(args)
        stdout_path = None
        stderr_path = None

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

            # Write ALL output (stdout + stderr) to a single temp file.
            #
            # Why a temp file instead of pipes?
            # Celery's gevent pool monkey-patches threading.Thread to
            # greenlets.  Pipe reads (os.read on an fd) are blocking
            # syscalls that gevent does NOT patch, so the reading
            # greenlets starve the gevent hub and prevent heartbeats.
            #
            # Why merge stderr into stdout?
            # mystmd logs errors (including notebook tracebacks) to stderr
            # via console.error.  Keeping them separate risks losing the
            # traceback content if anything goes wrong with the second
            # file/stream.  A single interleaved stream guarantees every
            # line — including error tracebacks — is visible in the logs.
            output_file = tempfile.NamedTemporaryFile(
                mode='w+', suffix='.myst.log', delete=False
            )
            stdout_path = output_file.name
            stderr_path = None  # not used, stderr merged into stdout

            # Build subprocess arguments
            popen_kwargs = {
                'env': env,
                'stdout': output_file,
                'stderr': subprocess.STDOUT,  # merge stderr into stdout
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

            # Record before anything can fail, so a crash from here on still
            # leaves a reapable record
            self._record_process(process.pid)

            # Close our copy of the file handle — the subprocess owns it now.
            output_file.close()

            # Poll loop: fully cooperative under gevent.
            # time.sleep() is monkey-patched to gevent.sleep(), yielding
            # to the hub so heartbeats and other greenlets can run.
            output_pos = 0
            deadline = (time.monotonic() + timeout) if timeout else None

            while process.poll() is None:
                if deadline is not None and time.monotonic() > deadline:
                    self.logger.error(
                        f"myst process (PID {process.pid}) timed out after {timeout}s, "
                        f"killing process tree"
                    )
                    self._kill_process_tree(process.pid)
                    raise subprocess.TimeoutExpired(
                        cmd=command, timeout=timeout
                    )
                output_pos = self._tail_file(stdout_path, output_pos, "light_grey")
                time.sleep(1)

            # Final flush — pick up anything written between last poll and exit
            self._tail_file(stdout_path, output_pos, "light_grey")

            # Read complete output
            with open(stdout_path, 'r') as f:
                all_output = f.read()

            return all_output, ""

        except subprocess.TimeoutExpired:
            raise
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error running command: {e}")
            self.logger.error(f"Command output: {e.output}")
            self.logger.error(f"Error output: {e.stderr}")
            return "Error", e.stderr or ""
        except (OSError, PermissionError, FileNotFoundError) as e:
            self.logger.error(f"System error running myst command: {e}")
            return "Error", str(e)
        finally:
            # The process is no longer ours to reap, whether it exited cleanly,
            # timed out and was killed, or errored
            if self.run_pid is not None:
                self._forget_process(self.run_pid)
            self._cleanup_files(stdout_path, stderr_path)

    # ------------------------------------------------------------------
    # Orphan tracking
    #
    # Killing the process group handles teardown while this process is alive.
    # It cannot help after a crash or worker restart, where no PID survives to
    # signal - myst and its children (npm run start -> node ./server.js) stay
    # up holding ports.
    #
    # Ports are the wrong key for this. With `myst build --execute`, mystmd runs
    # buildSite (the whole execution phase) *before* it starts either server, so
    # for a heavy paper no port exists for most of the build and both appear
    # only near the end. Catching that would mean polling for the build's entire
    # duration, and blocking syscalls in a background thread are exactly what
    # starves the gevent hub under Celery (see run_command).
    #
    # The process group id is known at Popen time instead: immediately, for free,
    # and valid for the whole build no matter what mystmd does internally.
    # ------------------------------------------------------------------

    @staticmethod
    def _read_state(path: Path) -> List[Dict]:
        """Read the process state file. Returns [] if absent or unreadable."""
        try:
            with open(path) as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    @staticmethod
    def _write_state(path: Path, entries: List[Dict]):
        """Write the process state file atomically."""
        tmp = f"{path}.{os.getpid()}.tmp"
        try:
            with open(tmp, 'w') as f:
                json.dump(entries, f, indent=2)
            os.replace(tmp, path)
        except OSError as e:
            logging.warning(f"Could not write process state file {path}: {e}")
            try:
                os.unlink(tmp)
            except OSError:
                pass

    @classmethod
    def _update_state(cls, path: Path, mutate):
        """
        Apply mutate(entries) -> entries under an exclusive lock.

        Several workers can share one state file, so read-modify-write has to be
        serialized. The lock is held only for a small JSON file, which keeps the
        blocking window short enough not to matter under gevent.
        """
        lock_path = f"{path}.lock"
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
        except OSError as e:
            logging.warning(f"Could not open state lock {lock_path}: {e}; proceeding unlocked")
            cls._write_state(path, mutate(cls._read_state(path)))
            return

        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            cls._write_state(path, mutate(cls._read_state(path)))
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def _record_process(self, pid: int):
        """Record a launched myst process group so it can be reaped later."""
        try:
            pgid = os.getpgid(pid)
        except OSError as e:
            logging.debug(f"Could not read pgid for {pid}, not tracking: {e}")
            return

        entry = {
            'pid': pid,
            'pgid': pgid,
            'start_key': _process_start_key(pid),
            'build_dir': str(self.build_dir),
            'recorded_at': time.time(),
        }

        self._update_state(
            self.state_file,
            lambda entries: [e for e in entries if e.get('pid') != pid] + [entry]
        )
        self.logger.debug(f"Tracking myst process pid={pid} pgid={pgid}")

    def _forget_process(self, pid: int):
        """Drop a process from the state file once it has been dealt with."""
        self._update_state(
            self.state_file,
            lambda entries: [e for e in entries if e.get('pid') != pid]
        )

    @classmethod
    def reap_orphans(cls, state_file: Optional[str] = None) -> List[Dict]:
        """
        Kill myst process groups left behind by a previous run.

        Call once at worker startup, before accepting work. Each record is only
        acted on if the PID is still alive *and* its start key matches what was
        recorded; a mismatch means the PID was recycled and the original process
        is already gone, so it is dropped rather than signalled.

        Args:
            state_file: Override the state file path (default: PROCESS_STATE_FILE)

        Returns:
            The entries that were reaped
        """
        path = Path(state_file or PROCESS_STATE_FILE)
        reaped: List[Dict] = []

        def mutate(entries):
            survivors = []
            for entry in entries:
                pid = entry.get('pid')
                pgid = entry.get('pgid')
                if pid is None or pgid is None:
                    continue

                current = _process_start_key(pid)
                if current is None:
                    logging.info(f"Orphan record pid={pid} is gone, dropping")
                    continue

                if current != entry.get('start_key'):
                    logging.info(
                        f"Orphan record pid={pid} start key differs "
                        f"(PID reused), dropping without signalling"
                    )
                    continue

                logging.warning(
                    f"Reaping orphaned myst process group pgid={pgid} "
                    f"(pid={pid}, build_dir={entry.get('build_dir')})"
                )
                try:
                    os.killpg(pgid, signal.SIGTERM)
                except (ProcessLookupError, OSError) as e:
                    logging.debug(f"Process group {pgid} already gone: {e}")
                    continue
                reaped.append(entry)

            # Give the groups a moment, then force-kill whatever ignored SIGTERM
            if reaped:
                time.sleep(3)
                for entry in reaped:
                    try:
                        os.killpg(entry['pgid'], signal.SIGKILL)
                    except (ProcessLookupError, OSError):
                        pass

            return survivors

        cls._update_state(path, mutate)
        return reaped

    @staticmethod
    def find_open_port(start: int = 3000, end: int = 3100) -> int:
        """Find an available port in the given range.

        Uses the same default range as mystmd's theme server (3000-3100).
        """
        for port in range(start, end):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(('localhost', port))
                    return port
                except OSError:
                    continue
        raise RuntimeError(f"No available port in range {start}-{end}")

    def cleanup(self):
        """Kill the myst process tree if it is still running.

        Safe to call multiple times or when no process was started.
        """
        if self.run_pid is not None:
            self.logger.info(f"Cleaning up myst process tree (PID {self.run_pid})")
            self._kill_process_tree(self.run_pid)
            self._forget_process(self.run_pid)
            self.run_pid = None

    def _kill_process_tree(self, pid: int):
        """
        Kill an entire process tree by sending SIGTERM then SIGKILL to the
        process group. Works because we launch subprocesses with
        start_new_session=True, making the child the session/group leader.
        """
        try:
            pgid = os.getpgid(pid)
            self.logger.info(f"Sending SIGTERM to process group {pgid}")
            os.killpg(pgid, signal.SIGTERM)
        except (ProcessLookupError, OSError) as e:
            self.logger.debug(f"Process group already gone on SIGTERM: {e}")
            return

        # Give processes a few seconds to shut down gracefully
        time.sleep(3)

        try:
            os.killpg(pgid, signal.SIGKILL)
            self.logger.info(f"Sent SIGKILL to process group {pgid}")
        except (ProcessLookupError, OSError):
            pass

    def _tail_file(self, path: str, pos: int, color: str) -> int:
        """Read new content from a file starting at *pos*, log it, return new pos."""
        try:
            with open(path, 'r') as f:
                f.seek(pos)
                new_data = f.read()
                if new_data:
                    for line in new_data.splitlines():
                        # Strip ANSI escape codes so Rich Console and Celery's
                        # LoggingProxy always see clean text.  The raw ANSI from
                        # chalk/IPython causes lines to vanish in non-TTY contexts.
                        clean = _ANSI_RE.sub('', line)
                        self.cprint(clean, color)
                return f.tell()
        except FileNotFoundError:
            return pos

    @staticmethod
    def _cleanup_files(*paths):
        """Remove temp files, ignoring errors."""
        for p in paths:
            if p is None:
                continue
            try:
                os.unlink(p)
            except OSError:
                pass

    def build(
        self,
        *args: str,
        user: Optional[str] = None,
        group: Optional[str] = None,
        timeout: Optional[int] = None
    ) -> str:
        """
        Build the MyST markdown project with specified arguments.

        Args:
            *args: Variable length argument list for the myst build command
            user: Optional username to run command as
            group: Optional group to run command as
            timeout: Optional timeout in seconds for the build process

        Returns:
            Combined stdout and stderr output
        """
        stdout_log, stderr_log = self.run_command(
            *args,
            env_vars=self.env_vars,
            user=user,
            group=group,
            timeout=timeout
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
        group: Optional[str] = None,
        timeout: Optional[int] = None
    ) -> Tuple[str, str]:
        """
        Convert a MyST markdown file to another format.

        Args:
            input_file: Path to the input MyST markdown file
            output_file: Path to the output file
            user: Optional username to run command as
            group: Optional group to run command as
            timeout: Optional timeout in seconds for the conversion process

        Returns:
            Tuple of (stdout_log, stderr_log)
        """
        return self.run_command(
            'convert', input_file, '-o', output_file,
            env_vars=self.env_vars,
            user=user,
            group=group,
            timeout=timeout
        )


# Deprecated aliases for backward compatibility
check_node_installed = MystMD._check_node_installed
check_mystmd_installed = MystMD._check_mystmd_installed
