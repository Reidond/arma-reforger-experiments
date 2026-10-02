# Worklog

History of AI-assisted work on this repo. Append new entries at the end (oldest first).

<!--
Entry template:

## YYYY-MM-DD — <short title>

- **Agent:** <tool / model>
- **Goal:** <what the user asked for>
- **Done:** <changes, with paths>
- **Decisions:** <choice — why>
- **Verified:** <what was checked and how> / **Not verified:** <what still needs Workbench, game, or a human>
- **Next:** <open issues, follow-ups>
-->

## 2026-10-02 — Repository bootstrap

- **Agent:** Claude Code (Opus 5.5)
- **Goal:** Set up git repo, Arma Reforger docs, project-scoped Blender MCP, this worklog, and a mods monorepo.
- **Done:**
  - `git init` (branch `main`), Git LFS hooks installed locally; `.gitattributes` sends `.blend/.fbx/.xob/.edds/.tif/...` to LFS, text resources stay in git with LF endings.
  - `tools/sync_docs.py` fetches reference material into gitignored `docs/vendor/`: vanilla scripts (Script-Diff, game 1.8.0.13), official samples and misc repos (sparse, text only), a 258-page BI wiki export, and community Blender/rigging notes. Index in `docs/README.md`.
  - `.mcp.json` registers the `blender` MCP server (`uvx mcp-for-blender@2.1.3`, `localhost:9876`, telemetry off).
  - Monorepo layout: `mods/<AddonID>/` addons (`tools/new_mod.py` scaffolds `addon.gproj` with a random GUID + base game dependency), `art/<AddonID>/` for Blender sources.
  - `AGENTS.md` (+ `CLAUDE.md` importing it) with layout, doc lookup rules and the worklog rule.
- **Decisions:**
  - Docs are fetched, not committed — Bohemia content is under the Arma Public License, and the vendored repos are large (Samples 1.3 GB, Misc 3.7 GB); sparse text-only clones keep `docs/vendor/` around 175 MB.
  - BI Community Wiki blocks scripted access (Cloudflare challenge, HTTP 403), so the wiki comes from the pinned export in `steffenbk/enfusion-mcp-BK` (Feb 2026 snapshot).
  - `mcp-for-blender` is pinned (it runs arbitrary Python inside Blender); bump the version in `.mcp.json` deliberately.
  - Addon layout and `addon.gproj` format follow the user's `Reidond/stavka` repo; Blender sources kept outside addons so they are never packed.
- **Verified:** `sync_docs.py` clean run and re-run (update path); `new_mod.py` creates a valid-looking `addon.gproj` and rejects bad names, duplicate addons, and bad GUIDs; `uvx mcp-for-blender@2.1.3 --help` runs; `claude mcp get blender` shows the server as a pending project server.
  Blender 5.2.2 add-on installed (`install-addon`) and connected on port 9876; a raw socket `get_scene_info` call returned the default scene (Cube, Light, Camera).
  After a Claude Code restart, the `blender` MCP tools work end to end: `get_addon_status` (addon 1.8, protocol 13, up to date, telemetry off), `get_scene_info`, `get_viewport_screenshot`.
- **Not verified:** No addon has been opened in Workbench yet.
- **Next:** Create the first experiment addon, decide on a remote (GitHub) for the repo.
