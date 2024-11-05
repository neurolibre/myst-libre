from myst_libre.tools import JupyterHubLocalSpawner, MystMD
from myst_libre.abstract_class import AbstractClass

class MystBuilder(AbstractClass):
    def __init__(self, hub=None, build_dir=None):
        if hub is not None:
            if not isinstance(hub, JupyterHubLocalSpawner):
                raise TypeError(f"Expected 'hub' to be an instance of JupyterHubLocalSpawner, got {type(hub).__name__} instead")
            self.hub = hub
            self.env_vars = {
                "JUPYTER_BASE_URL": f"{self.hub.jh_url}",
                "JUPYTER_TOKEN": f"{self.hub.jh_token}",
                "port": f"{self.hub.port}"
            }
            self.build_dir = self.hub.rees.build_dir
        else:
            if build_dir is None:
                raise ValueError("If 'hub' is None, 'build_dir' must be provided")
            self.build_dir = build_dir
            self.env_vars = {}
            self.hub = None

        super().__init__()
        self.myst_client = MystMD(self.build_dir, self.env_vars)
    
    def setenv(self,key,value):
        self.env_vars[key] = value

    def build(self,*args):
        if self.hub is not None:
            self.cprint(f'Starting MyST build {self.hub.jh_url}','yellow')
        else:
            self.cprint(f'Starting MyST build no exec.','yellow')
        self.myst_client.build('build',*args)