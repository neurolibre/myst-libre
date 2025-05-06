from myst_libre.abstract_class import AbstractClass
from myst_libre.tools.docker_registry_client import DockerRegistryClient
from myst_libre.tools.build_source_manager import BuildSourceManager
import docker
import subprocess
import os

class REES(DockerRegistryClient,BuildSourceManager):
    def __init__(self, rees_dict):
        # These are needed in the scope of the base classes
        self.registry_url = rees_dict['registry_url']
        self.gh_user_repo_name = rees_dict['gh_user_repo_name']
        self.gh_repo_commit_hash = rees_dict.get('gh_repo_commit_hash', "latest")
        self.binder_image_name_override = rees_dict.get('binder_image_name_override', None)
        self.binder_image_tag = rees_dict.get('binder_image_tag', "latest")
        self.bh_private_project_name = rees_dict.get('bh_private_project_name', None)
        self.bh_image_prefix = rees_dict.get('bh_image_prefix', "binder-")
        self.bh_project_name = rees_dict.get('bh_project_name', None)

        if 'dotenv' in rees_dict.keys():
            self.dotenvloc = rees_dict['dotenv']

        # Initialize as base to rees
        BuildSourceManager.__init__(self)
        DockerRegistryClient.__init__(self)

        # Get the latest commit hash from the GitHub API
        if self.gh_repo_commit_hash == "latest":
            self.cprint("🔎 Searching for latest commit hash in GitHub.","light_blue")
            api_url = f'https://api.github.com/repos/{self.gh_user_repo_name}/commits/{self.branch}'
            response = self.rest_client.get(api_url)
            if response.status_code == 200:
                latest_commit_hash = response.json()['sha']
                self.gh_repo_commit_hash = latest_commit_hash
                self.cprint(f"🎉 Found latest commit hash: {self.gh_repo_commit_hash}","white","on_blue")

        if self.search_img_by_repo_name():
            if self.binder_image_tag == "latest":
                self.cprint("🔎 Searching for latest image tag in registry.","light_blue")
                if self.get_tags_sorted_by_date():
                    self.cprint(f"🎉 Found latest tag in {self.registry_url}","light_blue")
                    self.cprint(f"🏷️  Latest runtime tag {self.found_image_tags_sorted[0]} for {self.found_image_name}","white","on_blue")
                    self.binder_image_tag = self.found_image_tags_sorted[0]
        else:
            raise Exception(f"[ERROR] A docker image has not been found for {self.gh_user_repo_name} at {self.binder_image_tag}.")

        self.cprint(f"␤[Preflight checks]","light_grey")
        self.check_docker_installed()

        self.pull_image_name = ""
        self.use_public_registry = False
        self.repo_commit_info = {}
        self.binder_commit_info = {}
        # CHECK: This may not work properly without
        # logging in to the registry on the host machine 
        # which keeps that auth info on the config file. 
        self.docker_client = docker.from_env()
    
    def check_docker_installed(self):
        """
        Check if Docker is installed and available in the system PATH.

        Raises:
            EnvironmentError: If Docker is not installed or not found in PATH.
        """
        try:
            result = subprocess.run(['docker', '--version'], env=os.environ, capture_output=True, text=True, check=True)
            self.cprint(f"✓ Docker is installed: {result.stdout.strip()}",'green')
        except subprocess.CalledProcessError as e:
            raise EnvironmentError("Docker is not installed or not found in PATH. Please install Docker to proceed.") from e

    def login_to_registry(self):
        """
        Login to a private docker registry.
        """
        self.docker_client.login(username=self._auth['username'], password=self._auth['password'], registry=self.registry_url)

    def pull_image(self):
        """
        Pull the Docker image from the registry.
        """
        if bool(self._auth) or not self.use_public_registry:
            self.login_to_registry()
            self.logger.info(f"Logging into {self.registry_url}")

        try:
            self.pull_image_name = f'{self.bh_private_project_name}/{self.found_image_name}'
            self.logger.info(f'Pulling image {self.pull_image_name}:{self.binder_image_tag} from {self.registry_url}.')
            self.docker_image = self.docker_client.images.pull(self.pull_image_name, tag=self.binder_image_tag)
        except:
            self.logger.info(f'Pulling image {self.found_image_name}:{self.binder_image_tag} from {self.registry_url}.')
            self.docker_image = self.docker_client.images.pull(self.found_image_name, tag=self.binder_image_tag)