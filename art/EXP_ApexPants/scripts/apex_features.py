"""Construction details of the MCDU APEX pants as analytic fields (numpy only).

evaluate(P, N, mode) takes rest-pose surface points and normals of Pants_base
and returns height and material fields. The same code drives
  * mode="geo": soft, low-frequency height used to displace the game mesh;
  * mode="tex": sharp height + material/stitch masks baked into the textures.

Placement follows the product photos (art/EXP_ApexPants/reference). Feature
coordinates are (a, z): a = arc length in metres around the leg from its front
centre line (+ towards the outer side), z = height. "aw" is the same arc measured
0..360 deg so back features do not wrap. Left leg values; the right leg mirrors.
"""

import numpy as np

import apex_panels as APN
from apex_common import LEG_CENTRE, LEG_ELLIPSE

MM = 0.001

PARTS_GEOMETRY = True   # pockets, flaps, zips, straps, waistband, loops are real geometry

# Material codes
CAMO, STRETCH, CORDURA, TAPE, COIL, METAL, VELCRO, WEBBING, FACING, CREVICE = range(10)

# Panel ids: each fabric piece gets its own camo offset, as if cut separately.
(P_FRONT, P_BACK, P_WAIST, P_LOOP, P_FLY, P_CARGO, P_PLEAT, P_FLAP, P_BPKT, P_BFLAP,
 P_YOKE, P_GUSSET, P_KNEE, P_BKNEE, P_STRAP, P_CUFF, P_TAB, P_FACING) = range(18)


# --------------------------------------------------------------------------- noise
_G = np.array([[1, 1, 0], [-1, 1, 0], [1, -1, 0], [-1, -1, 0], [1, 0, 1], [-1, 0, 1],
               [1, 0, -1], [-1, 0, -1], [0, 1, 1], [0, -1, 1], [0, 1, -1], [0, -1, -1],
               [1, 1, 0], [-1, 1, 0], [0, -1, 1], [0, -1, -1]], np.float32)


def _hash3(ix, iy, iz, seed):
    with np.errstate(over="ignore"):
        h = (ix.astype(np.uint32) * np.uint32(0x8DA6B343)) ^ (iy.astype(np.uint32) * np.uint32(0xD8163841)) \
            ^ (iz.astype(np.uint32) * np.uint32(0xCB1AB31F)) ^ np.uint32((seed * 0x9E3779B1) & 0xFFFFFFFF)
        h ^= h >> np.uint32(15)
        h *= np.uint32(0x2C1B3C6D)
        h ^= h >> np.uint32(12)
    return h & np.uint32(15)


def noise3(p, seed=0):
    """Gradient noise, roughly in [-1, 1]. p: (n, 3)."""
    pf = np.floor(p)
    i = pf.astype(np.int64)
    f = (p - pf).astype(np.float32)
    u = f * f * f * (f * (f * 6 - 15) + 10)
    out = np.zeros(len(p), np.float32)
    for dx in (0, 1):
        wx = u[:, 0] if dx else 1 - u[:, 0]
        for dy in (0, 1):
            wy = u[:, 1] if dy else 1 - u[:, 1]
            for dz in (0, 1):
                wz = u[:, 2] if dz else 1 - u[:, 2]
                g = _G[_hash3(i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz, seed)]
                d = f - np.array([dx, dy, dz], np.float32)
                out += (g * d).sum(1) * wx * wy * wz
    return out * 1.4


def fbm3(p, octaves=4, seed=0, lac=2.0, gain=0.5):
    out = np.zeros(len(p), np.float32)
    amp, norm = 1.0, 0.0
    for o in range(octaves):
        out += amp * noise3(p, seed + o * 17)
        norm += amp
        p = p * lac
        amp *= gain
    return out / norm


# --------------------------------------------------------------------------- helpers
def sstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def interp_table(table, z):
    zs = np.array([k for k, _ in table], np.float32)
    vals = np.array([v for _, v in table], np.float32)
    zc = np.clip(z, zs[0], zs[-1])
    i = np.clip(np.searchsorted(zs, zc) - 1, 0, len(zs) - 2)
    t = (zc - zs[i]) / (zs[i + 1] - zs[i])
    t = t * t * (3 - 2 * t)
    return vals[i] + (vals[i + 1] - vals[i]) * t[:, None]


