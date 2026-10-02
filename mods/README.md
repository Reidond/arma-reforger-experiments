# Mods

One Arma Reforger addon per directory: `mods/<AddonID>/addon.gproj`.

Create one with:

```bash
uv run tools/new_mod.py EXP_Sandbox --title "Experiments: Sandbox"
```

This writes `addon.gproj` with a random 16-hex GUID and a dependency on the base
game (`58D0FB3206B6F859`). Open the `.gproj` in Arma Reforger Workbench (Windows)
to finish setup; commit any files Workbench generates (`.meta`, `.et`, `.conf`, …)
except `*.rdb`.

## Layout inside an addon

Follow the base game's layout so resource paths stay familiar:

```
mods/<AddonID>/
  addon.gproj
  Scripts/Game/<AddonID>/   Enforce Script (.c)
  Prefabs/                  .et prefabs
  Configs/                  .conf
  Assets/                   imported models (.fbx → .xob), textures (.tif → .edds), materials (.emat)
  Worlds/                   .ent worlds and layers
  Missions/                 mission headers (.conf)
```

## Conventions

- Prefix every new script class with the addon's tag (e.g. `EXP_`) to avoid clashes.
- Change vanilla behaviour with `modded class`, never by copying vanilla files.
- Override vanilla prefabs/configs by inheritance, not duplication.
- Cross-addon dependencies go in `Dependencies` by GUID.
- Blender source files live in `art/<AddonID>/`; only exported FBX/TIF go into the addon.
