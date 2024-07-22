"""
docker_registry_client.py

This module contains the DockerRegistryClient class for interacting with a Docker registry.
"""

import re
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

        self.registry_url_bare = self.registry_url.replace("http://", "").replace("https://", "")
        self.found_image_name = None
        self.found_image_tags = None
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
        """
        self.get_image_list()
        user_repo_formatted = self.gh_user_repo_name.replace('-', '-2d').replace('_', '-5f').replace('/', '-2d')
        pattern = f'{self.registry_url_bare}/binder-{user_repo_formatted}.*'
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
