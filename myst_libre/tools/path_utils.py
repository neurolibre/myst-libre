"""Path utilities for Docker-in-Docker scenarios.

This module provides utilities for translating container paths to host paths,
which is necessary when myst-libre runs inside a Docker container and spawns
sibling containers on the host machine.
"""

from pathlib import Path
from typing import Optional, Union


def translate_container_path_to_host(
    container_path: Union[str, Path],
    host_path_prefix: str,
    container_path_prefix: str = "/",
) -> Path:
    """Translate a path from container context to host context.

    When myst-libre runs inside a container, paths visible to it are relative to
    the container's filesystem. However, when spawning sibling containers via the
    Docker daemon, volume mounts must use host filesystem paths.

    This function translates paths by replacing the container prefix with the
    corresponding host prefix.

    Args:
        container_path: The path as seen from inside the myst-libre container.
        host_path_prefix: The absolute host path that corresponds to the
            container_path_prefix. Example: /home/user/workspace
        container_path_prefix: The container prefix to replace. Default: "/"
            (root of container filesystem).

    Returns:
        The translated path as a Path object, suitable for use in Docker volume
        mounts.

    Example:
        If myst-libre container mounts /home/user/workspace as /workspace:
        >>> translate_container_path_to_host(
        ...     "/workspace/builds/repo",
        ...     host_path_prefix="/home/user/workspace",
        ...     container_path_prefix="/workspace"
        ... )
        PosixPath('/home/user/workspace/builds/repo')
    """
    container_path = Path(container_path)
    container_prefix = Path(container_path_prefix)

    # Check if the container_path starts with the container_path_prefix
    try:
        relative_path = container_path.relative_to(container_prefix)
    except ValueError:
        # If container_path doesn't start with container_path_prefix,
        # return original path (assume it's already a host path)
        return container_path

    # Construct the host path by joining host prefix with relative path
    host_path = Path(host_path_prefix) / relative_path

    return host_path


def should_translate_paths(host_path_prefix: Optional[str]) -> bool:
    """Determine whether path translation should be applied.

    Args:
        host_path_prefix: The host path prefix from configuration.

    Returns:
        True if path translation should be applied (host_path_prefix is set).
    """
    return host_path_prefix is not None and host_path_prefix.strip() != ""
