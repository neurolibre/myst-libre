from myst_libre.tools import JupyterHubLocalSpawner, MystMD
from myst_libre.rees import REES
from myst_libre.builders import MystBuilder



rees = REES(dict(
    registry_url="https://binder-registry.conp.cloud",
    gh_user_repo_name = "roboneurolibre/QC-imaging-demographics",
    gh_repo_commit_hash = "latest",
    binder_image_tag = "latest",
    dotenv = "/Users/agah/Desktop/dev/evidencepub/myst-libre",
    bh_project_name = "binder-registry.conp.cloud"
))

hub = JupyterHubLocalSpawner(rees,
                        host_build_source_parent_dir = "/Users/agah/Desktop/tmp",
                        container_build_source_mount_dir = '/home/jovyan',
                        host_data_parent_dir = "/Users/agah/Desktop/tmp/DATA",
                        container_data_mount_dir = '/home/jovyan/data')

# # This has to be called
hub_logs = hub.spawn_jupyter_hub()

builder = MystBuilder(hub=hub)
myst_logs = builder.build('--execute','--html')

print(myst_logs)