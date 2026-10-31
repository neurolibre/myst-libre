"""
saved_build.py

Saving a successful build under its commit: keep what is read later, store
each file once.

Only two parts of a build are read from a saved commit: _build/html, the
static export that is served, and _build/site, the site content that CDNs
and archives copy. The sources, .git, the theme's node_modules and the
execute cache stay in the working folder, which keeps them for the next
build.

Files are stored once by hard-linking identical ones:

- _build/html/build holds the same figures as _build/site/public, under the
  same content-hash names, so the static export's copy is a link.
- A file identical to the one at the same place in the previous saved commit
  is a link to it. Saved builds are never changed after saving (only removed),
  so sharing is safe; removing one commit leaves the other's files in place.

Nothing is linked to the working folder: mystmd rewrites files there in place,
which would change the saved builds through the link.

The new copy is assembled in <commit>.saving and moved into place at the end,
so a half-written build is never served.
"""

import filecmp
import os
import shutil
from collections import namedtuple
from pathlib import Path
from typing import Iterable, Optional

SAVED_BUILD_PARTS = ("_build/html", "_build/site")

# The static export's assets folder and the site's figures folder hold the same files
_SAME_FILES = (("_build/html/build", "_build/site/public"),)

# stored_bytes: what the saved build takes on disk, each file counted once. shared_bytes: the part of it that other
# saved builds also hold, so removing this build would not free it.
Report = namedtuple("Report", "stored_bytes shared_bytes")


def _same(a: Path, b: Path) -> bool:
    try:
        return a.is_file() and b.is_file() and a.stat().st_size == b.stat().st_size and filecmp.cmp(a, b, shallow=False)
    except OSError:
        return False


def _link_over(target: Path, existing: Path) -> None:
    """Replace target with a hard link to existing, without a moment where target is missing."""
    temporary = target.with_name(target.name + ".link")
    os.link(existing, temporary)
    os.replace(temporary, target)


def save_build(latest: Path, commit: Path, previous: Optional[Path] = None,
               parts: Iterable[str] = SAVED_BUILD_PARTS) -> Report:
    """Save the build in the working folder `latest` as `commit`, linking identical files (see the module text).

    Args:
        latest: The working folder the build ran in
        commit: Where the saved build goes; replaced if it exists
        previous: The previously saved commit, to share unchanged files with (optional)
        parts: The folders under `latest` to keep

    Returns:
        Report: what the saved build takes on disk, and how much of it is shared with other saved builds
    """
    latest, commit = Path(latest), Path(commit)
    staging = commit.with_name(commit.name + ".saving")
    if staging.exists():
        shutil.rmtree(staging)

    for part in parts:
        source = latest / part
        if source.is_dir():
            shutil.copytree(source, staging / part, symlinks=False)

    # Files outside the duplicate folders are settled first (shared with the previous commit where identical),
    # then each duplicate links to whatever its original ended up as. The other order relinked an original to the
    # previous commit after its duplicate had been linked to it, leaving the two stored apart.
    files = sorted(p for p in staging.rglob("*") if p.is_file() and not p.is_symlink())
    duplicate_dirs = [duplicate for duplicate, _ in _SAME_FILES]

    def is_duplicate(path):
        return any(str(path.relative_to(staging)).startswith(d + "/") for d in duplicate_dirs)

    for path in [p for p in files if not is_duplicate(p)] + [p for p in files if is_duplicate(p)]:
        relative = path.relative_to(staging)
        candidates = []
        for duplicate_dir, original_dir in _SAME_FILES:
            if str(relative).startswith(duplicate_dir + "/"):
                candidates.append(staging / original_dir / relative.relative_to(duplicate_dir))
        if previous is not None:
            candidates.append(Path(previous) / relative)
        for candidate in candidates:
            if _same(path, candidate):
                if not os.path.samefile(path, candidate):
                    _link_over(path, candidate)
                break

    if commit.exists():
        shutil.rmtree(commit)
    os.replace(staging, commit)
    return _report(commit)


def _report(folder: Path) -> Report:
    """Count what folder takes on disk from the files themselves, each once, after all linking is done."""
    inside = {}
    for path in folder.rglob("*"):
        if path.is_file() and not path.is_symlink():
            info = path.stat()
            key = (info.st_dev, info.st_ino)
            count, size, links = inside.get(key, (0, info.st_size, info.st_nlink))
            inside[key] = (count + 1, size, links)
    stored = sum(size for _, size, _ in inside.values())
    shared = sum(size for count, size, links in inside.values() if links > count)
    return Report(stored, shared)
