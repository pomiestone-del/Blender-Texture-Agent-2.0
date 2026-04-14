"""
Asset pipeline: texture processing + GLB export + local Blender render
Handles: OBJ/FBX import, AAAX/AAAT, MROX/MROE, NNNX normal swizzle
Supports: weapon (we), monster (mo)
Usage: python pipeline_weapon.py
"""
import os
import subprocess
import tempfile
import numpy as np
from PIL import Image

# ============================================================
# Config
# ============================================================
BLENDER = r"C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
RENDER_SCRIPT = r"C:\Users\Administrator\Downloads\blender_render_preview.py"

ASSET_TYPE = "weapon"  # "weapon" or "monster"
ASSET_PREFIX_MAP = {"weapon": "we", "monster": "mo"}

WEAPON_ID = "003"  # Change this to process different categories
BASE_DIR = rf"\\172.16.8.156\art-data-intern\FF7EC\model\{ASSET_TYPE}\{WEAPON_ID}\model"
OUTPUT_UNC = rf"\\172.16.8.156\art-data-intern\FF7EC\output\{ASSET_TYPE}"


# ============================================================
# Auto-detect model structure
# ============================================================
def detect_model(mid):
    """Detect import method and texture types for a model."""
    model_dir = os.path.join(BASE_DIR, mid)
    asset_prefix = ASSET_PREFIX_MAP.get(ASSET_TYPE, "we")
    prefix = f"{asset_prefix}{WEAPON_ID}_{mid}"

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

    # Detect OBJ (collect all)
    obj_paths = []
    for f in sorted(os.listdir(model_dir)):
        if f.endswith(".obj"):
            obj_paths.append(os.path.join(model_dir, f))

    # Texture directory (FBX dir has its own textures, fallback to materials/)
    mat_dir = os.path.join(model_dir, "materials")
    tex_dir = fbx_tex_dir if fbx_path else mat_dir
    tex_files = os.listdir(tex_dir) if os.path.isdir(tex_dir) else []

    # Detect texture prefix: tex_ or stat_
    tex_prefix_str = "tex_"
    if any(f.startswith(f"stat_{prefix}_") for f in tex_files):
        tex_prefix_str = "stat_"

    # Detect all part suffixes (e.g. _body, _acc in tex_mo001_003_body_AAAT.png)
    base_pattern = f"{tex_prefix_str}{prefix}_"
    tex_parts = set()
    for f in tex_files:
        if not f.startswith(base_pattern):
            continue
        for tag in ["_AAAT", "_AAAX"]:
            if tag in f:
                mid_part = f[len(base_pattern):f.index(tag)]
                tex_parts.add(mid_part if mid_part else "")
                break

    # Use first part for single-material detection, keep all for multi-material
    tex_parts = sorted(tex_parts)
    tex_part = f"_{tex_parts[0]}" if tex_parts and tex_parts[0] else ""

    # Detect texture variants (using first part)
    full_prefix = f"{tex_prefix_str}{prefix}{tex_part}"
    has_aaat = any(f"{full_prefix}_AAAT" in f for f in tex_files)
    has_aaax = any(f"{full_prefix}_AAAX" in f for f in tex_files)
    has_mroe = any(f"{full_prefix}_MROE" in f for f in tex_files)
    has_mrox = any(f"{full_prefix}_MROX" in f for f in tex_files)
    has_morx = any(f"{full_prefix}_MORX" in f for f in tex_files)
    has_more = any(f"{full_prefix}_MORE" in f for f in tex_files)

    base_type = "AAAT" if has_aaat else "AAAX"
    mr_type = "MROE" if has_mroe else ("MROX" if has_mrox else ("MORX" if has_morx else "MORE"))

    # Per-part texture info for multi-material models
    multi_parts = []
    if len(tex_parts) > 1:
        for p in tex_parts:
            p_prefix = f"{tex_prefix_str}{prefix}_{p}" if p else f"{tex_prefix_str}{prefix}"
            p_aaat = any(f"{p_prefix}_AAAT" in f for f in tex_files)
            p_aaax = any(f"{p_prefix}_AAAX" in f for f in tex_files)
            p_mroe = any(f"{p_prefix}_MROE" in f for f in tex_files)
            p_mrox = any(f"{p_prefix}_MROX" in f for f in tex_files)
            p_morx = any(f"{p_prefix}_MORX" in f for f in tex_files)
            p_more = any(f"{p_prefix}_MORE" in f for f in tex_files)
            multi_parts.append({
                "part": p,
                "base_type": "AAAT" if p_aaat else "AAAX",
                "mr_type": "MROE" if p_mroe else ("MROX" if p_mrox else ("MORX" if p_morx else "MORE")),
                "has_alpha": p_aaat,
                "has_emissive": p_mroe,
            })

    return {
        "mid": mid,
        "prefix": prefix,
        "tex_prefix": tex_prefix_str,  # "tex_" or "stat_"
        "tex_part": tex_part,          # "" or "_body" etc.
        "model_dir": model_dir,
        "tex_dir": tex_dir,
        "weapon_id": WEAPON_ID,
        "import": "FBX" if fbx_path else "OBJ",
        "import_path": fbx_path if fbx_path else obj_paths,
        "base_type": base_type,  # AAAX or AAAT
        "mr_type": mr_type,      # MROX or MROE
        "has_alpha": has_aaat,
        "has_emissive": has_mroe,
        "multi_parts": multi_parts,  # [] for single-material, list of dicts for multi
    }


