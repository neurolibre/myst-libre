from myst_libre.tools import JupyterHubLocalSpawner, MystMD
from myst_libre.abstract_class import AbstractClass

class MystBuilder(AbstractClass):
    def __init__(self, hub):
        if not isinstance(hub, JupyterHubLocalSpawner):
            raise TypeError(f"Expected 'hub' to be an instance of JupyterHubLocalSpawner, got {type(hub).__name__} instead")
        super().__init__()
        self.env_vars = {}
        self.build_dir = ""
        self.hub = hub
        self.env_vars = {"JUPYTER_BASE_URL":f"{self.hub.jh_url}",
                         "JUPYTER_TOKEN":f"{self.hub.jh_token}",
                         "port":f"{self.hub.port}"
                         }
        self.myst_client = MystMD(hub.rees.build_dir, self.env_vars)

    def build(self):
        self.cprint(f'Starting MyST build {self.hub.jh_url}','yellow')
        self.myst_client.build()