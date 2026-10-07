"""Build Pants_LOD0 (displaced game mesh) with a preview material and a render setup.

Run inside Blender after gen_textures.py:
    p = "<repo>/art/EXP_ApexPants/scripts/setup_preview.py"
    exec(compile(open(p).read(), p, "exec"), {"__file__": p, "__name__": "__main__"})
"""

import os

import bpy
import numpy as np
from mathutils import Vector

ART = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PREVIEW = os.path.join(ART, "textures", "preview")
NAME = "Pants_MCDU_APEX"


def displaced_lod0():
    base = bpy.data.objects.get("Pants_full") or bpy.data.objects["Pants_base"]
    h = np.load(os.path.join(ART, "build", "vertex_height.npy"))
    old = bpy.data.objects.get("Pants_LOD0")
    if old:
        bpy.data.meshes.remove(old.data)
    me = base.data.copy()
    me.name = "Pants_LOD0"
    ob = bpy.data.objects.new("Pants_LOD0", me)
    base.users_collection[0].objects.link(ob)
    n = len(me.vertices)
    co = np.empty(n * 3, np.float32)
    nor = np.empty(n * 3, np.float32)
    me.vertices.foreach_get("co", co)
    me.vertices.foreach_get("normal", nor)
    if len(h) != n:   # stale heights from another mesh: no displacement
        h = np.zeros(n, np.float32)
    co = co.reshape(-1, 3) + nor.reshape(-1, 3) * h[:, None]
    me.vertices.foreach_set("co", co.ravel())
    me.update()
    for p in me.polygons:
        p.use_smooth = True
    base.hide_set(True)
    return ob


def image(name, colorspace):
    path = os.path.join(PREVIEW, f"{NAME}_{name}.png")
    img = bpy.data.images.get(f"{NAME}_{name}")
    if img is None:
        img = bpy.data.images.load(path)
        img.name = f"{NAME}_{name}"
    else:
        img.filepath = path
        img.reload()
    img.colorspace_settings.name = colorspace
    return img


def material():
    mat = bpy.data.materials.get(NAME) or bpy.data.materials.new(NAME)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (600, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (300, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    def tex(name, cs, y):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = image(name, cs)
        n.location = (-400, y)
        return n

    bc = tex("BaseColor", "sRGB", 300)
    ro = tex("Roughness", "Non-Color", 0)
    me = tex("Metallic", "Non-Color", -250)
    nm = tex("Normal_GL", "Non-Color", -500)
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nmap.location = (0, -500)
    nt.links.new(bc.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(ro.outputs["Color"], bsdf.inputs["Roughness"])
    nt.links.new(me.outputs["Color"], bsdf.inputs["Metallic"])
    nt.links.new(nm.outputs["Color"], nmap.inputs["Color"])
    nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    # fabric sheen
    for key in ("Sheen Weight", "Sheen"):
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = 0.06
            break
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.25
    return mat


def studio():
    scn = bpy.context.scene
    world = bpy.data.worlds.get("ApexStudio") or bpy.data.worlds.new("ApexStudio")
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    bg = nt.nodes.new("ShaderNodeBackground")
    backdrop = nt.nodes.new("ShaderNodeBackground")
    backdrop.inputs["Color"].default_value = (0.82, 0.82, 0.82, 1)
    backdrop.inputs["Strength"].default_value = 1.0
    path = nt.nodes.new("ShaderNodeLightPath")
    mix = nt.nodes.new("ShaderNodeMixShader")
    out = nt.nodes.new("ShaderNodeOutputWorld")
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    hdr_dir = bpy.utils.system_resource("DATAFILES", path="studiolights/world")
    hdrs = sorted(f for f in os.listdir(hdr_dir) if f.endswith(".exr")) if hdr_dir else []
    pick = next((f for f in hdrs if "forest" in f), hdrs[0] if hdrs else None)
    if pick:
        env.image = bpy.data.images.load(os.path.join(hdr_dir, pick), check_existing=True)
        nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.35
    # HDRI lights the model, the camera sees a plain product-shot backdrop
    nt.links.new(path.outputs["Is Camera Ray"], mix.inputs["Fac"])
    nt.links.new(bg.outputs["Background"], mix.inputs[1])
    nt.links.new(backdrop.outputs["Background"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    scn.world = world

    def light(name, kind, loc, energy, size):
        ob = bpy.data.objects.get(name)
        if ob is None:
            ob = bpy.data.objects.new(name, bpy.data.lights.new(name, kind))
            scn.collection.objects.link(ob)
        ob.data.energy = energy
        if kind == "AREA":
            ob.data.size = size
        ob.location = loc
        d = Vector((0, 0, 0.6)) - Vector(loc)
        ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        return ob

    light("Key", "AREA", (-1.4, -2.0, 1.6), 110, 1.6)
    light("Fill", "AREA", (1.8, -1.2, 0.9), 35, 2.0)
    light("Rim", "AREA", (0.6, 2.2, 1.8), 90, 1.0)

    cam = bpy.data.objects.get("ApexCam")
    if cam is None:
        cam = bpy.data.objects.new("ApexCam", bpy.data.cameras.new("ApexCam"))
        scn.collection.objects.link(cam)
    cam.data.lens = 70
    scn.camera = cam
    scn.render.engine = "CYCLES"
    scn.cycles.samples = 64
    scn.cycles.use_denoising = True
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "METAL"
        prefs.get_devices()
        for dev in prefs.devices:
            dev.use = True
        scn.cycles.device = "GPU"
    except Exception as exc:  # CPU fallback
        print("GPU setup failed:", exc)
    scn.render.resolution_x = 1100
    scn.render.resolution_y = 1400
    scn.render.film_transparent = False
    scn.view_settings.view_transform = "AgX"
    try:
        scn.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    return cam


def aim(cam, loc, target=(0, 0, 0.6)):
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()


lod0 = displaced_lod0()
mat = material()
lod0.data.materials.clear()
lod0.data.materials.append(mat)
camera = studio()
aim(camera, (0.0, -2.6, 0.62))
print("Pants_LOD0 ready:", len(lod0.data.vertices), "verts")


def render(path, cam_loc, target=(0, 0, 0.6)):
    aim(bpy.context.scene.camera, cam_loc, target)
    for o in bpy.context.scene.objects:
        if o.type == "MESH":
            o.hide_render = o.name != "Pants_LOD0"
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
