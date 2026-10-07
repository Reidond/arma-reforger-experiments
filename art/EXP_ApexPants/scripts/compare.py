"""Render the skinned trousers like a reference photo and save a side-by-side sheet.

Run inside Blender (after export_game.py created Pants_MCDU_APEX_LOD0):
    p = "<repo>/art/EXP_ApexPants/scripts/compare.py"
    exec(compile(open(p).read(), p, "exec"), {"__file__": p, "__name__": "__main__", "SHOTS": ["15"]})

Each shot poses the Reforger skeleton roughly like the photo, frames the camera the same
way, lights a white product-shot studio and writes renders/compare_<photo>.png
(photo left, render right).
"""

import math
import os

import bpy
import numpy as np
from mathutils import Matrix, Vector

ART = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REF = os.path.join(ART, "reference")
OUT = os.path.join(ART, "renders")
NAME = "Pants_MCDU_APEX"

# pose: bone -> (axis, degrees) applied in world space about the bone head, in order
RIGHT_TWIST_15 = globals().get("RIGHT_TWIST_15", 18.0)   # the mannequin's right leg is turned out

SHOTS = {
    "15": dict(cam_azimuth=0.0, cam_elev=2.0, lens=120, dist=6.0, target=(0, 0, 0.57), frame_h=1.12,
               pose=[("LeftLeg", "Y", 6.5), ("RightLeg", "Y", -6.5), ("RightLeg", "TWIST", RIGHT_TWIST_15)], body=False),
    "8": dict(cam_azimuth=-104.0, cam_elev=8.0, lens=85, dist=4.2, target=(0, 0.05, 0.50), frame_h=1.08,
              pose=[("LeftLeg", "X", 20), ("RightLeg", "X", 5), ("RightKnee", "X", 4)], body=False),
}
SHOTS["13"] = dict(cam_azimuth=-90.0, cam_elev=0.0, lens=85, dist=3.0, target=(0, 0.0, 0.80), frame_h=0.47,
                   pose=[("LeftLeg", "Y", 6.5), ("RightLeg", "Y", -6.5)], body=False)
SHOTS["detail_waist"] = dict(cam_azimuth=-35.0, cam_elev=18.0, lens=85, dist=1.5, target=(-0.06, -0.02, 0.97),
                             frame_h=0.22, pose=[], body=False)
SHOTS["detail_flap"] = dict(cam_azimuth=-70.0, cam_elev=-22.0, lens=85, dist=1.5, target=(-0.17, -0.02, 0.76),
                            frame_h=0.22, pose=[], body=False)
SHOTS["detail_knee"] = dict(cam_azimuth=-25.0, cam_elev=5.0, lens=85, dist=1.5, target=(-0.13, -0.03, 0.47),
                            frame_h=0.34, pose=[], body=False)
SHOTS_TO_RUN = globals().get("SHOTS_RUN", ["15"])
LIGHT = globals().get("LIGHT", 0.43)          # calibrated: camo mean matches photo 15
WORLD_FILL = globals().get("WORLD_FILL", 0.146)


def reset_pose(arm):
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix()
    bpy.context.view_layer.update()


def rot_world(arm, bone, axis, deg):
    pb = arm.pose.bones[bone]
    head = pb.head.copy()
    if axis == "TWIST":   # about the leg's own line, hip -> ankle; + turns the knee outward
        foot = arm.pose.bones[bone.replace("Leg", "Foot")].head
        side = 1 if head.x > 0 else -1
        axis = (foot - head).normalized() * -side
    R = Matrix.Translation(head) @ Matrix.Rotation(math.radians(deg), 4, axis) @ Matrix.Translation(-head)
    pb.matrix = R @ pb.matrix
    bpy.context.view_layer.update()


