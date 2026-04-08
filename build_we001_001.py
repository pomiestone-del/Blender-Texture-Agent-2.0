import bpy
import os

# Clear the scene
bpy.ops.wm.read_factory_settings(use_empty=True)

# Paths
model_dir = r"\\172.16.8.156\art-data-intern\FF7EC\model\weapon\001\model\001"
obj_path = os.path.join(model_dir, "body_geo.obj")
tex_dir = os.path.join(model_dir, "materials")

tex_aaax = os.path.join(tex_dir, "tex_we001_001_AAAX.png")
tex_mrox = os.path.join(tex_dir, "tex_we001_001_MROX.png")
tex_nnnx = os.path.join(tex_dir, "tex_we001_001_NNNX.png")

# Import OBJ
bpy.ops.wm.obj_import(filepath=obj_path)

# Get the imported object
obj = bpy.context.selected_objects[0] if bpy.context.selected_objects else None
if obj is None:
    for o in bpy.data.objects:
        if o.type == 'MESH':
            obj = o
            break

print(f"Imported object: {obj.name}")

# Create material
mat_name = "mat_we001_001"
mat = bpy.data.materials.new(name=mat_name)
mat.use_nodes = True
tree = mat.node_tree
nodes = tree.nodes
links = tree.links

# Clear default nodes
nodes.clear()

# --- Create nodes ---

# Material Output
node_output = nodes.new('ShaderNodeOutputMaterial')
node_output.location = (200, 100)

# Principled BSDF
node_bsdf = nodes.new('ShaderNodeBsdfPrincipled')
node_bsdf.location = (-200, 100)
# Set defaults matching sample
node_bsdf.inputs['Metallic'].default_value = 1.0
node_bsdf.inputs['Specular IOR Level'].default_value = 1.0

# AAAX texture (Albedo)
node_tex_aaax = nodes.new('ShaderNodeTexImage')
node_tex_aaax.name = "Image Texture.001"
node_tex_aaax.location = (-1548, 205)
img_aaax = bpy.data.images.load(tex_aaax)
img_aaax.colorspace_settings.name = 'sRGB'
node_tex_aaax.image = img_aaax

# MROX texture (Metallic/Roughness/AO)
node_tex_mrox = nodes.new('ShaderNodeTexImage')
node_tex_mrox.name = "Image Texture.002"
node_tex_mrox.location = (-1855, -334)
img_mrox = bpy.data.images.load(tex_mrox)
img_mrox.colorspace_settings.name = 'sRGB'
node_tex_mrox.image = img_mrox

# NNNX texture (Normal)
node_tex_nnnx = nodes.new('ShaderNodeTexImage')
node_tex_nnnx.name = "Image Texture"
node_tex_nnnx.location = (-1750, -863)
img_nnnx = bpy.data.images.load(tex_nnnx)
img_nnnx.colorspace_settings.name = 'Non-Color'
node_tex_nnnx.image = img_nnnx

# Separate Color for MROX
node_sep_mrox = nodes.new('ShaderNodeSeparateColor')
node_sep_mrox.name = "Separate Color"
node_sep_mrox.location = (-1207, -146)

# Mix (Multiply) for Base Color = AAAX * AO
node_mix = nodes.new('ShaderNodeMix')
node_mix.name = "Mix"
node_mix.location = (-904, 108)
node_mix.data_type = 'RGBA'
node_mix.blend_type = 'MULTIPLY'
# Set factor to 1.0 for full multiply
node_mix.inputs[0].default_value = 1.0

# Normal Map (direct connection, swizzle already baked into texture)
node_normal = nodes.new('ShaderNodeNormalMap')
node_normal.name = "Normal Map"
node_normal.label = "Normal/Map"
node_normal.location = (-600, -600)

# --- Create links ---

# BSDF -> Output
links.new(node_bsdf.outputs['BSDF'], node_output.inputs['Surface'])

# MROX -> Separate Color
links.new(node_tex_mrox.outputs['Color'], node_sep_mrox.inputs['Color'])

# Separate Color MROX channels
links.new(node_sep_mrox.outputs['Red'], node_bsdf.inputs['Metallic'])
links.new(node_sep_mrox.outputs['Green'], node_bsdf.inputs['Roughness'])

# Mix node: AAAX * AO(Blue channel of MROX)
# For ShaderNodeMix with RGBA: input 6 = A (Color), input 7 = B (Color)
links.new(node_tex_aaax.outputs['Color'], node_mix.inputs[6])  # A color
links.new(node_sep_mrox.outputs['Blue'], node_mix.inputs[7])   # B color (AO)
links.new(node_mix.outputs[2], node_bsdf.inputs['Base Color'])  # Result (color output)

# NNNX -> Normal Map -> Principled BSDF (swizzle already baked into texture)
links.new(node_tex_nnnx.outputs['Color'], node_normal.inputs['Color'])
links.new(node_normal.outputs['Normal'], node_bsdf.inputs['Normal'])

# Assign material to object
if obj.data.materials:
    obj.data.materials[0] = mat
else:
    obj.data.materials.append(mat)

# Save
output_path = r"C:\Users\Administrator\Documents\sample\we001_001_textured.blend"
bpy.ops.wm.save_as_mainfile(filepath=output_path)
print(f"Saved to: {output_path}")
