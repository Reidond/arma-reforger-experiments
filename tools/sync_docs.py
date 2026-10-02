#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Fetch Arma Reforger reference material into docs/vendor/ (gitignored).

Usage:
    uv run tools/sync_docs.py                 # all sources
    uv run tools/sync_docs.py scripts wiki    # selected sources
    uv run tools/sync_docs.py scripts-experimental
    uv run tools/sync_docs.py misc --with-art # also fetch .blend/.fbx (GBs)

Re-running updates each source in place. Fetched commits are recorded in
docs/vendor/sources.json.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "docs" / "vendor"
MANIFEST = VENDOR / "sources.json"

# Text resources worth grepping; binary assets are skipped unless --with-art.
TEXT_PATTERNS = [
    "*.c", "*.et", "*.conf", "*.gproj", "*.meta", "*.layer", "*.ent", "*.emat",
    "*.txo", "*.txa", "*.asi", "*.acp", "*.st", "*.aw", "*.ast", "*.agr",
    "*.agf", "*.layout", "*.imageset", "*.styles", "*.desc", "*.json",
    "*.md", "*.txt", "*.py", "LICENSE", "README*",
]
ART_PATTERNS = ["*.blend", "*.fbx", "*.FBX"]

# Plain-text export of 250+ BI Community Wiki pages (the wiki itself sits
# behind a bot challenge). Pinned to the commit that last changed the file.
WIKI_REF = "2e7d2cede6faf6573c2d5b96a16b6a809830d990"
WIKI_URL = (
    "https://raw.githubusercontent.com/steffenbk/enfusion-mcp-BK/"
    f"{WIKI_REF}/data/wiki/pages.json"
)

GIT_SOURCES = {
    "scripts": {
        "repo": "BohemiaInteractive/Arma-Reforger-Script-Diff",
        "branch": "main",
        "sparse": None,
        "about": "Vanilla Enforce Script sources; scripts/Core/proto holds engine API declarations",
    },
    "scripts-experimental": {
        "repo": "BohemiaInteractive/Arma-Reforger-Script-Diff-Experimental",
        "branch": "main",
        "sparse": None,
        "about": "Vanilla Enforce Script sources from the Experimental branch",
    },
    "samples": {
        "repo": "BohemiaInteractive/Arma-Reforger-Samples",
        "branch": "main",
        "sparse": TEXT_PATTERNS,
        "about": "Official sample mods (text resources only)",
    },
    "misc": {
        "repo": "BohemiaInteractive/Arma-Reforger-Misc",
        "branch": "main",
        "sparse": TEXT_PATTERNS,
        "about": "Official art/rig/terrain resources (text only unless --with-art)",
    },
    "notes": {
        "repo": "Mavericktfius/arma-reforger-modding",
        "branch": "master",
        "sparse": None,
        "about": "Community field notes: Blender export, rigging, terrain, QA (CC BY-SA 4.0)",
    },
}
ALL_SOURCES = [*GIT_SOURCES, "wiki"]
DEFAULT_SOURCES = [s for s in ALL_SOURCES if s != "scripts-experimental"]


def git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, check=True, text=True, capture_output=True
    )
    return result.stdout.strip()


def sync_git(name: str, spec: dict, with_art: bool) -> dict:
    repo = spec["repo"]
    dest = VENDOR / name
    url = f"https://github.com/{repo}.git"
    patterns = spec["sparse"]
    if patterns and with_art:
        patterns = [*patterns, *ART_PATTERNS]

    if dest.exists() and git("remote", "get-url", "origin", cwd=dest) != url:
        sys.exit(f"{dest} tracks a different repo; delete it and re-run.")

    if not dest.exists():
        clone = ["clone", "-q", "--depth", "1", "--branch", spec["branch"]]
        if patterns:
            clone += ["--filter=blob:none", "--no-checkout"]
        git(*clone, url, str(dest))
    else:
        git("fetch", "-q", "--depth", "1", "origin", spec["branch"], cwd=dest)

    if patterns:
        git("sparse-checkout", "set", "--no-cone", *patterns, cwd=dest)
    git("reset", "-q", "--hard", f"origin/{spec['branch']}", cwd=dest)

    return {
        "repo": repo,
        "commit": git("rev-parse", "HEAD", cwd=dest),
        "subject": git("log", "-1", "--format=%s", cwd=dest),
        "about": spec["about"],
    }


def slug(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", title).strip("_")


def sync_wiki() -> dict:
    with urllib.request.urlopen(WIKI_URL, timeout=60) as response:
        pages = json.load(response)

    dest = VENDOR / "wiki"
    dest.mkdir(parents=True, exist_ok=True)
    for old in dest.glob("*.md"):
        old.unlink()

    index = ["# BI Community Wiki export (Arma Reforger)", ""]
    for page in sorted(pages, key=lambda p: p["title"]):
        title = page["title"]
        url = page.get("url") or (
            "https://community.bistudio.com/wiki/Arma_Reforger:" + title.replace(" ", "_")
        )
        name = slug(title) + ".md"
        body = f"# {title}\n\nSource: {url}\n\n{page['content'].strip()}\n"
        (dest / name).write_text(body, encoding="utf-8")
        index.append(f"- [{title}]({name})")
    (dest / "INDEX.md").write_text("\n".join(index) + "\n", encoding="utf-8")

    return {
        "repo": "steffenbk/enfusion-mcp-BK (data/wiki/pages.json)",
        "commit": WIKI_REF,
        "subject": f"{len(pages)} pages",
        "about": "Plain-text BI Community Wiki pages; check Source URL for the live version",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("sources", nargs="*", metavar="source",
                        help=f"any of: {', '.join(ALL_SOURCES)} (default: all but scripts-experimental)")
    parser.add_argument("--with-art", action="store_true",
                        help="include .blend/.fbx files in samples/misc (several GB)")
    args = parser.parse_args()
    unknown = sorted(set(args.sources) - set(ALL_SOURCES))
    if unknown:
        parser.error(f"unknown source(s): {', '.join(unknown)}")

    VENDOR.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}

    for name in args.sources or DEFAULT_SOURCES:
        print(f"syncing {name}...", flush=True)
        try:
            entry = sync_wiki() if name == "wiki" else sync_git(
                name, GIT_SOURCES[name], args.with_art
            )
        except subprocess.CalledProcessError as error:
            sys.exit(f"{name}: git {' '.join(error.cmd[1:])} failed\n{error.stderr}")
        entry["fetched"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        manifest[name] = entry
        print(f"  {entry['repo']} @ {entry['commit'][:12]} ({entry['subject']})")

    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
