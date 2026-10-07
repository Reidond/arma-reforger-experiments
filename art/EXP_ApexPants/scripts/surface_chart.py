# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "scipy", "pillow"]
# ///
"""Flatten the textured trousers into one chart per leg: angle around the leg x height.

x: phi from -180 (back, inner side) .. 0 (front) .. +90 (outer seam) .. +180 (back);
y: z from 1.07 (top) down to 0.08 m. Grid every 15 deg / 2 cm, labelled.
Used to read where the photographed features are, so 3D parts can be placed on them.

    uv run art/EXP_ApexPants/scripts/surface_chart.py
"""

import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_textures as GT  # noqa: E402
import photo_project as PP  # noqa: E402

ART = os.path.normpath(os.path.join(HERE, ".."))
OUT = os.path.join(ART, "renders")
DEG_PX, Z_PX = 2.0, 1.0 / 1000      # px per degree, metres per px (≈ physical aspect at the thigh)
Z_TOP, Z_BOT = 1.07, 0.08


def main(res=2048):
    d = np.load(os.path.join(ART, "build", "pants_base.npz"))
    co, uv, lvert, tri = d["co"], d["uv"], d["lvert"], d["tri"]
    tid, l0, l1 = GT.rasterize(uv, tri, res)
    valid = tid >= 0
    t = tid[valid]
    L = np.stack([l0[valid], l1[valid], 1 - l0[valid] - l1[valid]], 1)
    tv = lvert[tri[t]]
    P = (co[tv] * L[..., None]).sum(1)
    phi, side = PP.phi_side(P)
    img = np.asarray(Image.open(os.path.join(ART, "textures", "preview", "Pants_MCDU_APEX_BaseColor.png")).convert("RGB"))
    img = np.flipud(img)
    cols = img[valid]
    W = int(360 * DEG_PX)
    H = int((Z_TOP - Z_BOT) / Z_PX)
    for s, name in ((-1, "right"), (1, "left")):
        sel = side == s
        x = ((phi[sel] + 180) * DEG_PX).astype(np.int64)
        y = ((Z_TOP - P[sel, 2]) / Z_PX).astype(np.int64)
        ok = (x >= 0) & (x < W) & (y >= 0) & (y < H)
        acc = np.zeros((H, W, 3), np.float64)
        cnt = np.zeros((H, W), np.float64)
        np.add.at(acc, (y[ok], x[ok]), cols[sel][ok])
        np.add.at(cnt, (y[ok], x[ok]), 1)
        from scipy import ndimage
        have = cnt > 0
        avg = acc / np.maximum(cnt, 1)[..., None]
        _, (iy, ix) = ndimage.distance_transform_edt(~have, return_indices=True)
        dist = ndimage.distance_transform_edt(~have)
        chart = np.where((dist < 4)[..., None], avg[iy, ix], 255).astype(np.uint8)
        im = Image.fromarray(chart)
        dr = ImageDraw.Draw(im)
        for ph in range(-180, 181, 10):
            xx = int((ph + 180) * DEG_PX)
            dr.line([(xx, 0), (xx, H)], fill=(255, 0, 0) if ph % 90 == 0 else (0, 200, 255), width=1)
            if ph % 30 == 0:
                dr.text((xx + 2, 2), str(ph), fill=(255, 255, 0))
        for zc in range(8, 108, 2):
            yy = int((Z_TOP - zc / 100) / Z_PX)
            dr.line([(0, yy), (W, yy)], fill=(255, 0, 0) if zc % 10 == 0 else (0, 200, 255), width=1)
            dr.text((2, yy + 1), f"{zc / 100:.2f}", fill=(255, 255, 0))
        path = os.path.join(OUT, f"chart_{name}.png")
        im.save(path)
        print("wrote", path, im.size)


if __name__ == "__main__":
    main()
