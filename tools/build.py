#!/usr/bin/env python3
"""Build a Kodi-installable zip of the addon.

Writes ``<outdir>/<id>-<version>.zip``, each file under a top-level ``<id>/``
directory. The files are git archive's: everything tracked, less what
.gitattributes marks export-ignore, which is also what the repo-scripts
submission is packed by. Uncommitted changes to tracked files are included;
untracked files never are.

Usage: build.py [OUTDIR]      (default OUTDIR: ./dist)
"""

import re
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def addon_meta():
    """(id, version) read from addon.xml — the zip name and top-level dir."""
    root = ET.parse(ROOT / "addon.xml").getroot()
    return root.get("id"), root.get("version")


def check_news():
    """addon.xml's <news> must be changelog.txt's first paragraph.

    Kodi shows the one and the repo-scripts pull request quotes it; the other
    is what the GitHub release is written from.
    """
    news = ET.parse(ROOT / "addon.xml").getroot().find(".//news")
    changelog = (ROOT / "changelog.txt").read_text(encoding="utf-8")
    first = re.split(r"\n\s*\n", changelog.strip(), maxsplit=1)[0]
    if news is None or (news.text or "").strip() != first:
        sys.exit("addon.xml <news> does not match the first paragraph of changelog.txt")


def git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def build(outdir):
    addon_id, version = addon_meta()
    if not addon_id or not version:
        sys.exit("addon.xml is missing an id or version attribute")
    check_news()

    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    zip_path = (outdir / f"{addon_id}-{version}.zip").resolve()
    # A throwaway commit of the working tree's tracked changes; none, on a
    # clean tree.
    tree = git("stash", "create") or "HEAD"
    git("archive", "--format=zip", f"--prefix={addon_id}/", "-o", str(zip_path), tree)

    # An addon missing an entry point installs, then does nothing.
    with zipfile.ZipFile(zip_path) as archive:
        broken = archive.testzip()
        if broken is not None:
            sys.exit(f"built zip is corrupt at {broken}")
        names = archive.namelist()
        for required in ("addon.xml", "default.py", "service.py"):
            if f"{addon_id}/{required}" not in names:
                sys.exit(f"built zip lacks {addon_id}/{required}")
        files = [name for name in names if not name.endswith("/")]

    size_kib = zip_path.stat().st_size / 1024
    print(f"{zip_path}  ({len(files)} files, {size_kib:.0f} KiB)")
    return zip_path


if __name__ == "__main__":
    if len(sys.argv) > 2:
        sys.exit(__doc__.strip())
    build(sys.argv[1] if len(sys.argv) == 2 else ROOT / "dist")
