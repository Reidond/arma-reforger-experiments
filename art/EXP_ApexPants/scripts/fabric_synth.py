# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "scipy", "pillow"]
# ///
"""Synthesize large fabric textures from close-up crops of the product photos.

Every crop is brought to one physical scale using the ripstop grid (≈5 mm, measured
against the 45 mm belt in photo 14), fold shading is divided out, and image quilting
(Efros & Freeman, minimum-error boundary cut) assembles a seamless texture far larger
than any single crop, so the camo is real Multicam print + ripstop at the right size.

    uv run art/EXP_ApexPants/scripts/fabric_synth.py            # all fabrics
    uv run art/EXP_ApexPants/scripts/fabric_synth.py camo --size 2048

Reads art/EXP_ApexPants/reference/*.jpg (not committed), writes textures/source/fabric_*.png.
"""

import argparse
import os
import time

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.normpath(os.path.join(HERE, ".."))
REF = os.path.join(ART, "reference")
OUT = os.path.join(ART, "textures", "source")

GRID_MM = 5.0          # ripstop square
MM_PER_PX = 0.3        # output scale (texture baker samples at ~0.34 mm/texel)

# (photo, crop box x0 y0 x1 y1, ripstop period in px measured in that photo)
CAMO = [
    ("16", (305, 720, 495, 985), 14.3), ("16", (555, 305, 845, 535), 15.2),
    ("1", (455, 205, 815, 380), 18.0), ("2", (445, 425, 645, 795), 16.4),
    ("10", (255, 650, 695, 815), 17.4), ("3", (560, 20, 995, 400), 16.5),
    ("5", (565, 455, 995, 795), 25.7), ("9", (605, 660, 720, 890), 14.4),
    ("13", (565, 640, 690, 880), 15.0), ("14", (565, 545, 765, 715), 10.9),
    ("4", (525, 305, 880, 695), 24.4),
]
# olive stretch (yoke, back thigh) — plain fabric, scale from the same photos
STRETCH = [
    ("13", (275, 95, 535, 195), 15.0), ("9", (612, 185, 690, 300), 14.4),
]


def load_crop(photo, box, period, delight=0.75, sigma_mm=14.0):
    im = Image.open(os.path.join(REF, f"{photo}.jpg")).convert("RGB").crop(box)
    s = (GRID_MM / MM_PER_PX) / period
    im = im.resize((max(8, round(im.width * s)), max(8, round(im.height * s))), Image.LANCZOS)
    a = np.asarray(im, np.float32) / 255.0
    lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    lum = lin @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    # fold shading varies slowly; print detail is sharper — divide out the slow part
    shade = ndimage.gaussian_filter(lum, sigma_mm / MM_PER_PX) / (lum.mean() + 1e-6)
    lin = lin / np.clip(shade, 0.3, 3)[..., None] ** delight
    return lin


def match_colour(crops):
    m = np.mean([c.reshape(-1, 3).mean(0) for c in crops], 0)
    out = []
    for c in crops:
        cm = c.reshape(-1, 3).mean(0)
        out.append(c * (1 + 0.6 * (m / (cm + 1e-6) - 1)))
    return out


def min_cut_vertical(err):
    """Min-cost top-to-bottom path through err (H x W); returns mask True right of the path."""
    h, w = err.shape
    cost = err.copy()
    for y in range(1, h):
        prev = cost[y - 1]
        left = np.concatenate([[np.inf], prev[:-1]])
        right = np.concatenate([prev[1:], [np.inf]])
        cost[y] += np.minimum(np.minimum(left, prev), right)
    path = np.zeros(h, np.int64)
    path[-1] = int(np.argmin(cost[-1]))
    for y in range(h - 2, -1, -1):
        x = path[y + 1]
        lo, hi = max(0, x - 1), min(w, x + 2)
        path[y] = lo + int(np.argmin(cost[y, lo:hi]))
    mask = np.arange(w)[None, :] >= path[:, None]
    return mask


def quilt(sources, size, block=112, overlap=22, candidates=700, tol=0.08, seed=0, wrap=True):
    rng = np.random.default_rng(seed)
    step = block - overlap
    n = int(np.ceil((size - overlap) / step))
    H = n * step + overlap
    out = np.zeros((H, H, 3), np.float32)
    # all valid patch origins
    origins = []
    for si, s in enumerate(sources):
        h, w = s.shape[:2]
        if h < block or w < block:
            continue
        ys, xs = np.mgrid[0:h - block + 1:2, 0:w - block + 1:2]
        origins.append(np.stack([np.full(ys.size, si), ys.ravel(), xs.ravel()], 1))
    origins = np.concatenate(origins)
    print(f"quilt {H}px from {len(sources)} crops, {len(origins)} patch origins")

    def patch(o):
        s = sources[o[0]]
        return s[o[1]:o[1] + block, o[2]:o[2] + block]

    for by in range(n):
        for bx in range(n):
            y, x = by * step, bx * step
            pick = origins[rng.integers(0, len(origins), candidates)]
            cand = np.stack([patch(o) for o in pick])  # (K, B, B, 3)
            err = np.zeros(len(pick), np.float32)
            if bx > 0:
                t = out[y:y + block, x:x + overlap]
                err += ((cand[:, :, :overlap] - t) ** 2).sum((1, 2, 3))
            if by > 0:
                t = out[y:y + overlap, x:x + block]
                err += ((cand[:, :overlap, :] - t) ** 2).sum((1, 2, 3))
            if bx == 0 and by == 0:
                best = 0
            else:
                ok = np.nonzero(err <= err.min() * (1 + tol) + 1e-9)[0]
                best = int(rng.choice(ok))
            p = cand[best].copy()
            keep_new = np.ones((block, block), bool)
            if bx > 0:
                e = ((p[:, :overlap] - out[y:y + block, x:x + overlap]) ** 2).sum(-1)
                keep_new[:, :overlap] &= min_cut_vertical(e)
            if by > 0:
                e = ((p[:overlap, :] - out[y:y + overlap, x:x + block]) ** 2).sum(-1)
                keep_new[:overlap, :] &= min_cut_vertical(e.T).T
            # feather the cut by one pixel to hide JPEG-level steps
            soft = ndimage.uniform_filter(keep_new.astype(np.float32), 3)
            if bx == 0 and by == 0:
                soft[:] = 1
            region = out[y:y + block, x:x + block]
            out[y:y + block, x:x + block] = region * (1 - soft[..., None]) + p * soft[..., None]
    out = out[:size, :size]
    if wrap:
        out = make_tileable(out, rng)
    return out


