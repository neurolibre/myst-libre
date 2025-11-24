"""
Example usage of myst-libre running inside a Docker container.

This example demonstrates how to use myst-libre when it runs in a container
and needs to spawn Jupyter containers as siblings on the host machine
(Docker-in-Docker scenario).

Usage:
    Run inside myst-libre container:
    $ python example_docker_in_docker.py

    Or via docker-compose:
    $ docker-compose run myst-libre python example_docker_in_docker.py

    Or manually with docker:
    $ docker build -t myst-libre:latest .

    WITH .env FILE (Option A):
    $ docker run -it --rm \
        -v /var/run/docker.sock:/var/run/docker.sock \
        -v /host/workspace:/workspace \
        -v /host/.env:/workspace/config/.env:ro \
        -e HOST_WORKSPACE_PATH=/host/workspace \
        myst-libre:latest \
        python example_docker_in_docker.py

    WITH ENVIRONMENT VARIABLES (Option B - recommended for CI/CD):
    $ docker run -it --rm \
        -v /var/run/docker.sock:/var/run/docker.sock \
        -v /host/workspace:/workspace \
        -e HOST_WORKSPACE_PATH=/host/workspace \
        -e DOCKER_PRIVATE_REGISTRY_USERNAME=your_username \
        -e DOCKER_PRIVATE_REGISTRY_PASSWORD=your_password \
        -e CURVENOTE_TOKEN=your_token \
        myst-libre:latest \
        python example_docker_in_docker.py

Docker Run Command Explanation:
    -v /var/run/docker.sock:/var/run/docker.sock
        Mounts the host Docker daemon socket so the container can spawn
        other containers on the host.

    -v /host/workspace:/workspace
        Mounts a directory from the host at /workspace inside the container.
        This provides persistent storage for cloned repositories and data.
        Replace /host/workspace with your actual path on the host.

    OPTION A - Mount .env file:
    -v /host/.env:/workspace/config/.env:ro
        Mounts the .env file from the host into the container.
        The :ro flag makes it read-only (safer for secrets).
        Replace /host/.env with your actual .env file location.
        This keeps secrets OUT of the Docker image!

    OPTION B - Use environment variables (no .env file needed):
    -e DOCKER_PRIVATE_REGISTRY_USERNAME=your_username
    -e DOCKER_PRIVATE_REGISTRY_PASSWORD=your_password
    -e CURVENOTE_TOKEN=your_token
        Pass credentials as environment variables.
        Works great for CI/CD pipelines.
        No files needed - secrets never enter the image.

    -e HOST_WORKSPACE_PATH=/host/workspace
        Environment variable telling myst-libre the host path corresponding
        to /workspace. This enables correct path translation when spawning
        the Jupyter container.
"""

import os
from pathlib import Path
from myst_libre.tools import JupyterHubLocalSpawner
from myst_libre.rees import REES
from myst_libre.builders import MystBuilder


