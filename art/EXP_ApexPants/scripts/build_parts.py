"""Build the 3D parts (pockets, flaps, waistband, belt loops, straps, zips, pulls) as real
geometry on the trouser shell, then assemble Pants_full = shell + parts with packed UVs.

Run inside Blender after build_base.py:
    p = "<repo>/art/EXP_ApexPants/scripts/build_parts.py"
    exec(compile(open(p).read(), p, "exec"), {"__file__": p, "__name__": "__main__"})

Parts are laid out in surface coordinates (apex_parts.py): a ray from the leg axis (or the
pelvis axis for waistband/loops) at angle phi and height z finds the shell point; the part
surface is that point pushed out along the shell normal by a profile, then solidified.
"""

import importlib
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
import apex_common as C  # noqa: E402
import apex_parts as AP  # noqa: E402

importlib.reload(C)
importlib.reload(AP)

SHELL = bpy.data.objects["Pants_base"]
COLL = SHELL.users_collection[0]
GRID = 0.006            # target edge length of part grids (m)
_bvh = None


def bvh():
    global _bvh
    if _bvh is None:
        _bvh = BVHTree.FromObject(SHELL, bpy.context.evaluated_depsgraph_get())
    return _bvh


def cast(origin, d):
    """First exit hit of a ray leaving the shell; returns (point, normal) or (None, None)."""
    org = origin.copy()
    for _ in range(8):
        loc, nor, idx, dist = bvh().ray_cast(org, d, 0.6)
        if loc is None:
            return None, None
        if nor.dot(d) > 0:
            return loc, nor
        org = loc + d * 1e-4
    return None, None


def leg_point(s, phi, z):
    cx, cy = C.leg_centre(z)
    r = math.radians(phi)
    d = Vector((s * math.sin(r), -math.cos(r), 0.0))
    p, n = cast(Vector((s * cx, cy, z)), d)
    if p is None:
        return None, None, d
    return p, n, d


def pelvis_point(th, z):
    r = math.radians(th)
    d = Vector((math.sin(r), -math.cos(r), 0.0))
    p, n = cast(Vector((0.0, 0.012, z)), d)
    return p, n, d


def waist_top(y):
    t = (min(max(y, -0.11), 0.13) + 0.11) / 0.24
    return 1.000 + t * 0.045 + 0.003


def sstep(e0, e1, x):
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


# --------------------------------------------------------------------------- grid builder
_part_counter = [0]

# fabric codes = apex_features material codes
CAMO, TAPE, WEBBING, METAL = 0, 3, 7, 5


