# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "scipy", "pillow"]
# ///
"""Unwrap each reference photo onto the leg pattern chart (phi x z), one image per view and leg.

Only samples the view sees well (weight > MIN_W) are drawn, so every chart is pure evidence
from one photo. Grid: phi every 10 deg (labelled every 30), z every 2 cm (labelled every 10).
Needs build/surface_grid.npz (surface_samples.py) and build/lookup_<view>.npz (photo_lookup.py).

    uv run art/EXP_ApexPants/scripts/unwrap_views.py 15 8 13
"""

import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import photo_project as PP  # noqa: E402

ART = os.path.normpath(os.path.join(HERE, ".."))
BUILD = os.path.join(ART, "build")
OUT = os.path.join(ART, "renders")
MIN_W = 0.3
SX, SY = 3, 2          # display pixels per grid step (1 deg, 2.5 mm)


def chart(view, g, lk, s):
    v = PP.VIEWS[view]
    img = np.asarray(Image.open(os.path.join(PP.REF, f"{v.get('photo', view)}.jpg")).convert("RGB"), np.float32)
    phis, zs = g["phis"], g["zs"]
    n_p, n_z = len(phis), len(zs)
    base = 0 if s == -1 else n_p * n_z
    sl = slice(base, base + n_p * n_z)
    X = lk["x"][sl].reshape(n_z, n_p)
    Y = lk["y"][sl].reshape(n_z, n_p)
    W = lk["w"][sl].reshape(n_z, n_p)
    ok = (W > MIN_W) & ~np.isnan(X)
    col = np.full((n_z, n_p, 3), 255, np.float32)
    xi = np.clip(np.nan_to_num(X).astype(np.int64), 0, img.shape[1] - 1)
    yi = np.clip(np.nan_to_num(Y).astype(np.int64), 0, img.shape[0] - 1)
    col[ok] = img[yi[ok], xi[ok]]
    col = col[::-1]                       # top = high z
    im = Image.fromarray(col.astype(np.uint8)).resize((n_p * SX, n_z * SY), Image.NEAREST)
    dr = ImageDraw.Draw(im)
    for ph in range(-180, 181, 10):
        x = int((ph - phis[0]) / (phis[1] - phis[0]) * SX)
        dr.line([(x, 0), (x, im.height)], fill=(255, 0, 0) if ph % 90 == 0 else (0, 190, 255), width=1)
        if ph % 30 == 0:
            dr.text((x + 2, 2), str(ph), fill=(255, 0, 0))
    for zc in range(8, 108, 2):
        y = int((zs[-1] - zc / 100) / (zs[1] - zs[0]) * SY)
        dr.line([(0, y), (im.width, y)], fill=(255, 0, 0) if zc % 10 == 0 else (0, 190, 255), width=1)
        if zc % 10 == 0:
            dr.text((2, y + 1), f"{zc / 100:.1f}", fill=(255, 0, 0))
    path = os.path.join(OUT, f"unwrap_{view}_{'R' if s == -1 else 'L'}.png")
    im.save(path)
    return path


def main():
    views = sys.argv[1:] or ["15", "8", "13"]
    g = dict(np.load(os.path.join(BUILD, "surface_grid.npz")))
    for v in views:
        lk = dict(np.load(os.path.join(BUILD, f"lookup_{v}.npz")))
        for s in (-1, 1):
            print("wrote", chart(v, g, lk, s))


if __name__ == "__main__":
    main()
