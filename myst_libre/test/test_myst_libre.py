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
        self.gh_user_repo_name = 'testuser/testrepo'
        self.gh_repo_commit_hash = 'commit_hash'
        self.manager = BuildSourceManager(self.gh_user_repo_name, self.gh_repo_commit_hash)

    @patch('os.makedirs')
    @patch('os.path.exists', return_value=False)
    def test_create_build_dir_host(self, mock_exists, mock_makedirs):
        result = self.manager.create_build_dir_host()
        mock_makedirs.assert_called_once_with(self.manager.build_dir, exist_ok=True)
        self.assertTrue(result)

    @patch('os.path.exists', return_value=True)
    def test_create_build_dir_host_exists(self, mock_exists):
        result = self.manager.create_build_dir_host()
        self.assertFalse(result)

    @patch('myst_libre.tools.build_source_manager.Repo.clone_from')
    @patch('myst_libre.tools.build_source_manager.Repo')
    @patch('os.path.exists')
    @patch('os.makedirs')
    def test_git_clone_repo_new(self, mock_makedirs, mock_exists, mock_repo, mock_clone_from):
        # Test cloning into 'latest' directory when it doesn't exist
        mock_exists.return_value = False
        mock_repo_instance = MagicMock()
        mock_clone_from.return_value = mock_repo_instance

        self.manager.git_clone_repo('/tmp/test')

        # Verify build_dir uses 'latest' instead of commit hash
        expected_build_dir = '/tmp/test/testuser/testrepo/latest'
        self.assertEqual(self.manager.build_dir, expected_build_dir)
        mock_clone_from.assert_called_once_with('https://github.com/testuser/testrepo', expected_build_dir)

    @patch('myst_libre.tools.build_source_manager.Repo')
    @patch('os.path.exists')
    def test_git_clone_repo_existing(self, mock_exists, mock_repo):
        # Test reusing existing 'latest' directory
        mock_exists.return_value = True
        mock_repo_instance = MagicMock()
        mock_repo.return_value = mock_repo_instance

        self.manager.git_clone_repo('/tmp/test')

        # Verify build_dir uses 'latest'
        expected_build_dir = '/tmp/test/testuser/testrepo/latest'
        self.assertEqual(self.manager.build_dir, expected_build_dir)
        mock_repo.assert_called_once_with(expected_build_dir)

    @patch('builtins.open', new_callable=unittest.mock.mock_open, read_data='abc123def')
    @patch('os.path.exists', return_value=True)
    def test_read_latest_successful_hash(self, mock_exists, mock_open):
        self.manager.host_build_source_parent_dir = '/tmp/test'
        result = self.manager.read_latest_successful_hash()
        self.assertEqual(result, 'abc123def')

    @patch('builtins.open', new_callable=unittest.mock.mock_open)
    @patch('os.path.exists', return_value=False)
    def test_read_latest_successful_hash_no_file(self, mock_exists, mock_open):
        self.manager.host_build_source_parent_dir = '/tmp/test'
        result = self.manager.read_latest_successful_hash()
        self.assertIsNone(result)

    @patch('shutil.copytree')
    @patch('shutil.rmtree')
    @patch('builtins.open', new_callable=unittest.mock.mock_open)
    @patch('os.path.exists')
    def test_save_successful_build(self, mock_exists, mock_open, mock_rmtree, mock_copytree):
        self.manager.host_build_source_parent_dir = '/tmp/test'
        self.manager.build_dir = '/tmp/test/testuser/testrepo/latest'
        mock_exists.return_value = False

        result = self.manager.save_successful_build()

        self.assertTrue(result)
        expected_commit_dir = '/tmp/test/testuser/testrepo/commit_hash'
        mock_copytree.assert_called_once_with(self.manager.build_dir, expected_commit_dir, symlinks=False)
        # Verify latest.txt was written with commit hash
        mock_open.assert_called_once_with('/tmp/test/testuser/testrepo/latest.txt', 'w')
        mock_open().write.assert_called_once_with('commit_hash')

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