def grid_part(name, nu, nv, sample, thick, uv_scale=1.0, walls=True, solid=False, fabric=CAMO):
    """sample(i, j) -> (top point or None, (u_m, v_m)).

    walls=True:  top surface + side walls down to the trouser shell (pockets, bands, patches).
    solid=True:  top surface + an underside `thick` below it + rim walls (flaps, belt loops) —
                 a real slab you can see under/through.
    walls=False and solid=False: free-standing piece, solidified (zip pulls).
    Every visible face gets its own UV space; vertices carry part_id / part_fabric attributes.
    """
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    top, uvs = {}, {}
    for j in range(nv + 1):
        for i in range(nu + 1):
            p, uv = sample(i, j)
            if p is None:
                continue
            top[i, j] = bm.verts.new(p)
            uvs[i, j] = uv
    tops = []
    for j in range(nv):
        for i in range(nu):
            q = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
            if all(k in top for k in q):
                f = bm.faces.new([top[k] for k in q])
                tops.append(f)
                for lp, k in zip(f.loops, q):
                    lp[uvl].uv = (uvs[k][0] * uv_scale, uvs[k][1] * uv_scale)

    def shell_normal(co):
        loc, nor, _, _ = bvh().find_nearest(co)
        return loc, nor

    bottom = {}
    if solid and tops:
        for k, v in top.items():
            loc, nor = shell_normal(v.co)
            bottom[k] = bm.verts.new(v.co - nor * thick if nor is not None else v.co)
        for j in range(nv):
            for i in range(nu):
                q = [(i, j), (i, j + 1), (i + 1, j + 1), (i + 1, j)]      # reversed winding
                if all(k in bottom for k in q):
                    f = bm.faces.new([bottom[k] for k in q])
                    for lp, k in zip(f.loops, q):
                        lp[uvl].uv = ((uvs[k][0] + 100.0) * uv_scale, uvs[k][1] * uv_scale)
    if (walls or solid) and tops:
        perim = ([(i, 0) for i in range(nu + 1)] + [(nu, j) for j in range(1, nv + 1)]
                 + [(i, nv) for i in range(nu - 1, -1, -1)] + [(0, j) for j in range(nv - 1, 0, -1)])
        perim = [k for k in perim if k in top]
        perim.append(perim[0])
        base, acc, U0 = {}, 0.0, 50.0
        for k in set(perim):
            if solid:
                base[k] = bottom[k]
            else:
                loc, nor = shell_normal(top[k].co)
                base[k] = bm.verts.new(loc - nor * 0.0006) if loc is not None else bm.verts.new(top[k].co)
        for a, b in zip(perim[:-1], perim[1:]):
            if a == b:
                continue
            ta, tb, ba, bb = top[a], top[b], base[a], base[b]
            seg = (tb.co - ta.co).length
            ha, hb = (ta.co - ba.co).length, (tb.co - bb.co).length
            try:
                f = bm.faces.new((ta, ba, bb, tb))
            except ValueError:
                continue
            if acc > 0.08:          # short strips pack far better than one long ribbon
                U0 += 1.0
                acc = 0.0
            for lp, uv in zip(f.loops, ((U0 + acc, ha), (U0 + acc, 0.0), (U0 + acc + seg, 0.0), (U0 + acc + seg, hb))):
                lp[uvl].uv = (uv[0] * uv_scale, uv[1] * uv_scale)
            acc += seg
    # hard edges where the top meets walls / undersides: crisp part outlines, no "rod" shading
    top_set = set(tops)
    for e in bm.edges:
        lf = e.link_faces
        if len(lf) == 2 and ((lf[0] in top_set) != (lf[1] in top_set)):
            e.smooth = False
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.normal_update()
    score = 0.0
    for f in tops:
        loc, nor = shell_normal(f.calc_center_median())
        if loc is not None:
            score += f.normal.dot(nor) * f.calc_area()
    if score < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    COLL.objects.link(ob)
    if not walls and not solid and thick > 0:
        mod = ob.modifiers.new("Solid", "SOLIDIFY")
        mod.thickness = thick
        mod.offset = -1.0
        mod.use_even_offset = True
        mod.use_rim = True
        with bpy.context.temp_override(object=ob, active_object=ob):
            bpy.ops.object.modifier_apply(modifier=mod.name)
    for p in ob.data.polygons:
        p.use_smooth = True
    _part_counter[0] += 1
    n = len(ob.data.vertices)
    for attr, val in (("part_id", _part_counter[0]), ("part_fabric", fabric + 1)):
        a = ob.data.attributes.new(attr, "INT", "POINT")
        a.data.foreach_set("value", [val] * n)
    return ob


def counts(span_m, step=GRID):
    return max(2, int(round(span_m / step)))


# --------------------------------------------------------------------------- per-kind samplers
def quad_phi_z(part, u, v):
    """Bilinear (phi, z) inside a quad with possibly sloped bottom/top edges."""
    if "zb0" in part:
        zb = part["zb0"] + (part["zb1"] - part["zb0"]) * u
        zt = part["zt0"] + (part["zt1"] - part["zt0"]) * u
    else:
        zb, zt = part["z0"], part["z1"]
    phi = part["phi0"] + (part["phi1"] - part["phi0"]) * u
    return phi, zb + (zt - zb) * v


