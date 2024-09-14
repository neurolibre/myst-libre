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

    def spawn_jupyter_hub(self,jb_build_command=None):
        """
        Spawn a JupyterHub instance.
        """
        self.port = self.find_open_port()
        h = blake2b(digest_size=20)
        h.update(os.urandom(20))
        self.jh_token = h.hexdigest()

        if jb_build_command:
            this_entrypoint = f"/bin/sh -c 'jupyter-book build --all --verbose --path-output {self.container_build_source_mount_dir} content 2>&1 | tee -a jupyter_book_build.log'"
        else:
            this_entrypoint = f'jupyter server --allow-root --ip 0.0.0.0 --log-level=DEBUG --IdentityProvider.token="{self.jh_token}" --ServerApp.port="{self.port}"'

        if not self.rees.search_img_by_repo_name():
            raise Exception(f"[ERROR] A docker image has not been found for {self.rees.gh_user_repo_name} at {self.rees.binder_image_tag}.")
        if self.rees.binder_image_tag not in self.rees.found_image_tags:
            raise Exception(f"[ERROR] A docker image exists for {self.rees.gh_user_repo_name}, yet the tag {self.rees.binder_image_tag} is missing.")
        
        # self.rees.found_image_name is assigned if above not fails

        self.rees.git_clone_repo(self.host_build_source_parent_dir)
        self.rees.git_checkout_commit()
        if not self.rees.dataset_name:
            self.rees.get_project_name()
        
        if self.rees.dataset_name:
            self.rees.repo2data_download(self.host_data_parent_dir)
            mnt_vol = {f'{os.path.join(self.host_data_parent_dir,self.rees.dataset_name)}': {'bind': os.path.join(self.container_data_mount_dir,self.rees.dataset_name), 'mode': 'ro'},
                    self.rees.build_dir: {'bind': f'{self.container_build_source_mount_dir}', 'mode': 'rw'}}
        else:
            mnt_vol = {self.rees.build_dir: {'bind': f'{self.container_build_source_mount_dir}', 'mode': 'rw'}}
            
        self.rees.pull_image()
        self.jh_url = f"http://localhost:{self.port}"
        try:
            self.container = self.rees.docker_client.containers.run(
                self.rees.docker_image,
                ports={f'{self.port}/tcp': self.port},
                environment={"JUPYTER_TOKEN": f'{self.jh_token}',"port": f'{self.port}',"JUPYTER_BASE_URL": f'{self.jh_url}'},
                entrypoint= this_entrypoint,
                volumes=mnt_vol,
                detach=True)
            logging.info(f'Jupyter hub is {self.container.status}')
            self.cprint(f'␤[Status]', 'light_grey')
            self.cprint(f' ├─────── ⏺ running', 'green')
            self.cprint(f' └─────── Container {self.container.short_id} {self.container.name}', 'green')
            self.cprint(f' ℹ Run the following commands in the terminal if you are debugging locally:', 'yellow')
            self.cprint(f' port=\"{self.port}\"', 'cyan')
            self.cprint(f' export JUPYTER_BASE_URL=\"{self.jh_url}\"', 'cyan')
            self.cprint(f' export JUPYTER_TOKEN=\"{self.jh_token}\"', 'cyan')
            self.cprint(f'␤[Resources]', 'light_grey')
            self.cprint(f' ├── MyST repository', 'magenta')
            self.cprint(f' │   ├───────── ✸ {self.rees.gh_user_repo_name}','light_blue')
            self.cprint(f' │   ├───────── ⎌ {self.rees.gh_repo_commit_hash}','light_blue')
            self.cprint(f" │   └───────── ⏲ {self.rees.repo_commit_info['datetime']}: {self.rees.repo_commit_info['message']}".replace('\n', ''),'light_blue')
            self.cprint(f' └── Docker container', 'magenta')
            self.cprint(f'     ├───────── ✸ {self.rees.pull_image_name}','light_blue')
            self.cprint(f'     ├───────── ⎌ {self.rees.binder_image_tag}','light_blue')
            self.cprint(f"     ├───────── ⏲ {self.rees.binder_commit_info['datetime']}: {self.rees.binder_commit_info['message']}".replace('\n', ''),'light_blue')
            self.cprint(f'     └───────── ℹ This image was built from REES-compliant {self.rees.gh_user_repo_name} repository at the commit above','yellow')
        except Exception as e:
            logging.error(f'Could not spawn a JH: \n {e}')

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
        """
        Stop and remove the running container.
        """
        if self.container:
            self.container.stop()
            self.container.remove()