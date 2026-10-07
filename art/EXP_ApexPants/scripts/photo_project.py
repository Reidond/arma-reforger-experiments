"""Project the product photos onto the trousers (silhouette- and seam-anchored mapping).

Each photo is treated as an orthographic view from azimuth `theta` of the skinned mesh posed
like the person/mannequin in the photo (build/pose_<photo>.npz, written by compare.py).
A model point is placed in the photo by
  * height: posed z -> photo row through piecewise-linear landmarks;
  * width:  piecewise-linear through anchors present in both — the silhouette edges of the
    region (whole trousers above the split row, one leg below) and seams visible in the photo
    (fly, side zips) pinned to the same seams on the model.
Every view only "owns" the panels it faces (angle ranges around the leg, split at real seams),
so hand-overs between photos fall on seams where the camo changes anyway.
"""

import os

import numpy as np
from PIL import Image
from scipy import ndimage

import apex_common as AC

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.normpath(os.path.join(HERE, "..", "reference"))


def srgb_to_lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


# --------------------------------------------------------------------------- photo side
def photo_mask(img, thr=30, inset=2):
    bgc = np.median(np.concatenate([img[:30, :30].reshape(-1, 3), img[:30, -30:].reshape(-1, 3)]), 0)
    m = np.abs(img - bgc).sum(-1) > thr
    m = ndimage.binary_opening(m, iterations=1)
    m = ndimage.binary_fill_holes(m)
    lab, n = ndimage.label(m)
    sizes = ndimage.sum(m, lab, range(1, n + 1))
    m = lab == (np.argmax(sizes) + 1)
    return ndimage.binary_erosion(m, iterations=inset)


def olive_mean(img, mask):
    """Mean linear colour of the olive stretch/500D panels — a uniform colour reference."""
    c = img * 255.0
    R, G, B = c[..., 0], c[..., 1], c[..., 2]
    L = c.mean(-1)
    m = mask & (np.abs(R - G) < 9) & (B < G - 16) & (L > 70) & (L < 150)
    m = ndimage.binary_erosion(m, iterations=2)
    return srgb_to_lin(img[m]).mean(0)


def olive_regions(c, mask, px_per_mm=0.87, grow_mm=3.0):
    """Olive / coyote panels (stretch, 500D, webbing) of a photo: one uniform colour, unlike camo.

    Runs at the scale of the front product photo (0.87 px/mm) so the texture windows mean the
    same physical size in every photo. sRGB 0..255 input, boolean mask at the photo size out.
    """
    h, w = mask.shape
    k = 0.87 / px_per_mm
    if abs(k - 1) > 0.05:
        im = Image.fromarray(np.clip(c, 0, 255).astype(np.uint8)).resize((max(8, round(w * k)), max(8, round(h * k))), Image.LANCZOS)
        cs = np.asarray(im, np.float32)
        ms = np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).resize(im.size, Image.NEAREST)) > 0
    else:
        cs, ms = c, mask
    R, G, B = cs[..., 0], cs[..., 1], cs[..., 2]
    L = cs.mean(-1)
    col = ms & (R - G > -14) & (R - G < 26) & (B < G - 10) & (L > 25) & (L < 160)
    Lf = ndimage.gaussian_filter(L, 1.0)
    mu = ndimage.uniform_filter(Lf, 17)
    sd = np.sqrt(np.maximum(ndimage.uniform_filter(Lf ** 2, 17) - mu ** 2, 0))
    d = R - G
    md = ndimage.uniform_filter(d, 17)
    sdd = np.sqrt(np.maximum(ndimage.uniform_filter(d ** 2, 17) - md ** 2, 0))
    m = col & (sd < 12 + 0.08 * (100 - np.minimum(L, 100))) & (sdd < 8)
    m = ndimage.median_filter(m.astype(np.uint8), 7).astype(bool)
    m = ndimage.binary_opening(m, iterations=1)
    lab, n = ndimage.label(m)
    if n:
        sizes = ndimage.sum(m, lab, range(1, n + 1))
        m = np.isin(lab, np.nonzero(sizes > 250)[0] + 1)
    m = ndimage.binary_closing(m, iterations=3)
    if cs is not c:
        m = np.asarray(Image.fromarray(m.astype(np.uint8) * 255).resize((w, h), Image.NEAREST)) > 0
    g = max(1, int(round(grow_mm * px_per_mm)))
    return ndimage.binary_dilation(m, iterations=g) & mask


