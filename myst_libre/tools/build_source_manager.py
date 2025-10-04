"""
build_source_manager.py

This module contains the BuildSourceManager class for handling source code repositories.
"""

import os
import json
import shutil
os.environ["GIT_PYTHON_REFRESH"] = "quiet"
from git import Repo
from datetime import datetime
from myst_libre.abstract_class import AbstractClass
from repo2data.repo2data import Repo2Data

class BuildSourceManager(AbstractClass):
    """
    Manager for handling source code repositories.
    
    Args:
        gh_user_repo_name (str): GitHub user/repository name.
        gh_repo_commit_hash (str): Commit hash of the repository.
    """
    def __init__(self):
        super().__init__()
        self.build_dir = ""
        self.branch = 'main'
        self.provider = 'https://github.com'
        self.username = self.gh_user_repo_name.split('/')[0]
        self.repo_name = self.gh_user_repo_name.split('/')[1]
        now = datetime.now()
        self.created_at = now.strftime("%Y-%m-%dT%H:%M:%S")
        self.dataset_name = ""

    def create_build_dir_host(self):
        """
        Create build directory on the host machine.
        
        Returns:
            bool: True if directory created, else False.
        """
        if not os.path.exists(self.build_dir):
            os.makedirs(self.build_dir, exist_ok=True)
            return True
        return False

    def git_clone_repo(self,clone_parent_directory):
        """
        Clone the GitHub repository into the 'latest' directory.
        Always works in the 'latest' folder to avoid cache snowballing.

        Returns:
            bool: True if cloned successfully, else False.
        """
        self.host_build_source_parent_dir = clone_parent_directory
        # Always use 'latest' directory for builds
        self.build_dir = os.path.join(self.host_build_source_parent_dir, self.username, self.repo_name, 'latest')

        if os.path.exists(self.build_dir):
            self.cprint(f'Source {self.build_dir} already exists, will reuse and update.', "black","on_yellow")
            self.repo_object = Repo(self.build_dir)
        else:
            os.makedirs(os.path.dirname(self.build_dir), exist_ok=True)
            self.cprint(f'Cloning into {self.build_dir}', "green")
            self.repo_object = Repo.clone_from(f'{self.provider}/{self.gh_user_repo_name}', self.build_dir)

        self.set_commit_info()

    def git_checkout_commit(self):
        """
        Checkout the specified commit in the repository.
        Fetches latest changes, cleans the working directory, and checks out the commit.

        Returns:
            bool: True if checked out successfully.
        """
        try:
            # Fetch latest changes from remote
            self.cprint(f'Fetching latest changes from origin', "cyan")
            self.repo_object.remotes.origin.fetch()

            # Clean the working directory (remove untracked files and directories)
            self.cprint(f'Cleaning working directory', "cyan")
            self.repo_object.git.clean('-fdx')

            # Reset any local changes
            self.repo_object.git.reset('--hard')

            # Checkout the specified commit
            self.cprint(f'Checking out {self.gh_repo_commit_hash}', "green")
            self.repo_object.git.checkout(self.gh_repo_commit_hash)

            return True
        except Exception as e:
            self.logger.error(f'Failed to checkout commit: {e}')
            self.cprint(f'✗ Failed to checkout {self.gh_repo_commit_hash}: {e}', "white", "on_red")
            raise

    def get_project_name(self):
        """
        Get the project name from the data requirement file.
        If the file doesn't exist, use the repository name.
        
        Returns:
            str: Project name or repository name.
        """
        data_config_dir = os.path.join(self.build_dir, 'binder', 'data_requirement.json')
        if os.path.isfile(data_config_dir):
            with open(data_config_dir, 'r') as file:
                data = json.load(file)
            self.dataset_name = data.get('projectName', self.repo_name)
        else:
            self.cprint(f'Data requirement file not found at {data_config_dir}, using repository name', "yellow")
            self.dataset_name = None
    
    def repo2data_download(self,target_directory):
        data_req_path = os.path.join(self.build_dir, 'binder', 'data_requirement.json')
        if not os.path.isfile(data_req_path):
            self.cprint(f'Skipping repo2data download', "yellow")
        else:
            self.cprint(f'Starting repo2data download', "green")
            repo2data = Repo2Data(data_req_path, server=True)
            repo2data.set_server_dst_folder(target_directory)
            repo2data.install()

    def set_commit_info(self):
        if self.binder_image_name_override:
            self.binder_commit_info['datetime'] = "20 November 2024"
            self.binder_commit_info['message'] =  "Base runtime from myst-libre"
        else:
            self.binder_commit_info['datetime'] = self.repo_object.commit(self.binder_image_tag).committed_datetime
            self.binder_commit_info['message'] = self.repo_object.commit(self.binder_image_tag).message
        self.repo_commit_info['datetime'] = self.repo_object.commit(self.gh_repo_commit_hash).committed_datetime
        self.repo_commit_info['message'] = self.repo_object.commit(self.gh_repo_commit_hash).message

    def read_latest_successful_hash(self):
        """
        Read the latest successful build commit hash from latest.txt.

        Returns:
            str: Commit hash of last successful build, or None if file doesn't exist.
        """
        latest_txt_path = os.path.join(self.host_build_source_parent_dir, self.username, self.repo_name, 'latest.txt')
        if os.path.exists(latest_txt_path):
            try:
                with open(latest_txt_path, 'r') as f:
                    commit_hash = f.read().strip()
                    self.logger.info(f'Last successful build: {commit_hash}')
                    return commit_hash
            except Exception as e:
                self.logger.warning(f'Error reading latest.txt: {e}')
                return None
        return None

    def save_successful_build(self):
        """
        Save the current successful build by copying 'latest' directory to a commit-specific folder
        and updating latest.txt with the commit hash.

        Returns:
            bool: True if saved successfully, False otherwise.
        """
        try:
            # Define the target directory for this commit
            commit_dir = os.path.join(self.host_build_source_parent_dir, self.username, self.repo_name, self.gh_repo_commit_hash)

            # If commit directory already exists, remove it first
            if os.path.exists(commit_dir):
                self.cprint(f'Removing existing build at {self.gh_repo_commit_hash}', "yellow")
                shutil.rmtree(commit_dir)

            # Copy the latest directory to the commit-specific directory
            self.cprint(f'Preserving successful build to {self.gh_repo_commit_hash}', "green")
            shutil.copytree(self.build_dir, commit_dir, symlinks=False)

            # Update latest.txt with the successful commit hash
            latest_txt_path = os.path.join(self.host_build_source_parent_dir, self.username, self.repo_name, 'latest.txt')
            with open(latest_txt_path, 'w') as f:
                f.write(self.gh_repo_commit_hash)

            self.logger.info(f'Successfully saved build for commit {self.gh_repo_commit_hash}')
            self.cprint(f'✓ Build preserved at {commit_dir}', "white", "on_green")
            return True
        except Exception as e:
            self.logger.error(f'Failed to save successful build: {e}')
            self.cprint(f'✗ Failed to preserve build: {e}', "white", "on_red")
            return False
