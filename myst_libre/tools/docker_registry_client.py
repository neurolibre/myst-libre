"""
docker_registry_client.py

Refactored DockerRegistryClient for interacting with Docker registries.
"""

import re
import datetime
import yaml
from typing import Optional, List, Dict, Tuple
from pathlib import Path
from urllib.parse import urljoin

from ..abstract_class import AbstractClass
from ..models import REESConfig
from ..exceptions import DockerRegistryError, ImageNotFoundError
from ..utils import BinderHubNaming
from ..utils.retry import retry_github_api
from ..constants import MYST_CONFIG_FILE, CATALOG_PAGE_SIZE
from .rest_client import RestClient
from .decorators import request_set_decorator


class DockerRegistryClient(AbstractClass):
    """
    Client for interacting with Docker V2 registries.

    Handles image discovery, tag management, and registry authentication.
    """

    def __init__(self, config: REESConfig, dotenvloc: str = '.'):
        """
        Initialize Docker registry client.

        Args:
            config: REES configuration
            dotenvloc: Path to .env file for authentication
        """
        super().__init__()
        self.config = config
        self.rest_client = RestClient(dotenvloc)

        # Search results
        self.found_image_name: Optional[str] = None
        self.found_image_tags: Optional[List[str]] = None
        self.found_image_tags_sorted: Optional[List[str]] = None
        self.myst_yml_dict: Optional[Dict] = None
        self.docker_images: List[str] = []

    def get_token(self) -> bool:
        """
        Authenticate and get a token from the Docker registry.

        Returns:
            True if authenticated successfully

        Raises:
            DockerRegistryError: If authentication fails
        """
        auth_url = f"{self.config.registry_url}/v2/"
        response = self.rest_client.get(auth_url)

        if response.status_code == 200:
            return True
        else:
            error_msg = f"Failed to authenticate: {response.status_code} {response.text}"
            self.logger.error(error_msg)
            raise DockerRegistryError(error_msg)

    def search_image_by_repo_name(self) -> bool:
        """
        Search for a Docker image by repository name.

        Uses the following priority for determining the repository name:
        1. binder_image_name_override (explicit override)
        2. project.thebe.binder.repo from myst.yml
        3. project.github.repo from myst.yml
        4. gh_user_repo_name (fallback)

        Returns:
            True if image found

        Raises:
            ImageNotFoundError: If no matching image is found
        """
        # Determine source repository name
        src_name = self._determine_source_repo_name()

        # Preferred: reproduce the exact name BinderHub would publish, hash
        # suffix included. Images built from differently-cased spellings of the
        # same repo share a prefix and differ only in that suffix, so an exact
        # match is the only way to pick the right one.
        exact_name = BinderHubNaming.build_exact_image_name(
            src_name,
            self.config.bh_image_prefix,
            self.config.bh_project_name
        ).lower()

        self.cprint(f"🔍 Exact image name: {exact_name}", "light_blue")

        # Ask the registry about that one repository instead of looking it up in
        # the catalog listing: the listing is paginated and a repository past
        # the first page would otherwise read as missing.
        tags = self._fetch_tags(exact_name)
        if tags is not None:
            self.found_image_name = exact_name
            self.found_image_tags = tags
            return True

        # Fallback: prefix match, anchored to a single hash segment so a repo
        # whose name extends another's cannot match by accident.
        self.get_image_list()
        pattern = BinderHubNaming.build_search_pattern(
            src_name,
            self.config.bh_image_prefix,
            self.config.bh_project_name
        ).lower()

        matches = [image for image in self.docker_images if re.match(pattern, image)]

        if matches:
            self.print_warning(
                f"No image named {exact_name}; falling back to prefix match "
                f"'{pattern}', which found {len(matches)}: {', '.join(matches)}"
            )
            self.print_warning(
                "This usually means the image was built from a differently-cased "
                f"spelling of {src_name}. The hash suffix is derived from the "
                "case-sensitive owner-repo slug, so the runtime attached here may "
                "not correspond to this repository."
            )
            self.found_image_name = matches[0]
            self.list_tags()
            return True

        raise ImageNotFoundError(
            f"No Docker image named '{exact_name}' (nor matching pattern "
            f"'{pattern}') in {self.config.registry_url}"
        )

    def _determine_source_repo_name(self) -> str:
        """
        Determine which repository name to use for image search.

        Returns:
            Repository name to search for

        Priority:
            1. binder_image_name_override
            2. project.thebe.binder.repo from myst.yml
            3. project.github.repo from myst.yml
            4. gh_user_repo_name
        """
        # 1. Check for explicit override
        if self.config.binder_image_name_override:
            return self.config.binder_image_name_override

        # 2-3. Try to get from myst.yml
        if self._load_myst_config():
            src_name = self._extract_repo_from_myst_config()
            if src_name:
                self.cprint(
                    f"🥳 Using project::thebe::binder::repo from myst config to look for 🐳 in "
                    f"{self.config.registry_url}: {src_name}",
                    "light_blue"
                )
                return src_name
            else:
                # No binder config in myst.yml
                self.print_warning(
                    f"project::thebe::binder::repo not found in {MYST_CONFIG_FILE}, "
                    f"using GitHub {self.config.gh_user_repo_name}"
                )
                self.print_warning(
                    "Myst build may succeed, but binder-specific config should be added to "
                    "myst.yml to attach the built page to a proper runtime"
                )
        else:
            # myst.yml not found
            self.print_warning(f"{MYST_CONFIG_FILE} not found, using GitHub user/repo name for 🐳")

        # 4. Fallback to GitHub repo name
        return self.config.gh_user_repo_name

    @retry_github_api
    def _load_myst_config(self) -> bool:
        """
        Load and parse myst.yml from GitHub repository.

        Retries on network failures with exponential backoff.

        Returns:
            True if loaded successfully, False otherwise
        """
        try:
            url = (
                f"https://raw.githubusercontent.com/"
                f"{self.config.gh_user_repo_name}/{self.config.branch}/{MYST_CONFIG_FILE}"
            )
            response = self.rest_client.get(url)

            if response.status_code == 200:
                self.myst_yml_dict = yaml.safe_load(response.text)
                return True
            else:
                self.logger.debug(f"Failed to fetch {MYST_CONFIG_FILE}: {response.status_code}")
                return False

        except yaml.YAMLError as e:
            self.logger.error(f"Error parsing YAML: {e}")
            return False
        except (OSError, IOError) as e:
            self.logger.error(f"Error reading myst config file: {e}")
            return False

    def _extract_repo_from_myst_config(self) -> Optional[str]:
        """
        Extract repository name from loaded myst.yml.

        Returns:
            Repository name if found, None otherwise
        """
        if not self.myst_yml_dict:
            return None

        project = self.myst_yml_dict.get('project', {})

        # Try thebe.binder.repo first
        if 'thebe' in project and 'binder' in project['thebe']:
            repo = project['thebe']['binder'].get('repo')
            if repo:
                return repo

        # Fallback to github field (can be string or dict)
        if 'github' in project:
            github = project['github']

            # Handle both string and dict formats
            if isinstance(github, str):
                # github is directly the repo URL
                repo_url = github.rstrip('/')
            elif isinstance(github, dict):
                # github is a dict with 'repo' key
                repo_url = github.get('repo', '').rstrip('/')
            else:
                return None

            if repo_url:
                # Extract user/repo from URL
                parts = repo_url.split('/')
                if len(parts) >= 2:
                    return '/'.join(parts[-2:])
                return repo_url

        return None

    def get_image_list(self) -> List[str]:
        """
        Get the list of images from the Docker registry.

        Walks every page of /v2/_catalog: the registry caps a listing at its
        own page size and points at the rest through a Link header, so reading
        only the first response hides every repository beyond it.

        Returns:
            List of repository names

        Raises:
            DockerRegistryError: If a catalog page cannot be read
        """
        repositories: List[str] = []
        url = f"{self.config.registry_url}/v2/_catalog?n={CATALOG_PAGE_SIZE}"
        seen_urls = set()

        while url and url not in seen_urls:
            seen_urls.add(url)
            response = self.rest_client.get(url)

            if response.status_code != 200:
                # Raise rather than return a short list: a failed listing that
                # reads as an empty one turns any lookup into a spurious
                # 'image not found'.
                raise DockerRegistryError(
                    f"Failed to list catalog: {response.status_code} {response.text}"
                )

            repositories.extend(response.json().get('repositories') or [])
            url = self._next_catalog_url(response)

        self.docker_images = repositories
        return repositories

    def _next_catalog_url(self, response) -> Optional[str]:
        """
        Resolve the next catalog page from a response's Link header.

        Args:
            response: HTTP response for a catalog page

        Returns:
            Absolute URL of the next page, or None on the last page
        """
        next_link = response.links.get('next', {}).get('url')
        if not next_link:
            return None
        return urljoin(self.config.registry_url, next_link)

    def _fetch_tags(self, image_name: str) -> Optional[List[str]]:
        """
        Fetch the tags of one repository.

        Args:
            image_name: Repository name to query

        Returns:
            Tag list if the repository exists (possibly empty), None if it does not
        """
        tags_url = f"{self.config.registry_url}/v2/{image_name}/tags/list"
        response = self.rest_client.get(tags_url)

        if response.status_code == 200:
            return response.json().get('tags') or []

        if response.status_code != 404:
            self.logger.warning(
                f"HTTP Error listing tags for {image_name}: "
                f"{response.status_code} - {response.text}"
            )

        return None

    @request_set_decorator(success_status_code=200, set_attribute="found_image_tags", json_key="tags")
    def list_tags(self):
        """
        List tags for the found Docker image.

        Returns:
            HTTP response object
        """
        if not self.found_image_name:
            raise DockerRegistryError("No image name set. Call search_image_by_repo_name first.")

        tags_url = f"{self.config.registry_url}/v2/{self.found_image_name}/tags/list"
        return self.rest_client.get(tags_url)

    def get_tags_sorted_by_date(self) -> bool:
        """
        Get image tags sorted by creation date (newest first).

        Returns:
            True if tags were retrieved and sorted

        Raises:
            DockerRegistryError: If tag retrieval fails
        """
        tags = self.list_tags()
        tag_dates: List[Tuple[str, datetime.datetime]] = []

        for tag in tags:
            try:
                created_dt = self._get_tag_creation_date(tag)
                if created_dt:
                    tag_dates.append((tag, created_dt))
            except (KeyError, ValueError, AttributeError) as e:
                self.logger.warning(f"Failed to parse creation date for tag {tag}: {e}")
                continue

        if not tag_dates:
            raise DockerRegistryError(f"No valid tags found for image {self.found_image_name}")

        # Sort by date (newest first)
        sorted_tags = sorted(tag_dates, key=lambda x: x[1], reverse=True)
        self.found_image_tags_sorted = [tag for tag, _ in sorted_tags]

        return True

    def _get_tag_creation_date(self, tag: str) -> Optional[datetime.datetime]:
        """
        Get the creation date for a specific image tag.

        Args:
            tag: Image tag to query

        Returns:
            Creation datetime if available
        """
        if not self.found_image_name:
            return None

        # Get manifest
        manifest_url = f"{self.config.registry_url}/v2/{self.found_image_name}/manifests/{tag}"
        headers = {'Accept': 'application/vnd.docker.distribution.manifest.v2+json'}
        manifest_response = self.rest_client.get(manifest_url, headers=headers)

        if manifest_response.status_code != 200:
            return None

        manifest = manifest_response.json()
        config_digest = manifest.get('config', {}).get('digest')

        if not config_digest:
            return None

        # Get config blob
        config_url = f"{self.config.registry_url}/v2/{self.found_image_name}/blobs/{config_digest}"
        config_response = self.rest_client.get(config_url)

        if config_response.status_code != 200:
            return None

        config = config_response.json()
        created = config.get('created')

        if created:
            # Truncate fractional seconds to 6 digits to avoid parsing errors
            created = re.sub(r'(\.\d{6})\d+', r'\1', created)
            return datetime.datetime.fromisoformat(created.rstrip('Z'))

        return None

    # Deprecated method name for backward compatibility
    def search_img_by_repo_name(self) -> bool:
        """
        Deprecated: Use search_image_by_repo_name instead.

        Returns:
            True if image found
        """
        self.logger.warning("search_img_by_repo_name is deprecated, use search_image_by_repo_name")
        return self.search_image_by_repo_name()

    def get_myst_yml_as_dict(self) -> bool:
        """
        Deprecated: Use _load_myst_config instead.

        Returns:
            True if loaded successfully
        """
        self.logger.warning("get_myst_yml_as_dict is deprecated, use _load_myst_config")
        return self._load_myst_config()
