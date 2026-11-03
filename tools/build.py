#!/usr/bin/env python3
"""Build a Kodi-installable zip of the addon.

Writes ``<outdir>/<id>-<version>.zip``, each file under a top-level ``<id>/``
directory, leaving out development-only files. Keep in step with
plugin.video.kofin's tools/build.py.

Usage: build.py [OUTDIR]      (default OUTDIR: ./dist)
"""

import os
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Path components skipped wherever they appear: VCS, virtualenvs, caches.
EXCLUDE_ANYWHERE = {
    "CLAUDE.md",
    # Agent config can be in any directory, and the build copies ignored files.
    ".claude",
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".DS_Store",
}
# Development-only repo-root entries. README.md ships: it documents the skin
# contract.
EXCLUDE_TOP = {
    "docs",
    "tests",
    "tools",
    "dist",
    "mypy.ini",
    "tox.ini",
    "pyproject.toml",
    "requirements-dev.txt",
    ".gitignore",
    ".git-blame-ignore-revs",
    ".github",
    ".vscode",
    ".idea",
}
EXCLUDE_SUFFIX = (".pyc", ".pyo")


def addon_meta():
    """(id, version) read from addon.xml — the zip name and top-level dir."""
    root = ET.parse(ROOT / "addon.xml").getroot()
    return root.get("id"), root.get("version")


def iter_files():
    """Every repo-relative path to package, in deterministic order."""
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel = Path(dirpath).relative_to(ROOT)
        at_root = rel == Path(".")
        # Prune (and order) directories in place so os.walk skips them.
        dirnames[:] = sorted(
            name
            for name in dirnames
            if name not in EXCLUDE_ANYWHERE and not (at_root and name in EXCLUDE_TOP)
        )
        for name in sorted(filenames):
            if name in EXCLUDE_ANYWHERE or name.endswith(EXCLUDE_SUFFIX):
                continue
            if at_root and name in EXCLUDE_TOP:
                continue
            yield rel / name


def build(outdir):
    addon_id, version = addon_meta()
    if not addon_id or not version:
        sys.exit("addon.xml is missing an id or version attribute")

    files = list(iter_files())
    if Path("addon.xml") not in files:
        sys.exit("addon.xml not found in the tree; refusing to build")

    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    zip_path = outdir / f"{addon_id}-{version}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for rel in files:
            arcname = (Path(addon_id) / rel).as_posix()
            archive.write(ROOT / rel, arcname=arcname)

    # An addon missing an entry point installs, then does nothing.
    with zipfile.ZipFile(zip_path) as archive:
        broken = archive.testzip()
        if broken is not None:
            sys.exit(f"built zip is corrupt at {broken}")
        names = archive.namelist()
        for required in ("addon.xml", "default.py", "service.py"):
            if f"{addon_id}/{required}" not in names:
                sys.exit(f"built zip lacks {addon_id}/{required}")

    size_kib = zip_path.stat().st_size / 1024
    print(f"{zip_path}  ({len(files)} files, {size_kib:.0f} KiB)")
    return zip_path


if __name__ == "__main__":
    if len(sys.argv) > 2:
        sys.exit(__doc__.strip())
    build(sys.argv[1] if len(sys.argv) == 2 else ROOT / "dist")
