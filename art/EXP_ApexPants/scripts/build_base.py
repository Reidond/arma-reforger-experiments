"""Build the base trouser mesh (Pants_base) around the Reforger template body.

Run inside Blender with the template body (Body_LOD0) in the scene:
    p = "<repo>/art/EXP_ApexPants/scripts/build_base.py"
    exec(compile(open(p).read(), p, "exec"), {"__file__": p, "__name__": "__main__"})

Steps: cut a shell from the body between waist and ankle, loosen it into a
regular-fit trouser shape, remesh to even quads, add hem and waistband
turn-ups, cut sewing-pattern UV seams and unwrap.
"""

import heapq
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
import importlib  # noqa: E402

import apex_common as C  # noqa: E402

importlib.reload(C)

BODY = bpy.data.objects["Body_LOD0"]
COLL = bpy.data.collections.get("Pants") or bpy.data.collections.new("Pants")
if COLL.name not in bpy.context.scene.collection.children:
    bpy.context.scene.collection.children.link(COLL)

WAIST_FRONT = Vector((0, -0.11, 1.000))
WAIST_BACK = Vector((0, 0.13, 1.045))
CUT_Z = 0.17
SUBD_LEVELS = 2      # ~70k shell triangles: seams, knee dome and folds as real geometry
KNEE_SEAM_Z = 0.610  # top edge of the knee band (a real seam on the garment)


def body_bmesh():
    bm = bmesh.new()
    bm.from_mesh(BODY.data)
    names = [m.name if m else None for m in BODY.data.materials]
    keep = names.index("Basebody_01_Male_Body")
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index != keep], context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.0005)
    bm.normal_update()
    return bm


def largest_component(bm):
    seen, comps = set(), []
    for f in bm.faces:
        if f in seen:
            continue
        stack, comp = [f], []
        seen.add(f)
        while stack:
            g = stack.pop()
            comp.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h not in seen:
                        seen.add(h)
                        stack.append(h)
        comps.append(comp)
    comps.sort(key=len, reverse=True)
    for c in comps[1:]:
        bmesh.ops.delete(bm, geom=c, context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")


def cut_shell(bm):
    d = WAIST_BACK - WAIST_FRONT
    n = Vector((0, -d.z, d.y)).normalized()
    if n.z < 0:
        n = -n
    geom = lambda: bm.verts[:] + bm.edges[:] + bm.faces[:]  # noqa: E731
    bmesh.ops.bisect_plane(bm, geom=geom(), plane_co=WAIST_FRONT, plane_no=n, clear_outer=True)
    bmesh.ops.bisect_plane(bm, geom=geom(), plane_co=Vector((0, 0, CUT_Z)),
                           plane_no=Vector((0, 0, 1)), clear_inner=True)
    largest_component(bm)


def neighbours(bm):
    out = []
    for v in bm.verts:
        if v.is_boundary:
            out.append([e.other_vert(v).index for e in v.link_edges if e.is_boundary])
        else:
            out.append([e.other_vert(v).index for e in v.link_edges])
    return out


def smooth(bm, nbr, iters, fac, outward_only, weight=lambda v: 1.0):
    verts = bm.verts
    for _ in range(iters):
        bm.normal_update()
        new = []
        for v in verts:
            nb, w = nbr[v.index], weight(v)
            if not nb or w <= 0 or v.is_boundary:  # smoothing a loop shrinks it
                new.append(None)
                continue
            avg = sum((verts[i].co for i in nb), Vector()) / len(nb)
            delta = avg - v.co
            if outward_only and not v.is_boundary:
                dn = delta.dot(v.normal)
                if dn < 0:
                    delta -= v.normal * dn
            new.append(v.co + delta * fac * w)
        for v, c in zip(verts, new):
            if c is not None:
                v.co = c


def push_out(bm, bvh):
    for v in bm.verts:
        loc, nor, _, _ = bvh.find_nearest(v.co)
        if loc is None:
            continue
        c = C.clearance(v.co.z)
        if (v.co - loc).dot(nor) < c:
            v.co = loc + nor * c


def midline_gap(z):
    return 0.010 * (1.0 - C.sstep(C.CROTCH_Z - 0.04, C.CROTCH_Z + 0.01, z))


def separate_legs(bm):
    for v in bm.verts:
        g = midline_gap(v.co.z)
        if g > 0 and abs(v.co.x) < g:
            v.co.x = g if v.co.x >= 0 else -g


def loosen(bm, bvh):
    bm.verts.ensure_lookup_table()
    bm.normal_update()
    for v in bm.verts:
        v.co += v.normal * C.clearance(v.co.z)
    for v in bm.verts:
        z = v.co.z
        w = 1.0 - C.sstep(0.76, 0.86, z)
        if w <= 0:
            continue
        s = 1 if v.co.x >= 0 else -1
        cx, cy, a, b = C.leg_ellipse(z)
        dx, dy = v.co.x * s - cx, v.co.y - cy
        r = math.hypot(dx, dy)
        if r < 1e-6:
            continue
        ux, uy = dx / r, dy / r
        R = 1.0 / math.sqrt((ux / a) ** 2 + (uy / b) ** 2)
        r2 = r + w * (C.smax(r, R) - r)
        v.co.x = (cx + ux * r2) * s
        v.co.y = cy + uy * r2
    separate_legs(bm)
    nbr = neighbours(bm)
    crotch = lambda v: C.sstep(0.62, 0.74, v.co.z) * (1.0 - 0.6 * C.sstep(0.0, 0.12, abs(v.co.x)))  # noqa: E731
    smooth(bm, nbr, 60, 0.6, True, crotch)
    smooth(bm, nbr, 20, 0.35, False, lambda v: 0.6)
    push_out(bm, bvh)
    separate_legs(bm)
    smooth(bm, nbr, 10, 0.5, True)
    push_out(bm, bvh)
    separate_legs(bm)


def boundary_loops(bm):
    seen, loops = set(), []
    for e in [e for e in bm.edges if e.is_boundary]:
        if e in seen:
            continue
        loop, v = [e.verts[0]], e.verts[1]
        seen.add(e)
        while v != loop[0]:
            loop.append(v)
            nxt = [x for x in v.link_edges if x.is_boundary and x not in seen]
            if not nxt:
                break
            seen.add(nxt[0])
            v = nxt[0].other_vert(v)
        loops.append(loop)
    return loops


def bridge(bm, a, b):
    n = len(a)
    for i in range(n):
        try:
            bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]))
        except ValueError:
            pass


