# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "scipy", "pillow"]
# ///
"""Bake the MCDU APEX pants textures from analytic construction details.

Input : build/pants_base.npz (export_mesh_data.py, rest pose with UVs/tangents)
        textures/source/camo_print_*.png (optional; procedural camo otherwise)
        build/ao_geo.png (optional; Cycles AO bake of the displaced mesh)
Output: <mod>/Assets/Characters/Uniforms/Pants_MCDU_APEX/Data/Pants_MCDU_APEX_{BCR,NMO}.tif
        textures/preview/*.png, build/vertex_height.npy (mesh displacement, metres)

    uv run art/EXP_ApexPants/scripts/gen_textures.py --res 4096
"""

import argparse
import glob
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import apex_features as AF  # noqa: E402

ART = os.path.normpath(os.path.join(HERE, ".."))
BUILD = os.path.join(ART, "build")
REPO = os.path.normpath(os.path.join(ART, "..", ".."))
DATA = os.path.join(REPO, "mods", "EXP_ApexPants", "Assets", "Characters", "Uniforms", "Pants_MCDU_APEX", "Data")
PREVIEW = os.path.join(ART, "textures", "preview")
NAME = "Pants_MCDU_APEX"

MM = 0.001
CAMO_TILE_M = 0.62  # physical size of one camo swatch (matched to the photos)
CAMO_MEAN = np.array([124.0, 109.0, 84.0], np.float32)  # sRGB, from reference photos 15-17
CAMO_STD = np.array([34.0, 31.0, 27.0], np.float32)

# sRGB colours sampled from the product photos
COL = {
    AF.STRETCH: (141, 118, 82), AF.CORDURA: (138, 118, 82), AF.TAPE: (112, 100, 72),
    AF.COIL: (82, 74, 54), AF.METAL: (94, 88, 68), AF.VELCRO: (104, 101, 77),
    AF.WEBBING: (101, 95, 68), AF.CREVICE: (42, 38, 30),
}
THREAD = (126, 117, 88)
ROUGH = {AF.CAMO: 0.86, AF.FACING: 0.9, AF.STRETCH: 0.7, AF.CORDURA: 0.78, AF.TAPE: 0.8,
         AF.COIL: 0.5, AF.METAL: 0.4, AF.VELCRO: 0.97, AF.WEBBING: 0.82, AF.CREVICE: 0.9}


def srgb_to_lin(c):
    c = np.asarray(c, np.float32)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def col(rgb):
    return srgb_to_lin(np.array(rgb, np.float32) / 255.0)


# --------------------------------------------------------------------------- rasterize
def rasterize(uv, tri, R):
    tid = np.full((R, R), -1, np.int32)
    l0m = np.zeros((R, R), np.float32)
    l1m = np.zeros((R, R), np.float32)
    pts = uv[tri] * R - 0.5
    for t in range(len(tri)):
        (x0, y0), (x1, y1), (x2, y2) = pts[t]
        xmin, xmax = max(int(np.floor(min(x0, x1, x2))), 0), min(int(np.ceil(max(x0, x1, x2))), R - 1)
        ymin, ymax = max(int(np.floor(min(y0, y1, y2))), 0), min(int(np.ceil(max(y0, y1, y2))), R - 1)
        if xmax < xmin or ymax < ymin:
            continue
        det = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(det) < 1e-12:
            continue
        X, Y = np.meshgrid(np.arange(xmin, xmax + 1), np.arange(ymin, ymax + 1))
        l0 = ((y1 - y2) * (X - x2) + (x2 - x1) * (Y - y2)) / det
        l1 = ((y2 - y0) * (X - x2) + (x0 - x2) * (Y - y2)) / det
        inside = (l0 >= -1e-5) & (l1 >= -1e-5) & (1 - l0 - l1 >= -1e-5)
        tid[Y[inside], X[inside]] = t
        l0m[Y[inside], X[inside]] = l0[inside]
        l1m[Y[inside], X[inside]] = l1[inside]
    return tid, l0m, l1m


