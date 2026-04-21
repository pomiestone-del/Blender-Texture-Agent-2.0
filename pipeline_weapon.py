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

    # Detect texture prefix: tex_, stat_, or tex_mat_
    tex_prefix_str = "tex_"
    if any(f.startswith(f"stat_{prefix}_") for f in tex_files):
        tex_prefix_str = "stat_"
    elif any(f.startswith(f"tex_mat_{prefix}_") for f in tex_files):
        tex_prefix_str = "tex_mat_"

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

    # Detect cross-skin textures (e.g. tex_mo553_002_* in 001's skin dir)
    # These belong to a different character sharing the same FBX/model dir
    # Only treat as cross-skin if the group provides COMPLETE material sets
    # (at least one part has BOTH base texture AND MR texture).
    # Partial sharing (e.g. only NNNX or only AAAX) is just texture reuse, not a separate character.
    import re as _re
    _cross_candidates = {}  # {other_prefix: {part: set of texture types}}
    for f in tex_files:
        if not f.startswith(tex_prefix_str):
            continue
        # Match tex_moXXX_YYY_ where YYY != current mid
        m = _re.match(rf"{_re.escape(tex_prefix_str)}{_re.escape(asset_prefix)}(\d+)_(\d+)_", f)
        if m and m.group(2) != mid:
            cross_prefix = f"{tex_prefix_str}{asset_prefix}{m.group(1)}_{m.group(2)}"
            cross_pattern = cross_prefix + "_"
            for tag in ["_AAAT", "_AAAX", "_MROE", "_MROX", "_MORX", "_MORE", "_NNNX"]:
                if tag in f:
                    mid_part = f[len(cross_pattern):f.index(tag)]
                    part_key = mid_part if mid_part else ""
                    _cross_candidates.setdefault(cross_prefix, {}).setdefault(part_key, set())
                    _cross_candidates[cross_prefix][part_key].add(tag.strip("_"))
                    break

    # Filter: only keep cross-skin groups where at least one part has BOTH base AND MR
    _base_tags = {"AAAT", "AAAX"}
    _mr_tags = {"MROE", "MROX", "MORX", "MORE"}
    cross_skin_groups = {}
    for cp, parts_dict in _cross_candidates.items():
        has_complete = False
        for part_key, tags in parts_dict.items():
            if (tags & _base_tags) and (tags & _mr_tags):
                has_complete = True
                break
        if has_complete:
            cross_skin_groups[cp] = set(parts_dict.keys())

    # Determine mesh-name prefixes for cross-skin assignment
    # e.g. odin_* -> mo553_001 (main), sleip_* -> mo553_002 (cross)
    cross_mesh_prefixes = {}  # {cross_prefix: [mesh_prefix, ...]}
    if cross_skin_groups:
        # Get unique mesh name prefixes from OBJ files
        mesh_prefix_to_parts = {}  # {mesh_prefix: set of part names}
        for f in sorted(os.listdir(model_dir)):
            if f.endswith(".obj"):
                mesh_pfx = f.split("_")[0]
                # Extract part from mesh name: e.g. odin_bodyA_geo -> bodyA
                name_no_ext = f[:-4]  # strip .obj
                name_after_prefix = name_no_ext[len(mesh_pfx)+1:] if "_" in name_no_ext else ""
                # Remove _geo, _bf etc suffixes
                mesh_part = _re.sub(r'_(geo|bf|backface)$', '', name_after_prefix)
                mesh_part = _re.sub(r'_geo$', '', mesh_part)
                mesh_prefix_to_parts.setdefault(mesh_pfx, set()).add(mesh_part.lower())

        # For each mesh prefix, check if it has parts that exclusively match
        # cross-skin textures (not main). e.g. sleip has "hair" -> only in cross.
        main_parts_lower = {p.lower() for p in tex_parts if p}
        assigned_prefixes = set()
        for mesh_pfx, mesh_parts in mesh_prefix_to_parts.items():
            best_cross = None
            best_exclusive = 0
            for cp, cp_parts in cross_skin_groups.items():
                cp_lower = {p.lower() for p in cp_parts if p}
                # Count mesh parts that match cross but NOT main
                exclusive = 0
                for mp in mesh_parts:
                    matches_cross = any(tp in mp or mp in tp for tp in cp_lower)
                    matches_main = any(tp in mp or mp in tp for tp in main_parts_lower)
                    if matches_cross and not matches_main:
                        exclusive += 1
                if exclusive > best_exclusive:
                    best_exclusive = exclusive
                    best_cross = cp
            if best_exclusive > 0 and best_cross:
                cross_mesh_prefixes.setdefault(best_cross, []).append(mesh_pfx)
                assigned_prefixes.add(mesh_pfx)

        # Fallback: if multiple mesh prefixes exist but none assigned exclusively,
        # use a scoring approach: for each prefix, count how many of its mesh parts
        # match main tex parts vs cross tex parts with exact containment.
        # The prefix with higher cross-to-main ratio gets assigned to cross-skin.
        if not assigned_prefixes and len(mesh_prefix_to_parts) >= 2 and len(cross_skin_groups) == 1:
            cp = list(cross_skin_groups.keys())[0]
            cp_lower = {p.lower() for p in cross_skin_groups[cp] if p}
            best_pfx = None
            best_ratio = -9999
            for mesh_pfx, mesh_parts in mesh_prefix_to_parts.items():
                main_score = sum(1 for mp in mesh_parts
                                 for tp in main_parts_lower
                                 if mp == tp)  # exact match only
                cross_score = sum(1 for mp in mesh_parts
                                  for tp in cp_lower
                                  if mp == tp)  # exact match only
                # Prefer the prefix that has more exact cross matches and fewer main matches
                ratio = cross_score - main_score
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_pfx = mesh_pfx
            # Only assign if there's a clear signal (at least one exact cross match)
            if best_pfx and best_ratio > -999:
                cross_mesh_prefixes.setdefault(cp, []).append(best_pfx)

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

    # If no main tex_parts but cross-skin textures exist, adopt them as main.
    # e.g. mo516_001 only has tex_mo516_000_* textures -> use "mo516_000" as tex lookup prefix
    tex_lookup_prefix = prefix  # default: same as model prefix (e.g. "mo516_001")
    if not tex_parts and cross_skin_groups:
        adopt_key = list(cross_skin_groups.keys())[0]  # e.g. "tex_mo516_000"
        adopt_parts = cross_skin_groups[adopt_key]
        adopt_prefix = adopt_key[len(tex_prefix_str):]  # e.g. "mo516_000"
        tex_lookup_prefix = adopt_prefix
        tex_parts = sorted(adopt_parts)
        # Re-sort and re-detect
        tex_parts = sorted(tex_parts)
        tex_part = f"_{tex_parts[0]}" if tex_parts and tex_parts[0] else ""
        full_prefix = f"{tex_prefix_str}{adopt_prefix}{tex_part}"
        has_aaat = any(f"{full_prefix}_AAAT" in f for f in tex_files)
        has_aaax = any(f"{full_prefix}_AAAX" in f for f in tex_files)
        has_mroe = any(f"{full_prefix}_MROE" in f for f in tex_files)
        has_mrox = any(f"{full_prefix}_MROX" in f for f in tex_files)
        has_morx = any(f"{full_prefix}_MORX" in f for f in tex_files)
        has_more = any(f"{full_prefix}_MORE" in f for f in tex_files)
        base_type = "AAAT" if has_aaat else "AAAX"
        mr_type = "MROE" if has_mroe else ("MROX" if has_mrox else ("MORX" if has_morx else "MORE"))
        # If MR type is "MORE" (fallback/default), also check original prefix for MR textures
        if mr_type == "MORE":
            orig_full = f"{tex_prefix_str}{prefix}{tex_part}"
            if any(f"{orig_full}_MROE" in f for f in tex_files):
                mr_type = "MROE"
                tex_lookup_prefix = (adopt_prefix, prefix)  # tuple: base from adopted, MR from original
            elif any(f"{orig_full}_MROX" in f for f in tex_files):
                mr_type = "MROX"
                tex_lookup_prefix = (adopt_prefix, prefix)
        # Clear cross-skin since we adopted it
        cross_skin_groups = {}
        cross_mesh_prefixes = {}

    # Per-part texture info for multi-material models
    multi_parts = []
    if len(tex_parts) > 1 or cross_skin_groups:
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
        # Add cross-skin parts
        for cross_prefix, cross_parts in cross_skin_groups.items():
            for p in sorted(cross_parts):
                p_prefix = f"{cross_prefix}_{p}" if p else cross_prefix
                p_aaat = any(f"{p_prefix}_AAAT" in f for f in tex_files)
                p_aaax = any(f"{p_prefix}_AAAX" in f for f in tex_files)
                p_mroe = any(f"{p_prefix}_MROE" in f for f in tex_files)
                p_mrox = any(f"{p_prefix}_MROX" in f for f in tex_files)
                p_morx = any(f"{p_prefix}_MORX" in f for f in tex_files)
                p_more = any(f"{p_prefix}_MORE" in f for f in tex_files)
                multi_parts.append({
                    "part": p,
                    "cross_prefix": cross_prefix,  # e.g. "tex_mo553_002"
                    "mesh_prefixes": cross_mesh_prefixes.get(cross_prefix, []),
                    "base_type": "AAAT" if p_aaat else "AAAX",
                    "mr_type": "MROE" if p_mroe else ("MROX" if p_mrox else ("MORX" if p_morx else "MORE")),
                    "has_alpha": p_aaat,
                    "has_emissive": p_mroe,
                })

    # Build split_exports: only for mo553 (odin+sleipnir multi-character models)
    split_exports = []
    if cross_mesh_prefixes and WEAPON_ID == "553":
        for cross_pfx, mesh_pfxs in cross_mesh_prefixes.items():
            # Extract the cross skin id from cross_prefix (e.g. "tex_mo553_002" -> "002")
            m = _re.match(rf"{_re.escape(tex_prefix_str)}{_re.escape(asset_prefix)}\d+_(\d+)", cross_pfx)
            if m:
                cross_mid = m.group(1)
                cross_output_prefix = f"{asset_prefix}{WEAPON_ID}_{cross_mid}"
                cross_parts_list = [p for p in multi_parts if p.get("cross_prefix") == cross_pfx]
                split_exports.append({
                    "output_prefix": cross_output_prefix,
                    "mesh_prefixes": mesh_pfxs,
                    "parts": cross_parts_list,
                })

    return {
        "mid": mid,
        "prefix": prefix,
        "tex_prefix": tex_prefix_str,  # "tex_" or "stat_"
        "tex_lookup_prefix": tex_lookup_prefix,  # usually same as prefix, or adopted cross-skin prefix
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
        "split_exports": split_exports,  # [] or list of {output_prefix, mesh_prefixes, parts}
    }


