"""
jupyter_hub_local_spawner.py

This module contains the JupyterHubLocalSpawner class for managing JupyterHub instances locally.
"""

import os
import logging
import socket
from hashlib import blake2b
from myst_libre.abstract_class import AbstractClass
from myst_libre.rees import REES

class JupyterHubLocalSpawner(AbstractClass):
    """
    Spawner for managing JupyterHub instances locally.
    
    This class implements context manager protocol for proper resource cleanup.
    
    Args:
        registry_url (str): URL of the Docker registry (https://my-registry.example.com).
        gh_user_repo_name (str): GitHub user/repository name.
        auth (dict): Authentication credentials {username:"***","password":"***"}.
        binder_image_tag (str): Docker image tag of the container in which the article will be built.
        build_src_commit_hash (str): Commit hash of the repository from which the article will be built.
    """
    def __init__(self,rees,**kwargs):
        if not isinstance(rees, REES):
            raise TypeError(f"Expected 'rees' to be an instance of REES, got {type(rees).__name__} instead")
        super().__init__()
        self.rees = rees
        required_inputs = ['container_data_mount_dir','container_build_source_mount_dir',
                           'host_data_parent_dir','host_build_source_parent_dir']

        for inp in required_inputs:
            if inp not in kwargs.keys():
                raise(f'{inp} is not provided for JupyterHubLocalSpawner.')
            else:
                setattr(self, inp, kwargs[inp])

        self.container = None
        self.port = None
        self.jh_token = None
        self._cleanup_needed = False

    def find_open_port(self):
        """
        Find an open port to use.
        
        Returns:
            int: Available port number.
        
        Raises:
            Exception: If no open ports are available.
        """
        for port in range(8888, 10000):
            if not self._is_port_in_use(port):
                return port
        raise Exception("No open ports available")

    def _is_port_in_use(self, port):
        """
        Check if a port is in use.
        
        Args:
            port (int): Port number to check.
        
        Returns:
            bool: True if port is in use, else False.
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('127.0.0.1', port)) == 0

    def __enter__(self):
        """Context manager entry point."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit point - ensures cleanup."""
        self.cleanup()
        return False  # Don't suppress exceptions

    def cleanup(self):
        """
        Clean up all resources (container, etc.).
        """
        if self.container:
            try:
                self.logger.info(f"Cleaning up container {self.container.short_id}")
                self.container.stop(timeout=10)
                self.container.remove(force=True)
                self.logger.info("Container cleaned up successfully")
            except Exception as e:
                self.logger.error(f"Error during container cleanup: {e}")
            finally:
                self.container = None
        
        self._cleanup_needed = False

    def spawn_jupyter_hub(self, jb_build_command=None):
        """
        Spawn a JupyterHub instance.
        """
        output_logs = []  # Collect logs and cprints here
        self.port = self.find_open_port()
        h = blake2b(digest_size=20)
        h.update(os.urandom(20))
        self.jh_token = h.hexdigest()

        if jb_build_command:
            this_entrypoint = f"/bin/sh -c 'jupyter-book build --all --verbose --path-output {self.container_build_source_mount_dir} content 2>&1 | tee -a jupyter_book_build.log'"
        else:
            this_entrypoint = f'jupyter server --allow-root --ip 0.0.0.0 --log-level=DEBUG --IdentityProvider.token="{self.jh_token}" --ServerApp.port="{self.port}"'
        
        # self.rees.found_image_name is assigned if above not fails

        self.rees.git_clone_repo(self.host_build_source_parent_dir)
        self.rees.git_checkout_commit()
        if not self.rees.dataset_name:
            self.rees.get_project_name()

        # Pre-create the data directory in the build directory AFTER checkout to prevent Docker
        # from creating it as root when mounting volumes. This must be done after checkout
        # to avoid interfering with git operations.
        # Since self.rees.build_dir maps to /home/jovyan and data will be mounted
        # at /home/jovyan/data, we need to create 'data' subdirectory here
        data_dir_in_build = os.path.join(self.rees.build_dir, 'data')
        os.makedirs(data_dir_in_build, exist_ok=True)
        logging.debug(f"Pre-created data directory: {data_dir_in_build}")

        if self.rees.dataset_name:
            self.rees.repo2data_download(self.host_data_parent_dir)

            mnt_vol = {f'{os.path.join(self.host_data_parent_dir, self.rees.dataset_name)}': {'bind': os.path.join(self.container_data_mount_dir, self.rees.dataset_name), 'mode': 'ro'},
                        self.rees.build_dir: {'bind': f'{self.container_build_source_mount_dir}', 'mode': 'rw'}}
        else:
            mnt_vol = {self.rees.build_dir: {'bind': f'{self.container_build_source_mount_dir}', 'mode': 'rw'}}
            
        self.rees.pull_image()
        self.jh_url = f"http://localhost:{self.port}"
        try:
            # Run the container as the current host user (UID:GID) so files
            # created inside bind-mounted volumes are owned by the host user.
            # This avoids leaving root-owned files on the host that the user
            # cannot delete after the container stops.
            run_user = f"{os.getuid()}:{os.getgid()}"
            logging.debug(f"Running container as user {run_user}")
            self.container = self.rees.docker_client.containers.run(
                self.rees.docker_image,
                ports={f'{self.port}/tcp': self.port},
                environment={"JUPYTER_TOKEN": f'{self.jh_token}', "port": f'{self.port}', "JUPYTER_BASE_URL": f'{self.jh_url}'},
                entrypoint=this_entrypoint,
                volumes=mnt_vol,
                user=run_user,
                detach=True)
            self._cleanup_needed = True
            logging.info(f'Jupyter hub is {self.container.status}')

            # Use the helper function to log and print messages
            def log_and_print(message, color=None):
                output_logs.append(f"\n {message}")
                if color:
                    self.cprint(message, color)
                else:
                    print(message)

            # Collecting and printing output
            log_and_print('␤[Status]', 'light_grey')
            log_and_print(' ├─────── ⏺ running', 'green')
            log_and_print(f' └─────── Container {self.container.short_id} {self.container.name}', 'green')
            log_and_print(' ℹ Run the following commands in the terminal if you are debugging locally:', 'yellow')
            log_and_print(f' port="{self.port}"', 'cyan')
            log_and_print(f' export JUPYTER_BASE_URL="{self.jh_url}"', 'cyan')
            log_and_print(f' export JUPYTER_TOKEN="{self.jh_token}"', 'cyan')
            log_and_print('␤[Resources]', 'light_grey')
            log_and_print(' ├── MyST repository', 'magenta')
            log_and_print(f' │   ├───────── ✸ {self.rees.gh_user_repo_name}', 'light_blue')
            log_and_print(f' │   ├───────── ⎌ {self.rees.gh_repo_commit_hash}', 'light_blue')
            log_and_print(f" │   └───────── ⏲ {self.rees.repo_commit_info['datetime']}: {self.rees.repo_commit_info['message']}".replace('\n', ''), 'light_blue')
            log_and_print(' └── Docker container', 'magenta')
            log_and_print(f'     ├───────── ✸ {self.rees.pull_image_name}', 'light_blue')
            log_and_print(f'     ├───────── ⎌ {self.rees.binder_image_tag}', 'light_blue')
            log_and_print(f"     ├───────── ⏲ {self.rees.binder_commit_info['datetime']}: {self.rees.binder_commit_info['message']}".replace('\n', ''), 'light_blue')
            if self.rees.binder_image_name_override:
                log_and_print(f'     └───────── ℹ Using NeuroLibre base image {self.rees.binder_image_name_override}', 'yellow')
            else:    
                log_and_print(f'     └───────── ℹ This image was built from REES-compliant {self.rees.gh_user_repo_name} repository at the commit above', 'yellow')
        except Exception as e:
            logging.error(f'Could not spawn a JH: \n {e}')
            output_logs.append(f'Error: {e}')
            self.cleanup()
            raise

        return output_logs

    def delete_stopped_containers(self):
        """
        Delete all stopped Docker containers.
        """
        stopped_containers = self.rees.docker_client.containers.list(all=True, filters={"status": "exited"})
        for container in stopped_containers:
            logging.info(f"Deleting stopped container: {container.id}")
            container.remove()

    def delete_image(self):
        """
        Delete the pulled Docker image.
        """
        if self.docker_image:
            logging.info(f"Deleting image: {self.docker_image.id}")
            self.rees.docker_client.images.remove(image=self.docker_image.id)

    def stop_container(self):
        self.logger.warning("Attempting to stop and remove the running container.")
        self.cleanup()

    def is_running(self):
        """
        Check if the container is currently running.
        
        Returns:
            bool: True if container exists and is running, False otherwise.
        """
        if not self.container:
            return False
        
        try:
            self.container.reload()
            return self.container.status == 'running'
        except Exception as e:
            self.logger.error(f"Error checking container status: {e}")
            return False

    def get_container_logs(self, tail=100):
        """
        Get logs from the running container.
        
        Args:
            tail (int): Number of lines to tail from the logs.
            
        Returns:
            str: Container logs or empty string if container not available.
        """
        if not self.container:
            return ""
        
        try:
            return self.container.logs(tail=tail).decode('utf-8')
        except Exception as e:
            self.logger.error(f"Error getting container logs: {e}")
            return f"Error retrieving logs: {e}"