def _eval_chunk(args):
    P, N = args
    tex = AF.evaluate(P, N, "tex")
    geo = AF.evaluate(P, N, "geo")
    return dict(h=tex["h"], hg=geo["h"], mat=tex["mat"], panel=tex["panel"],
                stitch=tex["stitch"].astype(np.float16), dark=tex["dark"].astype(np.float16),
                wear=tex["wear"].astype(np.float16), cam_u=tex["cam_u"], cam_v=tex["cam_v"],
                side=tex["side"].astype(np.int8), z=tex["z"].astype(np.float32))


def evaluate_parallel(P, N, chunk=400_000, workers=None):
    parts = [(P[i:i + chunk], N[i:i + chunk]) for i in range(0, len(P), chunk)]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(_eval_chunk, parts))
    return {k: np.concatenate([r[k] for r in res]) for k in res[0]}


# --------------------------------------------------------------------------- camo
def make_tileable(img, seed=0):
    """Blend the swatch with its half-rolled copy along a noisy band so it wraps cleanly."""
    h, w = img.shape[:2]
    rolled = np.roll(np.roll(img, h // 2, 0), w // 2, 1)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    ex = np.minimum(xx, w - 1 - xx) / w
    ey = np.minimum(yy, h - 1 - yy) / h
    rng = np.random.default_rng(seed)
    noise = ndimage.gaussian_filter(rng.standard_normal((h, w)).astype(np.float32), w / 40)
    noise /= noise.std() + 1e-6
    edge = np.minimum(ex, ey) + 0.025 * noise
    m = np.clip((0.16 - edge) / 0.02, 0, 1)[..., None]
    return img * (1 - m) + rolled * m


def load_camo():
    files = sorted(glob.glob(os.path.join(ART, "textures", "source", "camo_print_ref_*.png")))
    out = []
    for f in files:
        im = np.asarray(Image.open(f).convert("RGB"), np.float32)
        # match the print to the product photos (sRGB mean/std of the cloth, slightly darker
        # than the photos because those include studio light); the generated swatches are
        # lighter, more yellow and lower in contrast
        m, s = im.reshape(-1, 3).mean(0), im.reshape(-1, 3).std(0)
        im = (im - m) / s * CAMO_STD + CAMO_MEAN
        im[..., 2] *= 0.95                                          # renders came out a touch blue
        grey = im.mean(-1, keepdims=True)
        im = grey + (im - grey) * 0.82                              # printed dye is duller
        im = np.where(im > 165, 165 + (im - 165) * 0.35, im)        # cream flecks, not white
        im = np.clip(im / 255.0, 0, 1)
        im = make_tileable(srgb_to_lin(im), seed=len(out))
        out.append(np.flipud(im))  # row 0 = bottom, like UV v
    return out, files


def sample_wrap(img, u, v):
    """Bilinear sample with wrap; u, v in tile units."""
    h, w = img.shape[:2]
    x = np.mod(u, 1.0) * w - 0.5
    y = np.mod(v, 1.0) * h - 0.5
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    x0 %= w
    y0 %= h
    x1, y1 = (x0 + 1) % w, (y0 + 1) % h
    return (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x1] * fx * (1 - fy)
            + img[y1, x0] * (1 - fx) * fy + img[y1, x1] * fx * fy)


def procedural_camo(u, v, seed):
    """Fallback multi-terrain camo in 2D (metres)."""
    p = np.stack([u, v, np.full_like(u, seed * 3.7)], 1).astype(np.float32)
    w = np.stack([AF.fbm3(p * 6, 3, 11), AF.fbm3(p * 6 + 5, 3, 12), np.zeros_like(u)], 1) * 0.025
    q = p + w
    bg = AF.fbm3(q * np.array([3, 4.5, 1], np.float32), 3, 13) * 0.5 + 0.5
    c = col((168, 151, 122)) * (1 - bg[:, None]) + col((143, 143, 104)) * bg[:, None]
    for rgb, sc, thr, sd in (((107, 115, 80), (9, 11), 0.18, 21), ((122, 90, 66), (10, 12), 0.22, 22),
                             ((62, 44, 36), (18, 9), 0.33, 23), ((63, 74, 48), (17, 9), 0.34, 24),
                             ((216, 207, 182), (28, 30), 0.42, 25)):
        n = AF.fbm3(q * np.array([sc[0], sc[1], 1], np.float32), 4, sd)
        m = np.clip((n - thr) / 0.02, 0, 1)[:, None]
        c = c * (1 - m) + col(rgb) * m
    return c


PHOTO_RELIEF = 3.0 * MM    # metres of relief per unit of log-shading (photo mode)
PHOTO_PX_M = 0.0012        # size of one product-photo pixel on the garment
PHOTO_SHARPEN = 0.7
PANEL_EDGE_TRUST_M = 0.008  # camo this close to an olive panel uses the print, not the photo


def olive_mask(srgb):
    c = srgb * 255.0
    R_, G_, B_ = c[..., 0], c[..., 1], c[..., 2]
    L = c.mean(-1)
    m = (np.abs(R_ - G_) < 12) & (B_ < G_ - 12) & (L > 55) & (L < 160)
    m = ndimage.binary_opening(m, iterations=2)
    return ndimage.binary_closing(m, iterations=3)


def load_detail():
    p = os.path.join(ART, "textures", "source", "fabric_detail.png")
    if not os.path.exists(p):
        return None
    d = np.asarray(Image.open(p), np.float32) / 65535.0
    return np.flipud(d - 0.5).copy()


# --------------------------------------------------------------------------- micro fabric
def micro_height(mat, um, vm, texel_m, rng):
    """Fabric structure in UV space (metres): ripstop grid, twill, cordura, velcro."""
    h = np.zeros_like(um)
    n = rng.standard_normal(um.shape).astype(np.float32)
    fine = ndimage.gaussian_filter(n, 0.7)
    grid = 5.5 * MM
    du = np.abs(np.mod(um, grid) - grid / 2) - grid / 2 + 0.35 * MM
    dv = np.abs(np.mod(vm, grid) - grid / 2) - grid / 2 + 0.35 * MM
    rip = np.maximum(np.exp(-(np.minimum(np.abs(du), 1) / (0.25 * MM)) ** 2) * (du > -0.5 * MM),
                     np.exp(-(np.minimum(np.abs(dv), 1) / (0.25 * MM)) ** 2) * (dv > -0.5 * MM))
    camo = (mat == AF.CAMO) | (mat == AF.FACING)
    h += np.where(camo, 0.10 * MM * rip + 0.02 * MM * fine, 0)
    twill_p = max(0.9 * MM, 3 * texel_m)
    twill = np.sin(2 * np.pi * (um + vm) / twill_p)
    h += np.where(mat == AF.STRETCH, 0.02 * MM * twill + 0.02 * MM * fine, 0)
    bw = max(1.0 * MM, 3 * texel_m)
    basket = np.sin(2 * np.pi * um / bw) * np.sin(2 * np.pi * vm / bw)
    h += np.where(mat == AF.CORDURA, 0.06 * MM * basket + 0.03 * MM * fine, 0)
    fuzz = ndimage.gaussian_filter(n, 1.2)
    h += np.where(mat == AF.VELCRO, 0.12 * MM * fuzz / (fuzz.std() + 1e-6), 0)
    rib = np.sin(2 * np.pi * vm / max(1.2 * MM, 3 * texel_m))
    h += np.where((mat == AF.WEBBING) | (mat == AF.TAPE), 0.05 * MM * rib, 0)
    return h, rip, fine


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", type=int, default=4096)
    ap.add_argument("--mesh", default=os.path.join(BUILD, "pants_base.npz"))
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--photos", nargs="*", default=[], help="project these reference photos (photo_project.VIEWS)")
    ap.add_argument("--heights-only", action="store_true", help="only write build/vertex_height.npy")
    args = ap.parse_args()
    R = args.res
    t0 = time.time()
    d = np.load(args.mesh)
    co, vnor, uv, tan, sign, lvert, tri = (d[k] for k in ("co", "vnor", "uv", "tan", "sign", "lvert", "tri"))

    # per-vertex part info (build_parts.py): 0 = trouser shell, else part id / fabric code + 1
    vpart = d["part_id"] if "part_id" in d.files else np.zeros(len(co), np.int32)
    vfab = d["part_fabric"] if "part_fabric" in d.files else np.zeros(len(co), np.int32)

    # vertex displacement for the game mesh (seams, knee dome, folds) — shell only, parts are modelled
    vh = evaluate_parallel(co.astype(np.float32), vnor.astype(np.float32), workers=args.workers)["hg"]
    vh = np.where(vpart > 0, 0.0, vh)
    os.makedirs(BUILD, exist_ok=True)
    np.save(os.path.join(BUILD, "vertex_height.npy"), vh.astype(np.float32))
    print(f"vertex heights: {len(vh)} verts, range {vh.min()*1000:.1f}..{vh.max()*1000:.1f} mm  ({time.time()-t0:.1f}s)")
    if args.heights_only:
        return

    tid, l0m, l1m = rasterize(uv, tri, R)
    valid = tid >= 0
    print(f"rasterized {R}x{R}: {valid.mean()*100:.1f}% coverage ({time.time()-t0:.1f}s)")

    t = tid[valid]
    L0, L1 = l0m[valid][:, None], l1m[valid][:, None]
    L2 = 1 - L0 - L1
    tl = tri[t]
    tv = lvert[tl]
    P = co[tv[:, 0]] * L0 + co[tv[:, 1]] * L1 + co[tv[:, 2]] * L2
    N = vnor[tv[:, 0]] * L0 + vnor[tv[:, 1]] * L1 + vnor[tv[:, 2]] * L2
    N /= np.linalg.norm(N, axis=1, keepdims=True) + 1e-9
    T = tan[tl[:, 0]] * L0 + tan[tl[:, 1]] * L1 + tan[tl[:, 2]] * L2
    S = sign[tl[:, 0]]

    # per-triangle Jacobian dP/d(texel u, texel v)
    duv = (uv[tri[:, 1:]] - uv[tri[:, :1]]) * R           # (nt,2,2) rows: e1, e2
    dp = co[lvert[tri[:, 1:]]] - co[lvert[tri[:, :1]]]    # (nt,2,3)
    inv = np.linalg.pinv(duv)                             # (nt,2,2)
    J = np.einsum("tij,tjk->tik", inv, dp)                # rows: dP/du, dP/dv
    area3d = 0.5 * np.linalg.norm(np.cross(dp[:, 0], dp[:, 1]), axis=1).sum()
    e = uv[tri[:, 1:]] - uv[tri[:, :1]]
    areauv = 0.5 * np.abs(e[:, 0, 0] * e[:, 1, 1] - e[:, 0, 1] * e[:, 1, 0]).sum()
    uv_scale = float(np.sqrt(area3d / areauv))            # metres per UV unit
    texel_m = uv_scale / R
    print(f"uv scale {uv_scale:.3f} m/UV, texel {texel_m*1000:.2f} mm")

    f = evaluate_parallel(P.astype(np.float32), N.astype(np.float32), workers=args.workers)
    tpart = vpart[tv[:, 0]]
    tfab = vfab[tv[:, 0]]
    on_part = tpart > 0
    f["mat"] = np.where(on_part, np.maximum(tfab - 1, 0), f["mat"]).astype(np.uint8)
    f["panel"] = np.where(on_part, (20 + tpart) % 250, f["panel"]).astype(np.uint8)
    for k in ("h", "hg", "stitch", "dark", "wear"):          # parts carry their own geometry
        f[k] = np.where(on_part, 0, f[k]).astype(f[k].dtype)
    print(f"features evaluated ({time.time()-t0:.1f}s)")

    proj = []
    if args.photos:
        import photo_project as PP
        pj = PP.Projector(args.mesh)
        bary = np.hstack([L0, L1, L2]).astype(np.float32)
        names = [n for n in PP.VIEW_ORDER if n in args.photos or args.photos == ["all"]]
        camo_t = (f["mat"] == AF.CAMO)
        for name in names:
            rgb, w = pj.project(name, bary, tv)
            # photo pixels are only trusted on camo fabric, and only where the photo shows camo:
            # olive panel shapes come from the explicit layout, never from a misregistered photo
            w = w * camo_t * (1.0 - pj.last_olive)
            proj.append((rgb, w))
            print(f"projected photo {name}: {np.mean(w > 0.01)*100:.1f}% of texels ({time.time()-t0:.1f}s)")

    # scatter into full maps and fill the gutter from the nearest texel
    _, (iy, ix) = ndimage.distance_transform_edt(~valid, return_indices=True)

    def full(arr, dtype=np.float32):
        m = np.zeros((R, R) + arr.shape[1:], dtype)
        m[valid] = arr
        return m[iy, ix]

    H, Hg = full(f["h"]), full(f["hg"])
    mat, panel = full(f["mat"], np.uint8), full(f["panel"], np.uint8)
    stitch, dark, wear = full(f["stitch"]), full(f["dark"]), full(f["wear"])
    camu, camv, side, zz = full(f["cam_u"]), full(f["cam_v"]), full(f["side"], np.int8), full(f["z"])
    Nf, Tf, Sf = full(N), full(T), full(S)
    proj = [(full(rgb), full(w)) for rgb, w in proj]
    Jf = J[full(t, np.int32)]
    del f, P, N, T

    photo_mode = bool(proj)
    if photo_mode:
        import photo_intrinsics as PI
        pc = np.zeros((R, R, 3), np.float32)
        pcov = np.zeros((R, R), np.float32)
        for rgb, w in proj:            # ascending priority: later views overwrite
            pc = pc * (1 - w[..., None]) + rgb * w[..., None]
            pcov = pcov * (1 - w) + w
        pc = np.where(pcov[..., None] > 1e-4, pc / np.maximum(pcov, 1e-4)[..., None], 0)
        camo_full = (mat == AF.CAMO) & valid
        # do not trust photo camo right next to olive panels: misregistration shows up there first
        olive_full = ((mat == AF.STRETCH) | (mat == AF.CORDURA)) & valid
        near_olive = ndimage.distance_transform_edt(~olive_full) * texel_m < PANEL_EDGE_TRUST_M
        pcov = pcov * ~near_olive
        pc, pcov = PI.fill_gaps(pc, pcov * camo_full, camo_full & ~near_olive, sigmas=(2, 4, 8))
        # the product photos are ~1.2 mm/px: restore some crispness at that scale
        sig = PHOTO_PX_M / texel_m
        blur = np.stack([ndimage.gaussian_filter(pc[..., c], sig) for c in range(3)], -1)
        pc = np.where((pcov > 0.05)[..., None], np.clip(pc + PHOTO_SHARPEN * (pc - blur), 0, 1), pc)
        print(f"photo coverage after fill {np.mean(pcov[valid] > 0.5)*100:.1f}% ({time.time()-t0:.1f}s)")
        photo_alb, photo_shp = PI.intrinsic(pc, valid & (pcov > 0.5), texel_m)
        print(f"intrinsic split, shading hp std {photo_shp[valid].std():.3f} ({time.time()-t0:.1f}s)")
        H = (H + np.where(pcov > 0.5, PHOTO_RELIEF * ndimage.gaussian_filter(photo_shp, 0.7), 0)).astype(np.float32)

    rng = np.random.default_rng(7)
    vv, uu = np.mgrid[0:R, 0:R].astype(np.float32)
    um, vm = (uu + 0.5) / R * uv_scale, (vv + 0.5) / R * uv_scale
    hmicro, rip, fine = micro_height(mat, um, vm, texel_m, rng)
    if photo_mode:
        olive = ((mat == AF.STRETCH) | (mat == AF.CORDURA)) & valid
        rip_tile = load_detail()
        if rip_tile is not None:
            tm = rip_tile.shape[0] * 0.3 * MM               # tile size in metres (0.3 mm/px)
            d_rip = sample_wrap(rip_tile[..., None].repeat(3, -1), um.ravel() / tm, vm.ravel() / tm)[:, 0].reshape(R, R)
        else:
            d_rip = np.zeros((R, R), np.float32)
        weave = ndimage.gaussian_filter(rng.standard_normal((R, R)).astype(np.float32), 0.6)
        hmicro = np.where(olive, 0.02 * MM * weave, 0.12 * MM * d_rip / (np.abs(d_rip).max() + 1e-6) + 0.01 * MM * weave)
        rip = np.where(olive, 0, np.clip(d_rip * 4, -1, 1))

    # ---------------------------------------------------------------- normal map
    Hd = H - Hg + hmicro
    hv, hu = np.gradient(Hd)
    Pu, Pv = Jf[..., 0, :], Jf[..., 1, :]
    a11, a12, a22 = (Pu * Pu).sum(-1), (Pu * Pv).sum(-1), (Pv * Pv).sum(-1)
    det = a11 * a22 - a12 * a12 + 1e-20
    c1 = (a22 * hu - a12 * hv) / det
    c2 = (-a12 * hu + a11 * hv) / det
    g = c1[..., None] * Pu + c2[..., None] * Pv
    n = Nf - g
    n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-9
    Tn = Tf - Nf * (Nf * Tf).sum(-1, keepdims=True)
    Tn /= np.linalg.norm(Tn, axis=-1, keepdims=True) + 1e-9
    B = Sf[..., None] * np.cross(Nf, Tn)
    nts = np.stack([(n * Tn).sum(-1), (n * B).sum(-1), (n * Nf).sum(-1)], -1)
    del g, n, Tn, B, Pu, Pv, Jf
    print(f"normals ({time.time()-t0:.1f}s)")

    # ---------------------------------------------------------------- ambient occlusion
    px = lambda m: m / texel_m  # noqa: E731
    ao = np.ones((R, R), np.float32)
    for sig, depth, w in ((1.2 * MM, 0.5 * MM, 0.35), (5 * MM, 1.5 * MM, 0.35), (15 * MM, 4 * MM, 0.3)):
        occ = np.clip((ndimage.gaussian_filter(H, px(sig)) - H) / depth, 0, 1)
        ao -= w * occ
    ao *= 1 - 0.5 * dark
    if photo_mode:
        ao *= np.where(pcov > 0.5, np.exp(np.minimum(photo_shp, 0) * 1.2), 1.0)
    ao = np.where(mat == AF.FACING, ao * 0.75, ao)
    geo_ao = os.path.join(BUILD, "ao_geo.png")
    if os.path.exists(geo_ao):
        g_ao = np.flipud(np.asarray(Image.open(geo_ao).convert("L").resize((R, R)), np.float32) / 255.0)
        ao *= g_ao
        print("applied geometric AO")
    ao = np.clip(ao, 0.05, 1)

    # ---------------------------------------------------------------- base colour
    camos, files = load_camo()
    print("camo:", [os.path.basename(x) for x in files] or "procedural")
    camo_px = (mat == AF.CAMO) | (mat == AF.FACING)
    base = np.zeros((R, R, 3), np.float32)
    idx = np.nonzero(camo_px)
    key = panel[idx].astype(np.int64) * 2 + (side[idx] > 0)
    off_u = ((key * 7919) % 997) / 997.0
    off_v = ((key * 104729) % 991) / 991.0
    if camos:
        ccol = np.zeros((len(key), 3), np.float32)
        for k, img in enumerate(camos):
            sel = (key % len(camos)) == k
            ccol[sel] = sample_wrap(img, camu[idx][sel] / CAMO_TILE_M + off_u[sel], camv[idx][sel] / CAMO_TILE_M + off_v[sel])
    else:
        ccol = procedural_camo(camu[idx] + off_u * CAMO_TILE_M, camv[idx] + off_v * CAMO_TILE_M, 1)
    base[idx] = ccol
    for m, rgb in COL.items():
        base[mat == m] = col(rgb)
    base = np.where((mat == AF.FACING)[..., None], base * 0.8, base)

    # fabric structure, dye variation, fading, dirt
    lum_var = 1 + 0.03 * fine + 0.05 * rip * camo_px
    big = ndimage.gaussian_filter(rng.standard_normal((R // 16, R // 16)).astype(np.float32), 3)
    big = np.kron(big / (big.std() + 1e-6), np.ones((16, 16), np.float32))[:R, :R]
    base *= (lum_var * (1 + 0.035 * big))[..., None]
    conv = np.clip((H - ndimage.gaussian_filter(H, px(6 * MM))) / (1.5 * MM), -1, 1)
    fade = np.clip(0.5 * wear + 0.35 * np.maximum(conv, 0), 0, 1)
    grey = base.mean(-1, keepdims=True)
    base = base * (1 - 0.25 * fade[..., None]) + (grey * 1.15 + 0.02) * 0.25 * fade[..., None]
    hem = np.clip(1 - (zz - 0.10) / 0.16, 0, 1) ** 1.5
    dirt_n = np.clip(0.5 + 0.5 * ndimage.gaussian_filter(rng.standard_normal((R, R)).astype(np.float32), px(4 * MM)) * 6, 0, 1)
    knee = np.clip(1 - np.abs(zz - 0.47) / 0.1, 0, 1) * (mat == AF.CORDURA)
    dirt = np.clip(hem * (0.55 + 0.45 * dirt_n) + 0.25 * knee * dirt_n + 0.25 * np.maximum(-conv, 0) * hem, 0, 1)
    base = base * (1 - 0.45 * dirt[..., None]) + col((96, 82, 62)) * 0.45 * dirt[..., None]
    base = base * (1 - stitch[..., None]) + col(THREAD) * (1 + 0.1 * fine[..., None]) * stitch[..., None]
    base *= (1 - 0.6 * dark)[..., None]
    base *= (0.55 + 0.45 * ao)[..., None]  # a little baked cavity, the engine adds the rest
    if photo_mode:
        pa = photo_alb * (1 + 0.06 * rip)[..., None]          # photographed ripstop, subtle
        pa *= (0.75 + 0.25 * ao)[..., None]                   # keep a bit of crease darkening
        base = base * (1 - pcov[..., None]) + pa * pcov[..., None]
    base_srgb = lin_to_srgb(base)

    rough = np.zeros((R, R), np.float32)
    for m, r in ROUGH.items():
        rough[mat == m] = r
    rough = np.clip(rough + 0.04 * fine + 0.06 * dirt - 0.08 * fade - 0.05 * stitch, 0.05, 1)
    metal = np.where(mat == AF.METAL, 0.55, 0.0).astype(np.float32)

    # ---------------------------------------------------------------- write
    os.makedirs(DATA, exist_ok=True)
    os.makedirs(PREVIEW, exist_ok=True)
    to8 = lambda x: np.clip(np.round(x * 255), 0, 255).astype(np.uint8)  # noqa: E731
    up = lambda x: np.flipud(x)  # noqa: E731  (image row 0 is the top)
    bcr = np.dstack([to8(base_srgb), to8(rough)])
    ngl = nts * 0.5 + 0.5
    ndx = ngl.copy()
    ndx[..., 1] = 1 - ndx[..., 1]  # Enfusion uses DirectX normals
    nmo = np.dstack([to8(ndx[..., 0]), to8(ndx[..., 1]), to8(metal), to8(ao)])
    Image.fromarray(up(bcr), "RGBA").save(os.path.join(DATA, f"{NAME}_BCR.tif"), compression="tiff_lzw")
    Image.fromarray(up(nmo), "RGBA").save(os.path.join(DATA, f"{NAME}_NMO.tif"), compression="tiff_lzw")
    Image.fromarray(up(to8(base_srgb))).save(os.path.join(PREVIEW, f"{NAME}_BaseColor.png"))
    Image.fromarray(up(to8(ngl))).save(os.path.join(PREVIEW, f"{NAME}_Normal_GL.png"))
    Image.fromarray(up(to8(rough))).save(os.path.join(PREVIEW, f"{NAME}_Roughness.png"))
    Image.fromarray(up(to8(ao))).save(os.path.join(PREVIEW, f"{NAME}_AO.png"))
    Image.fromarray(up(to8(metal))).save(os.path.join(PREVIEW, f"{NAME}_Metallic.png"))
    hh = H - H.min()
    Image.fromarray(up((hh / (hh.max() + 1e-9) * 65535).astype(np.uint16))).save(os.path.join(PREVIEW, f"{NAME}_Height16.png"))
    print(f"height range {H.min()*1000:.2f}..{H.max()*1000:.2f} mm")
    print(f"done in {time.time()-t0:.1f}s -> {DATA}")


if __name__ == "__main__":
    main()