# ============================================================
# Step 1: Texture processing (normal map swizzle only)
# ============================================================
def process_textures(cfg):
    tex_lp = cfg.get("tex_lookup_prefix", cfg["prefix"])
    prefix = tex_lp[0] if isinstance(tex_lp, tuple) else tex_lp
    tex_dir = cfg["tex_dir"]
    tp = cfg.get("tex_prefix", "tex_")
    multi_parts = cfg.get("multi_parts", [])

    # Collect all parts to process: (tex_prefix_to_use, part_suffix)
    tex_lp = cfg.get("tex_lookup_prefix", prefix)
    part_specs = []
    if multi_parts:
        for p in multi_parts:
            cross_pfx = p.get("cross_prefix", "")
            tpart = f"_{p['part']}" if p['part'] else ""
            if cross_pfx:
                part_specs.append((cross_pfx, tpart))
            else:
                part_specs.append((f"{tp}{tex_lp}", tpart))
    else:
        part_specs = [(f"{tp}{tex_lp}", cfg.get("tex_part", ""))]

    mat_dir = os.path.join(cfg["model_dir"], "materials")
    for pfx, tpart in part_specs:
        nnnx_path = os.path.join(tex_dir, f"{pfx}{tpart}_NNNX.png")
        fixed_path = os.path.join(tex_dir, f"{pfx}{tpart}_NNNX_fixed.png")
        if not os.path.isfile(nnnx_path):
            # Fallback to materials dir
            nnnx_path = os.path.join(mat_dir, f"{pfx}{tpart}_NNNX.png")
            fixed_path = os.path.join(mat_dir, f"{pfx}{tpart}_NNNX_fixed.png")
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
    tex_lp = cfg.get("tex_lookup_prefix", prefix)
    # tex_lp may be a tuple (base_prefix, mr_prefix) for mixed-source models
    if isinstance(tex_lp, tuple):
        base_lp, mr_lp = tex_lp
    else:
        base_lp = mr_lp = tex_lp
    tpart = cfg.get("tex_part", "")
    base_tex = f"{tp}{base_lp}{tpart}_{cfg['base_type']}.png"
    mr_tex = f"{tp}{mr_lp}{tpart}_{cfg['mr_type']}.png"
    normal_tex = f"{tp}{base_lp}{tpart}_NNNX_fixed.png"
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
    if base_path and os.path.isfile(base_path):
        n_base = nodes.new("ShaderNodeTexImage"); n_base.location=(-600,300)
        n_base.image = bpy.data.images.load(base_path)
        n_base.image.colorspace_settings.name = "sRGB"
        links.new(n_base.outputs["Color"], bsdf.inputs["Base Color"])
        if has_alpha:
            links.new(n_base.outputs["Alpha"], bsdf.inputs["Alpha"])
            mat.surface_render_method = 'DITHERED'
            mat.use_backface_culling = False
    else:
        bsdf.inputs["Base Color"].default_value = (0.8, 0.8, 0.8, 1.0)
    if mr_path and os.path.isfile(mr_path):
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
        mat_names = {}       # {part: var_name} for main skin
        cross_mat_names = {} # {mesh_prefix: {part: var_name}} for cross-skin
        for p in multi_parts:
            part = p["part"]
            cross_pfx = p.get("cross_prefix", "")
            mesh_prefixes = p.get("mesh_prefixes", [])
            part_suffix = f"_{part}" if part else ""

            if cross_pfx:
                # Cross-skin texture: use cross_prefix for file lookup
                tex_file_pfx = cross_pfx
                var_tag = f"x_{part or 'default'}"
                mat_name = f"mat_{cross_pfx.replace('tex_', '')}{part_suffix}"
            else:
                tex_file_pfx = f"{tp}{base_lp}"
                var_tag = part or "default"
                mat_name = f"mat_{prefix}{part_suffix}"

            b_tex = os.path.join(tex_dir, f"{tex_file_pfx}{part_suffix}_{p['base_type']}.png")
            if not cross_pfx and base_lp != mr_lp:
                m_tex = os.path.join(tex_dir, f"{tp}{mr_lp}{part_suffix}_{p['mr_type']}.png")
            else:
                m_tex = os.path.join(tex_dir, f"{tex_file_pfx}{part_suffix}_{p['mr_type']}.png")
            n_tex = os.path.join(tex_dir, f"{tex_file_pfx}{part_suffix}_NNNX_fixed.png")
            # Fallback to materials dir for base/MR/NNNX
            mat_dir = os.path.normpath(os.path.join(cfg["model_dir"], "materials"))
            if not os.path.isfile(b_tex):
                b_alt = os.path.join(mat_dir, f"{tex_file_pfx}{part_suffix}_{p['base_type']}.png")
                if os.path.isfile(b_alt):
                    b_tex = b_alt
                else:
                    b_tex = ""
            if not os.path.isfile(m_tex):
                m_alt = os.path.join(mat_dir, f"{tex_file_pfx}{part_suffix}_{p['mr_type']}.png")
                if os.path.isfile(m_alt):
                    m_tex = m_alt
                else:
                    m_tex = ""
            # Fallback to materials dir for NNNX
            if not os.path.isfile(n_tex):
                n_tex_alt = os.path.join(mat_dir, f"{tex_file_pfx}{part_suffix}_NNNX_fixed.png")
                if os.path.isfile(n_tex_alt):
                    n_tex = n_tex_alt
                else:
                    n_tex = ""  # No normal map for this part
            mat_lines.append(f'mat_{var_tag} = _make_mat("{mat_name}", r"{b_tex}", r"{m_tex}", r"{n_tex}", {p["has_alpha"]}, {p["has_emissive"]})')

            if cross_pfx:
                for mp in mesh_prefixes:
                    cross_mat_names.setdefault(mp, {})[part] = f"mat_{var_tag}"
            else:
                mat_names[part] = f"mat_{var_tag}"

        material_cmd = "\n".join(mat_lines)

        # Assignment: fuzzy match part name to mesh name, with cross-skin prefix routing
        assign_lines = ["_part_mats = {"]
        for part, var in mat_names.items():
            assign_lines.append(f'    "{part}": {var},')
        # Add cross-skin mesh prefix routing
        if cross_mat_names:
            assign_lines.append("}")
            assign_lines.append("_cross_mats = {")
            for mp, parts_dict in cross_mat_names.items():
                inner = ", ".join(f'"{p}": {v}' for p, v in parts_dict.items())
                assign_lines.append(f'    "{mp}": {{{inner}}},')
            assign_lines.append("}")
        else:
            assign_lines.append("}")
            assign_lines.append("_cross_mats = {}")
        assign_lines.append("""
import re as _re2

def _normalize(s):
    return _re2.sub(r'[_\\s]', '', s).lower()

def _match_part_to_mesh(part_key, mesh_name):
    if not part_key:
        return False
    pk = _normalize(part_key)
    mn = _normalize(mesh_name)
    if pk in mn:
        return True
    mesh_base = _re2.sub(r'(geo|bf|backface|lod\\d+|\\d+)$', '', mn).strip('_')
    mesh_base = _normalize(mesh_base)
    if mesh_base and mesh_base in pk:
        return True
    if mesh_base and pk.startswith(mesh_base):
        return True
    if len(pk) >= 3 and pk in mesh_base:
        return True
    return False

_mesh_to_part = {"eyelash": "hair", "inmouth": "head"}

def _best_match(obj_name, part_mats):
    mn = _normalize(obj_name)
    mesh_base = _re2.sub(r'(geo|bf|backface|lod\\d+|\\d+)$', '', mn).strip('_')
    mesh_base = _normalize(mesh_base) if mesh_base else mn
    # Explicit mesh->part mapping (e.g. eyelash->hair, inmouth->head)
    if mesh_base in _mesh_to_part:
        mapped = _mesh_to_part[mesh_base]
        if mapped in part_mats:
            return part_mats[mapped]
    best = None
    best_score = 999
    for pk, pm in part_mats.items():
        if _match_part_to_mesh(pk, obj_name):
            score = abs(len(_normalize(pk)) - len(mesh_base))
            if score < best_score:
                best_score = score
                best = pm
    return best

for obj in bpy.data.objects:
    if obj.type == "MESH":
        # Cross-skin routing: check if mesh name starts with a cross-skin prefix
        mesh_lower = obj.name.lower()
        routed_mats = None
        for cpfx, cmats in _cross_mats.items():
            if mesh_lower.startswith(cpfx.lower()):
                routed_mats = cmats
                break
        if routed_mats:
            assigned = _best_match(obj.name, routed_mats)
            if assigned is None:
                assigned = list(routed_mats.values())[0]
        else:
            assigned = _best_match(obj.name, _part_mats)
            if assigned is None:
                for slot in obj.data.materials:
                    if slot:
                        assigned = _best_match(slot.name, _part_mats)
                        if assigned:
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

    # Split export logic: if split_exports, export each group separately
    split_exports = cfg.get("split_exports", [])
    if split_exports:
        # Collect cross-skin mesh prefixes
        cross_prefixes_all = set()
        for se in split_exports:
            cross_prefixes_all.update(se["mesh_prefixes"])
        cross_prefixes_lower = [p.lower() for p in cross_prefixes_all]

        split_lines = []
        # First: export main (non-cross meshes)
        split_lines.append(f'# --- Split export: main ({prefix}) ---')
        split_lines.append(f'_cross_prefixes = {cross_prefixes_lower}')
        split_lines.append('''
_all_meshes = [o for o in bpy.data.objects if o.type == "MESH"]
# Hide cross-skin meshes, export main
for obj in _all_meshes:
    obj.hide_set(obj.name.split("_")[0].lower() in _cross_prefixes)
    obj.hide_render = obj.hide_get()
''')
        split_lines.append(f'bpy.ops.export_scene.gltf(filepath=r"{remote_glb}", export_format="GLB", export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO", use_visible=True)')
        split_lines.append(f'print("GLB exported: {prefix}.glb")')

        # Then: for each cross-skin group, hide everything except those meshes
        for se in split_exports:
            se_prefix = se["output_prefix"]
            se_mesh_pfxs = [p.lower() for p in se["mesh_prefixes"]]
            se_glb = os.path.normpath(os.path.join(OUTPUT_UNC, f"{se_prefix}.glb"))
            split_lines.append(f'\n# --- Split export: {se_prefix} ---')
            split_lines.append(f'_se_prefixes = {se_mesh_pfxs}')
            split_lines.append('''
for obj in _all_meshes:
    obj.hide_set(obj.name.split("_")[0].lower() not in _se_prefixes)
    obj.hide_render = obj.hide_get()
''')
            split_lines.append(f'bpy.ops.export_scene.gltf(filepath=r"{se_glb}", export_format="GLB", export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO", use_visible=True)')
            split_lines.append(f'print("GLB exported: {se_prefix}.glb")')

        # Restore visibility
        split_lines.append('''
for obj in _all_meshes:
    obj.hide_set(False)
    obj.hide_render = False
''')
        split_export_cmd = "\n".join(split_lines)
    else:
        split_export_cmd = f'''bpy.ops.export_scene.gltf(filepath=r"{remote_glb}", export_format="GLB", export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO")
print("GLB exported: {prefix}.glb")'''

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

# Remove duplicate overlapping meshes (e.g. body_01/body_02/body_03 with same vert count)
import re as _re
_mesh_groups = {{}}
for obj in list(bpy.data.objects):
    if obj.type == "MESH":
        base_name = _re.sub(r'_?\\d{{2,3}}(_)', r'\\1', obj.name, count=1)
        key = (base_name, len(obj.data.vertices))
        if key not in _mesh_groups:
            _mesh_groups[key] = []
        _mesh_groups[key].append(obj)
for key, objs in _mesh_groups.items():
    if len(objs) > 1:
        for dup in objs[1:]:
            bpy.data.objects.remove(dup, do_unlink=True)

# Create materials
{material_cmd}

# Assign materials
{assign_cmd}

# Export GLB
{split_export_cmd}
'''
    return script


def export_glb(cfg):
    mid = cfg["mid"]
    script_path = os.path.join(tempfile.gettempdir(), f"_export_{mid}.py")

    with open(script_path, "w", encoding="utf-8") as f:
        f.write(generate_blender_script(cfg))

    result = subprocess.run(
        [BLENDER, "--background", "--python", script_path],
        capture_output=True, text=True, timeout=180,
        encoding="utf-8", errors="replace"
    )
    stdout = result.stdout or ""
    if "GLB exported" in stdout:
        # Count how many GLBs were exported
        exports = [l for l in stdout.splitlines() if "GLB exported" in l]
        for e in exports:
            print(f"[{mid}] {e.strip()}")
    else:
        print(f"[{mid}] GLB export FAILED")
        print((result.stderr or stdout)[-500:])
    os.remove(script_path)


# ============================================================
# Step 3: Local Blender render
# ============================================================
def render_glb(cfg):
    # Render main GLB
    prefixes_to_render = [cfg["prefix"]]
    # Also render split exports
    for se in cfg.get("split_exports", []):
        prefixes_to_render.append(se["output_prefix"])

    for pfx in prefixes_to_render:
        glb_path = os.path.normpath(os.path.join(OUTPUT_UNC, f"{pfx}.glb"))
        png_path = os.path.normpath(os.path.join(OUTPUT_UNC, f"{pfx}.png"))

        if not os.path.isfile(glb_path):
            print(f"[{pfx}] GLB not found, skip render")
            continue

        result = subprocess.run(
            [BLENDER, "--background", "--python", RENDER_SCRIPT,
             "--", glb_path, png_path, "512"],
            capture_output=True, text=True, timeout=180,
            encoding="utf-8", errors="replace"
        )
        if os.path.isfile(png_path):
            print(f"[{pfx}] Rendered")
        else:
            print(f"[{pfx}] Render FAILED")
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
