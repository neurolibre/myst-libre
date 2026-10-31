"""
Whether a build worked is decided by mystmd's exit code and by the site it
wrote, not by words in its output.

The build used to count as failed whenever the output contained "Error",
"error:" or "failed". A notebook that raises (a ValueError in one figure) put
those words in the output, so a complete site was not saved under its commit
and the caller reported that no webpage was produced. qmrlab/mooc: 113 pages
built and exported, 10 notebooks with errors, build reported as failed.
"""

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from myst_libre.builders.myst_builder import MystBuilder
from myst_libre.tools.jupyter_hub_local_spawner import JupyterHubLocalSpawner

NOTEBOOK_ERROR = (
    "⛔️ 5 B0 Mapping/Figure-5-1-1.ipynb An exception occurred during code execution, halting further execution:\n"
    "ValueError: Invalid property specified for object of type plotly.graph_objs.heatmap.ColorBar: 'titleside'\n"
    "📚 Built 113 pages for project in 2.13 min.\n"
)


class TestBuildSuccess(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.hub = MagicMock(spec=JupyterHubLocalSpawner)
        self.hub.jh_url, self.hub.jh_token, self.hub.port = 'http://localhost:8888', 't', 8888
        self.hub.rees = MagicMock()
        self.hub.rees.build_dir = self.tmp.name

    def build(self, output, returncode, writes_site=True, args=('--execute', '--html')):
        index = Path(self.tmp.name) / '_build' / 'html' / 'index.html'

        def run(*a, **k):
            if writes_site:
                index.parent.mkdir(parents=True, exist_ok=True)
                index.write_text('<html>')
            client.last_returncode = returncode
            return output

        with patch('myst_libre.builders.myst_builder.MystMD') as MystMD:
            client = MystMD.return_value
            client.build.side_effect = run
            builder = MystBuilder(hub=self.hub)
            logs = builder.build(*args)
        return builder, logs

    def test_notebook_errors_do_not_fail_a_build_that_wrote_its_site(self):
        builder, logs = self.build(NOTEBOOK_ERROR, returncode=0)
        self.hub.rees.save_successful_build.assert_called_once()
        self.assertTrue(builder.succeeded)
        self.assertEqual(logs, NOTEBOOK_ERROR)

    def test_a_non_zero_exit_fails_the_build(self):
        builder, _ = self.build("fetch failed\n", returncode=1)
        self.hub.rees.save_successful_build.assert_not_called()
        self.assertFalse(builder.succeeded)

    def test_no_site_written_by_this_build_fails_it(self):
        index = Path(self.tmp.name) / '_build' / 'html' / 'index.html'
        index.parent.mkdir(parents=True)
        index.write_text('<html> from an earlier build')
        old = time.time() - 3600
        os.utime(index, (old, old))

        builder, _ = self.build("Built 113 pages\n", returncode=0, writes_site=False)

        self.hub.rees.save_successful_build.assert_not_called()
        self.assertFalse(builder.succeeded)

    def test_a_build_without_html_needs_only_the_exit_code(self):
        builder, _ = self.build("Built\n", returncode=0, writes_site=False, args=('--execute',))
        self.assertTrue(builder.succeeded)
        self.hub.rees.save_successful_build.assert_called_once()


if __name__ == '__main__':
    unittest.main()
