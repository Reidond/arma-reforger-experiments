# Experiments: MCDU APEX Pants (Multicam)

- Addon ID: `EXP_ApexPants`
- GUID: `C4A331D81B532878`

## Purpose

Wearable MCDU APEX combat trousers in Multicam for Arma Reforger, built from product
photos with a scripted Blender pipeline (sources and scripts in `art/EXP_ApexPants/`).

## Contents

| Resource | GUID | Notes |
| --- | --- | --- |
| `Prefabs/Characters/Uniforms/Pants_MCDU_APEX.et` | `44201A94191F5B27` | Inventory item; inherits vanilla `Pants_M88.et` (`DCF980831E880F6A`) for pockets/storage, overrides meshes and name |
| `Prefabs/Characters/Uniforms/Pants_MCDU_APEX_Wear.et` | `11EB171F8C8D6175` | Worn model |
| `Prefabs/Characters/Uniforms/Pants_MCDU_APEX_Item.et` | `EC46F4D24DBFB888` | Dropped item model |
| `Assets/.../Pants_MCDU_APEX.fbx` → `.xob` | `4EEB0A1B18F90C38` | Skeleton + skinned LOD0–LOD3, material `Pants_MCDU_APEX` |
| `Assets/.../Pants_MCDU_APEX_item.fbx` → `.xob` | `A8D1B46D3F06A607` | Flat item mesh + `UBX_Item` (`ItemFireView`) |
| `Assets/.../Data/Pants_MCDU_APEX.emat` | `EC98A1EF5B15F6EC` | `MatPBRBasic`, BCR + NMO |
| `Assets/.../Data/Pants_MCDU_APEX_{BCR,NMO}.tif` → `.edds` | `92FB95F4BD2BB523`, `92C0B51CC3D8E5F9` | 4096², DirectX normals |

The `.meta` files were written by hand (format copied from the official samples) so the
GUIDs above are fixed before the first Workbench import.

## First run in Workbench (Windows) — not verified yet

1. Open `addon.gproj`.
2. Resource Browser → register and import the two TIFs and the two FBX files (keep the
   existing `.meta` files). Check the worn `.xob` import settings: *Export Skinning* and
   *Export Scene Hierarchy* on, material assigned to `Pants_MCDU_APEX.emat`.
3. Open `Pants_MCDU_APEX_Wear.et` / place `Pants_MCDU_APEX.et` and put it on a character
   (e.g. in a loadout or the character's `BaseLoadoutManagerComponent` slot).
4. Optional: add a cloth game material to `UBX_Item` in the item `.xob` import settings.