def add_turnups(bm):
    bm.normal_update()
    loops = boundary_loops(bm)
    for loop in loops:
        zavg = sum(v.co.z for v in loop) / len(loop)
        if zavg < 0.5:  # trouser hem: lengthen with a slight break, then roll under
            cen = sum((v.co for v in loop), Vector()) / len(loop)
            prev = loop
            for zf, zb, sc in ((0.152, 0.146, 1.003), (0.135, 0.123, 1.008), (0.118, 0.100, 1.014)):
                new = []
                for v in loop:
                    d = Vector((v.co.x - cen.x, v.co.y - cen.y, 0))
                    t = max(0.0, min(1.0, d.y / (d.length + 1e-9) * 0.5 + 0.5))
                    new.append(bm.verts.new(Vector((cen.x + d.x * sc, cen.y + d.y * sc, zf + (zb - zf) * t))))
                bridge(bm, prev, new)
                prev = new
            inner1 = []
            for v in prev:
                d = Vector((v.co.x - cen.x, v.co.y - cen.y, 0)).normalized()
                inner1.append(bm.verts.new(v.co - d * 0.003 - Vector((0, 0, 0.002))))
            bridge(bm, prev, inner1)
            inner2 = []
            for v in inner1:
                d = Vector((v.co.x - cen.x, v.co.y - cen.y, 0)).normalized()
                inner2.append(bm.verts.new(v.co - d * 0.001 + Vector((0, 0, 0.03))))
            bridge(bm, inner1, inner2)
        else:  # waistband: fold over and face inside
            up, inn, inn2 = [], [], []
            for v in loop:
                n = Vector((v.normal.x, v.normal.y, 0)).normalized()
                up.append(bm.verts.new(v.co + Vector((0, 0, 0.003)) - n * 0.0015))
            bridge(bm, loop, up)
            for v in loop:
                n = Vector((v.normal.x, v.normal.y, 0)).normalized()
                inn.append(bm.verts.new(v.co - n * 0.0035))
            bridge(bm, up, inn)
            for v in inn:
                inn2.append(bm.verts.new(v.co - Vector((0, 0, 0.035))))
            bridge(bm, inn, inn2)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])


