# MyST Libre

![PyPI - Version](https://img.shields.io/pypi/v/myst-libre?style=flat&logo=python&logoColor=white&logoSize=8&labelColor=rgb(255%2C0%2C0)&color=white)

Following the [REES](https://repo2docker.readthedocs.io/en/latest/specification.html), `myst-libre` streamlines building [✨MyST articles✨](https://mystmd.org/) in containers.

* A repository containing MyST sources
* A Docker image (built by [`binderhub`](https://github.com/jupyterhub/binderhub)) in a public (or private) registry, including:
  * Dependencies to execute notebooks/markdown files in the MyST repository
  * JupyterHub (typically part of images built by `binderhub`)
* Input data required by the executable content (optional)

Given these resources, myst-libre starts a Docker container, mounts the MyST repository and data (if available), and builds a MyST publication.

> [!NOTE]
> This project was started to support publishing MyST articles as living preprints on [`NeuroLibre`](https://neurolibre.org).

## Installation

### External dependencies 

> [!IMPORTANT]
> Ensure the following prerequisites are installed:

- Node.js (For MyST)  [installation guide](https://mystmd.org/guide/installing-prerequisites)
- Docker              [installation guide](https://docs.docker.com/get-docker/)

### Install myst-libre

```
pip install myst-libre
```

**Set up environment variables:**

If you are using a private image registry, create a `.env` file in the project root and add the following:

```env
DOCKER_PRIVATE_REGISTRY_USERNAME=your_username
DOCKER_PRIVATE_REGISTRY_PASSWORD=your_password
```

## Quick Start

**Import libraries and define REES resources**

Minimal example to create a rees object:

```python
from myst_libre.tools import JupyterHubLocalSpawner, MystMD
from myst_libre.rees import REES
from myst_libre.builders import MystBuilder

rees = REES(dict(
                  registry_url="https://your-registry.io",
                  gh_user_repo_name = "owner/repository"
                  ))
```

Other optional parameters that can be passed to the REES constructor:


- `gh_repo_commit_hash`: Full SHA commit hash of the `gh_user_repo_name` repository (optional, default: latest commit)
- `binder_image_tag`: Full SHA commit hash at which a binder tag is available for the "found image name" (optional, default: latest)
- `binder_image_name_override`: Override the "found image name" whose container will be used to build the MyST article (optional, default: None)
- `dotenv`: Path to a directory containing the .env file for authentication credentials to pull images from `registry_url` (optional, default: None)
- `bh_image_prefix`: Binderhub names the images with a prefix, e.g., `<prefix>agahkarakuzu-2dmriscope-7a73fb`, typically set as `binder-`. This will be used in the regex pattern to find the "binderhub built image name" in the `registry_url`. See [reference docs](https://binderhub.readthedocs.io/en/latest/zero-to-binderhub/setup-binderhub.html) for more details. 
- `bh_project_name`: See [this issue ](https://github.com/jupyterhub/binderhub/issues/800) (optional, default: [`registry_url` without `http://` or `https://`])


Note that in this context what is meant by "prefix" is not the same as in the reference docs. (optional, default: `binder-`)

**Image Selection Order**

1. If the `myst.yml` file in the `gh_user_repo_name` repository contains `project/thebe/binder/repo`, this image is prioritized.
2. If `project/thebe/binder/repo` is not specified, the `gh_user_repo_name` is used as the image name.

Note that if (2) is the case, your build command probably should not be `myst build`, but you can still use other builders, e.g., `jupyter-book build`.

If you specify `binder_image_name_override`, it will be used as the repository name to locate the image.

This allows you to build the MyST article using a runtime from a different repository than the one specified in `gh_user_repo_name`, as defined in `myst.yml` or overridden by `binder_image_name_override`.

The `binder_image_tag` set to `latest` refers to the most recent successful build of an image that meets the specified conditions. The repository content might be more recent than the `binder_image_tag` (e.g., `gh_repo_commit_hash`), but the same binder image can be reused.

**Fetch resources and spawn JupyterHub in the respective container**

```python
hub = JupyterHubLocalSpawner(rees_resources,
                             host_build_source_parent_dir = '/tmp/myst_repos',
                             container_build_source_mount_dir = '/home/jovyan', #default
                             host_data_parent_dir = "/tmp/myst_data", #optional
                             container_data_mount_dir = '/home/jovyan/data', #optional
                             )
hub.spawn_jupyter_hub()
```

* MyST repository will be cloned at:

```
tmp/
└── myst_repos/
    └── owner/
        └── repository/
            └── full_commit_SHA_A/
                ├── myst.yml
                ├── _toc.yml
                ├── binder/
                │   ├── requirements.txt (or other REES dependencies)
                │   └── data_requirement.json (optional)
                ├── content/
                │   ├── my_notebook.ipynb
                │   └── my_myst_markdown.md
                ├── paper.md
                └── paper.bib
```

Repository will be mounted to the container as `/tmp/myst_repos/owner/repository/full_commit_SHA_A:/home/jovyan`.

* If a [`repo2data`](https://github.com/SIMEXP/Repo2Data) manifest is found in the repository, the data will be downloaded to and cached at:

```
tmp/
└── myst_data/
    └── my-dataset
```

otherwise, it can be manually defined for an existing data under `/tmp/myst_data` as follows:

```
rees_resources.dataset_name = "my-dataset"
```

In either case, data will be mounted as `/tmp/myst_data/my-dataset:/home/jovyan/data/my-dataset`. If no data is provided, this step will be skipped.

**Build your MyST article**

```python
MystBuilder(hub).build()
```

**Check out the built document**

In your terminal:

```
npx serve /tmp/myst_repos/owner/repository/full_commit_SHA_A/_build/html
```

Visit ✨`http://localhost:3000`✨.

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
