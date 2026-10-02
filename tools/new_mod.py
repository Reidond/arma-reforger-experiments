#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Scaffold a new Arma Reforger addon under mods/<Name>.

Usage:
    uv run tools/new_mod.py MyMod
    uv run tools/new_mod.py MyMod --title "My Mod" --depends 0123456789ABCDEF

Creates mods/<Name>/addon.gproj (random GUID, depends on the base game) and
Scripts/Game/<Name>/. Open the .gproj in Workbench to finish setup.
"""

from __future__ import annotations

import argparse
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODS = ROOT / "mods"
BASE_GAME_GUID = "58D0FB3206B6F859"  # ArmaReforger.gproj
GUID_RE = re.compile(r"^[0-9A-F]{16}$")


def existing_guids() -> set[str]:
    return {
        match
        for gproj in MODS.glob("*/addon.gproj")
        for match in re.findall(r'GUID "([0-9A-F]{16})"', gproj.read_text())
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("name", help="addon ID and folder name, e.g. EXP_Sandbox")
    parser.add_argument("--title", help="display title (default: name)")
    parser.add_argument("--depends", nargs="*", default=[], metavar="GUID",
                        help="extra dependency GUIDs (base game is always included)")
    args = parser.parse_args()

    if not re.match(r"^[A-Za-z][A-Za-z0-9_]*$", args.name):
        parser.error("name must start with a letter and use only letters, digits, _")
    depends = [BASE_GAME_GUID, *(g.upper() for g in args.depends)]
    bad = [g for g in depends if not GUID_RE.match(g)]
    if bad:
        parser.error(f"invalid GUID(s): {', '.join(bad)}")

    mod = MODS / args.name
    if mod.exists():
        sys.exit(f"{mod.relative_to(ROOT)} already exists")

    taken = existing_guids()
    guid = secrets.token_hex(8).upper()
    while guid in taken:
        guid = secrets.token_hex(8).upper()

    deps = "\n".join(f'  "{g}"' for g in dict.fromkeys(depends))
    gproj = (
        "GameProject {\n"
        f' ID "{args.name}"\n'
        f' GUID "{guid}"\n'
        f' TITLE "{args.title or args.name}"\n'
        " Dependencies {\n"
        f"{deps}\n"
        " }\n"
        "}\n"
    )

    scripts = mod / "Scripts" / "Game" / args.name
    scripts.mkdir(parents=True)
    (mod / "addon.gproj").write_text(gproj)
    (scripts / ".gitkeep").touch()
    (mod / "README.md").write_text(
        f"# {args.title or args.name}\n\n"
        f"- Addon ID: `{args.name}`\n"
        f"- GUID: `{guid}`\n\n"
        "## Purpose\n\nTODO\n"
    )
    print(f"created mods/{args.name} (GUID {guid})")


if __name__ == "__main__":
    main()
