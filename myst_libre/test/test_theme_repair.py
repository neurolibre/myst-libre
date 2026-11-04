"""
A theme whose npm install never finished must be removed before the build.

mystmd downloads and installs the site theme only when its folder is missing.
The build keeps _build between builds (to reuse executed notebook outputs), so
a theme whose install was interrupted is kept too, and every later build fails
when the theme server cannot load its packages. qmrlab/mooc's book theme had
17 of its packages instead of 113, express without its package.json, and
"Cannot find module 'express'" on every build.
"""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from myst_libre.builders.myst_builder import MystBuilder, remove_incomplete_themes, remove_site_themes


def _theme(build_dir, name, dependencies, installed):
    theme = os.path.join(build_dir, '_build', 'templates', 'site', 'myst', name)
    os.makedirs(theme)
    with open(os.path.join(theme, 'package.json'), 'w') as f:
        json.dump({'name': name, 'dependencies': dependencies}, f)
    for package in installed:
        folder = os.path.join(theme, 'node_modules', package)
        os.makedirs(folder)
        with open(os.path.join(folder, 'package.json'), 'w') as f:
            json.dump({'name': package}, f)
    return theme


class TestRemoveIncompleteThemes(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.deps = {'express': '^4.18.2', '@remix-run/express': '^1.15.0'}

    def test_complete_theme_is_kept(self):
        theme = _theme(self.tmp.name, 'book-theme', self.deps, ['express', '@remix-run/express'])
        self.assertEqual(remove_incomplete_themes(self.tmp.name), [])
        self.assertTrue(os.path.isdir(theme))

    def test_theme_with_a_package_missing_its_package_json_is_removed(self):
        theme = _theme(self.tmp.name, 'book-theme', self.deps, ['@remix-run/express'])
        os.makedirs(os.path.join(theme, 'node_modules', 'express', 'lib'))

        removed = remove_incomplete_themes(self.tmp.name)

        self.assertEqual(removed, [theme])
        self.assertFalse(os.path.exists(theme))

    def test_missing_scoped_package_is_detected(self):
        theme = _theme(self.tmp.name, 'article-theme', self.deps, ['express'])
        self.assertEqual(remove_incomplete_themes(self.tmp.name), [theme])

    def test_no_templates_folder_is_fine(self):
        self.assertEqual(remove_incomplete_themes(self.tmp.name), [])

    def test_other_build_outputs_are_untouched(self):
        _theme(self.tmp.name, 'book-theme', self.deps, [])
        execute = os.path.join(self.tmp.name, '_build', 'execute')
        os.makedirs(execute)
        open(os.path.join(execute, 'abc.json'), 'w').close()

        remove_incomplete_themes(self.tmp.name)

        self.assertTrue(os.path.exists(os.path.join(execute, 'abc.json')))

    def test_build_checks_themes_before_running_myst(self):
        theme = _theme(self.tmp.name, 'book-theme', self.deps, [])
        with patch('myst_libre.builders.myst_builder.MystMD') as client:
            client.return_value.build.side_effect = lambda *a, **k: (
                self.assertFalse(os.path.exists(theme)) or 'Built'
            )
            MystBuilder(build_dir=self.tmp.name).build('--html')
            client.return_value.build.assert_called_once()


if __name__ == '__main__':
    unittest.main()


class TestFreshBuildRefreshesTheTheme(unittest.TestCase):
    """A fresh build installs the current release of its site theme: a project otherwise keeps the theme of its
    first build, and moranebienvenu/stroke_article's predated the Plotly renderer (2026-11-04)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.deps = {'express': '^4.18.2'}

    def _build(self, **kwargs):
        with patch('myst_libre.builders.myst_builder.MystMD') as client:
            client.return_value.build.return_value = 'Built'
            builder = MystBuilder(build_dir=self.tmp.name)
            builder.build('--html', **kwargs)
        return builder

    def test_a_fresh_build_removes_the_cached_theme_and_keeps_the_rest_of_build(self):
        theme = _theme(self.tmp.name, 'article-theme', self.deps, ['express'])
        site = os.path.join(self.tmp.name, '_build', 'site')
        os.makedirs(site)
        builder = self._build(fresh_execution=True)
        self.assertFalse(os.path.exists(theme))
        self.assertEqual(builder.themes_refreshed, [theme])
        self.assertTrue(os.path.isdir(site))

    def test_an_ordinary_build_keeps_a_complete_theme(self):
        theme = _theme(self.tmp.name, 'article-theme', self.deps, ['express'])
        builder = self._build()
        self.assertTrue(os.path.isdir(theme))
        self.assertEqual(builder.themes_refreshed, [])

    def test_no_theme_yet_is_fine(self):
        self.assertEqual(remove_site_themes(self.tmp.name), [])
