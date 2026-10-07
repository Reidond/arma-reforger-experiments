"""Skin Pants_LOD0 to the Reforger skeleton, build LODs and the dropped-item model, export FBX.

Run inside Blender after setup_preview.py (needs Pants_LOD0, Body_LOD0, Armature):
    p = "<repo>/art/EXP_ApexPants/scripts/export_game.py"
    exec(compile(open(p).read(), p, "exec"), {"__file__": p, "__name__": "__main__"})

Writes into mods/EXP_ApexPants/Assets/Characters/Uniforms/Pants_MCDU_APEX/:
    Pants_MCDU_APEX.fbx       worn model: skeleton + skinned LOD0..LOD3
    Pants_MCDU_APEX_item.fbx  item lying on the ground + UBX_Item collider
"""

import math
import os

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

ART = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REPO = os.path.normpath(os.path.join(ART, "..", ".."))
OUT = os.path.join(REPO, "mods", "EXP_ApexPants", "Assets", "Characters", "Uniforms", "Pants_MCDU_APEX")
NAME = "Pants_MCDU_APEX"
LOD_RATIOS = (1.0, 0.5, 0.25, 0.12)
MAX_INFLUENCES = 4

# Bones the trousers must never follow (nearest-surface transfer can reach them).
EXCLUDE = ("Hand", "Arm", "Shoulder", "Head", "Neck", "Camera", "Eye", "Jaw", "tongue", "Pectoral")
# The hem sits around the ankle: let it follow the shin, not the foot.
REMAP = {"LeftFoot": "LeftKneeTwist", "LeftToe": "LeftKneeTwist",
         "RightFoot": "RightKneeTwist", "RightToe": "RightKneeTwist"}


def select_only(*objs):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def weights_matrix(ob):
    names = [g.name for g in ob.vertex_groups]
    W = np.zeros((len(ob.data.vertices), len(names)), np.float32)
    for v in ob.data.vertices:
        for g in v.groups:
            W[v.index, g.group] = g.weight
    return names, W


def write_weights(ob, names, W):
    ob.vertex_groups.clear()
    used = np.nonzero(W.max(0) > 0)[0]
    for j in used:
        vg = ob.vertex_groups.new(name=names[j])
        idx = np.nonzero(W[:, j] > 0)[0]
        for i in idx:
            vg.add([int(i)], float(W[i, j]), "REPLACE")


def clean_weights(names, W, nbr, smooth_iters=3):
    for j, n in enumerate(names):
        if any(k in n for k in EXCLUDE):
            W[:, j] = 0
    for src, dst in REMAP.items():
        if src in names and dst in names:
            W[:, names.index(dst)] += W[:, names.index(src)]
            W[:, names.index(src)] = 0
    # cloth does not follow individual muscles: relax the weights over the surface
    for _ in range(smooth_iters):
        avg = np.stack([W[n].mean(0) if len(n) else W[i] for i, n in enumerate(nbr)])
        W = 0.5 * W + 0.5 * avg
    # keep the strongest influences and normalise
    if W.shape[1] > MAX_INFLUENCES:
        cut = -np.sort(-W, axis=1)[:, MAX_INFLUENCES - 1:MAX_INFLUENCES]
        W = np.where(W >= cut, W, 0)
    W[W < 0.01] = 0
    s = W.sum(1, keepdims=True)
    W = np.where(s > 0, W / np.maximum(s, 1e-9), W)
    return W


def skin(ob, body, arm):
    for m in list(ob.modifiers):
        ob.modifiers.remove(m)
    ob.vertex_groups.clear()
    select_only(ob)
    mod = ob.modifiers.new("WeightTransfer", "DATA_TRANSFER")
    mod.object = body
    mod.use_vert_data = True
    mod.data_types_verts = {"VGROUP_WEIGHTS"}
    mod.vert_mapping = "POLYINTERP_NEAREST"
    mod.layers_vgroup_select_src = "ALL"
    mod.layers_vgroup_select_dst = "NAME"
    bpy.ops.object.datalayout_transfer(modifier=mod.name)
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    nbr = [[e.other_vert(v).index for e in v.link_edges] for v in bm.verts]
    bm.free()
    names, W = weights_matrix(ob)
    write_weights(ob, names, clean_weights(names, W, nbr))
    attach(ob, arm)


def attach(ob, arm):
    am = ob.modifiers.get("Armature") or ob.modifiers.new("Armature", "ARMATURE")
    am.object = arm
    ob.parent = arm
    ob.matrix_parent_inverse = arm.matrix_world.inverted()


