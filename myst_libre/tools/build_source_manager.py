"""
build_source_manager.py

This module contains the BuildSourceManager class for handling source code repositories.
"""

import os
import json
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
            os.makedirs(self.build_dir)
            return True
        return False

    def git_clone_repo(self,clone_parent_directory):
        """
        Clone the GitHub repository.
        
        Returns:
            bool: True if cloned successfully, else False.
        """
        self.host_build_source_parent_dir = clone_parent_directory
        self.build_dir = os.path.join(self.host_build_source_parent_dir, self.username, self.repo_name, self.gh_repo_commit_hash)
        if self.create_build_dir_host():
            self.cprint(f'Cloning into {self.build_dir}', "green")
            self.repo_object = Repo.clone_from(f'{self.provider}/{self.gh_user_repo_name}', self.build_dir)
        else:
            self.cprint(f'Source {self.build_dir} already exists.', "yellow")
            self.repo_object = Repo(self.build_dir)
        
        self.set_commit_info()
        self.validate_commits()

    def git_checkout_commit(self):
        """
        Checkout the specified commit in the repository.
        
        Returns:
            bool: True if checked out successfully.
        """
        self.cprint(f'Checking out {self.gh_repo_commit_hash}', "green")
        self.repo_object.git.checkout(self.gh_repo_commit_hash)
        return True

    def get_project_name(self):
        """
        Get the project name from the data requirement file.
        
        Returns:
            str: Project name.
        """
        data_config_dir = os.path.join(self.build_dir, 'binder', 'data_requirement.json')
        with open(data_config_dir, 'r') as file:
            data = json.load(file)
        self.dataset_name = data['projectName']
    
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
        self.binder_commit_info['datetime'] = self.repo_object.commit(self.binder_image_tag).committed_datetime
        self.binder_commit_info['message'] = self.repo_object.commit(self.binder_image_tag).message
        self.repo_commit_info['datetime'] = self.repo_object.commit(self.gh_repo_commit_hash).committed_datetime
        self.repo_commit_info['message'] = self.repo_object.commit(self.gh_repo_commit_hash).message
        self.validate_commits()

    def validate_commits(self):
        if self.repo_commit_info['datetime'] < self.binder_commit_info['datetime']:
            raise ValueError("The repo commit datetime cannot be older than the binder commit datetime.")

    def create_latest_symlink(self):
        """
        Create a symlink to the latest build directory.
        """
        self.latest_dir = os.path.join(self.host_build_source_parent_dir, self.username, self.repo_name, 'latest')
        self.logger.info(f'Creating symlink {self.gh_repo_commit_hash} --> latest')
        if not os.path.exists(self.latest_dir):
            os.makedirs(self.latest_dir)
        else:
            for item in os.listdir(self.build_dir):
                os.unlink(item)
        for item in os.listdir(self.build_dir):
            source_path = os.path.join(self.build_dir, item)
            target_path = os.path.join(self.latest_dir, item)
            if os.path.isdir(source_path):
                os.symlink(source_path, target_path, target_is_directory=True)
            else:
                os.symlink(source_path, target_path)
