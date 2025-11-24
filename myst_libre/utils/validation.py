"""
validation.py

Input validation utilities for URLs, paths, and other inputs.
"""

import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


def validate_url(url: str, allowed_schemes: Optional[list] = None) -> bool:
    """
    Validate a URL string.

    Args:
        url: URL string to validate
        allowed_schemes: List of allowed schemes (default: ['http', 'https'])

    Returns:
        True if valid, False otherwise

    Example:
        >>> validate_url("https://github.com/user/repo")
        True
        >>> validate_url("ftp://example.com")
        False
    """
    if allowed_schemes is None:
        allowed_schemes = ['http', 'https']

    if not url or not isinstance(url, str):
        return False

    try:
        result = urlparse(url)
        return all([
            result.scheme in allowed_schemes,
            result.netloc,
            # Ensure no dangerous characters
            not any(char in url for char in ['\x00', '\n', '\r'])
        ])
    except (ValueError, AttributeError):
        return False


def sanitize_url(url: str) -> str:
    """
    Sanitize a URL by removing dangerous characters and normalizing.

    Args:
        url: URL to sanitize

    Returns:
        Sanitized URL string

    Raises:
        ValueError: If URL is invalid after sanitization
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL must be a non-empty string")

    # Remove whitespace and null bytes
    sanitized = url.strip().replace('\x00', '').replace('\n', '').replace('\r', '')

    # Validate the sanitized URL
    if not validate_url(sanitized):
        raise ValueError(f"Invalid URL after sanitization: {sanitized}")

    return sanitized


def validate_github_repo(repo_name: str) -> bool:
    """
    Validate a GitHub repository name in the format 'user/repo'.

    Args:
        repo_name: Repository name to validate

    Returns:
        True if valid, False otherwise

    Example:
        >>> validate_github_repo("octocat/Hello-World")
        True
        >>> validate_github_repo("invalid repo")
        False
    """
    if not repo_name or not isinstance(repo_name, str):
        return False

    # GitHub repo pattern: user/repo where both parts are alphanumeric with hyphens/underscores
    pattern = r'^[a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+$'
    return bool(re.match(pattern, repo_name))


def validate_path(
    path: str,
    must_exist: bool = False,
    must_be_file: bool = False,
    must_be_dir: bool = False,
    allow_absolute_only: bool = False
) -> bool:
    """
    Validate a file system path.

    Args:
        path: Path string to validate
        must_exist: If True, path must exist on filesystem
        must_be_file: If True, path must be a file
        must_be_dir: If True, path must be a directory
        allow_absolute_only: If True, only absolute paths are valid

    Returns:
        True if valid, False otherwise

    Example:
        >>> validate_path("/tmp/test.txt", must_exist=False)
        True
        >>> validate_path("../../../etc/passwd", allow_absolute_only=True)
        False
    """
    if not path or not isinstance(path, str):
        return False

    try:
        path_obj = Path(path)

        # Check for path traversal attempts
        if '..' in path:
            # Allow .. in paths but check if it's trying to escape
            resolved = path_obj.resolve()
            if allow_absolute_only and not resolved.is_absolute():
                return False

        # Check absolute path requirement
        if allow_absolute_only and not path_obj.is_absolute():
            return False

        # Check existence requirements
        if must_exist and not path_obj.exists():
            return False

        if must_be_file:
            if must_exist and not path_obj.is_file():
                return False
        elif must_be_dir:
            if must_exist and not path_obj.is_dir():
                return False

        # Check for null bytes and other dangerous characters
        if '\x00' in path:
            return False

        return True

    except (ValueError, OSError):
        return False


def sanitize_path(path: str, resolve: bool = True) -> Path:
    """
    Sanitize a file system path.

    Args:
        path: Path to sanitize
        resolve: If True, resolve to absolute path

    Returns:
        Sanitized Path object

    Raises:
        ValueError: If path is invalid
    """
    if not path or not isinstance(path, str):
        raise ValueError("Path must be a non-empty string")

    # Remove null bytes and other dangerous characters
    sanitized = path.replace('\x00', '')

    if not sanitized:
        raise ValueError("Path is empty after sanitization")

    try:
        path_obj = Path(sanitized)
        if resolve:
            path_obj = path_obj.resolve()
        return path_obj
    except (ValueError, OSError) as e:
        raise ValueError(f"Invalid path: {e}") from e


def validate_docker_image_name(image_name: str) -> bool:
    """
    Validate a Docker image name.

    Args:
        image_name: Docker image name to validate

    Returns:
        True if valid, False otherwise

    Example:
        >>> validate_docker_image_name("ubuntu:latest")
        True
        >>> validate_docker_image_name("invalid image name!")
        False
    """
    if not image_name or not isinstance(image_name, str):
        return False

    # Docker image naming rules:
    # - lowercase letters, digits, separators (., -, _)
    # - optional tag after :
    # - optional registry prefix
    pattern = r'^(?:[a-z0-9]+(?:[._-][a-z0-9]+)*/)*[a-z0-9]+(?:[._-][a-z0-9]+)*(?::[a-z0-9]+(?:[._-][a-z0-9]+)*)?$'
    return bool(re.match(pattern, image_name.lower()))


def validate_port(port: int, min_port: int = 1, max_port: int = 65535) -> bool:
    """
    Validate a network port number.

    Args:
        port: Port number to validate
        min_port: Minimum allowed port (default: 1)
        max_port: Maximum allowed port (default: 65535)

    Returns:
        True if valid, False otherwise

    Example:
        >>> validate_port(8080)
        True
        >>> validate_port(99999)
        False
    """
    if not isinstance(port, int):
        return False

    return min_port <= port <= max_port
