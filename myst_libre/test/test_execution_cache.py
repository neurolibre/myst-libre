"""
mystmd reuses a notebook's saved outputs while its code cells are unchanged.
Its cache key does not cover the execution environment or the data, so a new
image or a new dataset version left old outputs in place. MystBuilder records
the image and the data requirement next to the cache, and when either differs
from the build that filled the cache (or a fresh run is asked for), it clears
the cache with mystmd's own `myst clean --execute --yes` before building.
"""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from myst_libre.builders.myst_builder import MystBuilder, EXECUTION_INPUTS_FILE
from myst_libre.tools.jupyter_hub_local_spawner import JupyterHubLocalSpawner


class TestExecutionCache(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / 'binder').mkdir()
        (self.root / 'binder' / 'data_requirement.json').write_text('{"a": {"src": "v1.zip"}}')
        self.image = 'sha256:aaa'
        self.calls = []

    def cache(self, entries=1):
        execute = self.root / '_build' / 'execute'
        execute.mkdir(parents=True, exist_ok=True)
        for i in range(entries):
            (execute / f'{i}.json').write_text('{}')

    def build(self, *args, fresh_execution=False):
        args = args or ('--execute', '--html')
        hub = MagicMock(spec=JupyterHubLocalSpawner)
        hub.jh_url, hub.jh_token, hub.port = 'http://localhost:8888', 't', 8888
        hub.rees = MagicMock()
        hub.rees.build_dir = str(self.root)
        hub.rees.docker_image = SimpleNamespace(id=self.image)

        def run_command(*a, **k):
            self.calls.append(('run_command',) + a)
            if a[:2] == ('clean', '--execute'):
                import shutil
                shutil.rmtree(self.root / '_build' / 'execute', ignore_errors=True)
            return '', ''

        def build(*a, **k):
            self.calls.append(('build',) + a)
            client.last_returncode = 0
            return 'Built'

        with patch('myst_libre.builders.myst_builder.MystMD') as MystMD:
            client = MystMD.return_value
            client.run_command.side_effect = run_command
            client.build.side_effect = build
            builder = MystBuilder(hub=hub)
            builder.build(*args, fresh_execution=fresh_execution)
        return builder

    def cleaned(self):
        return [c for c in self.calls if c[:3] == ('run_command', 'clean', '--execute')]

    def test_the_first_build_records_its_inputs(self):
        self.build()
        self.assertEqual(self.cleaned(), [])
        recorded = json.loads((self.root / EXECUTION_INPUTS_FILE).read_text())
        self.assertEqual(recorded['image'], 'sha256:aaa')
        self.assertTrue(recorded['data_requirement'])

    def test_unchanged_inputs_keep_the_cache(self):
        self.build()
        self.cache()
        self.build()
        self.assertEqual(self.cleaned(), [])
        self.assertTrue((self.root / '_build' / 'execute' / '0.json').exists())

    def test_a_new_image_clears_the_cache_before_building(self):
        self.build()
        self.cache()
        self.image = 'sha256:bbb'
        start = len(self.calls)
        builder = self.build()
        self.assertEqual(len(self.cleaned()), 1)
        self.assertEqual(self.cleaned()[0][1:4], ('clean', '--execute', '--yes'))
        second = [c[:2] for c in self.calls[start:]]
        self.assertEqual(second, [('run_command', 'clean'), ('build', 'build')])
        self.assertIn('image', builder.execution_cache_cleared)
        self.assertEqual(json.loads((self.root / EXECUTION_INPUTS_FILE).read_text())['image'], 'sha256:bbb')

    def test_a_new_data_requirement_clears_the_cache(self):
        self.build()
        self.cache()
        (self.root / 'binder' / 'data_requirement.json').write_text('{"a": {"src": "v2.zip"}}')
        builder = self.build()
        self.assertEqual(len(self.cleaned()), 1)
        self.assertIn('data', builder.execution_cache_cleared)

    def test_a_fresh_run_clears_the_cache_even_when_nothing_changed(self):
        self.build()
        self.cache()
        builder = self.build(fresh_execution=True)
        self.assertEqual(len(self.cleaned()), 1)
        self.assertIn('fresh', builder.execution_cache_cleared)

    def test_a_cache_with_no_record_of_its_inputs_is_cleared(self):
        self.cache()                         # filled before this check existed
        builder = self.build()
        self.assertEqual(len(self.cleaned()), 1)
        self.assertIn('not recorded', builder.execution_cache_cleared)

    def test_nothing_to_clear_means_no_clean(self):
        self.image = 'sha256:bbb'
        builder = self.build(fresh_execution=True)     # no cache folder yet
        self.assertEqual(self.cleaned(), [])
        self.assertIsNone(builder.execution_cache_cleared)

    def test_a_build_without_execution_leaves_the_cache_alone(self):
        self.cache()
        self.build('--html', fresh_execution=True)
        self.assertEqual(self.cleaned(), [])
        self.assertFalse((self.root / EXECUTION_INPUTS_FILE).exists())


if __name__ == '__main__':
    unittest.main()
