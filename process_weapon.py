"""
Weapon model processing pipeline:
  Step 1: Import OBJ + original material wiring -> textured.blend
  Step 2: Bake normal swizzle into texture, simplify nodes -> processed.blend
  Step 3: Convert to glTF-compatible materials, export -> .glb

Usage: python process_weapon.py (uses system Python for texture processing)
       Then run the 3 Blender scripts generated.
"""
import sys
import os
import numpy as np
from PIL import Image

# ============================================================
# Config
# ============================================================
MODEL_ID = "002"
MODEL_DIR = rf"\\172.16.8.156\art-data-intern\FF7EC\model\weapon\001\model\{MODEL_ID}"
TEX_DIR = os.path.join(MODEL_DIR, "materials")
OUTPUT_DIR = r"C:\Users\Administrator\Documents\sample"

PREFIX = f"we001_{MODEL_ID}"
TEX_AAAX = os.path.join(TEX_DIR, f"tex_{PREFIX}_AAAX.png")
TEX_MROX = os.path.join(TEX_DIR, f"tex_{PREFIX}_MROX.png")
TEX_NNNX = os.path.join(TEX_DIR, f"tex_{PREFIX}_NNNX.png")
TEX_NNNX_FIXED = os.path.join(TEX_DIR, f"tex_{PREFIX}_NNNX_fixed.png")
TEX_ORM = os.path.join(TEX_DIR, f"tex_{PREFIX}_ORM.png")

# ============================================================
# Texture processing
# ============================================================
def srgb_to_linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)

# --- Convert normal map: swizzle R->Z, G->X, B->Y baked into pixels ---
print("[Texture] Converting normal map (pink -> blue/purple)...")
img = np.array(Image.open(TEX_NNNX))
r, g, b = img[:,:,0].copy(), img[:,:,1].copy(), img[:,:,2].copy()
img[:,:,0] = g  # new R = old G
img[:,:,1] = b  # new G = old B
img[:,:,2] = r  # new B = old R
Image.fromarray(img).save(TEX_NNNX_FIXED)
print(f"  Saved: {TEX_NNNX_FIXED}")

# --- Convert MROX to glTF ORM (R<->B swap + sRGB->Linear) ---
print("[Texture] Converting MROX -> ORM (linearized, channel swapped)...")
img = np.array(Image.open(TEX_MROX)).astype(np.float64) / 255.0
r = srgb_to_linear(img[:,:,0])  # Metallic
g = srgb_to_linear(img[:,:,1])  # Roughness
b = srgb_to_linear(img[:,:,2])  # Occlusion
out = np.stack([b, g, r], axis=2)  # glTF ORM: R=Occ, G=Rough, B=Metal
out = np.clip(out * 255.0, 0, 255).astype(np.uint8)
Image.fromarray(out).save(TEX_ORM)
print(f"  Saved: {TEX_ORM}")

# ============================================================
# Generate Blender scripts
# ============================================================
COMMON_IMPORT = f'''
import bpy, os
bpy.ops.wm.read_factory_settings(use_empty=True)

MODEL_DIR = r"{MODEL_DIR}"
TEX_DIR = r"{TEX_DIR}"
OBJ_PATH = os.path.join(MODEL_DIR, "body_geo.obj")

bpy.ops.wm.obj_import(filepath=OBJ_PATH)
obj = None
for o in bpy.data.objects:
    if o.type == "MESH":
        obj = o
        break
print(f"Imported: {{obj.name}}")

mat = bpy.data.materials.new(name="mat_{PREFIX}")
mat.use_nodes = True
tree = mat.node_tree
nodes = tree.nodes
links = tree.links
nodes.clear()

node_output = nodes.new("ShaderNodeOutputMaterial")
node_output.location = (200, 100)
node_bsdf = nodes.new("ShaderNodeBsdfPrincipled")
node_bsdf.location = (-200, 100)
node_bsdf.inputs["Metallic"].default_value = 1.0
node_bsdf.inputs["Specular IOR Level"].default_value = 1.0
links.new(node_bsdf.outputs["BSDF"], node_output.inputs["Surface"])
'''

COMMON_ASSIGN = '''
if obj.data.materials:
    obj.data.materials[0] = mat
else:
    obj.data.materials.append(mat)
'''

