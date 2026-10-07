# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "scipy", "pillow"]
# ///
"""Photo | render at the same garment height, with guide lines every 2.5 % of the height.

Scales the render so the garment's top and bottom rows match the photo's, then draws shared
horizontal lines (fraction of the garment height labelled every 10 %). Reads
renders/_render_<view>.png from compare.py, writes renders/aligned_<view>.png.

    uv run art/EXP_ApexPants/scripts/align_compare.py 15 8 13
"""

import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import photo_project as PP  # noqa: E402

ART = os.path.normpath(os.path.join(HERE, ".."))


def extent(im):
    m = PP.photo_mask(np.asarray(im, np.float32), inset=1)
    rows = np.nonzero(m.sum(1) > 20)[0]
    cols = np.nonzero(m.sum(0) > 20)[0]
    return rows[0], rows[-1], cols[0], cols[-1]


def main():
    for view in sys.argv[1:] or ["15", "8", "13"]:
        a = Image.open(os.path.join(PP.REF, f"{view}.jpg")).convert("RGB")
        b = Image.open(os.path.join(ART, "renders", f"_render_{view}.png")).convert("RGB")
        pt, pb, pl, pr = extent(a)
        rt, rb, rl, rr = extent(b)
        k = (pb - pt) / max(rb - rt, 1)
        b2 = b.resize((max(1, round(b.width * k)), max(1, round(b.height * k))), Image.LANCZOS)
        W = a.width
        canvas = Image.new("RGB", (W * 2, a.height), (255, 255, 255))
        canvas.paste(a, (0, 0))
        x_off = W + (pl + pr) // 2 - round((rl + rr) / 2 * k)
        canvas.paste(b2, (x_off, round(pt - rt * k)))
        d = ImageDraw.Draw(canvas)
        H = pb - pt
        for i in range(0, 41):
            y = round(pt + H * i / 40)
            c = (255, 0, 0) if i % 4 == 0 else (0, 170, 255)
            d.line([(0, y), (canvas.width, y)], fill=c, width=1)
            if i % 4 == 0:
                d.text((2, y + 1), f"{i / 40:.1f}", fill=(255, 0, 0))
        out = os.path.join(ART, "renders", f"aligned_{view}.png")
        canvas.save(out)
        print("wrote", out)


if __name__ == "__main__":
    main()
