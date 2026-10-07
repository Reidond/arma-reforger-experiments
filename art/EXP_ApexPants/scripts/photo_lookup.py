# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "scipy", "pillow"]
# ///
"""Map the (side, phi, z) surface grid into every reference photo.

Writes build/lookup_<view>.npz (photo x, y and visibility weight per grid sample) and
renders/overlay_<view>.png: the photo with the model's iso-lines drawn on it — phi every
10 deg (red = 0/90/180, labelled) and z every 2 cm (labelled every 10 cm). Feature corners
can then be read straight off the clean photo in model coordinates.

    uv run art/EXP_ApexPants/scripts/photo_lookup.py 15 13 8
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


def lookup(view, g, pj):
    hit = g["hit"]
    rgb, w = pj.project(view, g["bary"][hit], g["tv"][hit])
    # recompute photo coordinates (project() returns colours; repeat the mapping cheaply)
    X, Y = pj.last_xy
    out = dict(x=np.full(len(hit), np.nan, np.float32), y=np.full(len(hit), np.nan, np.float32),
               w=np.zeros(len(hit), np.float32))
    out["x"][hit], out["y"][hit], out["w"][hit] = X, Y, w
    np.savez_compressed(os.path.join(BUILD, f"lookup_{view}.npz"), **out)
    return out


def overlay(view, g, lk, sides=(-1, 1)):
    v = PP.VIEWS[view]
    photo = v.get("photo", view)
    im = Image.open(os.path.join(PP.REF, f"{photo}.jpg")).convert("RGB")
    im = im.resize((im.width * 2, im.height * 2), Image.LANCZOS)
    dr = ImageDraw.Draw(im)
    phis, zs = g["phis"], g["zs"]
    n_p, n_z = len(phis), len(zs)
    for s in sides:
        base = 0 if s == -1 else n_p * n_z
        X = lk["x"][base:base + n_p * n_z].reshape(n_z, n_p) * 2
        Y = lk["y"][base:base + n_p * n_z].reshape(n_z, n_p) * 2
        W = lk["w"][base:base + n_p * n_z].reshape(n_z, n_p)
        ok = W > 0.15
        col_leg = (255, 60, 60) if s == -1 else (60, 160, 255)
        for j, ph in enumerate(phis):
            if int(ph) % 10:
                continue
            pts = [(X[i, j], Y[i, j]) if ok[i, j] else None for i in range(n_z)]
            c = (255, 255, 0) if int(ph) % 90 == 0 else col_leg
            draw_poly(dr, pts, c)
            for zl in LABEL_Z:
                i = int(round((zl - zs[0]) / (zs[1] - zs[0])))
                if 0 <= i < n_z and pts[i] is not None and int(ph) % 20 == 0:
                    dr.text((pts[i][0] + 2, pts[i][1] - 10), f"{int(ph)}", fill=c)
        for i, zz in enumerate(zs):
            zc = round(zz * 1000)
            if zc % 20:
                continue
            pts = [(X[i, j], Y[i, j]) if ok[i, j] else None for j in range(n_p)]
            c = (255, 255, 0) if zc % 100 == 0 else col_leg
            draw_poly(dr, pts, c)
            lab = [p for p in pts if p is not None]
            if lab and zc % 100 == 0:
                dr.text((lab[0][0] - 30, lab[0][1] - 6), f"{zz:.2f}", fill=c)
            elif lab and zc % 50 == 0:
                dr.text((lab[-1][0] + 4, lab[-1][1] - 6), f"{zz:.2f}", fill=c)
    path = os.path.join(ART, "renders", f"overlay_{view}.png")
    im.save(path)
    print("wrote", path)


LABEL_Z = (0.95, 0.75, 0.55, 0.35, 0.18)


def draw_poly(dr, pts, c):
    run = []
    for p in pts + [None]:
        if p is None or (run and abs(p[0] - run[-1][0]) + abs(p[1] - run[-1][1]) > 40):
            if len(run) > 1:
                dr.line(run, fill=c, width=1)
            run = [p] if p is not None else []
        else:
            run.append(p)


def main():
    views = sys.argv[1:] or ["15", "13", "8"]
    g = dict(np.load(os.path.join(BUILD, "surface_grid.npz")))
    pj = PP.Projector(os.path.join(BUILD, "pants_base.npz"))
    for v in views:
        lk = lookup(v, g, pj)
        overlay(v, g, lk)


if __name__ == "__main__":
    main()