def main():
    """Run myst-libre build in Docker-in-Docker mode."""

    # Get the host workspace path from environment variable
    # This is CRITICAL for Docker-in-Docker scenarios
    host_workspace_path = os.environ.get('HOST_WORKSPACE_PATH')

    if not host_workspace_path:
        raise EnvironmentError(
            "HOST_WORKSPACE_PATH environment variable is not set.\n"
            "When running in Docker-in-Docker mode, you must provide\n"
            "the host path corresponding to your container workspace.\n\n"
            "Example:\n"
            "  docker run -e HOST_WORKSPACE_PATH=/home/user/workspace ...\n"
            "  -v /home/user/workspace:/workspace ..."
        )

    print(f"✓ Using host workspace path: {host_workspace_path}")

    # ========================================================================
    # Handle credentials: .env file OR environment variables
    # ========================================================================
    # You have two options for passing secrets to the container:
    #
    # Option A: Mount .env file at runtime (recommended for file-based configs)
    #   - More secure: keeps .env out of Docker image
    #   - Mount as read-only: -v /path/to/.env:/workspace/config/.env:ro
    #
    # Option B: Pass environment variables directly (recommended for CI/CD)
    #   - docker run -e DOCKER_PRIVATE_REGISTRY_USERNAME=user ...
    #   - docker run -e DOCKER_PRIVATE_REGISTRY_PASSWORD=pass ...
    #   - docker run -e CURVENOTE_TOKEN=token ...
    #   - No files needed, secrets stay out of images
    #
    # The Authenticator class uses python-dotenv which handles both:
    # - load_dotenv() loads from .env file if it exists
    # - os.getenv() picks up environment variables set in the container
    # - Environment variables take precedence over .env file

    env_path = Path("/workspace/config/.env")
    has_env_file = env_path.exists()

    # Check if credentials are available via environment variables
    has_env_vars = bool(
        os.getenv('DOCKER_PRIVATE_REGISTRY_USERNAME') or
        os.getenv('CURVENOTE_TOKEN')
    )

    if has_env_file:
        print(f"✓ Using credentials from .env file at {env_path}")
    elif has_env_vars:
        print("✓ Using credentials from environment variables")
    else:
        print(
            "⚠ WARNING: No credentials found (neither .env file nor environment variables)\n"
            "\n"
            "If you need private Docker registry access, provide credentials via:\n"
            "\n"
            "Option A: Mount .env file\n"
            "  docker run -v /path/to/.env:/workspace/config/.env:ro ...\n"
            "\n"
            "Option B: Set environment variables\n"
            "  docker run \\\n"
            "    -e DOCKER_PRIVATE_REGISTRY_USERNAME=your_username \\\n"
            "    -e DOCKER_PRIVATE_REGISTRY_PASSWORD=your_password \\\n"
            "    -e CURVENOTE_TOKEN=your_token \\\n"
            "    ...\n"
            "\n"
            "Continuing without private registry access..."
        )

    # ========================================================================
    # Configure REES (Reproducible Execution Environment Specification)
    # ========================================================================
    # This configuration is identical to the local example (example2.py)
    # The difference is in the JupyterHubLocalSpawner configuration below

    rees = REES(dict(
        registry_url="https://binder-registry.conp.cloud",
        gh_user_repo_name="roboneurolibre/QC-imaging-demographics",
        gh_repo_commit_hash="latest",
        binder_image_tag="latest",
        # Note: This path is from the container's perspective
        dotenv="/workspace/config",
        bh_project_name="binder-registry.conp.cloud"
    ))

    # ========================================================================
    # Configure JupyterHub spawner with Docker-in-Docker support
    # ========================================================================
    # Key difference from local mode: We pass host_path_prefix and
    # container_path_prefix to enable path translation

    hub = JupyterHubLocalSpawner(
        rees,
        # These paths are from the myst-libre container's perspective
        host_build_source_parent_dir="/workspace/builds",
        container_build_source_mount_dir='/home/jovyan',
        host_data_parent_dir="/workspace/DATA",
        container_data_mount_dir='/home/jovyan/data',

        # Docker-in-Docker configuration
        # host_path_prefix: The actual host path that corresponds to /workspace
        # container_path_prefix: The container path to translate from
        host_path_prefix=host_workspace_path,
        container_path_prefix="/workspace",

        # Enable Docker-in-Docker networking fix:
        # When True, uses the spawned Jupyter container's name instead of localhost.
        # This is REQUIRED for proper networking when myst-libre runs inside a container
        # and needs to execute notebooks (--execute flag) in sibling Jupyter containers.
        enable_dind=True
    )

    print("✓ JupyterHub spawner configured")

    # ========================================================================
    # Spawn Jupyter container (sibling, not child)
    # ========================================================================
    # The spawned container is a SIBLING container on the host, not a child
    # of the myst-libre container. It communicates with the host Docker daemon.

    print("Spawning Jupyter container...")
    hub_logs = hub.spawn_jupyter_hub()

    # Print spawn status
    for log in hub_logs:
        print(log)

    print("✓ Jupyter container spawned successfully")

    # ========================================================================
    # Build MyST project with execution
    # ========================================================================
    # MyST CLI runs inside the myst-libre container
    # But it connects to Jupyter running in the sibling container via HTTP

    print("\nBuilding MyST project...")
    builder = MystBuilder(hub=hub)

    myst_logs = builder.build('--execute', '--html', '--keep-host','debug')

    print("\n" + "="*70)
    print("BUILD OUTPUT")
    print("="*70)
    print(myst_logs)
    print("="*70)

    print("\n✓ Build completed successfully")

    # ========================================================================
    # Cleanup
    # ========================================================================
    # CRITICAL: Stop the Jupyter container and clean up resources
    print("\n 🧹 Cleaning up Jupyter container...")
    try:
        hub.cleanup()
        print("✅ Jupyter container terminated")
    except Exception as e:
        print(f"⚠️ Warning during cleanup: {e}")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"Error: {e}")
        exit(1)