def row_spans(mask):
    """Per row: whole lo/hi, first run lo/hi, last run lo/hi (NaN when absent)."""
    h = mask.shape[0]
    out = np.full((h, 6), np.nan, np.float32)
    for y in range(h):
        xs = np.nonzero(mask[y])[0]
        if len(xs) < 5:
            continue
        out[y, 0], out[y, 1] = xs[0], xs[-1]
        runs = np.split(xs, np.nonzero(np.diff(xs) > 3)[0] + 1)
        runs = [r for r in runs if len(r) > 6]
        if len(runs) >= 2:
            out[y, 2], out[y, 3] = runs[0][0], runs[0][-1]
            out[y, 4], out[y, 5] = runs[-1][0], runs[-1][-1]
    return out


def interp_rows(table, idx):
    idx = np.nan_to_num(idx, nan=0.0)
    i0 = np.clip(np.floor(idx).astype(np.int64), 0, len(table) - 2)
    t = (idx - i0)[:, None]
    return table[i0] * (1 - t) + table[i0 + 1] * t


def polyline_x(pts, y):
    """x of a (roughly vertical) photo polyline at rows y; NaN outside its extent."""
    pts = np.asarray(sorted(pts, key=lambda p: p[1]), np.float32)
    x = np.interp(y, pts[:, 1], pts[:, 0])
    return np.where((y >= pts[0, 1]) & (y <= pts[-1, 1]), x, np.nan)


def bilinear(img, x, y):
    h, w = img.shape[:2]
    x = np.clip(x, 0, w - 1.001)
    y = np.clip(y, 0, h - 1.001)
    x0, y0 = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    return (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x0 + 1] * fx * (1 - fy)
            + img[y0 + 1, x0] * (1 - fx) * fy + img[y0 + 1, x0 + 1] * fx * fy)


# --------------------------------------------------------------------------- model side
def view_axes(theta_deg):
    t = np.radians(theta_deg)
    d = np.array([np.sin(t), np.cos(t), 0.0], np.float32)     # looking direction
    r = np.array([np.cos(t), -np.sin(t), 0.0], np.float32)    # image right
    return d, r


def depth_buffer(co, tris, d, r, cell=0.002):
    u, z, dep = co @ r, co[:, 2], co @ d
    u0, z0 = u.min() - 0.01, z.min() - 0.01
    W = int((u.max() - u0) / cell) + 3
    H = int((z.max() - z0) / cell) + 3
    buf = np.full((H, W), np.inf, np.float32)
    pu, pz = (u - u0) / cell, (z - z0) / cell
    for a, b, c in tris:
        xs = (pu[a], pu[b], pu[c])
        ys = (pz[a], pz[b], pz[c])
        x0, x1 = int(np.floor(min(xs))), int(np.ceil(max(xs)))
        y0, y1 = int(np.floor(min(ys))), int(np.ceil(max(ys)))
        det = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
        if abs(det) < 1e-12:
            continue
        X, Y = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        l0 = ((ys[1] - ys[2]) * (X - xs[2]) + (xs[2] - xs[1]) * (Y - ys[2])) / det
        l1 = ((ys[2] - ys[0]) * (X - xs[2]) + (xs[0] - xs[2]) * (Y - ys[2])) / det
        l2 = 1 - l0 - l1
        ins = (l0 >= -0.02) & (l1 >= -0.02) & (l2 >= -0.02)
        if ins.any():
            np.minimum.at(buf, (Y[ins], X[ins]), (l0 * dep[a] + l1 * dep[b] + l2 * dep[c])[ins].astype(np.float32))
    return buf, u0, z0, cell


def smooth_fill(col):
    ok = ~np.isnan(col)
    if ok.sum() < 2:
        return col
    out = np.interp(np.arange(len(col)), np.nonzero(ok)[0], col[ok])
    return ndimage.gaussian_filter1d(out, 1.5)


def phi_side(P):
    """Angle around the leg (deg; 0 front, +90 outer, ±180 back, -90 inner) and side, vectorised."""
    zt = np.array([k for k, _ in AC.LEG_CENTRE], np.float32)
    cx = np.array([v[0] for _, v in AC.LEG_CENTRE], np.float32)
    cy = np.array([v[1] for _, v in AC.LEG_CENTRE], np.float32)
    z = np.clip(P[:, 2], zt[0], zt[-1])
    i = np.clip(np.searchsorted(zt, z) - 1, 0, len(zt) - 2)
    t = (z - zt[i]) / (zt[i + 1] - zt[i])
    t = t * t * (3 - 2 * t)
    ccx = cx[i] + (cx[i + 1] - cx[i]) * t
    ccy = cy[i] + (cy[i + 1] - cy[i]) * t
    s = np.where(P[:, 0] >= 0, 1, -1)
    return np.degrees(np.arctan2(P[:, 0] * s - ccx, -(P[:, 1] - ccy))), s