# --- Script 1: Original wiring (textured.blend) ---
script1 = COMMON_IMPORT + f'''
# AAAX
n_aaax = nodes.new("ShaderNodeTexImage")
n_aaax.location = (-1548, 205)
n_aaax.image = bpy.data.images.load(os.path.join(TEX_DIR, "tex_{PREFIX}_AAAX.png"))
n_aaax.image.colorspace_settings.name = "sRGB"

# MROX
n_mrox = nodes.new("ShaderNodeTexImage")
n_mrox.location = (-1855, -334)
n_mrox.image = bpy.data.images.load(os.path.join(TEX_DIR, "tex_{PREFIX}_MROX.png"))
n_mrox.image.colorspace_settings.name = "sRGB"

# NNNX (original pink)
n_nnnx = nodes.new("ShaderNodeTexImage")
n_nnnx.location = (-1750, -863)
n_nnnx.image = bpy.data.images.load(os.path.join(TEX_DIR, "tex_{PREFIX}_NNNX.png"))
n_nnnx.image.colorspace_settings.name = "Non-Color"

# Separate Color (MROX)
n_sep = nodes.new("ShaderNodeSeparateColor")
n_sep.location = (-1207, -146)

# Mix (Multiply) AAAX * AO
n_mix = nodes.new("ShaderNodeMix")
n_mix.location = (-904, 108)
n_mix.data_type = "RGBA"
n_mix.blend_type = "MULTIPLY"
n_mix.inputs[0].default_value = 1.0

# Separate Color (NNNX)
n_sep2 = nodes.new("ShaderNodeSeparateColor")
n_sep2.location = (-1332, -842)

# Combine XYZ (normal swizzle)
n_comb = nodes.new("ShaderNodeCombineXYZ")
n_comb.location = (-917, -851)

# Normal Map
n_nmap = nodes.new("ShaderNodeNormalMap")
n_nmap.label = "Normal/Map"
n_nmap.location = (-600, -600)

# Links - MROX
links.new(n_mrox.outputs["Color"], n_sep.inputs["Color"])
links.new(n_sep.outputs["Red"], node_bsdf.inputs["Metallic"])
links.new(n_sep.outputs["Green"], node_bsdf.inputs["Roughness"])
links.new(n_sep.outputs["Blue"], n_mix.inputs[7])

# Links - Base Color
links.new(n_aaax.outputs["Color"], n_mix.inputs[6])
links.new(n_mix.outputs[2], node_bsdf.inputs["Base Color"])

# Links - Normal (swizzle: R->Z, G->X, B->Y)
links.new(n_nnnx.outputs["Color"], n_sep2.inputs["Color"])
links.new(n_sep2.outputs["Red"], n_comb.inputs["Z"])
links.new(n_sep2.outputs["Green"], n_comb.inputs["X"])
links.new(n_sep2.outputs["Blue"], n_comb.inputs["Y"])
links.new(n_comb.outputs["Vector"], n_nmap.inputs["Color"])
links.new(n_nmap.outputs["Normal"], node_bsdf.inputs["Normal"])
''' + COMMON_ASSIGN + f'''
bpy.ops.wm.save_as_mainfile(filepath=r"{OUTPUT_DIR}\\{PREFIX}_textured.blend")
print("Step 1 done: {PREFIX}_textured.blend")
'''

