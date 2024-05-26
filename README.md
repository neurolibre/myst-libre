
# MyST Libre

![PyPI - Version](https://img.shields.io/pypi/v/myst-libre?style=flat&logo=python&logoColor=white&logoSize=8&labelColor=rgb(255%2C0%2C0)&color=white)

## JupyterHub in Docker for MyST

A small library to manage reproducible execution environments using Docker and JupyterHub 
to build MyST articles in containers.

## Table of Contents

- [Myst Libre](#myst-libre)
  - [Table of Contents](#table-of-contents)
  - [Installation](#installation)
  - [Usage](#usage)
    - [Authentication](#authentication)
    - [Docker Registry Client](#docker-registry-client)
    - [Build Source Manager](#build-source-manager)
    - [JupyterHub Local Spawner](#jupyterhub-local-spawner)
    - [MyST Markdown Client](#myst-markdown-client)
  - [Module and Class Descriptions](#module-and-class-descriptions)
  - [Contributing](#contributing)
  - [License](#license)

## Installation

1. **Clone the repository:**
    ```sh
    git clone https://github.com/yourusername/myst_libre.git
    cd myst_libre
    ```

2. **Create a virtual environment:**
    ```sh
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3. **Install the required packages:**
    ```sh
    pip install -r requirements.txt
    ```

4. **Set up environment variables:**
    Create a `.env` file in the project root and add the following:
    ```env
    DOCKER_PRIVATE_REGISTRY_USERNAME=your_username
    DOCKER_PRIVATE_REGISTRY_PASSWORD=your_password
    ```

## External requirements

- Node.js (For MyST)
- Docker 

## Quick Start

```python
from myst_libre.rees import REES
from myst_libre.tools import JupyterHubLocalSpawner

resources = REES(dict(registry_url="https://binder-registry.conp.cloud",
                      gh_user_repo_name = "agahkarakuzu/mriscope",
                      gh_repo_commit_hash = "6d3f64da214441bbb55b2005234fd4fd745fb372",
                      binder_image_tag = "489ae0eb0d08fe30e45bc31201524a6570b9b7dd"))

hub = JupyterHubLocalSpawner(resources,
                             host_data_parent_dir = "~/neurolibre/mriscope/data",
                             host_build_source_parent_dir = '~/Desktop/tmp',
                             container_data_mount_dir = '/home/jovyan/data',
                             container_build_source_mount_dir = '/home/jovyan')

hub.spawn_jupyter_hub()
```
## Usage

### Authentication

The `Authenticator` class handles loading authentication credentials from environment variables.

```python
from myst_libre.tools.authenticator import Authenticator

auth = Authenticator()
print(auth._auth)
```


### Docker Registry Client

The DockerRegistryClient class provides methods to interact with a Docker registry.

```python
from myst_libre.tools.docker_registry_client import DockerRegistryClient

client = DockerRegistryClient(registry_url='https://my-registry.example.com', gh_user_repo_name='user/repo')
token = client.get_token()
print(token)
```

### Build Source Manager

The BuildSourceManager class manages source code repositories.

```python
from myst_libre.tools.build_source_manager import BuildSourceManager

manager = BuildSourceManager(gh_user_repo_name='user/repo', gh_repo_commit_hash='commit_hash')
manager.git_clone_repo('/path/to/clone')
project_name = manager.get_project_name()
print(project_name)
```

## Module and Class Descriptions

### AbstractClass
**Description**: Provides basic logging functionality and colored printing capabilities.

### Authenticator
**Description**: Handles authentication by loading credentials from environment variables.  
**Inherited from**: AbstractClass  
**Inputs**: Environment variables `DOCKER_PRIVATE_REGISTRY_USERNAME` and `DOCKER_PRIVATE_REGISTRY_PASSWORD`

### RestClient
**Description**: Provides a client for making REST API calls.  
**Inherited from**: Authenticator

### DockerRegistryClient
**Description**: Manages interactions with a Docker registry.  
**Inherited from**: Authenticator  
**Inputs**:
- `registry_url`: URL of the Docker registry
- `gh_user_repo_name`: GitHub user/repository name
- `auth`: Authentication credentials

### BuildSourceManager
**Description**: Manages source code repositories.  
**Inherited from**: AbstractClass  
**Inputs**:
- `gh_user_repo_name`: GitHub user/repository name
- `gh_repo_commit_hash`: Commit hash of the repository

### JupyterHubLocalSpawner
**Description**: Manages JupyterHub instances locally.  
**Inherited from**: AbstractClass  
**Inputs**:
- `rees`: Instance of the REES class
- `registry_url`: URL of the Docker registry
- `gh_user_repo_name`: GitHub user/repository name
- `auth`: Authentication credentials
- `binder_image_tag`: Docker image tag
- `build_src_commit_hash`: Commit hash of the repository
- `container_data_mount_dir`: Directory to mount data in the container
- `container_build_source_mount_dir`: Directory to mount build source in the container
- `host_data_parent_dir`: Host directory for data
- `host_build_source_parent_dir`: Host directory for build source

### MystMD
**Description**: Manages MyST markdown operations such as building and converting files.  
**Inherited from**: AbstractClass  
**Inputs**:
- `build_dir`: Directory where the build will take place
- `env_vars`: Environment variables needed for the build process
- `executable`: Name of the MyST executable (default is 'myst')
