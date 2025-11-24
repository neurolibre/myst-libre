"""
naming.py

BinderHub image naming utilities following BinderHub conventions.
"""

from typing import Optional
from ..constants import BINDERHUB_CHAR_ENCODING


class BinderHubNaming:
    """
    Utilities for encoding and building BinderHub-compliant image names.

    BinderHub uses specific character encoding for repository names:
    - '-' becomes '-2d'
    - '_' becomes '-5f'
    - '/' becomes '-2d'
    """

    @staticmethod
    def encode_repo_name(repo_name: str) -> str:
        """
        Encode repository name following BinderHub conventions.

        Args:
            repo_name: Repository name (e.g., 'owner/repo-name')

        Returns:
            Encoded repository name (e.g., 'owner-2drepo-2dname')

        Example:
            >>> BinderHubNaming.encode_repo_name('user/my-repo')
            'user-2dmy-2drepo'
        """
        encoded = repo_name
        for char, encoding in BINDERHUB_CHAR_ENCODING.items():
            encoded = encoded.replace(char, encoding)
        return encoded.lower()

    @staticmethod
    def build_image_name(
        repo_name: str,
        prefix: str = 'binder-',
        project: Optional[str] = None
    ) -> str:
        """
        Build full BinderHub image name.

        Args:
            repo_name: Repository name to encode
            prefix: Image prefix (default: 'binder-')
            project: Optional project name to prepend

        Returns:
            Full image name

        Example:
            >>> BinderHubNaming.build_image_name('user/repo', project='myproject')
            'myproject/binder-user-2drepo'
        """
        encoded = BinderHubNaming.encode_repo_name(repo_name)
        image_name = f"{prefix}{encoded}"

        if project:
            return f"{project}/{image_name}"
        return image_name

    @staticmethod
    def build_search_pattern(
        repo_name: str,
        prefix: str = 'binder-',
        project: Optional[str] = None
    ) -> str:
        """
        Build regex search pattern for BinderHub images.

        Args:
            repo_name: Repository name to encode
            prefix: Image prefix (default: 'binder-')
            project: Optional project name to prepend

        Returns:
            Regex pattern for matching images

        Example:
            >>> BinderHubNaming.build_search_pattern('user/repo', project='proj')
            'proj/binder-user-2drepo.*'
        """
        base_name = BinderHubNaming.build_image_name(repo_name, prefix, project)
        return f"{base_name}.*"
