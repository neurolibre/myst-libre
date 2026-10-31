"""
Saving a successful build keeps what is served and read later, once.

save_successful_build used to copy the whole working folder into the commit's
folder: sources, .git, the theme's node_modules, the execute cache, and the
figures twice (_build/site/public and the static export's _build/html/build
hold the same files). For qmrlab/mooc that was 1.9 GB per commit. Only
_build/html (served) and _build/site (the CDN, the Zenodo archive) are read
from a saved commit.
"""

import os
import tempfile
import unittest
from pathlib import Path

from myst_libre.tools.saved_build import save_build


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


class TestSaveBuild(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.latest = self.root / 'latest'
        write(self.latest / 'index.md', 'source')
        write(self.latest / '.git' / 'HEAD', 'ref')
        write(self.latest / '_build' / 'execute' / 'abc.json', 'outputs')
        write(self.latest / '_build' / 'templates' / 'site' / 'myst' / 'book-theme' / 'server.js', 'theme')
        write(self.latest / '_build' / 'html' / 'index.html', '<html>')
        write(self.latest / '_build' / 'html' / 'build' / 'fig1.json', 'figure one')
        write(self.latest / '_build' / 'html' / 'build' / 'theme.js', 'theme code')
        write(self.latest / '_build' / 'site' / 'config.json', '{}')
        write(self.latest / '_build' / 'site' / 'public' / 'fig1.json', 'figure one')
        write(self.latest / '_build' / 'site' / 'content' / 'index.json', '{"page": 1}')

    def test_only_the_site_and_the_static_export_are_kept(self):
        commit = self.root / 'c1'
        save_build(self.latest, commit)
        kept = sorted(str(p.relative_to(commit)) for p in commit.rglob('*') if p.is_file())
        self.assertEqual(kept, [
            '_build/html/build/fig1.json', '_build/html/build/theme.js', '_build/html/index.html',
            '_build/site/config.json', '_build/site/content/index.json', '_build/site/public/fig1.json',
        ])

    def test_a_figure_in_both_folders_is_stored_once(self):
        commit = self.root / 'c1'
        save_build(self.latest, commit)
        self.assertTrue(os.path.samefile(commit / '_build/html/build/fig1.json',
                                         commit / '_build/site/public/fig1.json'))

    def test_files_with_the_same_name_but_different_bytes_are_not_linked(self):
        write(self.latest / '_build' / 'site' / 'public' / 'theme.js', 'something else')
        commit = self.root / 'c1'
        save_build(self.latest, commit)
        self.assertFalse(os.path.samefile(commit / '_build/html/build/theme.js',
                                          commit / '_build/site/public/theme.js'))
        self.assertEqual((commit / '_build/site/public/theme.js').read_text(), 'something else')

    def test_files_unchanged_since_the_previous_commit_are_shared_with_it(self):
        previous = self.root / 'c1'
        save_build(self.latest, previous)
        write(self.latest / '_build' / 'site' / 'content' / 'index.json', '{"page": 2}')
        commit = self.root / 'c2'

        report = save_build(self.latest, commit, previous=previous)

        self.assertTrue(os.path.samefile(commit / '_build/site/public/fig1.json', previous / '_build/site/public/fig1.json'))
        self.assertFalse(os.path.samefile(commit / '_build/site/content/index.json',
                                          previous / '_build/site/content/index.json'))
        self.assertEqual((previous / '_build/site/content/index.json').read_text(), '{"page": 1}')
        self.assertGreater(report.shared_bytes, 0)

    def test_the_working_folder_is_not_linked_to_the_saved_build(self):
        # mystmd rewrites files in place: a link from latest would change saved builds
        commit = self.root / 'c1'
        save_build(self.latest, commit)
        self.assertFalse(os.path.samefile(commit / '_build/site/public/fig1.json',
                                          self.latest / '_build/site/public/fig1.json'))

    def test_a_build_without_a_static_export_keeps_the_site(self):
        import shutil
        shutil.rmtree(self.latest / '_build' / 'html')
        commit = self.root / 'c1'
        save_build(self.latest, commit)
        self.assertTrue((commit / '_build/site/config.json').is_file())
        self.assertFalse((commit / '_build/html').exists())

    def test_saving_the_same_commit_again_replaces_it(self):
        commit = self.root / 'c1'
        save_build(self.latest, commit)
        write(self.latest / '_build' / 'html' / 'index.html', '<html> again')
        save_build(self.latest, commit, previous=commit)
        self.assertEqual((commit / '_build/html/index.html').read_text(), '<html> again')
        self.assertFalse((self.root / 'c1.saving').exists())


if __name__ == '__main__':
    unittest.main()


class TestSaveSuccessfulBuild(unittest.TestCase):
    """BuildSourceManager.save_successful_build saves through save_build and shares with the previous commit."""

    def test_keeps_the_two_parts_shares_with_the_previous_commit_and_updates_latest_txt(self):
        from types import SimpleNamespace
        from myst_libre.tools.build_source_manager import BuildSourceManager

        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            repo = parent / 'someone' / 'book'
            latest = repo / 'latest'
            write(latest / 'index.md', 'source')
            write(latest / '_build' / 'execute' / 'a.json', 'outputs')
            write(latest / '_build' / 'html' / 'index.html', '<html>')
            write(latest / '_build' / 'site' / 'public' / 'fig.json', 'figure')

            def save(commit_hash):
                manager = BuildSourceManager(SimpleNamespace(username='someone', repo_name='book',
                                                             gh_repo_commit_hash=commit_hash))
                manager.host_build_source_parent_dir = parent
                manager.build_context = SimpleNamespace(build_dir=latest)
                return manager.save_successful_build()

            self.assertTrue(save('a' * 40))
            write(latest / '_build' / 'html' / 'index.html', '<html> 2')
            self.assertTrue(save('b' * 40))

            self.assertEqual((repo / 'latest.txt').read_text(), 'b' * 40)
            self.assertFalse((repo / ('b' * 40) / 'index.md').exists())
            self.assertFalse((repo / ('b' * 40) / '_build' / 'execute').exists())
            self.assertTrue(os.path.samefile(repo / ('a' * 40) / '_build/site/public/fig.json',
                                             repo / ('b' * 40) / '_build/site/public/fig.json'))


class TestLinkOrder(unittest.TestCase):
    """The static export's figures must end up as the same file as the site's, also when the site's files are
    shared with a previous commit that stored them twice (a full copy made before 0.4.7, or by hand). 0.4.7 linked
    html/build first and then relinked site/public to the previous commit, leaving every figure stored twice while
    reporting it as linked."""

    def test_figures_are_stored_once_when_the_previous_commit_stored_them_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            latest = root / 'latest'
            for folder in ('_build/html/build', '_build/site/public'):
                write(latest / folder / 'fig1.json', 'figure one')
            write(latest / '_build' / 'html' / 'index.html', '<html>')
            previous = root / 'previous'
            for folder in ('_build/html/build', '_build/site/public'):
                write(previous / folder / 'fig1.json', 'figure one')      # two separate copies

            report = save_build(latest, root / 'commit', previous=previous)

            commit = root / 'commit' / '_build'
            self.assertTrue(os.path.samefile(commit / 'html/build/fig1.json', commit / 'site/public/fig1.json'))
            self.assertTrue(os.path.samefile(commit / 'site/public/fig1.json', previous / '_build/site/public/fig1.json'))
            self.assertEqual(report.stored_bytes, len('figure one') + len('<html>'))
            self.assertEqual(report.shared_bytes, len('figure one'))

    def test_the_report_counts_what_is_on_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            latest = root / 'latest'
            write(latest / '_build' / 'html' / 'build' / 'fig1.json', 'figure one')
            write(latest / '_build' / 'site' / 'public' / 'fig1.json', 'figure one')
            write(latest / '_build' / 'site' / 'config.json', '{}')
            report = save_build(latest, root / 'commit')
            self.assertEqual(report.stored_bytes, len('figure one') + len('{}'))
            self.assertEqual(report.shared_bytes, 0)
