"""
constants.py

Configuration constants and default values for myst-libre.
"""

from typing import Tuple

# Git Configuration
DEFAULT_BRANCH = 'main'
DEFAULT_GIT_PROVIDER = 'https://github.com'

# Docker Configuration
DEFAULT_BINDER_IMAGE_PREFIX = 'binder-'
DEFAULT_IMAGE_TAG = 'latest'

# Container Configuration
DEFAULT_PORT_RANGE: Tuple[int, int] = (8888, 10000)
DEFAULT_CONTAINER_STOP_TIMEOUT = 10

# Resource Limits (for "max" mode)
RESOURCE_RESERVE_CPUS = 1          # CPU cores to reserve for host
RESOURCE_RESERVE_MEMORY_GB = 2     # GB of RAM to reserve for host
MIN_CONTAINER_CPUS = 1             # Floor for container CPU allocation
MIN_CONTAINER_MEMORY_GB = 2        # Floor for container memory allocation

# JupyterHub Configuration
DEFAULT_JUPYTER_PORT = 8888
TOKEN_DIGEST_SIZE = 20

# Build Configuration
DEFAULT_LOG_TAIL_LINES = 100
BUILD_CACHE_DIR = '_build'
DATA_DIR = 'data'

# File Paths
MYST_CONFIG_FILE = 'myst.yml'
DATA_REQUIREMENT_FILE = 'binder/data_requirement.json'
GIT_EXCLUDE_FILE = '.git/info/exclude'
LATEST_BUILD_MARKER = 'latest.txt'

# Build Directories
LATEST_DIR_NAME = 'latest'

# BinderHub Naming Conventions
BINDERHUB_CHAR_ENCODING = {
    '-': '-2d',
    '_': '-5f',
    '/': '-2d'
}

# BinderHub appends a short sha256 of the build slug to every image name. The
# digest is taken over the *case-sensitive* slug, but the final name is
# lowercased, so 'owner/My-Repo' and 'owner/my-repo' yield identical prefixes
# and different suffixes. See BinderHubNaming.slug_hash.
BINDERHUB_HASH_LENGTH = 6
BINDERHUB_NAME_LIMIT = 255

# Commit Info Defaults (for overridden images)
DEFAULT_OVERRIDE_IMAGE_DATE = "2024-11-20"  # ISO format for datetime.fromisoformat()
DEFAULT_OVERRIDE_IMAGE_MESSAGE = "Base runtime from myst-libre"