# ============================================================
# Step 1: Texture processing (normal map swizzle only)
# ============================================================
def process_textures(cfg):
    prefix, tex_dir = cfg["prefix"], cfg["tex_dir"]
    tp = cfg.get("tex_prefix", "tex_")
    multi_parts = cfg.get("multi_parts", [])

    # Collect all parts to process
    if multi_parts:
        parts = [f"_{p['part']}" if p['part'] else "" for p in multi_parts]
    else:
        parts = [cfg.get("tex_part", "")]

    mat_dir = os.path.join(cfg["model_dir"], "materials")
    for tpart in parts:
        nnnx_path = os.path.join(tex_dir, f"{tp}{prefix}{tpart}_NNNX.png")
        fixed_path = os.path.join(tex_dir, f"{tp}{prefix}{tpart}_NNNX_fixed.png")
        if not os.path.isfile(nnnx_path):
            # Fallback to materials dir
            nnnx_path = os.path.join(mat_dir, f"{tp}{prefix}{tpart}_NNNX.png")
            fixed_path = os.path.join(mat_dir, f"{tp}{prefix}{tpart}_NNNX_fixed.png")
            if not os.path.isfile(nnnx_path):
                continue
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
    tex_dir = os.path.normpath(cfg["tex_dir"])
    remote_glb = os.path.normpath(os.path.join(OUTPUT_UNC, f"{prefix}.glb"))

    tp = cfg.get("tex_prefix", "tex_")
    tpart = cfg.get("tex_part", "")
    base_tex = f"{tp}{prefix}{tpart}_{cfg['base_type']}.png"
    mr_tex = f"{tp}{prefix}{tpart}_{cfg['mr_type']}.png"
    normal_tex = f"{tp}{prefix}{tpart}_NNNX_fixed.png"
    # Fallback: check materials dir if normal not in tex_dir
    normal_path = os.path.join(tex_dir, normal_tex)
    if not os.path.isfile(normal_path):
        mat_fallback = os.path.normpath(os.path.join(cfg["model_dir"], "materials"))
        if os.path.isfile(os.path.join(mat_fallback, normal_tex)):
            tex_dir_normal = mat_fallback
        else:
            tex_dir_normal = tex_dir  # will be missing, but handled gracefully
    else:
        tex_dir_normal = tex_dir

    # Import command
    if cfg["import"] == "FBX":
        fbx_norm = os.path.normpath(cfg["import_path"])
        import_cmd = f'bpy.ops.import_scene.fbx(filepath=r"{fbx_norm}", use_custom_normals=True, automatic_bone_orientation=True)'
    else:
        # Import all OBJs
        import_lines = [f'bpy.ops.wm.obj_import(filepath=r"{os.path.normpath(p)}")' for p in cfg["import_path"]]
        import_cmd = "\n".join(import_lines)

    # Generate material creation + assignment code
    multi_parts = cfg.get("multi_parts", [])

    if multi_parts:
        # Multi-material: create one material per part, assign by mesh name match
        mat_lines = []
        mat_lines.append("""
def _make_mat(name, base_path, mr_path, normal_path, has_alpha, has_emissive):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes; links = mat.node_tree.links; nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial"); out.location=(200,100)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location=(-200,100)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    n_base = nodes.new("ShaderNodeTexImage"); n_base.location=(-600,300)
    n_base.image = bpy.data.images.load(base_path)
    n_base.image.colorspace_settings.name = "sRGB"
    links.new(n_base.outputs["Color"], bsdf.inputs["Base Color"])
    if has_alpha:
        links.new(n_base.outputs["Alpha"], bsdf.inputs["Alpha"])
        mat.surface_render_method = 'DITHERED'
        mat.use_backface_culling = False
    n_mr = nodes.new("ShaderNodeTexImage"); n_mr.location=(-600,-100)
    n_mr.image = bpy.data.images.load(mr_path)
    n_mr.image.colorspace_settings.name = "sRGB"
    n_sep = nodes.new("ShaderNodeSeparateColor"); n_sep.location=(-300,-100)
    links.new(n_mr.outputs["Color"], n_sep.inputs["Color"])
    links.new(n_sep.outputs["Red"], bsdf.inputs["Metallic"])
    links.new(n_sep.outputs["Green"], bsdf.inputs["Roughness"])
    if has_emissive:
        bsdf.inputs["Emission Strength"].default_value = 0.0
    if normal_path and os.path.isfile(normal_path):
        n_nnn = nodes.new("ShaderNodeTexImage"); n_nnn.location=(-600,-500)
        n_nnn.image = bpy.data.images.load(normal_path)
        n_nnn.image.colorspace_settings.name = "Non-Color"
        n_nmap = nodes.new("ShaderNodeNormalMap"); n_nmap.location=(-300,-500)
        links.new(n_nnn.outputs["Color"], n_nmap.inputs["Color"])
        links.new(n_nmap.outputs["Normal"], bsdf.inputs["Normal"])
    return mat
""")
        # Create each part's material
        mat_names = {}
        for p in multi_parts:
            part = p["part"]
            part_suffix = f"_{part}" if part else ""
            mat_name = f"mat_{prefix}{part_suffix}"
            b_tex = os.path.join(tex_dir, f"{tp}{prefix}{part_suffix}_{p['base_type']}.png")
            m_tex = os.path.join(tex_dir, f"{tp}{prefix}{part_suffix}_{p['mr_type']}.png")
            n_tex = os.path.join(tex_dir, f"{tp}{prefix}{part_suffix}_NNNX_fixed.png")
            # Fallback to materials dir for NNNX
            if not os.path.isfile(n_tex):
                mat_dir = os.path.join(cfg["model_dir"], "materials")
                n_tex_alt = os.path.join(mat_dir, f"{tp}{prefix}{part_suffix}_NNNX_fixed.png")
                if os.path.isfile(n_tex_alt):
                    n_tex = n_tex_alt
                else:
                    n_tex = ""  # No normal map for this part
            mat_lines.append(f'mat_{part or "default"} = _make_mat("{mat_name}", r"{b_tex}", r"{m_tex}", r"{n_tex}", {p["has_alpha"]}, {p["has_emissive"]})')
            mat_names[part] = f'mat_{part or "default"}'

        material_cmd = "\n".join(mat_lines)

        # Assignment: match part name in mesh name
        assign_lines = ["_part_mats = {"]
        for part, var in mat_names.items():
            assign_lines.append(f'    "{part}": {var},')
        assign_lines.append("}")
        assign_lines.append("""
for obj in bpy.data.objects:
    if obj.type == "MESH":
        assigned = None
        for part_key, part_mat in _part_mats.items():
            if part_key and part_key in obj.name:
                assigned = part_mat
                break
        if assigned is None:
            assigned = list(_part_mats.values())[0]
        if obj.data.materials:
            for i in range(len(obj.data.materials)):
                obj.data.materials[i] = assigned
        else:
            obj.data.materials.append(assigned)
""")
        assign_cmd = "\n".join(assign_lines)

    else:
        # Single material (original logic)
        alpha_links = ""
        alpha_nodes = ""
        if cfg["has_alpha"]:
            alpha_links = 'links.new(n_base.outputs["Alpha"], bsdf.inputs["Alpha"])'
            alpha_nodes = """
mat.surface_render_method = 'DITHERED'
mat.use_backface_culling = False
"""
        emissive_nodes = ""
        if cfg["has_emissive"]:
            emissive_nodes = """
bsdf.inputs["Emission Strength"].default_value = 0.0
"""
        material_cmd = f'''mat = bpy.data.materials.new(name="mat_{prefix}")
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

n_base = nodes.new("ShaderNodeTexImage")
n_base.location = (-600, 300)
n_base.image = bpy.data.images.load(r"{os.path.join(tex_dir, base_tex)}")
n_base.image.colorspace_settings.name = "sRGB"
links.new(n_base.outputs["Color"], bsdf.inputs["Base Color"])
{alpha_links}
{alpha_nodes}

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

n_nnn = nodes.new("ShaderNodeTexImage")
n_nnn.location = (-600, -500)
n_nnn.image = bpy.data.images.load(r"{os.path.join(tex_dir_normal, normal_tex)}")
n_nnn.image.colorspace_settings.name = "Non-Color"
n_nmap = nodes.new("ShaderNodeNormalMap")
n_nmap.location = (-300, -500)
links.new(n_nnn.outputs["Color"], n_nmap.inputs["Color"])
links.new(n_nmap.outputs["Normal"], bsdf.inputs["Normal"])'''

        assign_cmd = '''for obj in bpy.data.objects:
    if obj.type == "MESH":
        if obj.data.materials:
            for i in range(len(obj.data.materials)):
                obj.data.materials[i] = mat
        else:
            obj.data.materials.append(mat)'''

    # Per-category rotation (key = "asset_type:id")
    rotate_cmd = ""
    rotation_map = {
        # weapon
        "weapon:001": [('X', -90), ('Z', -90)],
        "weapon:004": [('X', -90), ('Z', -90)],
        "weapon:005": [('X', -90), ('Z', -90)],
        "weapon:006": [('Z', -90), ('Y', 90)],
        "weapon:007": [('Z', -90)],
        "weapon:008": [('Y', 90), ('X', 90)],
        "weapon:009": [('X', -90), ('Z', -90)],
        "weapon:012": [('X', -90), ('Z', -90)],
        "weapon:020": [('X', -90), ('Z', -90)],
        "weapon:049": [('X', -90), ('Z', -90)],
        "weapon:050": [('X', -90), ('Z', -90)],
        "weapon:051": [('X', -90), ('Z', -90)],
        "weapon:052": [('X', 90), ('Z', 90)],
        "weapon:056": [('X', -90), ('Z', -90)],
        "weapon:057": [('X', -90), ('Z', -90), ('Z', 90)],
        "weapon:060": [('X', -90), ('Z', -90)],
        "weapon:509": [('X', -90), ('Z', -90)],
        "weapon:902": [('X', -90), ('Z', -90)],
        "weapon:908": [('X', -90), ('Z', -90)],
        "weapon:932": [('X', -90), ('Z', -90), ('Y', 180), ('Z', 180)],
        "weapon:969": [('X', -90), ('Z', -90), ('Z', -90)],
    }
    default_rotation = [('X', -90), ('Z', -90)]
    default_monster_rotation = [('X', -90), ('Z', -90), ('Y', -90), ('Z', 90)]
    rot_key = f"{ASSET_TYPE}:{cfg['weapon_id']}"
    fallback = default_monster_rotation if ASSET_TYPE == "monster" else default_rotation
    rotations = rotation_map.get(rot_key, fallback)
    if rotations:
        rot_lines = []
        for i, (axis, deg) in enumerate(rotations):
            rot_lines.append(f"r{i} = mathutils.Matrix.Rotation(math.radians({deg}), 4, '{axis}')")
        combined = " @ ".join(f"r{i}" for i in range(len(rotations) - 1, -1, -1))
        rotate_cmd = f"""
import math, mathutils
{chr(10).join(rot_lines)}
combined = {combined}
for obj in bpy.data.objects:
    if obj.parent is None:
        obj.matrix_world = combined @ obj.matrix_world
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
"""

    script = f'''import bpy, os
bpy.ops.wm.read_factory_settings(use_empty=True)

# Import
{import_cmd}

# Apply armature scale (FBX unit conversion leaves scale=0.01)
for obj in bpy.data.objects:
    if obj.type == "ARMATURE":
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        obj.select_set(False)

# Reset pose to rest pose, then apply armature modifiers (prevents GLB skinning distortion)
for obj in bpy.data.objects:
    if obj.type == "ARMATURE":
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='POSE')
        bpy.ops.pose.select_all(action='SELECT')
        bpy.ops.pose.transforms_clear()
        bpy.ops.object.mode_set(mode='OBJECT')
for obj in bpy.data.objects:
    if obj.type == "MESH":
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        for mod in list(obj.modifiers):
            if mod.type == "ARMATURE":
                bpy.ops.object.modifier_apply(modifier=mod.name)
        obj.vertex_groups.clear()
        obj.select_set(False)

# Rotation fix
{rotate_cmd}

# Create materials
{material_cmd}

# Assign materials
{assign_cmd}

# Export GLB
bpy.ops.export_scene.gltf(filepath=r"{remote_glb}", export_format="GLB", export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO")
print("GLB exported: {prefix}.glb")
'''
    return script


def export_glb(cfg):
    mid = cfg["mid"]
    script_path = os.path.join(tempfile.gettempdir(), f"_export_{mid}.py")

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
    glb_path = os.path.normpath(os.path.join(OUTPUT_UNC, f"{prefix}.glb"))
    png_path = os.path.normpath(os.path.join(OUTPUT_UNC, f"{prefix}.png"))

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
