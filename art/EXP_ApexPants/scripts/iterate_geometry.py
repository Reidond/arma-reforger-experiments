"""Blender: rebuild geometry (optionally the base), heights, preview mesh, export and posed meshes.

    p = "<repo>/art/EXP_ApexPants/scripts/iterate_geometry.py"
    exec(compile(open(p).read(), p, "exec"), {"__file__": p, "__name__": "__main__", "BASE": True})
Then run gen_textures.py and compare.py.
"""

import os
import subprocess
import time

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = globals().get("BASE", True)


def run(name, **kw):
    p = os.path.join(HERE, name)
    g = {"__file__": p, "__name__": "__main__"}
    g.update(kw)
    exec(compile(open(p).read(), p, "exec"), g)
    return g


t = time.time()
if BASE:
    run("build_base.py")
run("build_parts.py")
run("export_mesh_data.py")
uv = os.path.expanduser("~/.local/bin/uv")
r = subprocess.run([uv, "run", os.path.join(HERE, "gen_textures.py"), "--heights-only"], capture_output=True, text=True)
print(r.stdout.strip()[-200:], r.stderr[-800:] if r.returncode else "")
run("setup_preview.py")
run("export_game.py")
run("compare.py", SHOTS_RUN=["15", "8", "13"], POSE_ONLY=True)
bpy.ops.wm.save_mainfile()
print(f"geometry iteration done in {time.time() - t:.1f}s")
