"""
Blender batch script: process one weapon model
Usage: blender --background --python batch_blender.py -- MODEL_ID
  e.g. blender --background --python batch_blender.py -- 001
"""
import bpy
import mathutils
import sys
import os

argv = sys.argv
mid = argv[argv.index("--") + 1]  # e.g. "001"

PREFIX = f"we001_{mid}"
BASE_DIR = r"\\172.16.8.156\art-data-intern\FF7EC\model\weapon\001\model"
MODEL_DIR = os.path.join(BASE_DIR, mid)
TEX_DIR = os.path.join(MODEL_DIR, "materials")
OBJ_PATH = os.path.join(MODEL_DIR, "body_geo.obj")
OUTPUT_DIR = r"C:\Users\Administrator\Documents\outputTest"

TEX_AAAX = os.path.join(TEX_DIR, f"tex_{PREFIX}_AAAX.png")
TEX_MROX = os.path.join(TEX_DIR, f"tex_{PREFIX}_MROX.png")
TEX_NNNX = os.path.join(TEX_DIR, f"tex_{PREFIX}_NNNX.png")
TEX_NNNX_FIXED = os.path.join(TEX_DIR, f"tex_{PREFIX}_NNNX_fixed.png")
TEX_ORM = os.path.join(TEX_DIR, f"tex_{PREFIX}_ORM.png")
TEX_BASECOLOR = os.path.join(TEX_DIR, f"tex_{PREFIX}_BaseColor.png")


# ============================================================
# Render setup helper
# ============================================================
def setup_render(scene_name="render"):
    """Set up camera, lights, and render settings. Camera at 45 degree angle to the right."""
    obj = None
    for o in bpy.data.objects:
        if o.type == 'MESH':
            obj = o
            break

    bbox_corners = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
    bbox_center = sum(bbox_corners, mathutils.Vector((0, 0, 0))) / 8
    bbox_size = max((max(c[i] for c in bbox_corners) - min(c[i] for c in bbox_corners)) for i in range(3))

    distance = bbox_size * 3.0

    # Camera: 45 degree to the right
    import math
    angle = math.radians(45)
    cam_offset = mathutils.Vector((
        distance * math.sin(angle),
        -distance * math.cos(angle),
        distance * 0.4
    ))
    cam_data = bpy.data.cameras.new("RenderCam")
    cam_obj = bpy.data.objects.new("RenderCam", cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj
    cam_obj.location = bbox_center + cam_offset
    direction = bbox_center - cam_obj.location
    cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    cam_data.lens = 85
    cam_data.clip_start = 0.001
    cam_data.clip_end = 100

    # Lights
    for name, energy, size_mult, offset in [
        ("Key", 300, 2, mathutils.Vector((distance * 0.6, -distance * 0.4, distance * 0.8))),
        ("Fill", 100, 5, mathutils.Vector((distance * 0.4, distance * 0.5, distance * 0.2))),
        ("Rim", 200, 1.5, mathutils.Vector((-distance * 0.5, 0, distance * 0.6))),
        ("Top", 150, 2, mathutils.Vector((distance * 0.3, 0, distance * 1.2))),
    ]:
        light_data = bpy.data.lights.new(name, 'AREA')
        light_obj = bpy.data.objects.new(name, light_data)
        bpy.context.scene.collection.objects.link(light_obj)
        light_data.energy = energy
        light_data.size = bbox_size * size_mult
        light_obj.location = bbox_center + offset
        d = bbox_center - light_obj.location
        light_obj.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()

    # World
    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = None
    for node in world.node_tree.nodes:
        if node.type == 'BACKGROUND':
            bg = node
            break
    if bg is None:
        bg = world.node_tree.nodes.new('ShaderNodeBackground')
        out = None
        for node in world.node_tree.nodes:
            if node.type == 'OUTPUT_WORLD':
                out = node
                break
        if out is None:
            out = world.node_tree.nodes.new('ShaderNodeOutputWorld')
        world.node_tree.links.new(bg.outputs[0], out.inputs[0])
    bg.inputs['Color'].default_value = (0.8, 0.8, 0.8, 1.0)
    bg.inputs['Strength'].default_value = 0.5

    # Render settings
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'GPU'
    scene.cycles.samples = 256
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 2560
    scene.render.resolution_y = 1440
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_depth = '16'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.film_transparent = True

    prefs = bpy.context.preferences.addons.get('cycles')
    if prefs:
        prefs.preferences.compute_device_type = 'CUDA'
        prefs.preferences.get_devices()
        for device in prefs.preferences.devices:
            device.use = True


def do_render(filepath):
    bpy.context.scene.render.filepath = filepath
    bpy.ops.render.render(write_still=True)
    print(f"Rendered: {filepath}")


def clear_render_objects():
    """Remove camera, lights, world for clean save."""
    for obj in list(bpy.data.objects):
        if obj.type in ('CAMERA', 'LIGHT'):
            bpy.data.objects.remove(obj, do_unlink=True)
    for w in list(bpy.data.worlds):
        if w.name == "World":
            bpy.data.worlds.remove(w)


# ============================================================
# Import OBJ helper
# ============================================================
def import_obj():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wm.obj_import(filepath=OBJ_PATH)
    obj = None
    for o in bpy.data.objects:
        if o.type == 'MESH':
            obj = o
            break
    return obj


def create_material():
    mat = bpy.data.materials.new(name=f"mat_{PREFIX}")
    mat.use_nodes = True
    tree = mat.node_tree
    nodes = tree.nodes
    links = tree.links
    nodes.clear()
    node_output = nodes.new('ShaderNodeOutputMaterial')
    node_output.location = (200, 100)
    node_bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    node_bsdf.location = (-200, 100)
    node_bsdf.inputs['Metallic'].default_value = 1.0
    node_bsdf.inputs['Specular IOR Level'].default_value = 1.0
    links.new(node_bsdf.outputs['BSDF'], node_output.inputs['Surface'])
    return mat, nodes, links, node_bsdf


def assign_material(obj, mat):
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)


