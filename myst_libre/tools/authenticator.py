import os
from dotenv import load_dotenv
from myst_libre.abstract_class import AbstractClass

class Authenticator(AbstractClass):
    def __init__(self,dotenvloc = '.'):
        super().__init__()
        self._auth = {}
        self.dotenvloc = dotenvloc
        self._load_auth_from_env()

    def _load_auth_from_env(self):
        
        load_dotenv(os.path.join(self.dotenvloc,'.env'))

        username = os.getenv('DOCKER_PRIVATE_REGISTRY_USERNAME')
        password = os.getenv('DOCKER_PRIVATE_REGISTRY_PASSWORD')

        if not username or not password:
            self._auth['username'] = None
            self._auth['password'] = None
        else:
            self._auth['username'] = username
            self._auth['password'] = password

        # Clean up environment variables for security
        env_vars_to_clean = ['DOCKER_PRIVATE_REGISTRY_USERNAME', 'DOCKER_PRIVATE_REGISTRY_PASSWORD']
        for var in env_vars_to_clean:
            try:
                del os.environ[var]
                self.logger.debug(f"Cleaned up environment variable: {var}")
            except KeyError:
                # Variable wasn't set, which is fine
                self.logger.debug(f"Environment variable {var} was not set")
            except Exception as e:
                # Log but don't fail - this is cleanup
                self.logger.warning(f"Could not clean up environment variable {var}: {e}") 
