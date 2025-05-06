"""
docker_registry_client.py

This module contains the DockerRegistryClient class for interacting with a Docker registry.
"""

import re
import datetime
import yaml

from .rest_client import RestClient
from .authenticator import Authenticator
from .decorators import request_set_decorator

class DockerRegistryClient(Authenticator):
    """
    DockerRegistryClient

    Client for interacting with a Docker registry.
    
    Args:
        registry_url (str): URL of the Docker registry.
        gh_user_repo_name (str): GitHub user/repository name.
        auth (dict): Authentication credentials.
    """
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        
        if hasattr(self, 'dotenvloc'):
            super().__init__(self.dotenvloc)
            self.rest_client = RestClient(self.dotenvloc)
        else:
            super().__init__()
            self.rest_client = RestClient()
        
        self.found_image_name = None
        self.found_image_tags = None
        self.found_image_tags_sorted = None
        self.myst_yml_dict = None
        self.docker_images = []


    def get_token(self):
        """
        Authenticate and get a token from the Docker registry.
        
        Returns:
            bool: True if authenticated successfully, else False.
        """
        auth_url = f"{self.registry_url}/v2/"
        response = self.rest_client.get(auth_url)
        if response.status_code == 200:
            return True
        else:
            self.logger.error(f"Failed to authenticate: {response.status_code} {response.text}")
            return False

    def search_img_by_repo_name(self):
        """
        Search for a Docker image by repository name.
        
        Returns:
            bool: True if image found, else False.
        
        Assuming use in rees, TODO refactored for clarity:
            binder_image_name_override
            gh_user_repo_name 
        """
        self.get_image_list()
        if self.binder_image_name_override:
            src_name = self.binder_image_name_override
        else:
            # If not overridden, the (thebe/binder)repo in myst.yml takes precedence
            if self.get_myst_yml_as_dict():
                src_name = self.myst_yml_dict['project']['thebe']['binder']['repo']
                if src_name:
                    self.cprint(f"🥳 Using project::thebe::binder::repo from myst config to look for 🐳 in {self.registry_url}: {src_name}","light_blue")
                else:
                    # Fallback to the GitHub user/repo name
                    src_name = self.gh_user_repo_name
                    self.cprint(f"ℹ️ project::thebe::binder::repo not found in myst.yml, using GitHub {self.gh_user_repo_name} name to look for 🐳 in {self.registry_url}.","light_blue")
                    self.cprint("‼️ IMPORTANT WARNING: Myst build may succeed, but binder-specific config must be added to myst.yml to attach the built page to a proper runtime.","light_red")
                    return False
            else:
                # Well, build will most likely fail, but we can try
                self.cprint("⚠️ myst.yml not found, using GitHub user/repo name for 🐳.","light_red")
                src_name = self.gh_user_repo_name

        user_repo_formatted = src_name.replace('-', '-2d').replace('_', '-5f').replace('/', '-2d')
        if self.bh_project_name:
            pattern = f'{self.bh_project_name}/{self.bh_image_prefix}{user_repo_formatted}.*'
        else:
            pattern = f'{self.bh_image_prefix}{user_repo_formatted}.*'

        pattern = pattern.lower()
        self.cprint(f"🔍 Search pattern: {pattern}","light_blue")
        for image in self.docker_images:
            if re.match(pattern, image):
                self.found_image_name = image
                self.list_tags()
                return True
        return False

    @request_set_decorator(success_status_code=200, set_attribute="docker_images", json_key="repositories")
    def get_image_list(self):
        """
        Get the list of images from the Docker registry.
        
        Returns:
            Response: HTTP response object.
        """
        repo_url = f"{self.registry_url}/v2/_catalog"
        return self.rest_client.get(repo_url)

    @request_set_decorator(success_status_code=200, set_attribute="found_image_tags", json_key="tags")
    def list_tags(self):
        """
        List tags for the found Docker image.
        
        Returns:
            Response: HTTP response object.
        """
        tags_url = f"{self.registry_url}/v2/{self.found_image_name}/tags/list"
        return self.rest_client.get(tags_url)

    #@request_set_decorator(success_status_code=200, set_attribute="found_image_tags_sorted", json_key="tags")
    def get_tags_sorted_by_date(self):
        tags = self.list_tags()
        tag_dates = []
        for tag in tags:
            manifest_url = f"{self.registry_url}/v2/{self.found_image_name}/manifests/{tag}"
            headers = {'Accept': 'application/vnd.docker.distribution.manifest.v2+json'}
            manifest = self.rest_client.get(manifest_url, headers=headers).json()

            config_digest = manifest['config']['digest']
            config_url = f"{self.registry_url}/v2/{self.found_image_name}/blobs/{config_digest}"
            config = self.rest_client.get(config_url).json()

            created = config.get('created', None)
            if created:
                # Truncate the fractional seconds to 6 digits
                created = re.sub(r'(\.\d{6})\d+', r'\1', created)
                dt = datetime.datetime.fromisoformat(created.rstrip('Z'))
                tag_dates.append((tag, dt))
        sorted_tags = sorted(tag_dates, key=lambda x: x[1], reverse=True)
        self.found_image_tags_sorted = [tag for tag, _ in sorted_tags]
        return bool(tag_dates)

    def get_myst_yml_as_dict(self):
        """
        Get the myst.yml file as a dictionary.
        
        Returns:
            dict: The parsed myst.yml file as a dictionary.
        """
        # This is a helper function to get the myst.yml file as a dictionary
        # Maybe move it to a helper file, but this whole project needs a refactor anyway.
        # I know it makes your eyes bleed, sorry.
        user, repo = self.gh_user_repo_name.split('/')
        url = f"https://raw.githubusercontent.com/{user}/{repo}/main/myst.yml"
        response = self.rest_client.get(url)
        
        if response.status_code == 200:
            try:
                # Parse the YAML content into a dictionary
                self.myst_yml_dict = yaml.safe_load(response.text)
                return True
            except yaml.YAMLError as e:
                self.logger.error(f"Error parsing YAML: {e}")
                return False
        else:
            self.logger.error(f"Failed to fetch myst.yml: {response.status_code}")
            return False