def make_lods(lod0, arm):
    lods = [lod0]
    for i, r in enumerate(LOD_RATIOS[1:], start=1):
        name = f"{NAME}_LOD{i}"
        old = bpy.data.objects.get(name)
        if old:
            bpy.data.meshes.remove(old.data)
        ob = lod0.copy()
        ob.data = lod0.data.copy()
        ob.data.name = name
        ob.name = name
        lod0.users_collection[0].objects.link(ob)
        for m in list(ob.modifiers):
            ob.modifiers.remove(m)
        select_only(ob)
        dec = ob.modifiers.new("Decimate", "DECIMATE")
        dec.decimate_type = "COLLAPSE"
        dec.ratio = r
        dec.use_symmetry = True
        dec.symmetry_axis = "X"
        bpy.ops.object.modifier_apply(modifier=dec.name)
        names, W = weights_matrix(ob)
        s = W.sum(1, keepdims=True)
        write_weights(ob, names, np.where(s > 0, W / np.maximum(s, 1e-9), W))
        attach(ob, arm)
        lods.append(ob)
    return lods


def item_model(src):
    """Trousers laid flat on the ground, front up, with a box collider for physics/pickup."""
    name = f"{NAME}_item_LOD0"
    for n in (name, "UBX_Item"):
        old = bpy.data.objects.get(n)
        if old:
            bpy.data.meshes.remove(old.data)
    me = src.data.copy()
    me.name = name
    ob = bpy.data.objects.new(name, me)
    src.users_collection[0].objects.link(ob)
    ob.vertex_groups.clear()
    bm = bmesh.new()
    bm.from_mesh(me)
    cy = sum(v.co.y for v in bm.verts) / len(bm.verts)
    for v in bm.verts:
        v.co.y = cy + (v.co.y - cy) * 0.22          # flatten front-to-back
    rot = Matrix.Rotation(math.radians(-90), 4, "X")  # lie down, front facing up
    bmesh.ops.transform(bm, matrix=rot, verts=bm.verts)
    xs = [v.co.x for v in bm.verts]
    ys = [v.co.y for v in bm.verts]
    zs = [v.co.z for v in bm.verts]
    off = Vector(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, min(zs)))
    bmesh.ops.translate(bm, vec=-off, verts=bm.verts)
    bm.to_mesh(me)
    bm.free()
    dims = Vector((max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)))

    cm = bpy.data.meshes.new("UBX_Item")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=dims * 0.95, verts=bm.verts)
    bm.to_mesh(cm)
    bm.free()
    col = bpy.data.objects.new("UBX_Item", cm)
    src.users_collection[0].objects.link(col)
    col.location = (0, 0, dims.z / 2)
    col["usage"] = "ItemFireView"
    col.display_type = "WIRE"
    return ob, col


def export_fbx(path, objs, skinned):
    select_only(*objs)
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, object_types={"ARMATURE", "MESH", "EMPTY"},
        use_custom_props=True, add_leaf_bones=False, bake_anim=False,
        mesh_smooth_type="FACE", use_mesh_modifiers=True, use_tspace=False,
        apply_unit_scale=True, apply_scale_options="FBX_SCALE_NONE",
        axis_forward="-Z", axis_up="Y", primary_bone_axis="Y", secondary_bone_axis="X",
        armature_nodetype="NULL", use_armature_deform_only=False,
    )
    print("exported", os.path.relpath(path, REPO), [o.name for o in objs], "skinned" if skinned else "static")


def main():
    body = bpy.data.objects["Body_LOD0"]
    arm = bpy.data.objects["Armature"]
    src = bpy.data.objects["Pants_LOD0"]
    mat = src.active_material

    lod0 = bpy.data.objects.get(f"{NAME}_LOD0")
    if lod0:
        bpy.data.meshes.remove(lod0.data)
    lod0 = src.copy()
    lod0.data = src.data.copy()
    lod0.name = lod0.data.name = f"{NAME}_LOD0"
    src.users_collection[0].objects.link(lod0)
    lod0.data.materials.clear()
    lod0.data.materials.append(mat)
    skin(lod0, body, arm)
    lods = make_lods(lod0, arm)
    for o in lods:
        print(o.name, len(o.data.polygons), "faces", sum(len(p.vertices) - 2 for p in o.data.polygons), "tris",
              len(o.vertex_groups), "bones")

    os.makedirs(OUT, exist_ok=True)
    helpers = [o for o in bpy.data.objects if o.type == "EMPTY" and (o.parent == arm or o.name == "EntityPosition")]
    export_fbx(os.path.join(OUT, f"{NAME}.fbx"), [arm, *helpers, *lods], True)

    item, col = item_model(lods[1])
    export_fbx(os.path.join(OUT, f"{NAME}_item.fbx"), [item, col], False)
    src.hide_set(True)
    item.hide_set(True)
    col.hide_set(True)


main()
