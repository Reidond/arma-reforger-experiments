# Clothing pipeline (Blender on macOS → Reforger)

Learned while building `EXP_ApexPants` (MCDU APEX trousers). "Verified" means checked
in Blender 5.2 on macOS; nothing here has been through Workbench yet.

## Body and skeleton

- Use `SampleMod_NewCharacter/Assets/Characters/SampleCharacter/Character_Weights_Template.blend`
  from the samples repo. `tools/sync_docs.py` clones samples without binaries; fetch the
  blob with `git -C docs/vendor/samples show HEAD:<path> > file` (25 MB, not LFS).
  It holds `Body_LOD0` (skinned, 189 groups), `Armature` (224 bones, at the origin,
  identity transform), IK-target empties and body colliders. Character faces −Y, left is +X,
  metres. *Verified.*
- Body mesh is split along UV seams: merge by distance (0.5 mm) before cutting shells
  from it, otherwise you get disconnected strips. *Verified.*
- Leg bones are `LeftLeg` (thigh, from the hip), `LeftKnee`, `LeftKneeTwist`, `LeftFoot`;
  there are dedicated cloth helpers `LeftLegClothF/B`. *Verified (names).*

## Shape

- Building trousers from the body's own topology (cut, inflate, relax, subdivide) gives
  clean quads that deform well. QuadriFlow welded the inner thighs below the crotch, so
  avoid it there. *Verified.*
- Laplacian smoothing shrinks boundary loops — exclude hem/waist boundary vertices or the
  cuffs end up narrower than the leg (looked like joggers). *Verified.*

## Textures

- `MatPBRBasic` with `BCRMap` (RGB colour + A roughness) and `NMOMap` (RG normal DirectX,
  B metal, A AO) — as in the sample vest. Vanilla trousers use `MatPBRCamo` with
  `CavityFromAO 1`.
- Baking analytic detail in numpy: rasterise UV triangles, interpolate rest positions /
  normals / MikkTSpace tangents (`mesh.calc_tangents`), evaluate features per texel, then
  convert height to tangent normals with the per-triangle Jacobian dP/d(uv). 4K takes
  ~40 s on an M-series Mac. *Verified visually in Cycles.*
- Codex image generation produces usable camo swatches but lighter/more yellow and lower in
  contrast than the photos; colour-transfer them to stats measured on the product photos.

## Skinning and export

- Weight transfer: Data Transfer modifier from `Body_LOD0`, `POLYINTERP_NEAREST`, all
  groups by name; then move foot/toe weights to `*KneeTwist` (hem should not follow the
  foot), drop arm/hand/head groups, smooth over the mesh, keep 4 influences, normalise.
  Posed stride showed no tearing or skin poke-through (body tinted red). *Verified.*
- Blender FBX export that re-imports cleanly: object types Armature/Mesh/Empty, custom
  properties on, no leaf bones, no animation, smoothing `FACE`, scale `FBX_SCALE_NONE`,
  `-Z` forward / `Y` up, meshes parented to the armature with an Armature modifier.
  Round-trip kept 224 bones, LOD names, material name and the `usage` property on
  `UBX_Item`. *Verified in Blender; Workbench import not verified.*
- Prefab structure to copy: `SampleMod_NewFaction/Prefabs/Characters/Uniforms/Pants_M88_*`
  — item prefab inherits vanilla `{DCF980831E880F6A}Prefabs/Characters/Uniforms/Pants_M88.et`,
  `BaseLoadoutClothComponent` points at separate Wear and Item prefabs.
- Item model collider: `UBX_Item` with LayerPreset `ItemFireView` (sample vest item).