def sd_box(pa, pz, ca, cz, ha, hz, r=0.0):
    """Rounded box SDF in (a, z) metres; also returns the along-edge coordinate."""
    qa = np.abs(pa - ca) - ha + r
    qz = np.abs(pz - cz) - hz + r
    d = np.hypot(np.maximum(qa, 0), np.maximum(qz, 0)) + np.minimum(np.maximum(qa, qz), 0) - r
    along = np.where(qa > qz, pz, pa)
    return d, along


def sd_polyline(pa, pz, pts):
    """Unsigned distance, signed side (+ left of travel) and arc position along a polyline."""
    pts = np.asarray(pts, np.float32)
    best = np.full(pa.shape, 1e9, np.float32)
    side = np.zeros(pa.shape, np.float32)
    along = np.zeros(pa.shape, np.float32)
    acc = 0.0
    for (a0, z0), (a1, z1) in zip(pts[:-1], pts[1:]):
        da, dz = a1 - a0, z1 - z0
        L2 = da * da + dz * dz
        t = np.clip(((pa - a0) * da + (pz - z0) * dz) / L2, 0, 1)
        ea, ez = pa - (a0 + t * da), pz - (z0 + t * dz)
        d = np.hypot(ea, ez)
        m = d < best
        best = np.where(m, d, best)
        side = np.where(m, np.sign(da * ez - dz * ea), side)
        along = np.where(m, acc + t * np.sqrt(L2), along)
        acc += float(np.sqrt(L2))
    return best, side, along


def sd_poly(pa, pz, pts):
    """Signed distance to a closed polygon in (a, z) metres (negative inside)."""
    pts = np.asarray(pts, np.float32)
    closed = np.vstack([pts, pts[:1]])
    d, _, along = sd_polyline(pa, pz, closed)
    inside = np.zeros(pa.shape, bool)
    for (a0, z0), (a1, z1) in zip(closed[:-1], closed[1:]):
        cond = (z0 > pz) != (z1 > pz)
        xi = a0 + (pz - z0) * (a1 - a0) / ((z1 - z0) if z1 != z0 else 1e-9)
        inside ^= cond & (pa < xi)
    return np.where(inside, -d, d), along


def ang_d(ph, lo, hi, Rm):
    """Signed arc distance (m) to the angular interval [lo, hi] degrees (same wrap as ph)."""
    return np.maximum(lo - ph, ph - hi) * np.radians(1.0) * Rm


def bezier(p0, p1, p2, p3, n=24):
    t = np.linspace(0, 1, n)[:, None]
    p0, p1, p2, p3 = (np.array(p, np.float32) for p in (p0, p1, p2, p3))
    return ((1 - t) ** 3) * p0 + 3 * ((1 - t) ** 2) * t * p1 + 3 * (1 - t) * t * t * p2 + t ** 3 * p3


