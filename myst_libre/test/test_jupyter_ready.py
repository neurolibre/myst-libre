"""
The spawner must not hand the Jupyter URL to mystmd until the server answers.

mystmd sends its first request as soon as it reaches a notebook. If the Jupyter
server in the container is still starting, the request is refused and the
build stops with nothing but "fetch failed". qmrlab/mooc's image takes about
25 seconds to start, and mystmd reached its first notebook after 10.
"""

import socket
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import MagicMock, patch

from myst_libre.exceptions import ContainerError
from myst_libre.rees import REES
from myst_libre.tools.jupyter_hub_local_spawner import JupyterHubLocalSpawner


def _free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class _StatusHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api/status':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


def _serve_after(port, delay):
    """Start answering /api/status on port after delay seconds, like a slow Jupyter."""
    holder = {}

    def run():
        time.sleep(delay)
        server = HTTPServer(('127.0.0.1', port), _StatusHandler)
        holder['server'] = server
        server.serve_forever()

    threading.Thread(target=run, daemon=True).start()
    return holder


def _container(status='running', logs=b''):
    container = MagicMock()
    container.status = status
    container.logs.return_value = logs
    return container


def _spawner(**kwargs):
    rees = MagicMock(spec=REES)
    spawner = JupyterHubLocalSpawner(
        rees,
        container_data_mount_dir='/home/jovyan/data',
        container_build_source_mount_dir='/home/jovyan',
        host_data_parent_dir='/tmp/data',
        host_build_source_parent_dir='/tmp/src',
        **kwargs
    )
    spawner.jh_token = 'token'
    return spawner


class TestWaitForJupyterReady(unittest.TestCase):

    def test_returns_once_a_slow_server_starts_answering(self):
        port = _free_port()
        holder = _serve_after(port, delay=1.5)
        self.addCleanup(lambda: holder.get('server') and holder['server'].shutdown())

        spawner = _spawner()
        spawner.container = _container()

        start = time.monotonic()
        spawner._wait_for_jupyter_ready(f'http://127.0.0.1:{port}', timeout=10)
        self.assertGreaterEqual(time.monotonic() - start, 1.5)

    def test_timeout_error_includes_the_container_log(self):
        spawner = _spawner()
        spawner.container = _container(logs=b'Extension package jupyterlab took 3.57s to import')

        with self.assertRaises(ContainerError) as ctx:
            spawner._wait_for_jupyter_ready(f'http://127.0.0.1:{_free_port()}', timeout=1)

        self.assertIn('did not answer within 1 seconds', str(ctx.exception))
        self.assertIn('jupyterlab took 3.57s', str(ctx.exception))

    def test_stops_waiting_when_the_container_exits(self):
        spawner = _spawner()
        spawner.container = _container(status='exited', logs=b'jupyter: command not found')

        start = time.monotonic()
        with self.assertRaises(ContainerError) as ctx:
            spawner._wait_for_jupyter_ready(f'http://127.0.0.1:{_free_port()}', timeout=30)

        self.assertLess(time.monotonic() - start, 5)
        self.assertIn('exited', str(ctx.exception))
        self.assertIn('jupyter: command not found', str(ctx.exception))


class TestSpawnWaitsForJupyter(unittest.TestCase):
    """spawn_jupyter_hub waits in the normal (not Docker-in-Docker) mode too."""

    def _spawn(self, spawner, wait_side_effect=None):
        def fake_spawn_container(entrypoint, volumes):
            spawner.container = _container()

        with patch.object(spawner, '_verify_container_network'), \
             patch.object(spawner, '_verify_metadata_blocked'), \
             patch.object(spawner, 'find_open_port', return_value=8888), \
             patch.object(spawner, '_prepare_repository'), \
             patch.object(spawner, '_prepare_data_directory'), \
             patch.object(spawner, '_ensure_dataset'), \
             patch.object(spawner, '_build_volume_mounts', return_value={}), \
             patch.object(spawner, '_spawn_container', side_effect=fake_spawn_container), \
             patch.object(spawner, '_log_spawn_status', return_value=[]), \
             patch('myst_libre.tools.jupyter_hub_local_spawner.ContainerStatsCollector'), \
             patch.object(spawner, '_wait_for_jupyter_ready',
                          side_effect=wait_side_effect) as wait:
            spawner.spawn_jupyter_hub()
        return wait

    def test_waits_on_localhost_with_the_default_timeout(self):
        wait = self._spawn(_spawner())
        wait.assert_called_once_with('http://localhost:8888', timeout=120)

    def test_timeout_is_configurable(self):
        wait = self._spawn(_spawner(jupyter_ready_timeout=300))
        wait.assert_called_once_with('http://localhost:8888', timeout=300)

    def test_container_is_cleaned_up_when_jupyter_never_answers(self):
        spawner = _spawner()
        with patch.object(spawner, 'cleanup') as cleanup:
            with self.assertRaises(ContainerError) as ctx:
                self._spawn(spawner, wait_side_effect=ContainerError('did not answer'))
        cleanup.assert_called_once()
        self.assertIn('did not answer', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
