"""
myst_client.py

This module contains the MystMD class for managing MyST markdown operations such as building and converting files.
"""

import subprocess
import os
from myst_libre.abstract_class import AbstractClass
import sys
import grp, pwd

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
        #self.cprint(f"{os.environ}","light_grey")
        self.check_node_installed()
        self.check_mystmd_installed()

    def check_node_installed(self):
        """
        Check if Node.js is installed and available in the system PATH.
        
        Raises:
            EnvironmentError: If Node.js is not installed or not found in PATH.
        """
        try:
            process = subprocess.Popen(['node', '--version'], 
                                    env=os.environ, 
                                    stdout=subprocess.PIPE, 
                                    stderr=subprocess.PIPE, 
                                    text=True)
            stdout, stderr = process.communicate()
            if process.returncode != 0:
                raise subprocess.CalledProcessError(process.returncode, process.args, stdout, stderr)
            
            self.cprint(f"✓ Node.js is installed: {stdout.strip()}", "green")
        except subprocess.CalledProcessError as e:
            self.cprint(f"✗ Error checking Node.js version: {e.stderr.strip()}", "red")
            raise
        except Exception as e:
            self.cprint(f"✗ Unexpected error occurred: {str(e)}", "red")
            raise

    def check_mystmd_installed(self):
        """
        Check if MyST markdown tool is installed and available in the system PATH.
        
        Raises:
            EnvironmentError: If MyST markdown tool is not installed or not found in PATH.
        """
        try:
            process = subprocess.Popen([self.executable, '--version'], 
                            env=os.environ, 
                            stdout=subprocess.PIPE, 
                            stderr=subprocess.PIPE, 
                            text=True)
            stdout, stderr = process.communicate()
            if process.returncode != 0:
                raise subprocess.CalledProcessError(process.returncode, process.args, stdout, stderr)
            self.cprint(f"✓ mystmd is installed: {stdout.strip()}","green")
        except subprocess.CalledProcessError as e:
            self.cprint(f"✗ Error checking myst version: {e.stderr.strip()}", "red")
            raise
        except Exception as e:
            self.cprint(f"✗ Unexpected error occurred: {str(e)}", "red")
            raise
        
    def run_command(self, *args, env_vars={}, user=None, group=None):
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

            # Debug information
            self.cprint(f"🐞 Running command from directory: {os.getcwd()}", "light_grey")
            self.cprint(f"🐞 Set cwd to: {self.build_dir}", "light_grey")
            self.cprint(f"🐞 Command: {' '.join(command)}", "light_grey")

            if user and group:
                uid = pwd.getpwnam(user).pw_uid  
                gid = grp.getgrnam(group).gr_gid
                process = subprocess.Popen(command, env=env, 
                                           preexec_fn=lambda: os.setgid(gid) or os.setuid(uid),
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                           cwd=self.build_dir)
            else:
                process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=self.build_dir)

            # Initialize logs
            stdout_log = ""
            stderr_log = ""
            # Stream stdout in real-time
            while True:
                output = process.stdout.readline()
                if output == "" and process.poll() is not None:
                    break
                if output:
                    stdout_log += output  # No need to decode
                    self.cprint(output, "light_grey")  # Print stdout in real-time
            # Stream stderr in real-time
            while True:
                error = process.stderr.readline()
                if error == "" and process.poll() is not None:
                    break
                if error:
                    stderr_log += error  # No need to decode
                    self.cprint(error, "red")  # Print stderr in real-time
            process.wait()
            return stdout_log, stderr_log  # Return both logs

        except subprocess.CalledProcessError as e:
            print(f"Error running command: {e}")
            print(f"Command output: {e.output}")
            print(f"Error output: {e.stderr}")
            return "Error", e.stderr 
        except Exception as e:
            print(f"Unexpected error: {e}")
            return "Error", str(e)
    
    def build(self, *args, user=None, group=None):
        """
        Build the MyST markdown project with specified arguments.
        
        Args:
            *args: Variable length argument list for the myst command.
        
        Returns:
            str: Command output or None if failed.
        """
        os.chdir(self.build_dir)
        stdout_log, stderr_log = self.run_command(*args, env_vars=self.env_vars, user=user, group=group)
        if stderr_log is not None:
            stdout_log += stderr_log
        return stdout_log
    
    def convert(self, input_file, output_file, user=None, group=None):
        """
        Convert a MyST markdown file to another format.
        
        Args:
            input_file (str): Path to the input MyST markdown file.
            output_file (str): Path to the output file.
        
        Returns:
            str: Command output or None if failed.
        """
        return self.run_command('convert', input_file, '-o', output_file,env_vars=self.env_vars, user=user, group=group)