# --- Script 2: Processed (baked normal, simplified nodes) ---
script2 = COMMON_IMPORT + f'''
# AAAX
n_aaax = nodes.new("ShaderNodeTexImage")
n_aaax.location = (-1548, 205)
n_aaax.image = bpy.data.images.load(os.path.join(TEX_DIR, "tex_{PREFIX}_AAAX.png"))
n_aaax.image.colorspace_settings.name = "sRGB"

# MROX
n_mrox = nodes.new("ShaderNodeTexImage")
n_mrox.location = (-1855, -334)
n_mrox.image = bpy.data.images.load(os.path.join(TEX_DIR, "tex_{PREFIX}_MROX.png"))
n_mrox.image.colorspace_settings.name = "sRGB"

# NNNX (fixed blue/purple, swizzle baked)
n_nnnx = nodes.new("ShaderNodeTexImage")
n_nnnx.location = (-1750, -863)
n_nnnx.image = bpy.data.images.load(os.path.join(TEX_DIR, "tex_{PREFIX}_NNNX_fixed.png"))
n_nnnx.image.colorspace_settings.name = "Non-Color"

# Separate Color (MROX)
n_sep = nodes.new("ShaderNodeSeparateColor")
n_sep.location = (-1207, -146)

# Mix (Multiply) AAAX * AO
n_mix = nodes.new("ShaderNodeMix")
n_mix.location = (-904, 108)
n_mix.data_type = "RGBA"
n_mix.blend_type = "MULTIPLY"
n_mix.inputs[0].default_value = 1.0

# Normal Map (direct, no swizzle nodes)
n_nmap = nodes.new("ShaderNodeNormalMap")
n_nmap.label = "Normal/Map"
n_nmap.location = (-600, -600)

# Links - MROX
links.new(n_mrox.outputs["Color"], n_sep.inputs["Color"])
links.new(n_sep.outputs["Red"], node_bsdf.inputs["Metallic"])
links.new(n_sep.outputs["Green"], node_bsdf.inputs["Roughness"])
links.new(n_sep.outputs["Blue"], n_mix.inputs[7])

# Links - Base Color
links.new(n_aaax.outputs["Color"], n_mix.inputs[6])
links.new(n_mix.outputs[2], node_bsdf.inputs["Base Color"])

# Links - Normal (direct)
links.new(n_nnnx.outputs["Color"], n_nmap.inputs["Color"])
links.new(n_nmap.outputs["Normal"], node_bsdf.inputs["Normal"])
''' + COMMON_ASSIGN + f'''
bpy.ops.wm.save_as_mainfile(filepath=r"{OUTPUT_DIR}\\{PREFIX}_processed.blend")
print("Step 2 done: {PREFIX}_processed.blend")
'''

# --- Script 3: glTF compatible + export GLB ---
script3 = COMMON_IMPORT + f'''
# AAAX -> Base Color (direct, no AO multiply)
n_aaax = nodes.new("ShaderNodeTexImage")
n_aaax.label = "Base Color"
n_aaax.location = (-600, 300)
n_aaax.image = bpy.data.images.load(os.path.join(TEX_DIR, "tex_{PREFIX}_AAAX.png"))
n_aaax.image.colorspace_settings.name = "sRGB"

# ORM (linearized, R=Occ G=Rough B=Metal)
n_orm = nodes.new("ShaderNodeTexImage")
n_orm.label = "ORM"
n_orm.location = (-600, -100)
n_orm.image = bpy.data.images.load(os.path.join(TEX_DIR, "tex_{PREFIX}_ORM.png"))
n_orm.image.colorspace_settings.name = "Non-Color"

# Separate Color (ORM)
n_sep = nodes.new("ShaderNodeSeparateColor")
n_sep.location = (-300, -100)

# Normal (fixed blue/purple)
n_nnnx = nodes.new("ShaderNodeTexImage")
n_nnnx.label = "Normal"
n_nnnx.location = (-600, -500)
n_nnnx.image = bpy.data.images.load(os.path.join(TEX_DIR, "tex_{PREFIX}_NNNX_fixed.png"))
n_nnnx.image.colorspace_settings.name = "Non-Color"

n_nmap = nodes.new("ShaderNodeNormalMap")
n_nmap.location = (-300, -500)

# Links
links.new(n_aaax.outputs["Color"], node_bsdf.inputs["Base Color"])
links.new(n_orm.outputs["Color"], n_sep.inputs["Color"])
links.new(n_sep.outputs["Blue"], node_bsdf.inputs["Metallic"])
links.new(n_sep.outputs["Green"], node_bsdf.inputs["Roughness"])
links.new(n_nnnx.outputs["Color"], n_nmap.inputs["Color"])
links.new(n_nmap.outputs["Normal"], node_bsdf.inputs["Normal"])
''' + COMMON_ASSIGN + f'''
bpy.ops.export_scene.gltf(
    filepath=r"{OUTPUT_DIR}\\{PREFIX}.glb",
    export_format="GLB",
    export_texcoords=True,
    export_normals=True,
    export_materials="EXPORT",
    export_image_format="AUTO",
)
print("Step 3 done: {PREFIX}.glb")
'''

# Write scripts
for i, script in enumerate([script1, script2, script3], 1):
    path = os.path.join(OUTPUT_DIR, f"_step{i}.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(script)
    print(f"[Script] Written: {path}")

print("\n[Done] Texture processing complete. Run Blender scripts next.")
