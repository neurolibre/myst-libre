from myst_libre.tools import JupyterHubLocalSpawner, MystMD
from myst_libre.rees import REES
from myst_libre.builders import MystBuilder



rees = REES(dict(
    registry_url="https://binder-registry.conp.cloud",
    gh_user_repo_name = "agahkarakuzu/mriscope",
    dotenv = "/Users/agah/Desktop/neurolibre/myst_libre",
    bh_project_name = "binder-registry.conp.cloud"
    ))     


# Under the hood it looks like this:
# if rees.search_img_by_repo_name():
#     print("🐳 Image name:",rees.found_image_name)
#     print("🏷️ Unsorted tags:",rees.found_image_tags)

# if rees.get_tags_sorted_by_date():
#     print("🏷️ Sorted image tags:",rees.found_image_tags_sorted)

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