def make_tileable(img, rng, band=0.08):
    """Hide the wrap seam: blend with the half-rolled image along a wobbly band."""
    h, w = img.shape[:2]
    rolled = np.roll(np.roll(img, h // 2, 0), w // 2, 1)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    edge = np.minimum(np.minimum(xx, w - 1 - xx) / w, np.minimum(yy, h - 1 - yy) / h)
    noise = ndimage.gaussian_filter(rng.standard_normal((h, w)).astype(np.float32), w / 60)
    noise /= noise.std() + 1e-6
    m = np.clip((band - (edge + 0.02 * noise)) / 0.01, 0, 1)[..., None]
    return img * (1 - m) + rolled * m


def detail_layer(lin, sigma_px=4.0, edge_px=7.0):
    """Ratio of luminance to its local mean: ripstop threads, weave, slubs — no print.

    Print edges also create ratios, so pixels near strong low-pass colour edges are
    replaced by the median detail value (1.0) before quilting.
    """
    lum = lin @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    base = ndimage.gaussian_filter(lum, sigma_px)
    ratio = lum / (base + 1e-4)
    col = ndimage.gaussian_filter(lin, (edge_px, edge_px, 0))
    gy, gx = np.gradient(col, axis=(0, 1))
    edge = np.sqrt((gx ** 2 + gy ** 2).sum(-1)) / (col.mean() + 1e-4)
    thr = np.percentile(edge, 70)  # the strongest 30 % of slopes are print edges
    w = np.clip(1 - (edge - thr) / thr, 0, 1)
    w = ndimage.minimum_filter(w, 5)
    ratio = 1 + (ratio - 1) * w
    return np.repeat(np.clip(ratio, 0.6, 1.5)[..., None], 3, -1)


def save(lin, name):
    srgb = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * np.power(np.clip(lin, 0, 1), 1 / 2.4) - 0.055)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    Image.fromarray(np.clip(srgb * 255 + 0.5, 0, 255).astype(np.uint8)).save(path)
    print("wrote", os.path.relpath(path, ART), lin.shape[:2])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("which", nargs="*", default=["camo", "stretch"])
    ap.add_argument("--size", type=int, default=4096)
    args = ap.parse_args()
    t0 = time.time()
    if "camo" in args.which:
        crops = match_colour([load_crop(*c) for c in CAMO])
        for (p, b, per), c in zip(CAMO, crops):
            print(f"  crop {p} {b}: {c.shape[1]}x{c.shape[0]} px = {c.shape[1]*MM_PER_PX/10:.1f}x{c.shape[0]*MM_PER_PX/10:.1f} cm")
        save(quilt(crops, args.size, seed=1), "fabric_camo.png")
        print(f"camo done {time.time()-t0:.0f}s")
    if "detail" in args.which:
        # one uniform brown window of the macro photo 3, cut to whole ripstop squares
        # (grid 34.0 x 32.1 px there, measured), so the tile wraps with the grid aligned
        im = np.asarray(Image.open(os.path.join(REF, "3.jpg")).convert("RGB"), np.float32) / 255
        cx, cy, px, py, n = 853, 261, 34.0, 32.1, 5
        w, h = round(px * n), round(py * n)
        win = im[cy - h // 2:cy - h // 2 + h, cx - w // 2:cx - w // 2 + w]
        lum = win @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        ratio = lum / (ndimage.gaussian_filter(lum, 10, mode="wrap") + 1e-4)
        side = round(n * GRID_MM / MM_PER_PX)
        tile = np.asarray(Image.fromarray(ratio.astype(np.float32), "F").resize((side, side), Image.LANCZOS))
        # wrap seam: crossfade with a copy rolled by whole squares, so threads stay aligned
        k = round(2 * side / n)
        rolled = np.roll(np.roll(tile, k, 0), k, 1)
        yy, xx = np.mgrid[0:side, 0:side].astype(np.float32)
        edge = np.minimum(np.minimum(xx, side - 1 - xx), np.minimum(yy, side - 1 - yy)) / side
        m = np.clip((0.12 - edge) / 0.08, 0, 1)
        tile = tile * (1 - m) + rolled * m
        img = np.clip(tile - 1.0 + 0.5, 0, 1)
        os.makedirs(OUT, exist_ok=True)
        Image.fromarray((img * 65535).astype(np.uint16)).save(os.path.join(OUT, "fabric_detail.png"))
        print("wrote textures/source/fabric_detail.png", tile.shape, f"= {n} ripstop squares, std {tile.std():.3f}")
    if "stretch" in args.which:
        crops = match_colour([load_crop(*c, delight=0.9, sigma_mm=8) for c in STRETCH])
        save(quilt(crops, 1024, block=64, overlap=16, seed=2), "fabric_stretch.png")
        print(f"stretch done {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
