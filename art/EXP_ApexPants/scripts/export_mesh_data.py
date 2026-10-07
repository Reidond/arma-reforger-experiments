"""Dump a mesh's triangles, smooth normals, UVs and MikkTSpace tangents to .npz.

Run inside Blender; gen_textures.py reads the result. Uses the rest (undisplaced)
mesh so texture features and vertex displacement share one coordinate frame.
"""

import os

import bpy
import numpy as np

OBJ = globals().get("OBJ") or ("Pants_full" if "Pants_full" in bpy.data.objects else "Pants_base")
OUT = globals().get("OUT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "build", "pants_base.npz")


def export(obj_name=OBJ, out=OUT):
    ob = bpy.data.objects[obj_name]
    me = ob.data
    uv = me.uv_layers.active
    me.calc_loop_triangles()
    me.calc_tangents(uvmap=uv.name)

    nv, nl, nt = len(me.vertices), len(me.loops), len(me.loop_triangles)
    co = np.empty(nv * 3, np.float32)
    me.vertices.foreach_get("co", co)
    vnor = np.empty(nv * 3, np.float32)
    me.vertices.foreach_get("normal", vnor)
    luv = np.empty(nl * 2, np.float32)
    uv.data.foreach_get("uv", luv)
    ltan = np.empty(nl * 3, np.float32)
    me.loops.foreach_get("tangent", ltan)
    lsign = np.empty(nl, np.float32)
    me.loops.foreach_get("bitangent_sign", lsign)
    lvert = np.empty(nl, np.int32)
    me.loops.foreach_get("vertex_index", lvert)
    tri_loops = np.empty(nt * 3, np.int32)
    me.loop_triangles.foreach_get("loops", tri_loops)

    extra = {}
    for name in ("part_id", "part_fabric"):
        if name in me.attributes:
            arr = np.zeros(nv, np.int32)
            me.attributes[name].data.foreach_get("value", arr)
            extra[name] = arr
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    np.savez_compressed(
        out,
        co=co.reshape(-1, 3), vnor=vnor.reshape(-1, 3),
        uv=luv.reshape(-1, 2), tan=ltan.reshape(-1, 3), sign=lsign,
        lvert=lvert, tri=tri_loops.reshape(-1, 3), **extra,
    )
    me.free_tangents()
    print("exported", obj_name, nv, "verts", nt, "tris ->", os.path.abspath(out))


export()
