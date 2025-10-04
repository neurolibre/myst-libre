from myst_libre.tools import JupyterHubLocalSpawner, Curvenote
from myst_libre.abstract_class import AbstractClass

class CurvenoteBuilder(AbstractClass):
    def __init__(self, hub=None, build_dir=None, dotenvloc='.'):
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
            # Use dotenvloc from REES if available, otherwise use provided value
            dotenvloc = getattr(self.hub.rees, 'dotenvloc', dotenvloc)
        else:
            if build_dir is None:
                raise ValueError("If 'hub' is None, 'build_dir' must be provided")
            self.build_dir = build_dir
            self.env_vars = {}
            self.hub = None

        super().__init__()
        self.curvenote_client = Curvenote(self.build_dir, self.env_vars, dotenvloc=dotenvloc)
    
    def setenv(self, key, value):
        self.env_vars[key] = value

    def build(self, *args, user=None, group=None):
        if self.hub is not None:
            self.cprint(f'Starting Curvenote build {self.hub.jh_url}','yellow')
        else:
            self.cprint(f'Starting Curvenote build no exec.','yellow')
        logs = self.curvenote_client.build(*args, user=user, group=group)

        # Check if build was successful by looking for error indicators in logs
        build_failed = logs and ('Error' in logs or 'error:' in logs.lower() or 'failed' in logs.lower())

        if not build_failed and self.hub is not None:
            # Save the successful build
            self.cprint('Build completed successfully, preserving...', 'green')
            self.hub.rees.save_successful_build()

        return logs
    
    def start(self, *args, user=None, group=None):
        if self.hub is not None:
            self.cprint(f'Starting Curvenote dev server {self.hub.jh_url}','yellow')
        else:
            self.cprint(f'Starting Curvenote dev server no exec.','yellow')
        logs = self.curvenote_client.start(*args, user=user, group=group)
        return logs
    
    def deploy(self, *args, user=None, group=None):
        if self.hub is not None:
            self.cprint(f'Deploying Curvenote project {self.hub.jh_url}','yellow')
        else:
            self.cprint(f'Deploying Curvenote project no exec.','yellow')
        logs = self.curvenote_client.deploy(*args, user=user, group=group)
        return logs
    
    def export_pdf(self, link=None, target=None, template=None, user=None, group=None):
        if self.hub is not None:
            self.cprint(f'Exporting PDF from Curvenote {self.hub.jh_url}','yellow')
        else:
            self.cprint(f'Exporting PDF from Curvenote no exec.','yellow')
        stdout_log, stderr_log = self.curvenote_client.export_pdf(link, target, template, user, group)
        
        combined_log = stdout_log
        if stderr_log:
            combined_log += "\n" + stderr_log
        return combined_log
    
    def export_jupyter_book(self, link=None, user=None, group=None):
        if self.hub is not None:
            self.cprint(f'Exporting Jupyter Book from Curvenote {self.hub.jh_url}','yellow')
        else:
            self.cprint(f'Exporting Jupyter Book from Curvenote no exec.','yellow')
        stdout_log, stderr_log = self.curvenote_client.export_jupyter_book(link, user, group)
        
        combined_log = stdout_log
        if stderr_log:
            combined_log += "\n" + stderr_log
        return combined_log
    
    def init(self, *args, user=None, group=None):
        if self.hub is not None:
            self.cprint(f'Initializing Curvenote project {self.hub.jh_url}','yellow')
        else:
            self.cprint(f'Initializing Curvenote project no exec.','yellow')
        logs = self.curvenote_client.init(*args, user=user, group=group)
        return logs
    
    def pull(self, path=None, user=None, group=None):
        if self.hub is not None:
            self.cprint(f'Pulling Curvenote content {self.hub.jh_url}','yellow')
        else:
            self.cprint(f'Pulling Curvenote content no exec.','yellow')
        logs = self.curvenote_client.pull(path, user=user, group=group)
        return logs