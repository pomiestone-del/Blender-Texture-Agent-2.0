"""
Weapon pipeline: texture processing + GLB export + local Blender render
Handles: OBJ/FBX import, AAAX/AAAT, MROX/MROE, NNNX normal swizzle
Usage: python pipeline_weapon.py
"""
import os
import subprocess
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


# ============================================================
# Auto-detect model structure
# ============================================================
def detect_model(mid):
    """Detect import method and texture types for a model."""
    model_dir = os.path.join(BASE_DIR, mid)
    prefix = f"we001_{mid}"

    # Detect FBX
    fbx_path = None
    fbx_tex_dir = None
    for d in os.listdir(model_dir):
        skin_dir = os.path.join(model_dir, d)
        if d.startswith("skin_") and os.path.isdir(skin_dir):
            for f in os.listdir(skin_dir):
                if f.endswith(".fbx"):
                    fbx_path = os.path.join(skin_dir, f)
                    fbx_tex_dir = skin_dir

    # Detect OBJ
    obj_path = None
    for f in os.listdir(model_dir):
        if f.endswith(".obj"):
            obj_path = os.path.join(model_dir, f)

    # Texture directory (FBX dir has its own textures, fallback to materials/)
    mat_dir = os.path.join(model_dir, "materials")
    tex_dir = fbx_tex_dir if fbx_path else mat_dir
    tex_files = os.listdir(tex_dir) if os.path.isdir(tex_dir) else []

    # Detect texture variants
    has_aaat = any(f"tex_{prefix}_AAAT" in f for f in tex_files)
    has_aaax = any(f"tex_{prefix}_AAAX" in f for f in tex_files)
    has_mroe = any(f"tex_{prefix}_MROE" in f for f in tex_files)
    has_mrox = any(f"tex_{prefix}_MROX" in f for f in tex_files)

    base_type = "AAAT" if has_aaat else "AAAX"
    mr_type = "MROE" if has_mroe else "MROX"

    return {
        "mid": mid,
        "prefix": prefix,
        "model_dir": model_dir,
        "tex_dir": tex_dir,
        "import": "FBX" if fbx_path else "OBJ",
        "import_path": fbx_path or obj_path,
        "base_type": base_type,  # AAAX or AAAT
        "mr_type": mr_type,      # MROX or MROE
        "has_alpha": has_aaat,
        "has_emissive": has_mroe,
    }


# ============================================================
# Step 1: Texture processing (normal map swizzle only)
# ============================================================
def process_textures(cfg):
    prefix, tex_dir = cfg["prefix"], cfg["tex_dir"]
    nnnx_path = os.path.join(tex_dir, f"tex_{prefix}_NNNX.png")
    fixed_path = os.path.join(tex_dir, f"tex_{prefix}_NNNX_fixed.png")

    nnnx = np.array(Image.open(nnnx_path))
    r, g, b = nnnx[:, :, 0].copy(), nnnx[:, :, 1].copy(), nnnx[:, :, 2].copy()
    nnnx[:, :, 0], nnnx[:, :, 1], nnnx[:, :, 2] = g, b, r
    Image.fromarray(nnnx).save(fixed_path)
    print(f"[{cfg['mid']}] Normal map fixed")