def model_spans(co, side, r, zbins):
    """Silhouette extents in view coordinates per z bin: whole, leg(-1), leg(+1)."""
    u, z = co @ r, co[:, 2]
    out = np.full((len(zbins), 6), np.nan, np.float32)
    half = (zbins[1] - zbins[0]) * 0.75
    for i, zz in enumerate(zbins):
        sel = np.abs(z - zz) < half
        if sel.sum() < 3:
            continue
        out[i, 0], out[i, 1] = u[sel].min(), u[sel].max()
        for k, s in ((2, -1), (4, 1)):
            ss = sel & (side == s)
            if ss.sum() >= 3:
                out[i, k], out[i, k + 1] = u[ss].min(), u[ss].max()
    for k in range(6):
        out[:, k] = smooth_fill(out[:, k])
    return out


def feature_curve(co, rest, r, zbins, kind, s):
    """View-u of a seam on the posed mesh per z bin (NaN outside the seam's extent)."""
    u, z = co @ r, co[:, 2]
    phi, side = phi_side(rest)
    if kind == "outseam":
        sel = (side == s) & (np.abs(phi - 90.0) < 6)
    elif kind == "inseam":
        sel = (side == s) & (np.abs(phi + 90.0) < 6)
    elif kind == "center_front":
        sel = (np.abs(rest[:, 0]) < 0.006) & (rest[:, 1] < 0)
    elif kind == "center_back":
        sel = (np.abs(rest[:, 0]) < 0.006) & (rest[:, 1] > 0)
    else:
        raise ValueError(kind)
    out = np.full(len(zbins), np.nan, np.float32)
    half = (zbins[1] - zbins[0]) * 1.5
    for i, zz in enumerate(zbins):
        ss = sel & (np.abs(z - zz) < half)
        if ss.sum():
            out[i] = u[ss].mean()
    ok = ~np.isnan(out)
    if ok.sum() > 3:
        lo, hi = np.nonzero(ok)[0][[0, -1]]
        out[lo:hi + 1] = smooth_fill(out[lo:hi + 1])
    return out


def ang_window(ph, lo, hi, feather=6.0):
    """~1 inside [lo, hi] degrees (wrap-aware), feathered over `feather` degrees at the ends."""
    phw = np.mod(ph, 360.0)
    lo, hi = lo % 360.0, hi % 360.0
    if lo <= hi:
        dist = np.minimum(phw - lo, hi - phw)
    else:
        dist = np.where(phw >= lo, np.minimum(phw - lo, hi + 360 - phw), np.minimum(phw + 360 - lo, hi - phw))
    return np.clip(dist / feather + 0.5, 0, 1)