def pocket_offset(part, s, phi, z, R):
    """Bellows pocket bag: steep sides, slightly domed face, raised box pleat."""
    if part is None:
        return 0.0
    if not (part["phi0"] <= phi <= part["phi1"] and part["z0"] <= z <= part["z1"]):
        return 0.0
    dphi = min(phi - part["phi0"], part["phi1"] - phi)
    dz = min(z - part["z0"], part["z1"] - z)
    edge = min(math.radians(dphi) * R, dz)
    sw = part["side_w"]
    o = 0.6 * AP.MM + part["depth"] * sstep(0.0, sw, edge)
    # dome a little towards the bottom (contents sag)
    v = (z - part["z0"]) / (part["z1"] - part["z0"])
    o += part.get("dome", 0.25) * part["depth"] * math.sin(math.pi * min(1.0, max(0.0, v))) * sstep(0.0, sw, edge)
    p0, p1 = part.get("pleat", (None, None))
    if p0 is not None and p0 <= phi <= p1:
        a = math.radians(min(phi - p0, p1 - phi)) * R
        o += 1.6 * AP.MM * sstep(0.0, 0.003, a) * sstep(0.0, 0.01, dz)
    return o


PARTS_BY_NAME = {p["name"]: p for p in AP.PARTS}


def build_leg_part(part, s):
    kind = part["kind"]
    name = f"Part_{part['name']}_{'L' if s > 0 else 'R'}"
    R_est = 0.10
    span_phi = abs(part.get("phi1", 0) - part.get("phi0", 0))
    if kind == "tab":
        return build_tab(part, s, name)
    zspan = max(part.get("z1", part.get("zt1", 0.8)) - part.get("z0", part.get("zb0", 0.7)), 0.01)
    nu = counts(math.radians(span_phi) * R_est)
    nv = counts(zspan)
    under = PARTS_BY_NAME.get(part.get("under")) if kind == "flap" else None

    def sample(i, j):
        u, v = i / nu, j / nv
        phi, z = quad_phi_z(part, u, v)
        p, n, d = leg_point(s, phi, z)
        if p is None:
            return None, None
        cx, cy = C.leg_centre(z)
        R = math.hypot(p.x - s * cx, p.y - cy)
        if kind == "pocket":
            off = pocket_offset(part, s, phi, z, R)
        elif kind == "flap":
            off = pocket_offset(under, s, phi, min(z, under["z1"] - 1e-4) if under else z, R)
            off = max(off, 0.6 * AP.MM) + part["thick"] + 0.6 * AP.MM + part["lift"] * (1 - v) ** 2
        elif kind == "band":
            off = part["off"]
            if part.get("dome"):
                off += part["dome"] * math.sin(math.pi * u) ** 0.7 * math.sin(math.pi * v) ** 0.7
        else:   # patch
            off = part["off"]
        uvc = (math.radians(phi) * R, z)
        return p + n * (off + part.get("thick", 1.5 * AP.MM)), uvc

    fabric = {"camo": CAMO, "tape": TAPE, "webbing": WEBBING}[part.get("fabric", "camo")]
    return grid_part(name, nu, nv, sample, part.get("thick", 1.5 * AP.MM),
                     solid=(kind == "flap"), walls=(kind != "flap"), fabric=fabric)


def build_tab(part, s, name):
    """Hanging pull/tab: a short slab hanging from (phi, z), standing slightly off the leg."""
    p, n, d = leg_point(s, part["phi"], part["z"])
    if p is None:
        return None
    down = Vector((0, 0, -1))
    side = n.cross(down).normalized()
    w, L = part["width"], part["length"]
    nu, nv = 3, max(3, int(L / 0.006))

    def sample(i, j):
        u, v = i / nu - 0.5, j / nv
        taper = 1.0 - 0.35 * v
        q = p + n * (part["out"] * (0.4 + 0.6 * v)) + side * (u * w * taper) + down * (v * L)
        return q, ((u + 0.5) * w, v * L)

    return grid_part(name, nu, nv, sample, part["thick"], walls=False, fabric=WEBBING)


