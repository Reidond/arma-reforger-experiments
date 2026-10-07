"""Bake large-scale ambient occlusion of Pants_LOD0 (crotch, folds, pocket edges) to build/ao_geo.png.

Run inside Blender after setup_preview.py; gen_textures.py multiplies it into the AO channel.
"""

import os

import bpy

ART = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
RES = globals().get("RES", 2048)


def bake_ao(res=RES, samples=96, distance=0.12):
    scn = bpy.context.scene
    ob = bpy.data.objects["Pants_LOD0"]
    for o in scn.objects:
        if o.type == "MESH":
            o.hide_render = o is not ob
    old = bpy.data.images.get("ao_geo")
    if old:  # a previous bake points at a file that may be gone
        bpy.data.images.remove(old)
    img = bpy.data.images.new("ao_geo", res, res, alpha=False, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    mat = ob.active_material
    nt = mat.node_tree
    node = nt.nodes.get("AO_BAKE") or nt.nodes.new("ShaderNodeTexImage")
    node.name = "AO_BAKE"
    node.image = img
    node.location = (-800, 600)
    for n in nt.nodes:
        n.select = False
    node.select = True
    nt.nodes.active = node

    scn.render.engine = "CYCLES"
    scn.cycles.samples = samples
    if scn.world:
        scn.world.light_settings.distance = distance
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.hide_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.bake(type="AO", margin=16, use_clear=True)
    out = os.path.join(ART, "build", "ao_geo.png")
    img.filepath_raw = out
    img.file_format = "PNG"
    img.save()
    nt.nodes.remove(node)
    print("baked AO ->", out)


bake_ao()