# --------------------------------------------------------------------------- views
VIEWS = {
    # ghost-mannequin front view; trousers' left leg (+X) is image right
    "15": dict(theta=0.0, landmarks=[(1.003, 150.0), (0.745, 402.0), (0.112, 926.0)],
               split_y=402, legs={-1: "first", 1: "last"}, exclude=[],
               anchors=[("center_front", 0, [(505, 165), (504, 300), (499, 396)])],
               own={-1: (-90.0, 50.0), 1: (-90.0, 50.0)}, priority=3),
    # the same photo as a low-priority fill up to the side seams
    "15b": dict(photo="15", pose="15", theta=0.0, landmarks=[(1.003, 150.0), (0.745, 402.0), (0.112, 926.0)],
                split_y=402, legs={-1: "first", 1: "last"}, exclude=[],
                anchors=[("center_front", 0, [(505, 165), (504, 300), (499, 396)])],
                own={-1: (-90.0, 92.0), 1: (-92.0, 92.0)}, priority=1),
    # walking, from behind-right: right leg (-X) shows its outer side, the left leg trails
    "8": dict(theta=104.0, landmarks=[(0.995, 20.0), (0.607, 440.0), (0.396, 585.0), (0.11, 850.0)],
              split_y=478, legs={1: "first", -1: "last"}, exclude=[(560, 0, 1000, 175), (640, 0, 1000, 290)],
              anchors=[("outseam", -1, [(592, 160), (597, 300), (603, 440)]),
                       ("outseam", -1, [(600, 610), (596, 690), (592, 760)])],
              own={-1: (40.0, 300.0), 1: (100.0, 260.0)}, priority=2),
    # close-up of the right hip/thigh from the side: back pocket, side zip, front cargo pocket
    "13": dict(theta=90.0, landmarks=[(0.995, 95.0), (0.808, 490.0), (0.607, 950.0), (0.585, 1000.0)],
               split_y=10000, legs={1: "first", -1: "last"}, exclude=[(0, 0, 1000, 95), (720, 60, 1000, 190)],
               anchors=[("outseam", -1, [(556, 215), (548, 330), (542, 410), (530, 600), (515, 800), (505, 995)])],
               own={-1: (40.0, 160.0)}, priority=4),
}
# mirrored copies: the left leg (+X) borrows the right leg's side and back photos
VIEWS["8m"] = dict(VIEWS["8"], photo="8", pose="8", mirror=True, own={1: (40.0, 200.0)}, priority=2)
VIEWS["8mb"] = dict(VIEWS["8"], photo="8", pose="8", mirror=True, own={-1: (200.0, 275.0)}, priority=2)
VIEWS["13m"] = dict(VIEWS["13"], photo="13", pose="13", mirror=True, own={1: (40.0, 160.0)}, priority=4)
VIEW_ORDER = ["15b", "8mb", "8m", "8", "15", "13m", "13"]   # ascending priority


