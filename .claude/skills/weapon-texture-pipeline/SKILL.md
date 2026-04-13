---
name: weapon-texture-pipeline
description: Process FF7EC weapon models (OBJ/FBX) with PBR textures (AAAX/AAAT/MROX/MROE/NNNX) into GLB + rendered preview PNG. Auto-detects model structure and texture variants.
argument-hint: <WEAPON_ID>
---

# Weapon Model Texture Pipeline

Process all models under `\\172.16.8.156\art-data-intern\FF7EC\model\weapon\{WEAPON_ID}\model`, output GLB + PNG to `\\172.16.8.156\art-data-intern\FF7EC\output\weapon`.

Change `WEAPON_ID` in `pipeline_weapon.py` to switch weapon category (001, 002, 003...).

## Input

Each model subdirectory contains:
- One or more `.obj` files, or a `skin_*` subdirectory with `.fbx` (FBX preferred for bone data)
- `materials/` with PBR textures:
  - `tex_weXXX_YYY_AAAX.png` or `_AAAT.png` — Albedo (AAAT has alpha transparency)
  - `tex_weXXX_YYY_MROX.png` or `_MROE.png` — R=Metallic, G=Roughness, B=Occlusion (MROE has A=Emissive)
  - `tex_weXXX_YYY_NNNX.png` — Normal map (pink, non-standard channels)
- Optional (ignored): `ditherTexture_int.png`, `tex_pb_chara_int.png`, `*_ramp.png`

## Auto-Detection

Script auto-detects per model:
- **Import method**: FBX (with custom normals + automatic bone orientation) or OBJ (all .obj files imported)
- **Base texture**: AAAT (alpha connected to Principled BSDF Alpha) or AAAX (standard)
- **MR texture**: MROE (Emission Strength set to 0, data near-zero) or MROX (standard)

## Pipeline (3 steps)

### Step 1: Texture Processing (Python PIL/numpy)

Only the normal map needs conversion:
- Original pink: R=Z(~255), G=X(~128), B=Y(~128) — non-standard channel layout
- Swizzle: `newR=oldG(X), newG=oldB(Y), newB=oldR(Z)` → standard purple (B dominant)
- Saved as `*_NNNX_fixed.png` alongside original

**No other texture conversion needed:**
- MROX/MROE: glTF exporter auto-handles channel remapping and sRGB→Linear when it sees `Separate Color → R→Metallic, G→Roughness`
- AAAX/AAAT: used directly as Base Color (no AO baking)

### Step 2: GLB Export (Blender 4.5)

Material node setup:
- `AAAX/AAAT` (sRGB) → Base Color (+ Alpha if AAAT)
- `MROX/MROE` (sRGB) → Separate Color → Red→Metallic, Green→Roughness
- `NNNX_fixed` (Non-Color) → Normal Map → Normal

Export directly to network drive.

### Step 3: Render (Blender 4.5 + blender_render_preview.py)

Official render script from `C:\Users\Administrator\Downloads\blender_render_preview.py`:
- Cycles GPU, 64 samples, max_bounces=2
- Camera: rotation (1.047, 0, -0.707), auto-fit to model
- Sun light: energy=2, angle=0.942
- World: gray (0.5, 0.5, 0.5), transparent background
- 512×512 RGBA PNG

Render directly to network drive.

## Output

`\\172.16.8.156\art-data-intern\FF7EC\output\weapon\`:
```
weXXX_001.glb + weXXX_001.png
weXXX_002.glb + weXXX_002.png
...
```

## Usage

**必须按顺序执行，先扫描再处理：**

### Step 0: 扫描文件结构（每次处理新文件夹前必须执行）

在执行 pipeline 之前，先扫描目标文件夹的所有模型目录，检查：
1. 每个模型的文件结构（OBJ/FBX、贴图类型、多 OBJ 等）
2. 是否有未见过的文件类型或缺失的必需贴图
3. 汇总异常情况，报告给用户确认后再执行

如果发现新的贴图类型或异常文件结构，**必须先告知用户并给出分析和解决方案**，得到确认后才能执行处理。

### Step 1-3: 执行 pipeline

```bash
# Edit WEAPON_ID in pipeline_weapon.py, then:
python pipeline_weapon.py
```

## Key Decisions

1. **No ORM conversion**: glTF exporter recognizes `Separate Color → Metallic/Roughness` and auto-converts
2. **No AO baking**: AAAX used directly as Base Color, keeps output clean
3. **Normal swizzle baked**: pink→purple, eliminates Separate Color + Combine XYZ nodes
4. **Blender 4.5**: official render script compatible (5.1 has World node issues)
5. **Direct network write**: GLB and PNG written directly to network drive
6. **Multi-OBJ support**: all .obj files in a model directory are imported together
7. **FBX priority**: preserves skeleton + custom normals via `use_custom_normals=True, automatic_bone_orientation=True`

## Known Variants

| Type | Handling |
|------|----------|
| AAAX | Standard albedo, direct to Base Color |
| AAAT | Albedo with alpha, Alpha→Principled BSDF Alpha |
| MROX | Standard M/R/O, R→Metallic G→Roughness |
| MROE | M/R/O/Emissive, Emission Strength=0 (A channel data near-zero) |
| Multi-OBJ | All imported, share one material |
| FBX | Bones + custom normals preserved |

## Script

`pipeline_weapon.py` — single file, handles everything.
