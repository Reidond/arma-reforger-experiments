# Agent instructions

Experiments with Arma Reforger (Enfusion engine) modding, done together with AI agents.

## Layout

| Path | What |
| --- | --- |
| `mods/<AddonID>/` | Monorepo of Reforger addons, one `addon.gproj` each — see `mods/README.md` |
| `art/<AddonID>/` | Blender / texture sources (Git LFS) |
| `docs/` | Reference index (`docs/README.md`), our verified notes (`docs/notes/`) |
| `docs/vendor/` | Fetched vanilla scripts, samples, wiki export — gitignored |
| `tools/` | `sync_docs.py` (fetch docs), `new_mod.py` (scaffold addon) |
| `worklog.md` | AI session history — **update it every session** |

## Environment

- Arma Reforger Tools (Workbench) runs on **Windows only**. On macOS we write scripts,
  configs and art; compiling, validating and packing happen in Workbench on Windows.
- Base game addon GUID: `58D0FB3206B6F859`. Target game version: the one recorded
  for `scripts` in `docs/vendor/sources.json`.
- Blender is reachable through the project MCP server `blender` (`.mcp.json`,
  package `mcp-for-blender`, socket `localhost:9876`). Blender must be running with the
  "MCP for Blender" addon enabled and its server started (N panel → MCP for Blender).

## Before writing Enforce Script

1. If `docs/vendor/` is missing, run `uv run tools/sync_docs.py`.
2. Look up real signatures instead of guessing: vanilla classes in
   `docs/vendor/scripts/scripts/Game`, engine API in `docs/vendor/scripts/scripts/Core`
   (and siblings). Wiki text in `docs/vendor/wiki`, sample mods in `docs/vendor/samples`.
3. Prefer `modded class` and prefab/config inheritance over copying vanilla files.
4. Prefix new classes with the addon's tag.
5. State clearly what was not verified in Workbench — nothing here compiles on macOS.

## Worklog

At the end of every session that changes the repo or reaches a decision, append an
entry to the end of `worklog.md` using the template at the top of that file. Keep it
factual: what was done, decisions and why, what was verified (and how), open issues,
next steps. Move durable, verified knowledge into `docs/notes/<topic>.md`.