def build_waistband():
    wb = AP.WAISTBAND
    nth = 140
    nv = 7

    def sample(i, j):
        th = -180.0 + 360.0 * i / nth
        p0, _, _ = pelvis_point(th, 1.0)
        if p0 is None:
            return None, None
        top = waist_top(p0.y) - 0.0035
        z = top - wb["height"] * (1 - j / nv)
        p, n, d = pelvis_point(th, z)
        if p is None:
            return None, None
        # rounded top edge
        bulge = math.sin(math.pi * 0.5 * min(1.0, (j / nv) * 1.4))
        return p + n * (wb["off"] + wb["thick"] * (0.6 + 0.4 * bulge)), (math.radians(th) * 0.17, z)

    return grid_part("Part_Waistband", nth, nv, sample, wb["thick"])


def build_loops():
    bl = AP.BELT_LOOPS
    wb = AP.WAISTBAND
    obs = []
    angles = [a for t in bl["thw"] for a in (t, -t)] + ([180.0] if bl["centre_back"] else [])
    for k, th0 in enumerate(angles):
        nu, nv = 3, 10

        def sample(i, j, th0=th0):
            p0, _, _ = pelvis_point(th0, 1.0)
            if p0 is None:
                return None, None
            Rw = math.hypot(p0.x, p0.y - 0.012)
            dth = math.degrees((i / nu - 0.5) * bl["width"] / Rw)
            top = waist_top(p0.y) - 0.002
            z = top - bl["height"] * (j / nv)
            p, n, d = pelvis_point(th0 + dth, z)
            if p is None:
                return None, None
            v = j / nv
            stand = wb["off"] + wb["thick"] + 0.8 * AP.MM + bl["off"] * math.sin(math.pi * v) ** 0.5
            return p + n * stand, ((i / nu) * bl["width"], z)

        obs.append(grid_part(f"Part_BeltLoop_{k}", nu, nv, sample, bl["thick"], walls=False, solid=True))
    return obs


def build_all():
    _part_counter[0] = 0
    for o in list(bpy.data.objects):
        if o.name.startswith("Part_") or o.name in ("Pants_parts", "Pants_full"):
            bpy.data.objects.remove(o, do_unlink=True)
    for m in list(bpy.data.meshes):
        if m.users == 0:
            bpy.data.meshes.remove(m)
    obs = [build_waistband()] + build_loops()
    for part in AP.PARTS:
        for s in (-1, 1):
            ob = build_leg_part(part, s)
            if ob is not None:
                obs.append(ob)
    obs = [o for o in obs if o is not None and len(o.data.vertices)]
    # join parts
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[0]
    bpy.ops.object.join()
    parts = bpy.context.view_layer.objects.active
    parts.name = parts.data.name = "Pants_parts"
    print("parts:", len(parts.data.vertices), "verts", sum(len(p.vertices) - 2 for p in parts.data.polygons), "tris")
    return parts


def assemble(parts):
    """Pants_full = shell + parts (shell vertices first), one UV atlas."""
    full = SHELL.copy()
    full.data = SHELL.data.copy()
    full.name = full.data.name = "Pants_full"
    COLL.objects.link(full)
    # one UV layer only: the shell's active one (body leftovers removed), parts renamed to match
    keep = full.data.uv_layers.active.name
    for lay in [l for l in full.data.uv_layers if l.name != keep]:
        full.data.uv_layers.remove(lay)
    full.data.uv_layers[keep].name = "UVMap"
    pc = parts.copy()
    pc.data = parts.data.copy()
    COLL.objects.link(pc)
    pc.data.uv_layers.active.name = "UVMap"
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    full.select_set(True)
    pc.select_set(True)
    bpy.context.view_layer.objects.active = full
    bpy.ops.object.join()
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, rotate_method="CARDINAL", margin_method="FRACTION",
                            margin=0.003, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")
    for p in full.data.polygons:
        p.use_smooth = True
    print("UV layers:", full.data.uv_layers.keys())
    SHELL.hide_set(True)
    parts.hide_set(True)
    print("Pants_full:", len(full.data.vertices), "verts", sum(len(p.vertices) - 2 for p in full.data.polygons), "tris",
          "(shell", len(SHELL.data.vertices), "verts first)")
    return full


assemble(build_all())
