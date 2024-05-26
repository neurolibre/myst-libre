import os
from dotenv import load_dotenv
from myst_libre.abstract_class import AbstractClass

class Authenticator(AbstractClass):
    def __init__(self):
        super().__init__()
        self._auth = {}
        self._load_auth_from_env()

    def _load_auth_from_env(self):
        load_dotenv()
        username = os.getenv('DOCKER_PRIVATE_REGISTRY_USERNAME')
        password = os.getenv('DOCKER_PRIVATE_REGISTRY_PASSWORD')

        if not username or not password:
            self._auth['username'] = None
            self._auth['password'] = None
        else:
            self._auth['username'] = username
            self._auth['password'] = password

        del os.environ['DOCKER_PRIVATE_REGISTRY_USERNAME']
        del os.environ['DOCKER_PRIVATE_REGISTRY_PASSWORD']