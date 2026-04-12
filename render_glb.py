"""
Render GLB using same settings as blender_render_preview.py (Blender 5.1 compatible)
Usage: blender --background --python render_glb.py -- <glb_path> <png_path> [resolution]
"""
import bpy
import sys
import os
import shutil
from mathutils import Vector

argv = sys.argv
index = argv.index("--") + 1
argv = argv[index:]

glb_path = argv[0]
png_path = argv[1]
resolution = int(argv[2]) if len(argv) > 2 else 512

# Use local temp for render, then copy to final destination
local_tmp = os.path.join(r"C:\Users\Administrator\Documents\outputTest", os.path.basename(png_path))

# Clear scene
for obj in bpy.data.objects:
    bpy.data.objects.remove(obj)
for mesh in bpy.data.meshes:
    bpy.data.meshes.remove(mesh)
for world in bpy.data.worlds:
    bpy.data.worlds.remove(world)

# Import GLB
bpy.ops.import_scene.gltf(filepath=glb_path)
bpy.ops.object.select_all(action="SELECT")

# Remove animations
for obj in bpy.context.selected_objects:
    if obj.animation_data:
        obj.animation_data.action = None
        obj.animation_data_clear()

# Make single user
for obj in bpy.context.selected_objects:
    if obj.type == "MESH" and obj.data.users > 1:
        obj.data = obj.data.copy()

bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

# Scale to unit sphere (after transform_apply so world coords = local coords)
min_c = [999999, 999999, 999999]
max_c = [-999999, -999999, -999999]
for obj in bpy.context.selected_objects:
    if obj.type == "MESH":
        for v in obj.bound_box:
            wv = obj.matrix_world @ Vector(v)
            for i in range(3):
                min_c[i] = min(min_c[i], wv[i])
                max_c[i] = max(max_c[i], wv[i])

center = [(min_c[i] + max_c[i]) / 2 for i in range(3)]
size = max(max_c[i] - min_c[i] for i in range(3))
scale = 2 / size

for obj in bpy.context.selected_objects:
    if obj.parent is None:
        obj.location = (-center[0] * scale, -center[1] * scale, -center[2] * scale)
        obj.scale = (scale, scale, scale)

# Camera (same as blender_render_preview.py)
bpy.data.scenes[0].render.film_transparent = True
bpy.ops.object.camera_add(
    enter_editmode=False, align="VIEW",
    location=(0, 0, 0), rotation=(1.047, 0, -0.707), scale=(1, 1, 1)
)
bpy.context.active_object.name = "Preview_Render_Camera"
bpy.context.scene.camera = bpy.context.active_object
bpy.context.scene.camera.data.clip_start = 0.001
bpy.context.scene.camera.data.clip_end = 500

# Render settings
bpy.context.scene.render.resolution_x = resolution
bpy.context.scene.render.resolution_y = resolution
bpy.context.scene.render.resolution_percentage = 100
bpy.context.scene.render.engine = "CYCLES"
bpy.context.scene.cycles.device = "GPU"
bpy.context.scene.cycles.samples = 64
bpy.context.scene.cycles.max_bounces = 2

# Fit camera to selected (objects still selected from above)
for window in bpy.context.window_manager.windows:
    for area in window.screen.areas:
        if area.type == "VIEW_3D":
            for region in area.regions:
                if region.type == "WINDOW":
                    with bpy.context.temp_override(window=window, area=area, region=region):
                        bpy.ops.view3d.camera_to_view_selected()
                    break

# World environment (gray background for reflections, transparent output)
world = bpy.data.worlds.new("RenderWorld")
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs[0].default_value = (0.5, 0.5, 0.5, 1)

# Sun light
bpy.ops.object.light_add(type="SUN", radius=1, align="WORLD", location=(0, 0, 0))
sun = bpy.context.active_object
sun.rotation_mode = "XYZ"
sun.rotation_euler = (0.314 * 5, 0.314, 0)
sun.data.energy = 2
sun.data.angle = 0.314 * 3

# GPU setup
prefs = bpy.context.preferences.addons.get("cycles")
if prefs:
    prefs.preferences.compute_device_type = "CUDA"
    prefs.preferences.get_devices()
    for d in prefs.preferences.devices:
        if d.type == "CUDA":
            d.use = True

# Render to local temp
bpy.context.scene.render.filepath = local_tmp
bpy.context.scene.render.image_settings.file_format = "PNG"
bpy.ops.render.render(write_still=True)

# Copy to final destination
if os.path.isfile(local_tmp):
    shutil.copy2(local_tmp, png_path)
    print(f"RENDER OK: {os.path.basename(png_path)}")
else:
    print("RENDER FAILED: output not found")
