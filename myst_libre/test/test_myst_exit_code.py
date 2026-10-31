"""
A myst process that exits with an error must say so in the output.

run_command used to return the output without looking at the exit code, so a
build that stopped at "fetch failed" produced a log that never said the build
had failed.
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


class TestMystExitCode(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _client(self, executable):
        with patch.object(MystMD, '_check_node_installed'), \
             patch.object(MystMD, '_check_mystmd_installed'):
            return MystMD(
                build_dir=self.tmp.name,
                env_vars={},
                executable=executable,
                state_file=os.path.join(self.tmp.name, 'state.json'),
            )

    def test_non_zero_exit_is_reported_in_the_output(self):
        client = self._client(_fake_myst(self.tmp.name, 'echo "fetch failed"; exit 1'))
        out, _ = client.run_command('build')
        self.assertIn('fetch failed', out)
        self.assertIn('exited with code 1', out)

    def test_zero_exit_output_is_unchanged(self):
        client = self._client(_fake_myst(self.tmp.name, 'echo "Built"; exit 0'))
        out, _ = client.run_command('build')
        self.assertEqual(out.strip(), 'Built')


if __name__ == '__main__':
    unittest.main()
