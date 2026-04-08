import bpy
import os

# ORM texture already converted by convert_mrox_to_orm.py

bpy.ops.wm.read_factory_settings(use_empty=True)

model_dir = r"\\172.16.8.156\art-data-intern\FF7EC\model\weapon\001\model\001"
tex_dir = os.path.join(model_dir, "materials")
obj_path = os.path.join(model_dir, "body_geo.obj")
tex_aaax = os.path.join(tex_dir, "tex_we001_001_AAAX.png")
tex_nnnx = os.path.join(tex_dir, "tex_we001_001_NNNX.png")
orm_path = os.path.join(tex_dir, "tex_we001_001_ORM.png")

# Import OBJ
bpy.ops.wm.obj_import(filepath=obj_path)
obj = None
for o in bpy.data.objects:
    if o.type == 'MESH':
        obj = o
        break
print(f"Imported: {obj.name}")

# Create material
mat = bpy.data.materials.new(name="mat_we001_001")
mat.use_nodes = True
tree = mat.node_tree
nodes = tree.nodes
links = tree.links
nodes.clear()

# Material Output
node_output = nodes.new('ShaderNodeOutputMaterial')
node_output.location = (400, 0)

# Principled BSDF
node_bsdf = nodes.new('ShaderNodeBsdfPrincipled')
node_bsdf.location = (0, 0)

# AAAX -> Base Color (direct, no AO multiply)
node_tex_base = nodes.new('ShaderNodeTexImage')
node_tex_base.label = "Base Color"
node_tex_base.location = (-600, 300)
img_base = bpy.data.images.load(tex_aaax)
img_base.colorspace_settings.name = 'sRGB'
node_tex_base.image = img_base

# ORM texture (R=Occlusion, G=Roughness, B=Metallic) - glTF standard
node_tex_orm = nodes.new('ShaderNodeTexImage')
node_tex_orm.label = "ORM"
node_tex_orm.location = (-600, -100)
img_orm = bpy.data.images.load(orm_path)
img_orm.colorspace_settings.name = 'Non-Color'
node_tex_orm.image = img_orm

# Separate Color for ORM
node_sep = nodes.new('ShaderNodeSeparateColor')
node_sep.location = (-300, -100)

# Normal Map
node_tex_normal = nodes.new('ShaderNodeTexImage')
node_tex_normal.label = "Normal"
node_tex_normal.location = (-600, -500)
img_normal = bpy.data.images.load(tex_nnnx)
img_normal.colorspace_settings.name = 'Non-Color'
node_tex_normal.image = img_normal

node_normal_map = nodes.new('ShaderNodeNormalMap')
node_normal_map.location = (-300, -500)

# --- Links ---
links.new(node_bsdf.outputs['BSDF'], node_output.inputs['Surface'])

# Base Color direct
links.new(node_tex_base.outputs['Color'], node_bsdf.inputs['Base Color'])

# ORM channels
links.new(node_tex_orm.outputs['Color'], node_sep.inputs['Color'])
links.new(node_sep.outputs['Blue'], node_bsdf.inputs['Metallic'])      # B = Metallic
links.new(node_sep.outputs['Green'], node_bsdf.inputs['Roughness'])    # G = Roughness
# Note: Occlusion (R) is not a Principled BSDF input, glTF exporter picks it up automatically

# Normal
links.new(node_tex_normal.outputs['Color'], node_normal_map.inputs['Color'])
links.new(node_normal_map.outputs['Normal'], node_bsdf.inputs['Normal'])

# Assign material
if obj.data.materials:
    obj.data.materials[0] = mat
else:
    obj.data.materials.append(mat)

# --- Step 3: Export GLB ---
output_glb = r"C:\Users\Administrator\Documents\sample\we001_001.glb"
bpy.ops.export_scene.gltf(
    filepath=output_glb,
    export_format='GLB',
    export_texcoords=True,
    export_normals=True,
    export_materials='EXPORT',
    export_image_format='AUTO',
)
print(f"GLB exported: {output_glb}")

# Also save blend for reference
output_blend = r"C:\Users\Administrator\Documents\sample\we001_001_glb.blend"
bpy.ops.wm.save_as_mainfile(filepath=output_blend)
print(f"Blend saved: {output_blend}")