class Fields:
    """Accumulates layered height/material while features are applied in order."""

    def __init__(self, n, sharp):
        self.sharp = sharp
        self.h = np.zeros(n, np.float32)
        self.hd = np.zeros(n, np.float32)       # seams/stitches: hidden by pieces sewn on top
        self.mat = np.full(n, CAMO, np.uint8)
        self.panel = np.full(n, P_FRONT, np.uint8)
        self.stitch = np.zeros(n, np.float32)   # thread coverage 0..1
        self.dark = np.zeros(n, np.float32)     # crevices / openings 0..1
        self.wear = np.zeros(n, np.float32)     # raised edges that fade first 0..1

    def soft(self, base):
        return base if self.sharp else max(base, 6 * MM)

    def layer(self, sd, thick, mat=None, panel=None, bevel=1.5 * MM, dome=0.0, inside_extra=None):
        """Put a piece of material of given thickness inside the region sd<0."""
        bev = self.soft(bevel)
        m = sstep(0.0, bev, -sd)
        prof = thick * m
        if dome:
            prof = prof + dome * sstep(0.0, self.soft(25 * MM), -sd)
        if inside_extra is not None:
            prof = prof + inside_extra * m
        self.h = self.h + prof
        # a piece sewn on top hides the seams, stitches and shadows underneath it
        self.hd *= 1 - m
        self.stitch *= 1 - m
        self.dark *= 1 - m
        sel = sd < 0
        if mat is not None:
            self.mat = np.where(sel, np.uint8(mat), self.mat)
        if panel is not None:
            self.panel = np.where(sel, np.uint8(panel), self.panel)
        if self.sharp:
            self.wear = np.maximum(self.wear, np.exp(-((sd + bev) / (1.2 * MM)) ** 2) * (thick > 1 * MM))
        return sel

    def seam(self, d, along, offsets=(3.5 * MM, 7.5 * MM), groove=0.6 * MM, mask=None):
        """Seam groove at d=0 and dashed topstitch rows at the given signed offsets."""
        w = 1.0 if mask is None else mask
        self.hd -= groove * np.exp(-(d / self.soft(1.1 * MM)) ** 2) * w
        if not self.sharp:
            return
        self.hd -= 0.25 * MM * np.exp(-(d / (4 * MM)) ** 2) * w
        self.dark = np.maximum(self.dark, 0.55 * np.exp(-(d / (0.5 * MM)) ** 2) * w)
        for off in offsets:
            self.stitch_row(d - off, along, w)

    def stitch_row(self, d, along, w=1.0, length=3.2 * MM, gap=1.1 * MM, width=0.45 * MM):
        if not self.sharp:
            return
        ph = np.mod(along, length + gap) / (length + gap)
        dash = sstep(0.0, 0.08, ph) * (1 - sstep(length / (length + gap) - 0.08, length / (length + gap), ph))
        line = np.exp(-(d / width) ** 2)
        thread = line * dash * w
        self.stitch = np.maximum(self.stitch, thread)
        self.hd += 0.3 * MM * thread - 0.15 * MM * line * (1 - dash) * w
        hole = line * (1 - dash) * w
        self.dark = np.maximum(self.dark, 0.35 * hole)


# --------------------------------------------------------------------------- evaluate
def coords(P, N):
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    s = np.where(x >= 0, 1.0, -1.0).astype(np.float32)
    c = interp_table(LEG_CENTRE, z)
    dx, dy = x * s - c[:, 0], y - c[:, 1]
    phi = np.degrees(np.arctan2(dx, -dy))
    e = interp_table(LEG_ELLIPSE, z)
    Rm = np.sqrt((e[:, 2] ** 2 + e[:, 3] ** 2) / 2)
    phw = np.mod(phi, 360.0)
    a = np.radians(phi) * Rm
    aw = np.radians(phw) * Rm
    # waist angle around the pelvis: 0 front centre, 90 side, 180 back centre
    thw = np.degrees(np.arctan2(np.abs(x), -(y - 0.01)))
    a_waist = np.radians(thw) * 0.165
    # inside-facing surfaces (waistband and hem facings)
    rx = np.where(z > 0.85, x, dx * s)
    ry = np.where(z > 0.85, y - 0.01, dy)
    rl = np.hypot(rx, ry) + 1e-9
    inward = (N[:, 0] * rx + N[:, 1] * ry) / rl < -0.25
    return dict(x=x, y=y, z=z, s=s, ax=np.abs(x), phi=phi, phw=phw, a=a, aw=aw, Rm=Rm,
                thw=thw, a_waist=a_waist, inward=inward)


def waist_top(y):
    return 1.000 + (np.clip(y, -0.11, 0.13) + 0.11) / 0.24 * 0.045 + 0.003


def hem_line(y, x_leg_centre_y):
    t = np.clip((y - x_leg_centre_y) / 0.07 * 0.5 + 0.5, 0, 1)
    return 0.118 + (0.100 - 0.118) * t


def crease_field(a, z, s, theta, lam, elong, seed, octaves=3):
    """Elongated fabric folds: rounded crests, sharp valleys. theta = fold direction in (a, z), degrees."""
    th = np.radians(theta)
    across = (-a * np.sin(th) + z * np.cos(th)) / lam
    along = (a * np.cos(th) + z * np.sin(th)) / (lam * elong)
    n = fbm3(np.stack([across, along, s * 5.31 + seed * 0.37], 1).astype(np.float32), octaves, seed)
    return np.abs(n) ** 0.8 - 0.42


