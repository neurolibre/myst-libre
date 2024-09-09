from myst_libre.tools import JupyterHubLocalSpawner, MystMD
from myst_libre.rees import REES
from myst_libre.builders import MystBuilder



resources = REES(dict(
            registry_url="https://binder-registry.conp.cloud",
            gh_user_repo_name = "agahkarakuzu/mriscope",
            gh_repo_commit_hash = "ae64d9ed17e6ce66ecf94d585d7b68a19a435d70",
            binder_image_tag = "489ae0eb0d08fe30e45bc31201524a6570b9b7dd"))


hub = JupyterHubLocalSpawner(resources,
                             host_data_parent_dir = "/Users/agah/Desktop/tmp/DATA",
                             host_build_source_parent_dir = '/Users/agah/Desktop/tmp',
                             container_data_mount_dir = '/home/jovyan/data',
                             container_build_source_mount_dir = '/home/jovyan')

hub.spawn_jupyter_hub()

MystBuilder(hub).build_site()
