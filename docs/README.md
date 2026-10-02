# Arma Reforger docs

Local, greppable reference material for Arma Reforger / Enfusion modding.

`docs/vendor/` is gitignored. Fetch or refresh it with:

```bash
uv run tools/sync_docs.py
```

`docs/vendor/sources.json` records the commit (and game version) of each source.

## What's in `docs/vendor/`

| Path | Source | Use it for |
| --- | --- | --- |
| `scripts/scripts/Game/` | [Arma-Reforger-Script-Diff](https://github.com/BohemiaInteractive/Arma-Reforger-Script-Diff) | Vanilla game scripts (`SCR_*`). Commit subject = game version. |
| `scripts/scripts/Core/proto/`, `GameLib/`, … | same | Engine API declarations (`proto native`) — the Script API surface |
| `scripts-experimental/` | [Script-Diff-Experimental](https://github.com/BohemiaInteractive/Arma-Reforger-Script-Diff-Experimental) | Same, Experimental branch (opt-in: `sync_docs.py scripts-experimental`) |
| `samples/` | [Arma-Reforger-Samples](https://github.com/BohemiaInteractive/Arma-Reforger-Samples) | Official sample mods: new prop/weapon/car/faction/character, modded script, Workbench plugin (text resources only) |
| `misc/` | [Arma-Reforger-Misc](https://github.com/BohemiaInteractive/Arma-Reforger-Misc) | Rigs, animation, terrain, weapon config resources. `.blend` rigs only with `--with-art` (GBs) |
| `wiki/` | BI Community Wiki export via [enfusion-mcp-BK](https://github.com/steffenbk/enfusion-mcp-BK) | 250+ wiki pages as plain text; `wiki/INDEX.md` lists them. Snapshot from Feb 2026 — each page links its live URL |
| `notes/` | [arma-reforger-modding](https://github.com/Mavericktfius/arma-reforger-modding) | Community field notes: Blender→Enfusion export, rigging, terrain, QA |

## Searching

```bash
rg -n "class SCR_BaseGameMode\b" docs/vendor/scripts
rg -n "proto.*GetWorld" docs/vendor/scripts/scripts/Core
rg -il "fbx import" docs/vendor/wiki docs/vendor/notes
rg -n --glob "*.et" "SCR_EditableEntityComponent" docs/vendor/samples
```

## Other references (online)

- BI Community Wiki — [Arma Reforger modding](https://community.bistudio.com/wiki/Category:Arma_Reforger/Modding) (browser only; blocks scripted access)
- Script API (Doxygen) — ships with Arma Reforger Tools under `Workbench/docs/` (`ArmaReforgerScriptAPIPublic`, `EnfusionScriptAPIPublic`)
- [Enfusion Script guidelines](https://community.bistudio.com/wiki/Category:Arma_Reforger/Modding/Scripting/Guidelines)
- [Bohemia feedback tracker](https://feedback.bistudio.com)

## Our own notes

Distilled, verified learnings from experiments go in `docs/notes/<topic>.md` (committed).
Session-by-session history goes in [`../worklog.md`](../worklog.md).
