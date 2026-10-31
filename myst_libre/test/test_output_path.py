"""
A caller can name the file myst's output goes to, so something else can read
it while the build runs (a live log page). Without output_path the output goes
to a temporary file that nothing else can find, and that file is deleted.
"""

import os
import stat
import tempfile
import unittest
from unittest.mock import patch

from myst_libre.tools.myst_client import MystMD


def _fake_myst(directory, body):
    path = os.path.join(directory, 'myst')
    with open(path, 'w') as f:
        f.write('#!/bin/sh\n' + body + '\n')
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path


class TestOutputPath(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _client(self, body):
        with patch.object(MystMD, '_check_node_installed'), \
             patch.object(MystMD, '_check_mystmd_installed'):
            return MystMD(
                build_dir=self.tmp.name,
                env_vars={},
                executable=_fake_myst(self.tmp.name, body),
                state_file=os.path.join(self.tmp.name, 'state.json'),
            )

    def test_output_is_written_to_the_named_file_and_kept(self):
        live = os.path.join(self.tmp.name, 'live', 'task.log')
        out, _ = self._client('echo "Built 2 T1 mapping.md"').run_command('build', output_path=live)

        self.assertIn('Built 2 T1 mapping.md', out)
        with open(live) as f:
            self.assertIn('Built 2 T1 mapping.md', f.read())

    def test_existing_content_is_kept_and_not_returned(self):
        live = os.path.join(self.tmp.name, 'task.log')
        with open(live, 'w') as f:
            f.write('Pulling image and starting Jupyter\n')

        out, _ = self._client('echo "Built"').run_command('build', output_path=live)

        self.assertEqual(out.strip(), 'Built')
        with open(live) as f:
            content = f.read()
        self.assertTrue(content.startswith('Pulling image and starting Jupyter\n'))
        self.assertIn('Built', content)

    def test_build_passes_output_path_through(self):
        live = os.path.join(self.tmp.name, 'task.log')
        self._client('echo "from build"').build('build', output_path=live)
        with open(live) as f:
            self.assertIn('from build', f.read())


if __name__ == '__main__':
    unittest.main()
