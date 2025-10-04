"""
curvenote_client.py

This module contains the Curvenote class for managing Curvenote CLI operations such as building, deploying, and exporting.
"""

import subprocess
import os
from myst_libre.tools.authenticator import Authenticator
import sys
import grp, pwd

class Curvenote(Authenticator):
    """
    Curvenote
    
    A class to manage Curvenote CLI operations such as building, deploying, and exporting content.
    
    Args:
        build_dir (str): Directory where the build will take place.
        env_vars (dict): Environment variables needed for the build process.
        executable (str): Name of the Curvenote executable. Default is 'curvenote'.
    """
    def __init__(self, build_dir, env_vars, executable='curvenote', dotenvloc='.'):
        """
        Initialize the Curvenote class with build directory, environment variables, and executable name.
        """
        super().__init__(dotenvloc=dotenvloc)
        self.executable = executable
        self.build_dir = build_dir
        self.env_vars = env_vars
        self.cprint(f"␤[Curvenote Preflight checks]","light_grey")
        self.check_node_installed()
        self.check_curvenote_installed()
        
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

    def check_curvenote_installed(self):
        """
        Check if Curvenote CLI is installed and available in the system PATH.
        
        Raises:
            EnvironmentError: If Curvenote CLI is not installed or not found in PATH.
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
            self.cprint(f"✓ curvenote is installed: {stdout.strip()}","green")
        except subprocess.CalledProcessError as e:
            self.cprint(f"✗ Error checking curvenote version: {e.stderr.strip()}", "red")
            raise
        except Exception as e:
            self.cprint(f"✗ Unexpected error occurred: {str(e)}", "red")
            raise
        
    def run_command(self, *args, env_vars={}, user=None, group=None):
        """
        Run a command using the Curvenote executable.
        
        Args:
            *args: Arguments for the Curvenote executable command.
            env_vars (dict): Environment variables to set for the command.
            user (str): Username to run the command as.
            group (str): Group name to run the command as.
        
        Returns:
            tuple: Command stdout and stderr output or None if failed.
        """
        command = [self.executable] + list(args)
        try:
            # Combine the current environment with the provided env_vars
            env = os.environ.copy()
            env.update(env_vars)
            
            # Add Curvenote token to environment if available
            if self._auth.get('curvenote_token'):
                env['CURVENOTE_TOKEN'] = self._auth['curvenote_token']
                self.cprint(f"🔑 Using Curvenote API token for authentication", "green")

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
                    stdout_log += output
                    self.cprint(output, "light_grey")
            # Stream stderr in real-time
            while True:
                error = process.stderr.readline()
                if error == "" and process.poll() is not None:
                    break
                if error:
                    stderr_log += error
                    self.cprint(error, "red")
            process.wait()
            return stdout_log, stderr_log

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
        Build the Curvenote project with specified arguments.
        
        Args:
            *args: Variable length argument list for the curvenote build command.
            user (str): Username to run the command as.
            group (str): Group name to run the command as.
        
        Returns:
            str: Command output or None if failed.
        """
        os.chdir(self.build_dir)
        stdout_log, stderr_log = self.run_command('build', *args, env_vars=self.env_vars, user=user, group=group)

        combined_log = stdout_log
        if stderr_log:
            combined_log += "\n" + stderr_log
        return combined_log
    
    def start(self, *args, user=None, group=None):
        """
        Start the Curvenote development server with specified arguments.
        
        Args:
            *args: Variable length argument list for the curvenote start command.
            user (str): Username to run the command as.
            group (str): Group name to run the command as.
        
        Returns:
            str: Command output or None if failed.
        """
        os.chdir(self.build_dir)
        stdout_log, stderr_log = self.run_command('start', *args, env_vars=self.env_vars, user=user, group=group)

        combined_log = stdout_log
        if stderr_log:
            combined_log += "\n" + stderr_log
        return combined_log
    
    def deploy(self, *args, user=None, group=None):
        """
        Deploy the Curvenote project with specified arguments.
        
        Args:
            *args: Variable length argument list for the curvenote deploy command.
            user (str): Username to run the command as.
            group (str): Group name to run the command as.
        
        Returns:
            str: Command output or None if failed.
        """
        os.chdir(self.build_dir)
        stdout_log, stderr_log = self.run_command('deploy', *args, env_vars=self.env_vars, user=user, group=group)

        combined_log = stdout_log
        if stderr_log:
            combined_log += "\n" + stderr_log
        return combined_log
    
    def export_pdf(self, link=None, target=None, template=None, user=None, group=None):
        """
        Export content to PDF using Curvenote CLI.
        
        Args:
            link (str): Link to the content to export.
            target (str): Target output directory.
            template (str): LaTeX template to use.
            user (str): Username to run the command as.
            group (str): Group name to run the command as.
        
        Returns:
            str: Command output or None if failed.
        """
        args = ['export', 'pdf']
        if link:
            args.append(link)
        if target:
            args.append(target)
        if template:
            args.extend(['-t', template])
            
        return self.run_command(*args, env_vars=self.env_vars, user=user, group=group)
    
    def export_jupyter_book(self, link=None, user=None, group=None):
        """
        Export content to Jupyter Book format using Curvenote CLI.
        
        Args:
            link (str): Link to the content to export.
            user (str): Username to run the command as.
            group (str): Group name to run the command as.
        
        Returns:
            str: Command output or None if failed.
        """
        args = ['export', 'jb']
        if link:
            args.append(link)
            
        return self.run_command(*args, env_vars=self.env_vars, user=user, group=group)
    
    def init(self, *args, user=None, group=None):
        """
        Initialize a Curvenote project.
        
        Args:
            *args: Variable length argument list for the curvenote init command.
            user (str): Username to run the command as.
            group (str): Group name to run the command as.
        
        Returns:
            str: Command output or None if failed.
        """
        os.chdir(self.build_dir)
        stdout_log, stderr_log = self.run_command('init', *args, env_vars=self.env_vars, user=user, group=group)

        combined_log = stdout_log
        if stderr_log:
            combined_log += "\n" + stderr_log
        return combined_log
    
    def pull(self, path=None, user=None, group=None):
        """
        Pull content from Curvenote.
        
        Args:
            path (str): Specific path to pull content from.
            user (str): Username to run the command as.
            group (str): Group name to run the command as.
        
        Returns:
            str: Command output or None if failed.
        """
        args = ['pull']
        if path:
            args.append(path)
            
        os.chdir(self.build_dir)
        stdout_log, stderr_log = self.run_command(*args, env_vars=self.env_vars, user=user, group=group)

        combined_log = stdout_log
        if stderr_log:
            combined_log += "\n" + stderr_log
        return combined_log