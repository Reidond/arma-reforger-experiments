"""One-shot rebuild inside Blender: base mesh -> mesh data -> textures -> LOD0 + preview.

    p = "<repo>/art/EXP_ApexPants/scripts/rebuild_all.py"
    exec(compile(open(p).read(), p, "exec"), {"__file__": p, "__name__": "__main__", "RES": 2048})
"""

import os
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
RES = globals().get("RES", 2048)
STEPS = globals().get("STEPS", ("base", "parts", "export", "textures", "preview"))
G = {}


def run_blender_script(name):
    p = os.path.join(HERE, name)
    g = {"__file__": p, "__name__": "__main__"}
    exec(compile(open(p).read(), p, "exec"), g)
    return g


if "base" in STEPS:
    run_blender_script("build_base.py")
if "parts" in STEPS or "base" in STEPS:
    run_blender_script("build_parts.py")
if "export" in STEPS:
    run_blender_script("export_mesh_data.py")
if "textures" in STEPS:
    uv = shutil.which("uv") or os.path.expanduser("~/.local/bin/uv")
    res = subprocess.run([uv, "run", os.path.join(HERE, "gen_textures.py"), "--res", str(RES), "--photos", "all"],
                         capture_output=True, text=True)
    print(res.stdout[-1500:], res.stderr[-1500:] if res.returncode else "")
    if res.returncode:
        raise RuntimeError("gen_textures.py failed")
if "preview" in STEPS:
    G.update(run_blender_script("setup_preview.py"))