class Projector:
    def __init__(self, mesh_npz):
        d = np.load(mesh_npz)
        self.rest = d["co"].astype(np.float32)
        self.rest_n = d["vnor"].astype(np.float32)
        self.tris = d["lvert"][d["tri"]]
        self.build = os.path.dirname(os.path.abspath(mesh_npz))
        self.side = np.where(self.rest[:, 0] >= 0, 1, -1)
        self._ref_olive = None

    def geometry(self, name):
        p = os.path.join(self.build, f"pose_{name}.npz")
        if os.path.exists(p):
            g = np.load(p)
            if len(g["co"]) == len(self.rest):
                return g["co"].astype(np.float32), g["vnor"].astype(np.float32), True
        return self.rest, self.rest_n, False

    def ref_olive(self):
        if self._ref_olive is None:
            ref = np.asarray(Image.open(os.path.join(REF, "15.jpg")).convert("RGB"), np.float32) / 255.0
            self._ref_olive = olive_mean(ref, photo_mask(ref * 255.0))
        return self._ref_olive

    def mirror_map(self):
        if not hasattr(self, "_mirror"):
            from scipy.spatial import cKDTree
            tree = cKDTree(self.rest)
            _, self._mirror = tree.query(self.rest * np.array([-1, 1, 1], np.float32))
        return self._mirror

    def project(self, name, bary, tverts):
        """bary: (n,3) barycentrics; tverts: (n,3) vertex ids of each texel's triangle."""
        v = VIEWS[name]
        if v.get("mirror"):   # texels of one leg sample the photo as the mirrored point of the other
            tverts = self.mirror_map()[tverts]
        photo = v.get("photo", name)
        co, vn, posed = self.geometry(v.get("pose", name))
        P = (co[tverts] * bary[..., None]).sum(1)
        N = (vn[tverts] * bary[..., None]).sum(1)
        N /= np.linalg.norm(N, axis=1, keepdims=True) + 1e-9
        phi, side = phi_side((self.rest[tverts] * bary[..., None]).sum(1))
        own_side = -side if v.get("mirror") else side

        img = np.asarray(Image.open(os.path.join(REF, f"{photo}.jpg")).convert("RGB"), np.float32) / 255.0
        lin = srgb_to_lin(img)
        mask = photo_mask(img * 255.0)
        for x0, y0, x1, y1 in v["exclude"]:
            mask[y0:y1, x0:x1] = False
        if photo != "15":
            gain = self.ref_olive() / (olive_mean(img, mask) + 1e-6)
            lin = lin * gain
            print(f"  view {name}: colour gain {np.round(gain, 3)}")
        pspan = row_spans(mask)
        d, r = view_axes(v["theta"])

        zs, ys = zip(*sorted(v["landmarks"]))
        zb = np.arange(co[:, 2].min() - 0.02, co[:, 2].max() + 0.02, 0.005, dtype=np.float32)
        mspan = model_spans(co, self.side, r, zb)

        z = P[:, 2]
        prow = np.interp(z, zs, ys, left=np.nan, right=np.nan)
        u = P @ r
        mi = np.clip((z - zb[0]) / (zb[1] - zb[0]), 0, len(zb) - 1.001)
        ms = interp_rows(mspan, mi)
        ps = interp_rows(pspan, prow)

        # silhouette anchors: whole trousers above the split row, the texel's own leg below
        below = np.nan_to_num(prow, nan=-1) > v["split_y"]
        run = {"first": 2, "last": 4}
        m0, m1 = ms[:, 0].copy(), ms[:, 1].copy()
        p0, p1 = ps[:, 0].copy(), ps[:, 1].copy()
        for s, k in ((-1, 2), (1, 4)):
            kp = run[v["legs"][s]]
            sel = below & (side == s) & ~np.isnan(ps[:, kp])
            m0[sel], m1[sel] = ms[sel, k], ms[sel, k + 1]
            p0[sel], p1[sel] = ps[sel, kp], ps[sel, kp + 1]
        AM, AP = [m0, m1], [p0, p1]
        # seam anchors
        for kind, s, pts in v["anchors"]:
            curve = feature_curve(co, self.rest, r, zb, kind, s if s else -1)
            mu = interp_rows(curve[:, None], mi)[:, 0]
            px = polyline_x(pts, np.nan_to_num(prow, nan=-1))
            use = ~np.isnan(mu) & ~np.isnan(px) & ((side == s) | (s == 0))
            AM.append(np.where(use, mu, np.nan))
            AP.append(np.where(use, px, np.nan))
        AM, AP = np.stack(AM, 1), np.stack(AP, 1)
        order = np.argsort(np.where(np.isnan(AM), np.inf, AM), axis=1)
        AM = np.take_along_axis(AM, order, 1)
        AP = np.take_along_axis(AP, order, 1)
        cnt = (~np.isnan(AM)).sum(1)
        j = np.clip((AM <= u[:, None]).sum(1) - 1, 0, np.maximum(cnt - 2, 0))
        rows = np.arange(len(u))
        a0, a1 = AM[rows, j], AM[rows, j + 1]
        b0, b1 = AP[rows, j], AP[rows, j + 1]
        da = np.where(np.abs(a1 - a0) < 1e-5, 1e-5, a1 - a0)
        X = b0 + (u - a0) / da * (b1 - b0)

        # visibility, viewing angle and panel ownership
        buf, u0, z0, cell = depth_buffer(co, self.tris, d, r)
        bi = np.clip(((z - z0) / cell).astype(np.int64), 0, buf.shape[0] - 1)
        bj = np.clip(((u - u0) / cell).astype(np.int64), 0, buf.shape[1] - 1)
        near = ndimage.minimum_filter(buf, 3)
        visible = (P @ d) <= near[bi, bj] + 0.012
        facing = -(N @ d)
        w = np.clip((facing - 0.05) / 0.3, 0, 1) * visible
        own = np.zeros_like(w)
        for s, (lo, hi) in v["own"].items():
            own = np.where(own_side == s, ang_window(phi, lo, hi), own)
        w *= own
        ok = ~np.isnan(X) & ~np.isnan(prow)
        X = np.where(ok, X, 0)
        Y = np.where(ok, prow, 0)
        inside = mask[np.clip(Y.astype(np.int64), 0, mask.shape[0] - 1),
                      np.clip(X.astype(np.int64), 0, mask.shape[1] - 1)]
        w = np.where(ok & inside, w, 0)
        rgb = bilinear(lin, X, Y)
        self.last_xy = (X.astype(np.float32), Y.astype(np.float32))
        ppm = abs(ys[-1] - ys[0]) / abs(zs[-1] - zs[0]) / 1000.0
        om = olive_regions(img * 255.0, mask, px_per_mm=ppm)
        self.last_olive = om[np.clip(Y.astype(np.int64), 0, om.shape[0] - 1),
                             np.clip(X.astype(np.int64), 0, om.shape[1] - 1)].astype(np.float32)
        print(f"  view {name}: {'posed' if posed else 'rest'} geometry, {np.mean(w > 0.5) * 100:.1f}% texels")
        return rgb.astype(np.float32), w.astype(np.float32)
