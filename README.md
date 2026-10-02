# Arma Reforger experiments

AI-assisted Arma Reforger modding experiments: a monorepo of addons, local reference
docs, and a Blender MCP setup.

## Setup

```bash
git lfs install --local
uv run tools/sync_docs.py
```

Blender MCP (project-scoped, `.mcp.json`):

1. Install Blender, then the addon: `uvx mcp-for-blender@2.1.3 install-addon`
2. In Blender: Edit → Preferences → Add-ons → enable **MCP for Blender**
3. N panel in the 3D viewport → **MCP for Blender** → Start MCP Server
4. Start Claude Code in this folder and approve the `blender` server

## Layout

- `mods/` — Reforger addons (`uv run tools/new_mod.py <AddonID>` to add one)
- `art/` — Blender and texture sources
- `docs/` — reference index and notes; `docs/vendor/` is fetched, not committed
- `worklog.md` — history of AI sessions
