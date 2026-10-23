"""
naming.py

BinderHub image naming utilities following BinderHub conventions.
"""

import hashlib
import re
from typing import Optional
from ..constants import (
    BINDERHUB_CHAR_ENCODING,
    BINDERHUB_HASH_LENGTH,
    BINDERHUB_NAME_LIMIT,
)


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
    def build_slug(repo_name: str) -> str:
        """
        Build the BinderHub build slug for a repository.

        BinderHub joins the owner and repository with '-' (not '/') and keeps
        the original casing. The slug is what gets hashed, so casing matters
        here even though the final image name is lowercased.

        Args:
            repo_name: Repository name (e.g., 'owner/My-Repo') or bare URL

        Returns:
            Build slug (e.g., 'owner-My-Repo')

        Example:
            >>> BinderHubNaming.build_slug('roboneurolibre/Neurolibre-Photon')
            'roboneurolibre-Neurolibre-Photon'
        """
        parts = [p for p in repo_name.rstrip('/').split('/') if p]
        return '-'.join(parts[-2:]) if len(parts) >= 2 else repo_name

    @staticmethod
    def slug_hash(repo_name: str) -> str:
        """
        Compute the short sha256 digest BinderHub appends to image names.

        The digest is taken over the case-sensitive build slug, which is why
        'owner/My-Repo' and 'owner/my-repo' produce two distinct images that
        share a prefix and differ only in this suffix.

        Args:
            repo_name: Repository name (e.g., 'owner/My-Repo')

        Returns:
            First BINDERHUB_HASH_LENGTH hex chars of sha256(build_slug)

        Example:
            >>> BinderHubNaming.slug_hash(
            ...     'roboneurolibre/Neurolibre-Photon-Number-Classification')
            '088418'
        """
        slug = BinderHubNaming.build_slug(repo_name)
        return hashlib.sha256(slug.encode('utf-8')).hexdigest()[:BINDERHUB_HASH_LENGTH]

    @staticmethod
    def build_exact_image_name(
        repo_name: str,
        prefix: str = 'binder-',
        project: Optional[str] = None
    ) -> str:
        """
        Build the exact BinderHub image name, including the hash suffix.

        Unlike build_image_name, this reproduces the complete name BinderHub
        would publish, so a lookup can distinguish images that differ only in
        the casing of the source repository.

        Args:
            repo_name: Repository name to encode
            prefix: Image prefix (default: 'binder-')
            project: Optional project name to prepend

        Returns:
            Full image name with hash suffix

        Example:
            >>> BinderHubNaming.build_exact_image_name(
            ...     'roboneurolibre/Neurolibre-Photon-Number-Classification')
            'binder-roboneurolibre-2dneurolibre-2dphoton-2dnumber-2dclassification-088418'
        """
        slug = BinderHubNaming.build_slug(repo_name)
        digest = BinderHubNaming.slug_hash(repo_name)

        # BinderHub truncates the encoded body so name + '-' + hash fits the limit
        body_limit = BINDERHUB_NAME_LIMIT - len(prefix) - BINDERHUB_HASH_LENGTH - 1
        body = BinderHubNaming.encode_repo_name(slug)[:body_limit]

        image_name = f"{prefix}{body}-{digest}"

        if project:
            return f"{project}/{image_name}"
        return image_name

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

        The pattern is anchored to exactly one trailing hash segment. A bare
        '.*' tail would also match repositories whose names merely extend this
        one ('repo' vs 'repo-extended'), since '-' encodes to '-2d' and leaves
        the shorter name a valid prefix of the longer.

        Returns:
            Regex pattern for matching images

        Example:
            >>> BinderHubNaming.build_search_pattern('user/repo', project='proj')
            'proj/binder\\\\-user\\\\-2drepo-[0-9a-f]{6}$'
        """
        base_name = BinderHubNaming.build_image_name(repo_name, prefix, project)
        return f"{re.escape(base_name)}-[0-9a-f]{{{BINDERHUB_HASH_LENGTH}}}$"
