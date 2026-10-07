"""Sample the base trousers surface on a (side, phi, z) grid (run inside Blender).

For every grid point a ray is cast from the leg axis outwards (the axis follows
apex_common.LEG_CENTRE); the first surface it leaves through is the outer shell. Saves
build/surface_grid.npz with the hit point, normal, triangle vertex ids and barycentrics in the
same loop-triangle convention as export_mesh_data.py, so photo_lookup.py can project photos
onto it and build_parts.py can map (phi, z) back to 3D.
"""

import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
import importlib  # noqa: E402

import apex_common as C  # noqa: E402

importlib.reload(C)

ART = os.path.normpath(os.path.join(SCRIPTS, ".."))
PHI_STEP = 1.0      # degrees
Z_STEP = 0.0025     # metres
Z0, Z1 = 0.08, 1.07


def leg_axis(z):
    cx, cy = C.leg_centre(z)
    return cx, cy


def sample(obj_name="Pants_base"):
    ob = bpy.data.objects[obj_name]
    me = ob.data
    me.calc_loop_triangles()
    bvh = BVHTree.FromObject(ob, bpy.context.evaluated_depsgraph_get())
    tri_of_poly = {}
    for lt in me.loop_triangles:
        tri_of_poly.setdefault(lt.polygon_index, []).append(lt)
    phis = np.arange(-180.0, 180.0, PHI_STEP)
    zs = np.arange(Z0, Z1 + 1e-9, Z_STEP)
    out = {k: [] for k in ("side", "phi", "z", "co", "no", "tv", "bary", "hit")}
    verts = me.vertices
    for s in (-1, 1):
        for z in zs:
            cx, cy = leg_axis(z)
            org0 = Vector((s * cx, cy, z))
            for ph in phis:
                r = math.radians(ph)
                d = Vector((s * math.sin(r), -math.cos(r), 0.0))
                org = org0.copy()
                hit = None
                for _ in range(6):
                    loc, nor, idx, dist = bvh.ray_cast(org, d, 0.6)
                    if loc is None:
                        break
                    if nor.dot(d) > 0:      # leaving the solid: outer shell
                        hit = (loc, nor, idx)
                        break
                    org = loc + d * 1e-4
                out["side"].append(s)
                out["phi"].append(ph)
                out["z"].append(z)
                if hit is None:
                    out["hit"].append(False)
                    out["co"].append((0, 0, 0))
                    out["no"].append((0, 0, 1))
                    out["tv"].append((0, 0, 0))
                    out["bary"].append((1, 0, 0))
                    continue
                loc, nor, idx = hit
                best = None
                for lt in tri_of_poly[idx]:
                    a, b, c = (verts[i].co for i in lt.vertices)
                    v0, v1, v2 = b - a, c - a, loc - a
                    d00, d01, d11 = v0.dot(v0), v0.dot(v1), v1.dot(v1)
                    d20, d21 = v2.dot(v0), v2.dot(v1)
                    den = d00 * d11 - d01 * d01
                    if den == 0:
                        continue
                    w1 = (d11 * d20 - d01 * d21) / den
                    w2 = (d00 * d21 - d01 * d20) / den
                    w0 = 1 - w1 - w2
                    err = -min(w0, w1, w2)
                    if best is None or err < best[0]:
                        best = (err, tuple(lt.vertices), (w0, w1, w2))
                out["hit"].append(True)
                out["co"].append(tuple(loc))
                out["no"].append(tuple(nor))
                out["tv"].append(best[1])
                out["bary"].append(best[2])
    np.savez_compressed(
        os.path.join(ART, "build", "surface_grid.npz"),
        side=np.array(out["side"], np.int8), phi=np.array(out["phi"], np.float32),
        z=np.array(out["z"], np.float32), co=np.array(out["co"], np.float32),
        no=np.array(out["no"], np.float32), tv=np.array(out["tv"], np.int64),
        bary=np.array(out["bary"], np.float32), hit=np.array(out["hit"], bool),
        phis=phis.astype(np.float32), zs=zs.astype(np.float32))
    print("surface grid:", len(out["hit"]), "samples,", int(np.sum(out["hit"])), "hits")


sample()
