"""
Weapon pipeline: texture processing + GLB export + local Blender render
Usage: python pipeline_weapon.py
"""
import os
import subprocess
import shutil
import numpy as np
from PIL import Image

# ============================================================
# Config
# ============================================================
BLENDER = r"C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
RENDER_SCRIPT = r"C:\Users\Administrator\Downloads\blender_render_preview.py"

BASE_DIR = r"\\172.16.8.156\art-data-intern\FF7EC\model\weapon\001\model"
OUTPUT_UNC = r"\\172.16.8.156\art-data-intern\FF7EC\output\weapon"
LOCAL_TMP = r"C:\Users\Administrator\Documents\outputTest"

MODELS = ["001", "002", "003"]

# ============================================================
# Step 1: Texture processing
# ============================================================
def process_textures(mid):
    prefix = f"we001_{mid}"
    tex_dir = os.path.join(BASE_DIR, mid, "materials")

    # Normal map: bake channel swizzle into pixels (pink -> purple)
    # Original pink (R=Z~255, G=X~128, B=Y~128), sample wiring: R→Z, G→X, B→Y via Combine XYZ
    # Standard normal map: R=X, G=Y, B=Z → newR=oldG, newG=oldB, newB=oldR
    nnnx = np.array(Image.open(os.path.join(tex_dir, f"tex_{prefix}_NNNX.png")))
    r, g, b = nnnx[:,:,0].copy(), nnnx[:,:,1].copy(), nnnx[:,:,2].copy()
    nnnx[:,:,0], nnnx[:,:,1], nnnx[:,:,2] = g, b, r
    Image.fromarray(nnnx).save(os.path.join(tex_dir, f"tex_{prefix}_NNNX_fixed.png"))

    print(f"[{mid}] Textures processed")

# ============================================================
# Step 2: Blender GLB export script (written to temp file)
# ============================================================
def export_glb(mid):
    prefix = f"we001_{mid}"
    model_dir = os.path.join(BASE_DIR, mid)
    tex_dir = os.path.join(model_dir, "materials")
    local_glb = os.path.join(r"C:\Users\Administrator\Documents\outputTest", f"{prefix}.glb")
    remote_glb = os.path.join(OUTPUT_UNC, f"{prefix}.glb")

    script_path = os.path.join(r"C:\Users\Administrator\Documents\outputTest", f"_export_{mid}.py")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(f'''import bpy, os, shutil
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.obj_import(filepath=r"{os.path.join(model_dir, "body_geo.obj")}")
obj = None
for o in bpy.data.objects:
    if o.type == "MESH":
        obj = o
        break

mat = bpy.data.materials.new(name="mat_{prefix}")
mat.use_nodes = True
tree = mat.node_tree
nodes = tree.nodes
links = tree.links
nodes.clear()

out = nodes.new("ShaderNodeOutputMaterial")
out.location = (200, 100)
bsdf = nodes.new("ShaderNodeBsdfPrincipled")
bsdf.location = (-200, 100)
links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

n_bc = nodes.new("ShaderNodeTexImage")
n_bc.location = (-600, 300)
n_bc.image = bpy.data.images.load(r"{os.path.join(tex_dir, f"tex_{prefix}_AAAX.png")}")
n_bc.image.colorspace_settings.name = "sRGB"

n_mrox = nodes.new("ShaderNodeTexImage")
n_mrox.location = (-600, -100)
n_mrox.image = bpy.data.images.load(r"{os.path.join(tex_dir, f"tex_{prefix}_MROX.png")}")
n_mrox.image.colorspace_settings.name = "sRGB"

n_sep = nodes.new("ShaderNodeSeparateColor")
n_sep.location = (-300, -100)

n_nnn = nodes.new("ShaderNodeTexImage")
n_nnn.location = (-600, -500)
n_nnn.image = bpy.data.images.load(r"{os.path.join(tex_dir, f"tex_{prefix}_NNNX_fixed.png")}")
n_nnn.image.colorspace_settings.name = "Non-Color"

n_nmap = nodes.new("ShaderNodeNormalMap")
n_nmap.location = (-300, -500)

links.new(n_bc.outputs["Color"], bsdf.inputs["Base Color"])
links.new(n_mrox.outputs["Color"], n_sep.inputs["Color"])
links.new(n_sep.outputs["Red"], bsdf.inputs["Metallic"])
links.new(n_sep.outputs["Green"], bsdf.inputs["Roughness"])
links.new(n_nnn.outputs["Color"], n_nmap.inputs["Color"])
links.new(n_nmap.outputs["Normal"], bsdf.inputs["Normal"])

if obj.data.materials:
    obj.data.materials[0] = mat
else:
    obj.data.materials.append(mat)

local = r"{local_glb}"
bpy.ops.export_scene.gltf(filepath=local, export_format="GLB", export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO")

# Copy to network drive
remote = r"{remote_glb}"
shutil.copy2(local, remote)
print("GLB exported and copied: {prefix}.glb")
''')

    result = subprocess.run(
        [BLENDER, "--background", "--python", script_path],
        capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace"
    )
    if "GLB exported" in (result.stdout or ""):
        print(f"[{mid}] GLB exported to network drive")
    else:
        print(f"[{mid}] GLB export FAILED")
        print((result.stderr or result.stdout or "")[-500:])
    os.remove(script_path)

# ============================================================
# Step 3: Local Blender render (using blender_render_preview.py)
# ============================================================
def render_glb(mid):
    prefix = f"we001_{mid}"
    glb_path = os.path.join(OUTPUT_UNC, f"{prefix}.glb")
    png_path = os.path.join(OUTPUT_UNC, f"{prefix}.png")

    result = subprocess.run(
        [BLENDER, "--background", "--python", RENDER_SCRIPT,
         "--", glb_path, png_path, "512"],
        capture_output=True, text=True, timeout=180,
        encoding="utf-8", errors="replace"
    )
    if os.path.isfile(png_path):
        print(f"[{mid}] Rendered: {prefix}.png")
    else:
        print(f"[{mid}] Render FAILED")
        print((result.stderr or result.stdout or "")[-500:])

# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    print("=" * 50)
    print("Step 1: Texture processing")
    print("=" * 50)
    for mid in MODELS:
        process_textures(mid)

    print("\n" + "=" * 50)
    print("Step 2: GLB export")
    print("=" * 50)
    for mid in MODELS:
        export_glb(mid)

    print("\n" + "=" * 50)
    print("Step 3: Local render")
    print("=" * 50)
    for mid in MODELS:
        render_glb(mid)

    print("\n" + "=" * 50)
    print("Output:")
    print("=" * 50)
    for mid in MODELS:
        prefix = f"we001_{mid}"
        print(f"  {OUTPUT_UNC}\\{prefix}.glb")
        print(f"  {OUTPUT_UNC}\\{prefix}.png")
