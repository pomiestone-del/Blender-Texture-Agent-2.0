---
name: weapon-texture-pipeline
description: Process FF7EC weapon models (OBJ/FBX) with PBR textures (AAAX/MROX/NNNX) into GLB + rendered preview PNG. Handles normal map swizzle, AO baking, and glTF-compatible material setup.
argument-hint: <model_dir> [output_dir]
---

# Weapon Model Texture Pipeline

Process weapon models from `$0`, output GLB + PNG to `$1` (default: network drive output folder).

## Input

Model directory containing:
- `body_geo.obj` or subdirectory with `.fbx` (FBX preferred if available)
- `materials/` with PBR textures:
  - `tex_*_AAAX.png` — Albedo (sRGB)
  - `tex_*_MROX.png` — R=Metallic, G=Roughness, B=Occlusion (sRGB)
  - `tex_*_NNNX.png` — Normal map (pink, non-standard channels)
- Optional: `ditherTexture_int.png`, `tex_pb_chara_int.png` (engine-specific, ignore)

## Pipeline (3 steps)

### Step 1: Texture Processing (Python PIL/numpy)

**Normal map** (pink → purple):
- Original: R=Z(~255), G=X(~128), B=Y(~128) — non-standard channel layout
- Sample Blender wiring: Separate Color → R→Z, G→X, B→Y via Combine XYZ → Normal Map
- Bake swizzle into pixels: `newR=oldG(X), newG=oldB(Y), newB=oldR(Z)` → standard purple (B dominant)
- Save as `*_NNNX_fixed.png`

**MROX**: No conversion needed. glTF exporter auto-handles channel remapping and sRGB→Linear when it sees `Separate Color → R→Metallic, G→Roughness` connected to Principled BSDF.

**AO**: Dropped. Not baked into BaseColor, not exported as occlusionTexture. Keeps output brighter and simpler.

### Step 2: GLB Export (Blender 4.5)

Material node setup matching sample wiring:
- `AAAX.png` (sRGB) → Base Color (direct, no AO)
- `MROX.png` (sRGB) → Separate Color → Red→Metallic, Green→Roughness
- `NNNX_fixed.png` (Non-Color) → Normal Map → Normal

glTF exporter auto-handles:
- MROX channel repack (R=Metallic,G=Roughness → glTF B=Metallic,G=Roughness)
- sRGB→Linear conversion for metallicRoughness texture

### Step 3: Render (Blender 4.5 + blender_render_preview.py)

Uses official `blender_render_preview.py` render script:
- Cycles GPU, 64 samples, max_bounces=2
- Camera: rotation (1.047, 0, -0.707), auto-fit to model
- Sun light: energy=2, angle=0.942
- World: gray (0.5, 0.5, 0.5)
- Transparent background, 512×512 PNG

## Output

Network drive `\\172.16.8.156\art-data-intern\FF7EC\output\weapon\`:
```
we001_001.glb + we001_001.png
we001_002.glb + we001_002.png
...
```

## Key Decisions

1. **No ORM conversion**: glTF exporter recognizes Separate Color → Metallic/Roughness pattern and auto-converts
2. **No AO**: dropped entirely — keeps output clean and avoids color space issues with baking
3. **Normal swizzle baked**: eliminates Separate Color + Combine XYZ nodes; direct connection to Normal Map node
4. **Blender 4.5**: better compatibility with official render script than 5.1
5. **Official render script**: `blender_render_preview.py` — same as public render API, consistent results

## Script

`pipeline_weapon.py` — single script handles everything:
```bash
python pipeline_weapon.py
```