def cut_seams(bm):
    bm.verts.ensure_lookup_table()
    for e in bm.edges:
        e.seam = False
    P = {v.index: C.phi_of(*v.co) for v in bm.verts}
    angdiff = lambda a, b: abs((a - b + 180) % 360 - 180)  # noqa: E731

    def path(start, goal, cost):
        dist, prev, pq = {start.index: 0}, {}, [(0, start.index)]
        while pq:
            d, i = heapq.heappop(pq)
            if i == goal.index:
                break
            if d > dist.get(i, 1e18):
                continue
            v = bm.verts[i]
            for e in v.link_edges:
                w = e.other_vert(v)
                c = d + cost(e, w)
                if c < dist.get(w.index, 1e18):
                    dist[w.index] = c
                    prev[w.index] = (i, e)
                    heapq.heappush(pq, (c, w.index))
        out, i = [], goal.index
        while i != start.index:
            j, e = prev[i]
            out.append(e)
            i = j
        return out

    def phi_cost(target, side, k=0.15):
        return lambda e, w: e.calc_length() * (1 + k * angdiff(P[w.index][0], target)) + (0 if P[w.index][1] == side else 50)

    pick = lambda cond, key: min([v for v in bm.verts if cond(v)], key=key)  # noqa: E731
    crosses = lambda v: any((e.other_vert(v).co.x > 0) != (v.co.x > 0) for e in v.link_edges)  # noqa: E731
    crotch = pick(lambda v: abs(v.co.x) < 0.015 and v.co.z < 0.95 and crosses(v), lambda v: v.co.z)
    bnd = lambda v: v.is_boundary  # noqa: E731
    top_f = pick(lambda v: bnd(v) and v.co.z > 0.9 and v.co.y < 0, lambda v: abs(v.co.x))
    top_b = pick(lambda v: bnd(v) and v.co.z > 0.9 and v.co.y > 0, lambda v: abs(v.co.x))
    centre = lambda e, w: e.calc_length() * (1 + 400 * abs(w.co.x))  # noqa: E731
    seams = path(crotch, top_f, centre) + path(crotch, top_b, centre)
    for side in (1, -1):
        on = lambda v: (1 if v.co.x >= 0 else -1) == side  # noqa: E731
        hem_out = pick(lambda v: bnd(v) and on(v) and v.co.z < 0.3, lambda v: angdiff(P[v.index][0], 90))
        top_out = pick(lambda v: bnd(v) and on(v) and v.co.z > 0.9, lambda v: angdiff(P[v.index][0], 90))
        hem_in = pick(lambda v: bnd(v) and on(v) and v.co.z < 0.3, lambda v: angdiff(P[v.index][0], -90))
        seams += path(hem_out, top_out, phi_cost(90, side))
        seams += path(hem_in, crotch, phi_cost(-90, side, 0.08))
        # horizontal cut along the knee-panel top seam: shorter islands pack much better
        z0 = KNEE_SEAM_Z
        ring = [v for v in bm.verts if on(v) and abs(v.co.z - z0) < 0.03 and not v.is_boundary]
        o = min(ring, key=lambda v: angdiff(P[v.index][0], 90) + 2000 * abs(v.co.z - z0))
        i = min(ring, key=lambda v: angdiff(P[v.index][0], -90) + 2000 * abs(v.co.z - z0))
        for front in (True, False):
            def hcost(e, w, front=front):
                ph = P[w.index][0]
                wrong = (abs(ph) > 100) if front else (abs(ph) < 80)
                return e.calc_length() * (1 + 300 * abs(w.co.z - z0)) + (5 if wrong else 0) + (50 if P[w.index][1] != side else 0)
            seams += path(o, i, hcost)
    for e in seams:
        e.seam = True
    return crotch.co.copy()


def relax_on_surface(bm, iters=8, fac=0.5):
    """Even out edge lengths while keeping the surface shape (tangential smoothing + reprojection)."""
    ref = BVHTree.FromBMesh(bm)
    nbr = neighbours(bm)
    verts = bm.verts
    for _ in range(iters):
        bm.normal_update()
        new = []
        for v in verts:
            nb = nbr[v.index]
            if not nb or v.is_boundary:
                new.append(None)
                continue
            avg = sum((verts[i].co for i in nb), Vector()) / len(nb)
            d = avg - v.co
            d -= v.normal * d.dot(v.normal)
            new.append(v.co + d * fac)
        for v, c in zip(verts, new):
            if c is not None:
                loc, _, _, _ = ref.find_nearest(c)
                v.co = loc if loc is not None else c


