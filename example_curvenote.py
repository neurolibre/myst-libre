from myst_libre.tools import JupyterHubLocalSpawner, Curvenote
from myst_libre.rees import REES
from myst_libre.builders import CurvenoteBuilder

# Example of using CurvenoteBuilder with REES and JupyterHub integration
# Note: Make sure you have CURVENOTE_TOKEN in your .env file for authentication
rees = REES(dict(
    registry_url="https://binder-registry.conp.cloud",
    gh_user_repo_name = "agahkarakuzu/mriscope",
    dotenv = "/Users/agah/Desktop/neurolibre/myst_libre",  # Path to directory containing .env file
    bh_project_name = "binder-registry.conp.cloud"
))

hub = JupyterHubLocalSpawner(rees,
                        host_build_source_parent_dir = "/Users/agah/Desktop/tmp",
                        container_build_source_mount_dir = '/home/jovyan',
                        host_data_parent_dir = "/Users/agah/Desktop/tmp/DATA",
                        container_data_mount_dir = '/home/jovyan/data')

# Spawn the JupyterHub
hub_logs = hub.spawn_jupyter_hub()

# Create CurvenoteBuilder instance
builder = CurvenoteBuilder(hub=hub)

# Initialize Curvenote project
print("Initializing Curvenote project...")
init_logs = builder.init('--yes')
print(init_logs)

# Build the project
print("Building Curvenote project...")
build_logs = builder.build()
print(build_logs)

# Start development server (non-blocking example)
print("Starting Curvenote development server...")
start_logs = builder.start()
print(start_logs)

# Export to PDF
print("Exporting to PDF...")
pdf_logs = builder.export_pdf(template='default')
print(pdf_logs)

# Export to Jupyter Book
print("Exporting to Jupyter Book...")
jb_logs = builder.export_jupyter_book()
print(jb_logs)

# Deploy the project
print("Deploying Curvenote project...")
deploy_logs = builder.deploy('--yes')
print(deploy_logs)

# Example of using CurvenoteBuilder without JupyterHub (standalone)
print("\n--- Standalone Usage ---")
# For standalone usage, you can specify a custom .env location
standalone_builder = CurvenoteBuilder(
    build_dir="/path/to/your/project",
    dotenvloc="/path/to/directory/containing/dotenv"  # Optional: defaults to current directory
)

# Build standalone project
build_logs = standalone_builder.build()
print(build_logs)

# Note: Operations requiring authentication will automatically use CURVENOTE_TOKEN 
# from the .env file if available. Commands that work locally (like 'curvenote start')
# will work fine without a token.