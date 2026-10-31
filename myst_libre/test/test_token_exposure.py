"""
The Jupyter server's token grants code execution in the build container, so:

- the server's port is published on the host's loopback address only. mystmd
  reaches it through localhost, and nothing outside the host needs it. Before,
  it was published on every interface, so anyone who learned a token while a
  build ran could reach the server from wherever the cloud firewall allowed.
- the token is not written to the log when mystmd starts.
"""

import os
import stat
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from myst_libre.rees import REES
from myst_libre.tools.jupyter_hub_local_spawner import JupyterHubLocalSpawner
from myst_libre.tools.myst_client import MystMD

TOKEN = "53ef131ace4ec5f40ec062b7c448f588c6515a0d"


class TestPortPublishedOnLoopbackOnly(unittest.TestCase):

    def test_the_port_is_bound_to_127_0_0_1(self):
        rees = MagicMock(spec=REES)
        rees.docker_client = MagicMock()
        rees.docker_image = 'registry.example.org/binder-image:abc'
        spawner = JupyterHubLocalSpawner(
            rees,
            container_data_mount_dir='/home/jovyan/data',
            container_build_source_mount_dir='/home/jovyan',
            host_data_parent_dir='/tmp/data',
            host_build_source_parent_dir='/tmp/src',
        )
        spawner.port = 8888
        spawner.jh_token = TOKEN
        spawner.jh_url = 'http://localhost:8888'

        spawner._spawn_container('jupyter server', {})

        ports = rees.docker_client.containers.run.call_args.kwargs['ports']
        self.assertEqual(ports, {'8888/tcp': ('127.0.0.1', 8888)})


class TestTokenNotLogged(unittest.TestCase):

    def test_run_command_does_not_log_the_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = os.path.join(tmp, 'myst')
            with open(exe, 'w') as f:
                f.write('#!/bin/sh\necho Built\n')
            os.chmod(exe, os.stat(exe).st_mode | stat.S_IEXEC)
            with patch.object(MystMD, '_check_node_installed'), \
                 patch.object(MystMD, '_check_mystmd_installed'):
                client = MystMD(build_dir=tmp, env_vars={}, executable=exe,
                                state_file=os.path.join(tmp, 'state.json'))
            client.logger = MagicMock()

            client.run_command('build', env_vars={'JUPYTER_TOKEN': TOKEN, 'port': '8888',
                                                  'JUPYTER_BASE_URL': 'http://localhost:8888'})

            logged = ' '.join(str(c) for c in client.logger.mock_calls)
            self.assertNotIn(TOKEN, logged)
            self.assertIn('JUPYTER_BASE_URL', logged)


if __name__ == '__main__':
    unittest.main()
