"""
myst_client.py

This module contains the MystMD class for managing MyST markdown operations such as building and converting files.
"""

import subprocess
import os
from myst_libre.abstract_class import AbstractClass
import sys

class MystMD(AbstractClass):
    """
    MystMD

    A class to manage MyST markdown operations such as building and converting files.
    
    Args:
        build_dir (str): Directory where the build will take place.
        env_vars (dict): Environment variables needed for the build process.
        executable (str): Name of the MyST executable. Default is 'myst'.
    """    
    def __init__(self, build_dir, env_vars, executable='myst'):
        """
        Initialize the MystMD class with build directory, environment variables, and executable name.
        """
        super().__init__()
        self.executable = executable
        self.build_dir = build_dir
        self.env_vars = env_vars
        self.cprint(f"␤[Preflight checks]","light_grey")
        self.check_node_installed()
        self.check_mystmd_installed()

    def check_node_installed(self):
        """
        Check if Node.js is installed and available in the system PATH.
        
        Raises:
            EnvironmentError: If Node.js is not installed or not found in PATH.
        """
        try:
            result = subprocess.run(['node', '--version'], capture_output=True, text=True, check=True)
            self.cprint(f"✓ Node.js is installed: {result.stdout.strip()}","green")
        except subprocess.CalledProcessError as e:
            raise EnvironmentError("Node.js is not installed or not found in PATH. Please install Node.js to proceed.") from e

    def check_mystmd_installed(self):
        """
        Check if MyST markdown tool is installed and available in the system PATH.
        
        Raises:
            EnvironmentError: If MyST markdown tool is not installed or not found in PATH.
        """
        try:
            result = subprocess.run([self.executable, '--version'], capture_output=True, text=True, check=True)
            self.cprint(f"✓ mystmd is installed: {result.stdout.strip()}","green")
        except subprocess.CalledProcessError as e:
            raise EnvironmentError(f"{self.executable} is not installed or not found in PATH. Please install mystmd to proceed.") from e
        
    def run_command(self, *args, env_vars={}):
        """
        Run a command using the MyST executable.
        
        Args:
            *args: Arguments for the MyST executable command.
            env_vars (dict): Environment variables to set for the command.
        
        Returns:
            str: Command output or None if failed.
        """
        command = [self.executable] + list(args)
        try:
            # Combine the current environment with the provided env_vars
            env = os.environ.copy()
            env.update(env_vars)

            process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            output = []
            error_output = []

            # Stream stdout and stderr in real-time
            while True:
                stdout_line = process.stdout.readline()
                stderr_line = process.stderr.readline()
                if not stdout_line and not stderr_line and process.poll() is not None:
                    break
                if stdout_line:
                    print(stdout_line, end='')
                    output.append(stdout_line)
                if stderr_line:
                    print(stderr_line, end='', file=sys.stderr)
                    error_output.append(stderr_line)
                    
            process.wait()

            if process.returncode != 0:
                raise subprocess.CalledProcessError(process.returncode, command, output='\n'.join(output), stderr='\n'.join(error_output))

            return ''.join(output)
        except subprocess.CalledProcessError as e:
            print(f"Error running command: {e}")
            print(f"Command output: {e.output}")
            print(f"Error output: {e.stderr}")
            return None
        except Exception as e:
            print(f"Unexpected error: {e}")
            return None
    
    def build(self):
        """
        Build the MyST markdown project.
        
        Returns:
            str: Command output or None if failed.
        """
        os.chdir(self.build_dir)
        env = os.environ.copy()
        self.env_vars.update(env)
        return self.run_command('build', '--execute', '--html',env_vars=self.env_vars)
    
    def convert(self, input_file, output_file):
        """
        Convert a MyST markdown file to another format.
        
        Args:
            input_file (str): Path to the input MyST markdown file.
            output_file (str): Path to the output file.
        
        Returns:
            str: Command output or None if failed.
        """
        return self.run_command('convert', input_file, '-o', output_file,env_vars=[])