# ============================================================
# Step 1: Textured blend (original wiring) + render
# ============================================================
print(f"\n{'='*50}")
print(f"[{mid}] Step 1: textured.blend")
print(f"{'='*50}")

obj = import_obj()
mat, nodes, links, bsdf = create_material()

# AAAX
n_aaax = nodes.new('ShaderNodeTexImage')
n_aaax.location = (-1548, 205)
n_aaax.image = bpy.data.images.load(TEX_AAAX)
n_aaax.image.colorspace_settings.name = 'sRGB'

# MROX
n_mrox = nodes.new('ShaderNodeTexImage')
n_mrox.location = (-1855, -334)
n_mrox.image = bpy.data.images.load(TEX_MROX)
n_mrox.image.colorspace_settings.name = 'sRGB'

# NNNX (original pink)
n_nnnx = nodes.new('ShaderNodeTexImage')
n_nnnx.location = (-1750, -863)
n_nnnx.image = bpy.data.images.load(TEX_NNNX)
n_nnnx.image.colorspace_settings.name = 'Non-Color'

# Separate Color (MROX)
n_sep = nodes.new('ShaderNodeSeparateColor')
n_sep.location = (-1207, -146)

# Mix (Multiply)
n_mix = nodes.new('ShaderNodeMix')
n_mix.location = (-904, 108)
n_mix.data_type = 'RGBA'
n_mix.blend_type = 'MULTIPLY'
n_mix.inputs[0].default_value = 1.0

# Separate Color (NNNX)
n_sep2 = nodes.new('ShaderNodeSeparateColor')
n_sep2.location = (-1332, -842)

# Combine XYZ
n_comb = nodes.new('ShaderNodeCombineXYZ')
n_comb.location = (-917, -851)

# Normal Map
n_nmap = nodes.new('ShaderNodeNormalMap')
n_nmap.label = "Normal/Map"
n_nmap.location = (-600, -600)

# MROX links
links.new(n_mrox.outputs['Color'], n_sep.inputs['Color'])
links.new(n_sep.outputs['Red'], bsdf.inputs['Metallic'])
links.new(n_sep.outputs['Green'], bsdf.inputs['Roughness'])
links.new(n_sep.outputs['Blue'], n_mix.inputs[7])

# Base Color
links.new(n_aaax.outputs['Color'], n_mix.inputs[6])
links.new(n_mix.outputs[2], bsdf.inputs['Base Color'])

# Normal swizzle
links.new(n_nnnx.outputs['Color'], n_sep2.inputs['Color'])
links.new(n_sep2.outputs['Red'], n_comb.inputs['Z'])
links.new(n_sep2.outputs['Green'], n_comb.inputs['X'])
links.new(n_sep2.outputs['Blue'], n_comb.inputs['Y'])
links.new(n_comb.outputs['Vector'], n_nmap.inputs['Color'])
links.new(n_nmap.outputs['Normal'], bsdf.inputs['Normal'])

assign_material(obj, mat)

# Render textured
setup_render()
do_render(os.path.join(OUTPUT_DIR, f"{PREFIX}_textured.png"))
clear_render_objects()

# Save textured blend
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUTPUT_DIR, f"{PREFIX}_textured.blend"))
print(f"[{mid}] Saved: {PREFIX}_textured.blend")


# ============================================================
# Step 2: Processed blend (baked normal, simplified) + no extra render needed
# ============================================================
print(f"\n{'='*50}")
print(f"[{mid}] Step 2: processed.blend")
print(f"{'='*50}")

obj = import_obj()
mat, nodes, links, bsdf = create_material()

# AAAX
n_aaax = nodes.new('ShaderNodeTexImage')
n_aaax.location = (-1548, 205)
n_aaax.image = bpy.data.images.load(TEX_AAAX)
n_aaax.image.colorspace_settings.name = 'sRGB'