# ============================================================
# Step 2: GLB export
# ============================================================
def generate_blender_script(cfg):
    """Generate a Blender Python script for GLB export."""
    mid = cfg["mid"]
    prefix = cfg["prefix"]
    tex_dir = cfg["tex_dir"]
    local_glb = os.path.join(LOCAL_TMP, f"{prefix}.glb")
    remote_glb = os.path.join(OUTPUT_UNC, f"{prefix}.glb")

    base_tex = f"tex_{prefix}_{cfg['base_type']}.png"
    mr_tex = f"tex_{prefix}_{cfg['mr_type']}.png"
    normal_tex = f"tex_{prefix}_NNNX_fixed.png"

    # Import command
    if cfg["import"] == "FBX":
        import_cmd = f'bpy.ops.import_scene.fbx(filepath=r"{cfg["import_path"]}", use_custom_normals=True, automatic_bone_orientation=True)'
    else:
        import_cmd = f'bpy.ops.wm.obj_import(filepath=r"{cfg["import_path"]}")'

    # Alpha setup
    alpha_nodes = ""
    alpha_links = ""
    if cfg["has_alpha"]:
        alpha_links = 'links.new(n_base.outputs["Alpha"], bsdf.inputs["Alpha"])'
        alpha_nodes = """
mat.surface_render_method = 'DITHERED'
mat.use_backface_culling = False
"""

    # Emissive: MROE A channel is emissive but near-zero for these models.
    # glTF exporter cannot reliably export Alpha->Emission Strength connections,
    # so we set Emission Strength to 0 to prevent default=1.0 causing full white glow.
    emissive_nodes = ""
    if cfg["has_emissive"]:
        emissive_nodes = """
bsdf.inputs["Emission Strength"].default_value = 0.0
"""

    script = f'''import bpy, os, shutil
bpy.ops.wm.read_factory_settings(use_empty=True)

# Import
{import_cmd}

# Create material
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

# Base Color ({cfg["base_type"]})
n_base = nodes.new("ShaderNodeTexImage")
n_base.location = (-600, 300)
n_base.image = bpy.data.images.load(r"{os.path.join(tex_dir, base_tex)}")
n_base.image.colorspace_settings.name = "sRGB"
links.new(n_base.outputs["Color"], bsdf.inputs["Base Color"])
{alpha_links}
{alpha_nodes}

# Metallic/Roughness ({cfg["mr_type"]})
n_mr = nodes.new("ShaderNodeTexImage")
n_mr.location = (-600, -100)
n_mr.image = bpy.data.images.load(r"{os.path.join(tex_dir, mr_tex)}")
n_mr.image.colorspace_settings.name = "sRGB"
n_sep = nodes.new("ShaderNodeSeparateColor")
n_sep.location = (-300, -100)
links.new(n_mr.outputs["Color"], n_sep.inputs["Color"])
links.new(n_sep.outputs["Red"], bsdf.inputs["Metallic"])
links.new(n_sep.outputs["Green"], bsdf.inputs["Roughness"])
{emissive_nodes}

# Normal (fixed purple)
n_nnn = nodes.new("ShaderNodeTexImage")
n_nnn.location = (-600, -500)
n_nnn.image = bpy.data.images.load(r"{os.path.join(tex_dir, normal_tex)}")
n_nnn.image.colorspace_settings.name = "Non-Color"
n_nmap = nodes.new("ShaderNodeNormalMap")
n_nmap.location = (-300, -500)
links.new(n_nnn.outputs["Color"], n_nmap.inputs["Color"])
links.new(n_nmap.outputs["Normal"], bsdf.inputs["Normal"])

# Assign material to all meshes
for obj in bpy.data.objects:
    if obj.type == "MESH":
        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)

# Export
local = r"{local_glb}"
bpy.ops.export_scene.gltf(filepath=local, export_format="GLB", export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO")

remote = r"{remote_glb}"
shutil.copy2(local, remote)
print("GLB exported: {prefix}.glb")
'''
    return script


def export_glb(cfg):
    mid = cfg["mid"]
    script_path = os.path.join(LOCAL_TMP, f"_export_{mid}.py")

    with open(script_path, "w", encoding="utf-8") as f:
        f.write(generate_blender_script(cfg))

    result = subprocess.run(
        [BLENDER, "--background", "--python", script_path],
        capture_output=True, text=True, timeout=120,
        encoding="utf-8", errors="replace"
    )
    if "GLB exported" in (result.stdout or ""):
        print(f"[{mid}] GLB exported")
    else:
        print(f"[{mid}] GLB export FAILED")
        print((result.stderr or result.stdout or "")[-500:])
    os.remove(script_path)


# ============================================================
# Step 3: Local Blender render
# ============================================================
def render_glb(cfg):
    prefix = cfg["prefix"]
    glb_path = os.path.join(OUTPUT_UNC, f"{prefix}.glb")
    png_path = os.path.join(OUTPUT_UNC, f"{prefix}.png")

    result = subprocess.run(
        [BLENDER, "--background", "--python", RENDER_SCRIPT,
         "--", glb_path, png_path, "512"],
        capture_output=True, text=True, timeout=180,
        encoding="utf-8", errors="replace"
    )
    if os.path.isfile(png_path):
        print(f"[{cfg['mid']}] Rendered")
    else:
        print(f"[{cfg['mid']}] Render FAILED")
        print((result.stderr or result.stdout or "")[-500:])


# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    # Detect all models
    models = sorted(d for d in os.listdir(BASE_DIR)
                    if os.path.isdir(os.path.join(BASE_DIR, d)))
    configs = [detect_model(mid) for mid in models]

    print(f"Found {len(configs)} models\n")

    print("=" * 50)
    print("Step 1: Texture processing")
    print("=" * 50)
    for cfg in configs:
        process_textures(cfg)

    print("\n" + "=" * 50)
    print("Step 2: GLB export")
    print("=" * 50)
    for cfg in configs:
        export_glb(cfg)

    print("\n" + "=" * 50)
    print("Step 3: Render")
    print("=" * 50)
    for cfg in configs:
        render_glb(cfg)

    print("\n" + "=" * 50)
    print(f"Done: {len(configs)} models → {OUTPUT_UNC}")
    print("=" * 50)