def studio_white(scn):
    world = bpy.data.worlds.get("PhotoStudio") or bpy.data.worlds.new("PhotoStudio")
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    bg = nt.nodes.new("ShaderNodeBackground")       # what the camera sees: paper white
    bg.inputs["Color"].default_value = (0.86, 0.86, 0.86, 1)
    bg.inputs["Strength"].default_value = 1.0
    amb = nt.nodes.new("ShaderNodeBackground")      # soft ambient fill
    amb.inputs["Color"].default_value = (1, 1, 1, 1)
    amb.inputs["Strength"].default_value = WORLD_FILL
    lp = nt.nodes.new("ShaderNodeLightPath")
    mix = nt.nodes.new("ShaderNodeMixShader")
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs["Fac"])
    nt.links.new(amb.outputs["Background"], mix.inputs[1])
    nt.links.new(bg.outputs["Background"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    scn.world = world
    for o in scn.objects:
        if o.type == "LIGHT":
            o.hide_render = True

    def light(name, loc, energy, size):
        ob = bpy.data.objects.get(name)
        if ob is None:
            ob = bpy.data.objects.new(name, bpy.data.lights.new(name, "AREA"))
            scn.collection.objects.link(ob)
        ob.hide_render = False
        ob.data.energy = energy
        ob.data.size = size
        ob.location = loc
        ob.rotation_euler = (Vector((0, 0, 0.6)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        return ob

    light("PS_Key", (-1.5, -3.0, 2.2), 260 * LIGHT, 3.0)
    light("PS_Fill", (2.0, -2.5, 1.0), 120 * LIGHT, 3.0)
    light("PS_Top", (0.0, 0.5, 3.5), 80 * LIGHT, 3.0)
    light("PS_Back", (0.5, 3.0, 1.5), 80 * LIGHT, 3.0)
    scn.view_settings.view_transform = "Standard"
    scn.view_settings.look = "None"
    scn.view_settings.exposure = 0.0


def camera(scn, shot):
    cam = bpy.data.objects.get("CompareCam")
    if cam is None:
        cam = bpy.data.objects.new("CompareCam", bpy.data.cameras.new("CompareCam"))
        scn.collection.objects.link(cam)
    cam.data.lens = shot["lens"]
    cam.data.sensor_fit = "VERTICAL"
    cam.data.sensor_height = 24
    az, el = math.radians(shot["cam_azimuth"]), math.radians(shot["cam_elev"])
    tgt = Vector(shot["target"])
    # azimuth 0 = in front (-Y), positive turns towards +X
    d = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
    # distance so that frame_h metres fill the frame height
    dist = shot["frame_h"] / 2 / math.tan(math.atan(12 / shot["lens"]))
    cam.location = tgt + d * dist
    cam.rotation_euler = (tgt - cam.location).to_track_quat("-Z", "Y").to_euler()
    scn.camera = cam


def export_pose(key):
    """Save the posed (skinned) LOD0 vertices for photo projection: build/pose_<key>.npz."""
    ob = bpy.data.objects[f"{NAME}_LOD0"]
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    n = len(me.vertices)
    co = np.empty(n * 3, np.float32)
    nor = np.empty(n * 3, np.float32)
    me.vertices.foreach_get("co", co)
    me.vertices.foreach_get("normal", nor)
    M = np.array(ob.matrix_world, np.float32)
    co = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
    nor = nor.reshape(-1, 3) @ M[:3, :3].T
    ev.to_mesh_clear()
    path = os.path.join(ART, "build", f"pose_{key}.npz")
    np.savez_compressed(path, co=co, vnor=nor)
    print("posed geometry ->", path, n, "verts")


def render_shot(key):
    scn = bpy.context.scene
    shot = SHOTS[key]
    arm = bpy.data.objects["Armature"]
    reset_pose(arm)
    for bone, axis, deg in shot["pose"]:
        rot_world(arm, bone, axis, deg)
    export_pose(key)
    if globals().get("POSE_ONLY"):
        reset_pose(arm)
        return
    show = {f"{NAME}_LOD0"} | ({"Body_LOD0"} if shot["body"] else set())
    for o in scn.objects:
        if o.type == "MESH":
            o.hide_render = o.name not in show
    studio_white(scn)
    camera(scn, shot)
    scn.render.engine = "CYCLES"
    scn.cycles.samples = 64
    scn.render.resolution_x = 1000
    scn.render.resolution_y = 1000
    scn.render.film_transparent = False
    path = os.path.join(OUT, f"_render_{key}.png")
    scn.render.filepath = path
    bpy.ops.render.render(write_still=True)
    reset_pose(arm)
    # side-by-side (detail shots without a reference photo stop here)
    if not os.path.exists(os.path.join(REF, f"{key}.jpg")):
        print("wrote", path)
        return
    ref = bpy.data.images.load(os.path.join(REF, f"{key}.jpg"), check_existing=False)
    ren = bpy.data.images.load(path, check_existing=False)
    w, h = ref.size
    a = np.array(ref.pixels[:], np.float32).reshape(h, w, 4)
    b = np.array(ren.pixels[:], np.float32).reshape(ren.size[1], ren.size[0], 4)
    sheet = np.ones((h, w * 2, 4), np.float32)
    sheet[:, :w] = a
    sheet[:b.shape[0], w:w + b.shape[1]] = b[:h, :w]
    out = bpy.data.images.new(f"compare_{key}", w * 2, h, alpha=True)
    out.pixels[:] = sheet.ravel()
    out.filepath_raw = os.path.join(OUT, f"compare_{key}.png")
    out.file_format = "PNG"
    out.save()
    for im in (ref, ren, out):
        bpy.data.images.remove(im)
    print("wrote", os.path.join(OUT, f"compare_{key}.png"))


for k in SHOTS_TO_RUN:
    render_shot(k)