def folds(C, zwb, sharp, seed):
    """Wrinkles placed where trousers bunch, hang or pull (see the reference photos)."""
    a, aw, z, phi, phw, s = C["a"], C["aw"], C["z"], C["phi"], C["phw"], C["s"]
    win = lambda lo0, lo1, hi0, hi1, v: sstep(lo0, lo1, v) * (1 - sstep(hi0, hi1, v))  # noqa: E731
    back = win(110, 145, 215, 250, phw)
    front = 1 - sstep(70, 110, np.abs(phi))
    # (weight, theta, wavelength, elongation, amplitude, geometric?)
    layers = [
        (1 - sstep(0.16, 0.34, z), 0, 0.050, 4.0, 6.5 * MM, True),                           # ankle stacking
        ((1 - sstep(0.15, 0.30, z)), 4, 0.020, 3.0, 2.0 * MM, False),                         # small ankle creases
        (win(0.20, 0.26, 0.34, 0.41, z) * front, 90, 0.065, 3.0, 4.0 * MM, True),            # shin drape
        (win(0.43, 0.46, 0.55, 0.59, z) * back, 0, 0.026, 4.0, 4.5 * MM, False),             # behind the knee
        (win(0.42, 0.46, 0.56, 0.60, z) * back, 0, 0.055, 3.0, 3.5 * MM, True),
        (win(0.57, 0.60, 0.64, 0.68, z) * front, 8, 0.040, 3.0, 3.0 * MM, True),             # above the knee
        (win(0.66, 0.70, 0.79, 0.82, z) * win(-95, -70, -10, 15, phi), -35, 0.034, 3.5, 3.6 * MM, True),  # crotch whiskers
        (win(0.69, 0.72, 0.77, 0.80, z) * win(140, 160, 200, 220, phw), 10, 0.030, 3.0, 2.8 * MM, False),  # under the seat
        (win(0.79, 0.82, 0.90, 0.93, z) * win(50, 70, 110, 130, phw), 30, 0.050, 3.0, 2.2 * MM, True),     # hip pull
        (win(zwb - 0.07, zwb - 0.04, zwb - 0.004, zwb, z), 90, 0.020, 2.0, 1.8 * MM, False),               # gathers under the belt
        (np.ones_like(z), 0, 0.075, 1.6, 2.6 * MM, True),                                    # general drape
        (np.ones_like(z), 25, 0.022, 2.5, 0.6 * MM, False),                                  # fine random creases
        (np.ones_like(z), -20, 0.011, 2.0, 0.25 * MM, False),                                # handling creases
    ]
    h = np.zeros_like(z)
    for i, (w, th, lam, el, amp, geo) in enumerate(layers):
        if not sharp and not geo:
            continue
        sel = w > 1e-3
        if not np.any(sel):
            continue
        part = np.zeros_like(z)
        part[sel] = crease_field(a[sel] if th != 0 else aw[sel], z[sel], s[sel], th, lam, el, seed + 31 * i)
        h += amp * w * part
    return h


def stiffness(mat):
    k = np.ones(mat.shape, np.float32)
    k[mat == CORDURA] = 0.5
    k[(mat == COIL) | (mat == TAPE)] = 0.35
    k[mat == METAL] = 0.0
    return k


