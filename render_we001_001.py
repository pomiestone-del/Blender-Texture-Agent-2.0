import bpy
import mathutils
import math

bpy.ops.wm.open_mainfile(filepath=r"C:\Users\Administrator\Documents\sample\we001_001_textured.blend")

# Get the mesh object and its bounding box
obj = None
for o in bpy.data.objects:
    if o.type == 'MESH':
        obj = o
        break

# Calculate bounding box center and size
bbox_corners = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
bbox_center = sum(bbox_corners, mathutils.Vector((0, 0, 0))) / 8
bbox_size = max((max(c[i] for c in bbox_corners) - min(c[i] for c in bbox_corners)) for i in range(3))

print(f"Object: {obj.name}, center: {bbox_center}, size: {bbox_size}")

# --- Camera setup ---
cam_data = bpy.data.cameras.new("RenderCam")
cam_obj = bpy.data.objects.new("RenderCam", cam_data)
bpy.context.scene.collection.objects.link(cam_obj)
bpy.context.scene.camera = cam_obj

# Position camera for front view (looking from +X towards model flat face)
distance = bbox_size * 3.5
cam_offset = mathutils.Vector((distance, 0, 0))
cam_obj.location = bbox_center + cam_offset

# Point camera at center
direction = bbox_center - cam_obj.location
rot_quat = direction.to_track_quat('-Z', 'Y')
cam_obj.rotation_euler = rot_quat.to_euler()

# Camera lens
cam_data.lens = 85
cam_data.clip_start = 0.001
cam_data.clip_end = 100

# --- Lighting ---
# Key light - strong, from front-upper-right to rake across the surface
key_data = bpy.data.lights.new("KeyLight", 'AREA')
key_obj = bpy.data.objects.new("KeyLight", key_data)
bpy.context.scene.collection.objects.link(key_obj)
key_data.energy = 300
key_data.size = bbox_size * 2
key_obj.location = bbox_center + mathutils.Vector((distance * 0.6, -distance * 0.4, distance * 0.8))
direction = bbox_center - key_obj.location
key_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

# Fill light - softer, opposite side
fill_data = bpy.data.lights.new("FillLight", 'AREA')
fill_obj = bpy.data.objects.new("FillLight", fill_data)
bpy.context.scene.collection.objects.link(fill_obj)
fill_data.energy = 100
fill_data.size = bbox_size * 5
fill_obj.location = bbox_center + mathutils.Vector((distance * 0.4, distance * 0.5, distance * 0.2))
direction = bbox_center - fill_obj.location
fill_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

# Rim/back light - strong edge highlight
rim_data = bpy.data.lights.new("RimLight", 'AREA')
rim_obj = bpy.data.objects.new("RimLight", rim_data)
bpy.context.scene.collection.objects.link(rim_obj)
rim_data.energy = 200
rim_data.size = bbox_size * 1.5
rim_obj.location = bbox_center + mathutils.Vector((-distance * 0.5, 0, distance * 0.6))
direction = bbox_center - rim_obj.location
rim_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

# Top light - raking light to bring out normal map details
top_data = bpy.data.lights.new("TopLight", 'AREA')
top_obj = bpy.data.objects.new("TopLight", top_data)
bpy.context.scene.collection.objects.link(top_obj)
top_data.energy = 150
top_data.size = bbox_size * 2
top_obj.location = bbox_center + mathutils.Vector((distance * 0.3, 0, distance * 1.2))
direction = bbox_center - top_obj.location
top_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

# --- World background ---
world = bpy.data.worlds.new("RenderWorld")
bpy.context.scene.world = world
world.use_nodes = True
# Find background node by type
bg_node = None
for node in world.node_tree.nodes:
    if node.type == 'BACKGROUND':
        bg_node = node
        break
if bg_node is None:
    bg_node = world.node_tree.nodes.new('ShaderNodeBackground')
    output_node = None
    for node in world.node_tree.nodes:
        if node.type == 'OUTPUT_WORLD':
            output_node = node
            break
    if output_node is None:
        output_node = world.node_tree.nodes.new('ShaderNodeOutputWorld')
    world.node_tree.links.new(bg_node.outputs[0], output_node.inputs[0])
bg_node.inputs['Color'].default_value = (0.15, 0.15, 0.18, 1.0)
bg_node.inputs['Strength'].default_value = 1.0

# --- Render settings ---
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
scene.render.filepath = r"C:\Users\Administrator\Documents\sample\we001_001_render_front.png"

# Enable GPU compute
prefs = bpy.context.preferences.addons.get('cycles')
if prefs:
    prefs.preferences.compute_device_type = 'CUDA'
    prefs.preferences.get_devices()
    for device in prefs.preferences.devices:
        device.use = True

# Render
bpy.ops.render.render(write_still=True)
print("Render complete!")