def uv_islands(bm):
    seen, islands = set(), []
    for f in bm.faces:
        if f in seen:
            continue
        stack, isl = [f], []
        seen.add(f)
        while stack:
            g = stack.pop()
            isl.append(g)
            for e in g.edges:
                if e.seam:
                    continue
                for h in e.link_faces:
                    if h not in seen:
                        seen.add(h)
                        stack.append(h)
        islands.append(isl)
    return islands


def orient_and_pack(ob, margin=0.004):
    """Rotate every UV island so garment-up is +V (fabric grain vertical), then pack.

    Packing may turn islands by 90 degrees: the ripstop grid is square and the camo
    is mapped from 3D coordinates, so only the fill rate changes.
    """
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    uv = bm.loops.layers.uv.active
    for isl in uv_islands(bm):
        gx = gy = 0.0
        loops = [lp for f in isl for lp in f.loops]
        for lp in loops:
            nxt = lp.link_loop_next
            dz = nxt.vert.co.z - lp.vert.co.z
            du, dv = nxt[uv].uv - lp[uv].uv
            gx += dz * du
            gy += dz * dv
        ang = math.atan2(gx, gy)  # rotate (gx, gy) onto +V
        ca, sa = math.cos(ang), math.sin(ang)
        cu = sum(lp[uv].uv.x for lp in loops) / len(loops)
        cv = sum(lp[uv].uv.y for lp in loops) / len(loops)
        for lp in loops:
            u, v = lp[uv].uv.x - cu, lp[uv].uv.y - cv
            lp[uv].uv = (cu + u * ca - v * sa, cv + u * sa + v * ca)
    bm.to_mesh(ob.data)
    bm.free()
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, rotate_method="CARDINAL", margin_method="FRACTION",
                            margin=margin, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")


def remove_pits(bm, thresh=0.0008, iters=6):
    """Pull single-vertex dents (mesh poles inherited from the body) up to their neighbours."""
    bm.verts.ensure_lookup_table()
    fixed = 0
    for _ in range(iters):
        bm.normal_update()
        moves = []
        for v in bm.verts:
            if v.is_boundary:
                continue
            nb = [e.other_vert(v).co for e in v.link_edges]
            avg = sum(nb, Vector()) / len(nb)
            if (avg - v.co).dot(v.normal) > thresh:
                moves.append((v, avg))
        for v, avg in moves:
            v.co = v.co.lerp(avg, 0.8)
        fixed += len(moves)
        if not moves:
            break
    return fixed


def build(subdivide=True):
    # Keep the body's own topology: it is built to deform with this skeleton and
    # keeps the two legs apart below the crotch (QuadriFlow welds them).
    bb = body_bmesh()
    bvh = BVHTree.FromBMesh(bb)
    bm = body_bmesh()
    cut_shell(bm)
    loosen(bm, bvh)
    bmesh.ops.join_triangles(bm, faces=bm.faces[:], angle_face_threshold=math.radians(40),
                             angle_shape_threshold=math.radians(40))
    bm.verts.ensure_lookup_table()
    relax_on_surface(bm)

    old = bpy.data.objects.get("Pants_base")
    if old:
        bpy.data.meshes.remove(old.data)
    me = bpy.data.meshes.new("Pants_base")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("Pants_base", me)
    COLL.objects.link(ob)

    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    if subdivide:
        mod = ob.modifiers.new("Subd", "SUBSURF")
        mod.levels = SUBD_LEVELS
        mod.boundary_smooth = "PRESERVE_CORNERS"
        bpy.ops.object.modifier_apply(modifier=mod.name)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    # the body's groin topology leaves a small pit under the fly after subdivision: relax it
    fly = lambda v: (1 - C.sstep(0.06, 0.10, abs(v.co.x))) * C.sstep(0.80, 0.84, v.co.z) * (1 - C.sstep(0.95, 0.99, v.co.z)) * (v.co.y < 0)  # noqa: E731
    smooth(bm, neighbours(bm), 12, 0.5, False, fly)
    push_out(bm, bvh)
    separate_legs(bm)
    print("pits removed:", remove_pits(bm))
    separate_legs(bm)
    add_turnups(bm)
    crotch = cut_seams(bm)
    bm.to_mesh(ob.data)
    bm.free()
    bb.free()

    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.unwrap(method="MINIMUM_STRETCH", fill_holes=True, margin=0.005)
    bpy.ops.object.mode_set(mode="OBJECT")
    orient_and_pack(ob)
    print("Pants_base", len(ob.data.vertices), "verts", len(ob.data.polygons), "faces, crotch", tuple(round(c, 3) for c in crotch))
    return ob


build()