def evaluate(P, N, mode="tex", seed=1):
    """Return dict of fields for points P (n,3) with normals N (n,3)."""
    sharp = mode == "tex"
    C = coords(P, N)
    x, y, z, a, aw, phi, phw, Rm, ax = C["x"], C["y"], C["z"], C["a"], C["aw"], C["phi"], C["phw"], C["Rm"], C["ax"]
    F = Fields(len(P), sharp)
    F.panel = np.where((phw > 90) & (phw < 270), np.uint8(P_BACK), np.uint8(P_FRONT))

    zt = waist_top(y)
    zwb = zt - 0.042                    # waistband lower edge
    a_side = np.radians(90.0) * Rm      # outseam
    a_in = np.radians(-90.0) * Rm       # inseam
    leg_c = interp_table(LEG_CENTRE, z)
    zhem = hem_line(y, leg_c[:, 1])

    # ---------------------------------------------------------------- base seams
    out_d = a - a_side
    in_d = a - a_in
    upper = z > 0.12
    side_zip = (z > 0.565) & (z < 0.94)
    F.seam(out_d, z, offsets=(-3.5 * MM, -7.5 * MM), mask=(upper & ~side_zip).astype(np.float32))
    F.seam(in_d, z, offsets=(3.5 * MM, 7.5 * MM), mask=((z < 0.76) & upper).astype(np.float32))
    back_c = (y > 0.0) & (z > 0.70) & (z < zwb)
    F.seam(ax, z, offsets=(4 * MM, 8 * MM), mask=back_c.astype(np.float32))
    front_c = (y < 0.0) & (z > 0.70) & (z < 0.87)
    F.seam(ax, z, offsets=(4 * MM,), mask=front_c.astype(np.float32))

    # ---------------------------------------------------------------- stretch and reinforcement panels
    # explicit layout read from all photos (apex_panels.py)
    PF = APN.panel_fields(phi, z, C["thw"], ax)
    yoke = PF["d_yoke"] < 0
    F.layer(np.where(yoke & (z < zwb), -1.0, 1.0), 0.0, STRETCH, P_YOKE)
    F.layer(np.where(PF["olive"] & ~PF["front_500d"], -1.0, 1.0), 0.0, STRETCH, P_BKNEE)
    F.layer(np.where(PF["front_500d"], -1.0, 1.0), 0.0, CORDURA, P_KNEE)
    # seams with double topstitching on the olive side
    knee_seam_mask = ((PF["d_wo"] >= 0) & (PF["d_wi"] >= 0)).astype(np.float32)
    F.seam(PF["d_band"], a, offsets=(-3.5 * MM, -7.5 * MM), mask=knee_seam_mask)
    for key in ("d_wo", "d_wi"):
        dd = PF[key]
        F.seam(dd, z, offsets=(3.5 * MM, 7.5 * MM), mask=((z > APN.K_BOT) & (z < 0.62)).astype(np.float32))
    F.seam(PF["d_strip"], z, offsets=(-3.5 * MM,), mask=((z > PF["ktop"]) & (z < 0.80)).astype(np.float32))
    F.seam(PF["d_v"], z, offsets=(-3.5 * MM,), mask=(z < APN.K_BOT).astype(np.float32))
    F.seam(PF["d_yoke"], C["a_waist"], offsets=(-3.5 * MM, -7.5 * MM), mask=(z < zwb).astype(np.float32))
    # 500D knee: double layer with pad pocket, slight dome, articulation seam
    F.layer(np.where(PF["front_500d"], PF["d_band"], 1.0), 0.8 * MM, None, None, bevel=3 * MM, dome=1.6 * MM)

    # ---------------------------------------------------------------- waistband, loops, fly, front pockets
    d_wb = zwb - z
    F.layer(d_wb, 0.0 if PARTS_GEOMETRY else 1.0 * MM, CAMO, P_WAIST)
    F.seam(d_wb, C["a_waist"], offsets=(-4 * MM,))
    F.stitch_row(z - (zt - 4 * MM), C["a_waist"])

    for th in (() if PARTS_GEOMETRY else (32.0, 92.0, 143.0, 180.0)):
        aw0 = np.radians(th) * 0.165
        d_loop, along = sd_box(C["a_waist"], z, aw0, zt - 0.024, 0.0085, 0.028, 0.002)
        F.layer(d_loop, 2.2 * MM, CAMO, P_LOOP, bevel=1.2 * MM, dome=0.4 * MM)
        if sharp:
            for zz in (zt - 0.006, zt - 0.046):  # bar tacks
                bt = np.exp(-((z - zz) / (1.6 * MM)) ** 2) * (np.abs(C["a_waist"] - aw0) < 0.007)
                F.stitch = np.maximum(F.stitch, 0.9 * bt * (0.6 + 0.4 * np.sin(C["a_waist"] / (0.6 * MM)) ** 2))
                F.h += 0.35 * MM * bt
            F.stitch_row(d_loop + 1.5 * MM, along, (z < zt - 0.008) & (z > zt - 0.044))

    # fly (left panel overlaps) with J-stitch
    fly_side = C["s"] > 0
    d_fly, along_fly = sd_box(x * C["s"], z, 0.0, (0.872 + zwb) / 2, 0.037, (zwb - 0.872) / 2, 0.028)
    d_fly = np.where(fly_side & (y < 0), d_fly, 1.0)
    F.layer(d_fly, 0.6 * MM, CAMO, P_FLY)
    if sharp:
        F.stitch_row(d_fly + 6 * MM, along_fly, ((z < zwb - 0.004) & (x * C["s"] > 0.002)).astype(np.float32))
        F.stitch_row(d_fly + 10 * MM, along_fly, ((z < zwb - 0.004) & (x * C["s"] > 0.002)).astype(np.float32))
        edge = fly_side & (y < 0) & (z > 0.872) & (z < zwb)
        F.dark = np.maximum(F.dark, 0.6 * np.exp(-(ax / (0.8 * MM)) ** 2) * edge)
    # waistband closure: velcro patch on the right, tab from the left
    d_vel, _ = sd_box(x, z, -0.035, zt - 0.021, 0.026, 0.016, 0.003)
    d_vel = np.where(y < 0, d_vel, 1.0)
    F.layer(d_vel, 0.8 * MM, VELCRO, P_WAIST, bevel=0.6 * MM)
    d_tab, along_tab = sd_box(x, z, -0.012, zt - 0.021, 0.026, 0.017, 0.006)
    d_tab = np.where(y < 0, d_tab, 1.0)
    F.layer(d_tab, 1.6 * MM, CAMO, P_TAB, bevel=1.0 * MM)
    F.stitch_row(d_tab + 2.5 * MM, along_tab, (d_tab < 0).astype(np.float32) + 0)

    # front slash pockets: opening curve with reinforced lip, gap behind it
    curve = bezier((0.040, 0.962), (0.058, 0.905), (0.105, 0.858), (0.158, 0.846))
    dp, sp, tp = sd_polyline(a, z, curve)
    near = (z > 0.83) & (z < zwb + 0.002) & (a > 0.02)
    pocket_side = sp < 0  # outer/upper side of the curve
    lip = near & ~pocket_side
    gap = near & pocket_side
    F.h += np.where(lip, 1.2 * MM * np.exp(-(dp / F.soft(4 * MM)) ** 2), 0)
    F.h -= np.where(gap, 1.6 * MM * np.exp(-(dp / F.soft(9 * MM)) ** 2), 0)
    if sharp:
        F.dark = np.maximum(F.dark, np.where(gap, 0.9 * np.exp(-(dp / (1.6 * MM)) ** 2), 0))
        for off in (4 * MM, 10 * MM):
            F.stitch_row(np.where(lip, dp - off, 1.0), tp)

    # ---------------------------------------------------------------- cargo pocket, pleat, flap, welt
    if not PARTS_GEOMETRY:  # these are real meshes now (build_parts.py)
        ca, cz, ha, hz = 0.062, 0.690, 0.085, 0.105
        d_cargo, al_c = sd_box(a, z, ca, cz, ha, hz, 0.010)
        F.layer(d_cargo, 2.0 * MM, CAMO, P_CARGO, bevel=2.5 * MM, dome=5.5 * MM)
        F.stitch_row(d_cargo + 3 * MM, al_c, (z < 0.79).astype(np.float32))
        F.seam(d_cargo, al_c, offsets=(), groove=0.9 * MM)
        if sharp:
            F.dark = np.maximum(F.dark, 0.45 * np.exp(-((d_cargo - 0.6 * MM) / (0.9 * MM)) ** 2))
        d_pl, al_pl = sd_box(a, z, ca + 0.003, cz - 0.01, 0.017, hz - 0.012, 0.002)
        F.layer(np.maximum(d_pl, d_cargo), 1.0 * MM, CAMO, P_PLEAT, bevel=0.9 * MM)
        F.stitch_row(d_pl + 2.5 * MM, al_pl, (d_cargo < -2 * MM).astype(np.float32))
        d_flap, al_f = sd_box(a, z, ca, 0.783, 0.091, 0.034, 0.014)
        F.layer(d_flap, 2.2 * MM, CAMO, P_FLAP, bevel=1.4 * MM, dome=0.6 * MM)
        F.stitch_row(d_flap + 3 * MM, al_f)
        if sharp:  # shadow under the free lower edge of the flap
            under = (z < 0.783) & (d_flap > 0)
            F.dark = np.maximum(F.dark, 0.7 * under * np.exp(-(d_flap / (2.5 * MM)) ** 2))
        # zipper pull of the zipped pocket under the flap
        d_pull, _ = sd_box(a, z, 0.138, 0.736, 0.0055, 0.016, 0.004)
        F.layer(d_pull, 1.8 * MM, WEBBING, P_TAB, bevel=0.8 * MM)
        # narrow welt pocket above the flap
        wd, ws, wt = sd_polyline(a, z, [(0.005, 0.836), (0.105, 0.840)])
        welt = (wt > 0.001) & (wt < 0.099)
        F.h += np.where(welt, 0.8 * MM * np.exp(-(wd / F.soft(2.5 * MM)) ** 2), 0)
        if sharp:
            F.dark = np.maximum(F.dark, 0.95 * welt * np.exp(-(wd / (0.7 * MM)) ** 2))
            F.stitch_row(np.where(welt, wd - 4 * MM, 1.0), wt)

    # ---------------------------------------------------------------- side vent zipper (long)
    if not PARTS_GEOMETRY:  # these are real meshes now (build_parts.py)
        zd = out_d
        zip_rng = (z > 0.575) & (z < 0.935)
        tape = np.where(zip_rng, np.abs(zd) - 0.0115, 1.0)
        F.layer(tape, 0.3 * MM, TAPE, P_FRONT, bevel=0.5 * MM)
        coil = np.where(zip_rng, np.abs(zd) - 0.0028, 1.0)
        F.layer(coil, 1.0 * MM, COIL, P_FRONT, bevel=0.4 * MM)
        if sharp:
            teeth = 0.35 * MM * (np.sin(2 * np.pi * z / (1.7 * MM)) > 0) * (coil < 0)
            F.h += teeth
            F.dark = np.maximum(F.dark, 0.5 * np.exp(-(zd / (0.35 * MM)) ** 2) * zip_rng)
        F.seam(np.abs(zd) - 0.0125, z, offsets=(-2.5 * MM,), groove=0.7 * MM, mask=zip_rng.astype(np.float32))
        d_sl, _ = sd_box(zd, z, 0.0, 0.592, 0.0062, 0.015, 0.003)
        F.layer(d_sl, 2.6 * MM, METAL, P_FRONT, bevel=0.8 * MM, dome=0.5 * MM)
        d_pt, _ = sd_box(zd, z, 0.0, 0.562, 0.005, 0.016, 0.004)
        F.layer(d_pt, 1.8 * MM, WEBBING, P_TAB, bevel=0.8 * MM)

    # ---------------------------------------------------------------- back flap pockets and welts
    if not PARTS_GEOMETRY:  # these are real meshes now (build_parts.py)
        bca, bcz = 0.248, 0.712
        d_bp, al_b = sd_box(aw, z, bca, bcz, 0.074, 0.082, 0.010)
        F.layer(d_bp, 1.6 * MM, CAMO, P_BPKT, bevel=2.0 * MM, dome=2.5 * MM)
        F.seam(d_bp, al_b, offsets=(-3 * MM,), groove=0.8 * MM)
        d_bf, al_bf = sd_box(aw, z, bca, 0.800, 0.080, 0.030, 0.013)
        F.layer(d_bf, 2.0 * MM, CAMO, P_BFLAP, bevel=1.3 * MM, dome=0.5 * MM)
        F.stitch_row(d_bf + 3 * MM, al_bf)
        if sharp:
            under = (z < 0.80) & (d_bf > 0)
            F.dark = np.maximum(F.dark, 0.7 * under * np.exp(-(d_bf / (2.5 * MM)) ** 2))
        bwd, bws, bwt = sd_polyline(aw, z, [(0.195, 0.888), (0.305, 0.877)])
        bwelt = (bwt > 0.001) & (bwt < 0.109)
        F.h += np.where(bwelt, 0.8 * MM * np.exp(-(bwd / F.soft(2.5 * MM)) ** 2), 0)
        if sharp:
            F.dark = np.maximum(F.dark, 0.95 * bwelt * np.exp(-(bwd / (0.7 * MM)) ** 2))
            F.stitch_row(np.where(bwelt, bwd - 4 * MM, 1.0), bwt)

    # ---------------------------------------------------------------- knee strap, lower zipper, hem
    if not PARTS_GEOMETRY:  # real meshes now (build_parts.py)
        st_a0, st_a1 = np.radians(72) * Rm, np.radians(176) * Rm
        d_st, al_st = sd_box(aw, z, (st_a0 + st_a1) / 2, 0.420, (st_a1 - st_a0) / 2, 0.015, 0.012)
        F.layer(d_st, 2.2 * MM, CAMO, P_STRAP, bevel=1.2 * MM, dome=0.3 * MM)
        F.stitch_row(d_st + 2.5 * MM, al_st)
        d_sv, _ = sd_box(aw, z, st_a0 + 0.02, 0.420, 0.014, 0.011, 0.003)
        if sharp:
            F.mat = np.where((d_sv < 0) & (d_st > -1.5 * MM), np.uint8(VELCRO), F.mat)

        lz = a - np.radians(70) * Rm
        lz_rng = (z > 0.205) & (z < 0.392)
        F.layer(np.where(lz_rng, np.abs(lz) - 0.0095, 1.0), 0.3 * MM, TAPE, None, bevel=0.5 * MM)
        lcoil = np.where(lz_rng, np.abs(lz) - 0.0026, 1.0)
        F.layer(lcoil, 1.0 * MM, COIL, None, bevel=0.4 * MM)
        if sharp:
            F.h += 0.35 * MM * (np.sin(2 * np.pi * z / (1.7 * MM)) > 0) * (lcoil < 0)
        F.seam(np.abs(lz) - 0.0105, z, offsets=(-2.5 * MM,), groove=0.7 * MM, mask=lz_rng.astype(np.float32))
        d_ls, _ = sd_box(lz, z, 0.0, 0.378, 0.006, 0.014, 0.003)
        F.layer(d_ls, 2.5 * MM, METAL, None, bevel=0.8 * MM, dome=0.5 * MM)
        d_lp, _ = sd_box(lz, z, 0.0, 0.350, 0.0048, 0.016, 0.004)
        F.layer(d_lp, 1.8 * MM, WEBBING, P_TAB, bevel=0.8 * MM)

    # hem: topstitch, rolled edge, velcro cuff tab
    F.stitch_row(z - (zhem + 0.021), aw, (z < 0.2).astype(np.float32))
    F.h += 0.6 * MM * np.exp(-((z - zhem - 0.004) / F.soft(3 * MM)) ** 2) * (z < 0.2)
    if not PARTS_GEOMETRY:  # real meshes now (build_parts.py)
        c_a0, c_a1 = np.radians(96) * Rm, np.radians(150) * Rm
        d_cf, al_cf = sd_box(aw, z, (c_a0 + c_a1) / 2, zhem + 0.019, (c_a1 - c_a0) / 2, 0.014, 0.011)
        F.layer(d_cf, 2.0 * MM, CAMO, P_CUFF, bevel=1.2 * MM)
        F.stitch_row(d_cf + 2.5 * MM, al_cf)

    F.h += folds(C, zwb, sharp, seed) * stiffness(F.mat)

    # ---------------------------------------------------------------- facings
    inward = C["inward"]
    F.mat = np.where(inward & (F.mat == CAMO), np.uint8(FACING), F.mat)
    F.panel = np.where(inward, np.uint8(P_FACING), F.panel)

    # camo mapping coordinates (metres): front panels use a, back panels use aw
    back = (phw > 90) & (phw < 270)
    cam_u = np.where(back, aw, a)
    cam_u = np.where(z > zwb, C["a_waist"], cam_u)
    cam_v = z.copy()

    return dict(h=F.h + F.hd, mat=F.mat, panel=F.panel, stitch=F.stitch, dark=F.dark, wear=F.wear,
                cam_u=cam_u.astype(np.float32), cam_v=cam_v.astype(np.float32), side=C["s"],
                inward=inward, z=z)
