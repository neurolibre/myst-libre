import unittest
from unittest.mock import patch, MagicMock
from tools import DockerRegistryClient, BuildSourceManager, JupyterHubLocalSpawner, request_set_decorator

class TestDockerRegistryClient(unittest.TestCase):

    def setUp(self):
        self.registry_url = 'http://example.com'
        self.gh_user_repo_name = 'user/repo'
        self.auth = {'username': 'user', 'password': 'pass'}
        self.client = DockerRegistryClient(self.registry_url, self.gh_user_repo_name, self.auth)

    @patch('myst_libre.tools.RestClient.get')
    def test_get_token_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        result = self.client.get_token()
        self.assertTrue(result)

    @patch('myst_libre.tools.RestClient.get')
    def test_get_token_failure(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        result = self.client.get_token()
        self.assertFalse(result)

    @patch('myst_libre.tools.RestClient.get')
    @patch('myst_libre.tools.DockerRegistryClient.get_image_list')
    def test_search_img_by_repo_name(self, mock_get_image_list, mock_get):
        self.client.docker_images = ['example.com/binder-user-2drepo']
        mock_get_image_list.return_value = True
        mock_response = MagicMock()
        mock_response.json.return_value = {'tags': ['latest']}
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        result = self.client.search_img_by_repo_name()
        self.assertTrue(result)

class TestBuildSourceManager(unittest.TestCase):

    def setUp(self):
        self.gh_user_repo_name = 'user/repo'
        self.gh_repo_commit_hash = 'commit_hash'
        self.manager = BuildSourceManager(self.gh_user_repo_name, self.gh_repo_commit_hash)

    @patch('os.makedirs')
    @patch('os.path.exists', return_value=False)
    def test_create_build_dir_host(self, mock_exists, mock_makedirs):
        result = self.manager.create_build_dir_host()
        mock_makedirs.assert_called_once_with(self.manager.build_dir)
        self.assertTrue(result)

    @patch('os.path.exists', return_value=True)
    def test_create_build_dir_host_exists(self, mock_exists):
        result = self.manager.create_build_dir_host()
        self.assertFalse(result)

    @patch('myst_libre.Repo.clone_from')
    @patch('myst_libre.BuildSourceManager.create_build_dir_host', return_value=True)
    def test_git_clone_repo(self, mock_create_build_dir_host, mock_clone_from):
        result = self.manager.git_clone_repo()
        mock_clone_from.assert_called_once_with(f'https://github.com/{self.gh_user_repo_name}', self.manager.build_dir)
        self.assertTrue(result)

class TestJupyterHubLocalSpawner(unittest.TestCase):

    def setUp(self):
        self.registry_url = 'http://example.com'
        self.gh_user_repo_name = 'user/repo'
        self.auth = {'username': 'user', 'password': 'pass'}
        self.gh_repo_commit_hash = 'commit_hash'
        self.spawner = JupyterHubLocalSpawner(self.registry_url, self.gh_user_repo_name, self.auth, self.gh_repo_commit_hash)

    @patch('myst_libre.docker.from_env')
    def test_login_to_registry(self, mock_docker):
        mock_docker_client = MagicMock()
        mock_docker.return_value = mock_docker_client

        self.spawner.login_to_registry()
        mock_docker_client.login.assert_called_once_with(username=self.auth['username'], password=self.auth['password'], registry=self.registry_url)

    @patch('myst_libre.tools.DockerRegistryClient.search_img_by_repo_name', return_value=True)
    @patch('myst_libre.tools.BuildSourceManager.git_clone_repo')
    @patch('myst_libre.tools.BuildSourceManager.git_checkout_commit')
    @patch('myst_libre.tools.JupyterHubLocalSpawner.pull_image')
    @patch('myst_libre.tools.JupyterHubLocalSpawner.find_open_port', return_value=8888)
    @patch('myst_libre.tools.JupyterHubLocalSpawner._is_port_in_use', return_value=False)
    @patch('myst_libre.rees.docker.from_env')
    def test_spawn_jupyter_hub(self, mock_docker, mock_is_port_in_use, mock_find_open_port, mock_pull_image, mock_git_checkout_commit, mock_git_clone_repo, mock_search_img_by_repo_name):
        mock_docker_client = MagicMock()
        mock_docker.return_value = mock_docker_client

        self.spawner.spawn_jupyter_hub()

        self.assertTrue(mock_search_img_by_repo_name.called)
        self.assertTrue(mock_git_clone_repo.called)
        self.assertTrue(mock_git_checkout_commit.called)
        self.assertTrue(mock_pull_image.called)
        self.assertTrue(mock_docker_client.containers.run.called)

if __name__ == '__main__':
    unittest.main()