# MROX
n_mrox = nodes.new('ShaderNodeTexImage')
n_mrox.location = (-1855, -334)
n_mrox.image = bpy.data.images.load(TEX_MROX)
n_mrox.image.colorspace_settings.name = 'sRGB'

# NNNX fixed (blue/purple)
n_nnnx = nodes.new('ShaderNodeTexImage')
n_nnnx.location = (-1750, -863)
n_nnnx.image = bpy.data.images.load(TEX_NNNX_FIXED)
n_nnnx.image.colorspace_settings.name = 'Non-Color'

# Separate Color (MROX)
n_sep = nodes.new('ShaderNodeSeparateColor')
n_sep.location = (-1207, -146)

# Mix (Multiply)
n_mix = nodes.new('ShaderNodeMix')
n_mix.location = (-904, 108)
n_mix.data_type = 'RGBA'
n_mix.blend_type = 'MULTIPLY'
n_mix.inputs[0].default_value = 1.0

# Normal Map (direct)
n_nmap = nodes.new('ShaderNodeNormalMap')
n_nmap.label = "Normal/Map"
n_nmap.location = (-600, -600)

# MROX links
links.new(n_mrox.outputs['Color'], n_sep.inputs['Color'])
links.new(n_sep.outputs['Red'], bsdf.inputs['Metallic'])
links.new(n_sep.outputs['Green'], bsdf.inputs['Roughness'])
links.new(n_sep.outputs['Blue'], n_mix.inputs[7])

# Base Color
links.new(n_aaax.outputs['Color'], n_mix.inputs[6])
links.new(n_mix.outputs[2], bsdf.inputs['Base Color'])

# Normal direct
links.new(n_nnnx.outputs['Color'], n_nmap.inputs['Color'])
links.new(n_nmap.outputs['Normal'], bsdf.inputs['Normal'])

assign_material(obj, mat)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUTPUT_DIR, f"{PREFIX}_processed.blend"))
print(f"[{mid}] Saved: {PREFIX}_processed.blend")


# ============================================================
# Step 3: GLB export
# ============================================================
print(f"\n{'='*50}")
print(f"[{mid}] Step 3: GLB export")
print(f"{'='*50}")

obj = import_obj()
mat, nodes, links, bsdf = create_material()

# BaseColor (AAAX * AO already baked into pixels)
n_bc = nodes.new('ShaderNodeTexImage')
n_bc.label = "Base Color"
n_bc.location = (-600, 300)
n_bc.image = bpy.data.images.load(TEX_BASECOLOR)
n_bc.image.colorspace_settings.name = 'sRGB'

# ORM
n_orm = nodes.new('ShaderNodeTexImage')
n_orm.label = "ORM"
n_orm.location = (-600, -100)
n_orm.image = bpy.data.images.load(TEX_ORM)
n_orm.image.colorspace_settings.name = 'Non-Color'

# Separate Color (ORM)
n_sep = nodes.new('ShaderNodeSeparateColor')
n_sep.location = (-300, -100)

# Normal fixed
n_nnnx = nodes.new('ShaderNodeTexImage')
n_nnnx.label = "Normal"
n_nnnx.location = (-600, -500)
n_nnnx.image = bpy.data.images.load(TEX_NNNX_FIXED)
n_nnnx.image.colorspace_settings.name = 'Non-Color'

n_nmap = nodes.new('ShaderNodeNormalMap')
n_nmap.location = (-300, -500)

# Links — all direct, glTF exporter will recognize every connection
links.new(n_bc.outputs['Color'], bsdf.inputs['Base Color'])
links.new(n_orm.outputs['Color'], n_sep.inputs['Color'])
links.new(n_sep.outputs['Blue'], bsdf.inputs['Metallic'])
links.new(n_sep.outputs['Green'], bsdf.inputs['Roughness'])
links.new(n_nnnx.outputs['Color'], n_nmap.inputs['Color'])
links.new(n_nmap.outputs['Normal'], bsdf.inputs['Normal'])

assign_material(obj, mat)

glb_path = os.path.join(OUTPUT_DIR, f"{PREFIX}.glb")
bpy.ops.export_scene.gltf(
    filepath=glb_path,
    export_format='GLB',
    export_texcoords=True,
    export_normals=True,
    export_materials='EXPORT',
    export_image_format='AUTO',
)
print(f"[{mid}] Exported: {PREFIX}.glb")


# ============================================================
# Step 4: Re-import GLB and render
# ============================================================
print(f"\n{'='*50}")
print(f"[{mid}] Step 4: GLB re-import render")
print(f"{'='*50}")

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb_path)

setup_render()
do_render(os.path.join(OUTPUT_DIR, f"{PREFIX}_glb.png"))

print(f"\n[{mid}] ALL DONE!")
