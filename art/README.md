# Art sources

Blender working files (`.blend`), Substance projects, and source textures, grouped
per addon: `art/<AddonID>/...`. Binary files are stored with Git LFS (see
`.gitattributes`).

Workflow: model in Blender (optionally via the `blender` MCP server) → export FBX
into `mods/<AddonID>/Assets/...` → import in Workbench (creates `.xob` + `.meta`).

Export rules: [FBX Import](../docs/vendor/wiki/FBX_Import.md) and
[Blender export notes](../docs/vendor/notes/blender-export.md) (after `tools/sync_docs.py`).
