---
name: weapon-texture-pipeline
description: Import weapon model (OBJ/FBX) with PBR textures (AAAX/MROX/NNNX), connect materials in Blender, convert to glTF-compatible format, export GLB, and render comparison images. Use when processing FF7EC weapon models or similar PBR asset pipelines.
argument-hint: <model_dir> [output_dir]
---

# Weapon Model Texture Pipeline

Process weapon models from `$0` and output to `$1` (default: `C:\Users\Administrator\Documents\outputTest`).

## Input Requirements

The model directory should contain:
- `body_geo.obj` or a subdirectory with `.fbx` file (FBX preferred if available)
- `materials/` folder with PBR textures:
  - `tex_*_AAAX.png` — Albedo/Base Color (sRGB)
  - `tex_*_MROX.png` — Packed texture: R=Metallic, G=Roughness, B=Occlusion (sRGB encoded)
  - `tex_*_NNNX.png` — Normal map (pink, non-standard channel layout)
- Optional engine-specific textures (`ditherTexture_int.png`, `tex_pb_chara_int.png`) can be ignored

## Pipeline Steps

### Step 0: Texture Processing (Python + PIL)

Convert textures before Blender processing:

1. **Normal map swizzle bake** (pink -> blue/purple):
   - Original channels: R=Z, G=X, B=Y (non-standard)
   - Remap: newR=oldG, newG=oldB, newB=oldR
   - Save as `tex_*_NNNX_fixed.png`

2. **MROX -> ORM** (glTF-compatible):
   - Swap R(Metallic) and B(Occlusion) channels
   - Apply sRGB-to-Linear conversion to all channels (critical! original MROX is sRGB-encoded, glTF expects linear values)
   - Save as `tex_*_ORM.png` (Non-Color in Blender)

   ```python
   def srgb_to_linear(c):
       return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
   ```

   **Why linearize?** In the original Blender file, MROX is loaded as sRGB — Blender auto-converts to linear. If we just swap channels and load as Non-Color, the raw sRGB values go straight through without gamma correction, resulting in different Metallic/Roughness values.

3. **Bake AO into BaseColor** for GLB:
   - Load AAAX and MROX.B(AO), both converted to linear space
   - Multiply: BaseColor_linear = AAAX_linear × AO_linear
   - Convert back to sRGB for storage
   - Save as `tex_*_BaseColor.png`

   **Why?** glTF's `occlusionTexture` is supported in spec, but Blender's Principled BSDF has no Occlusion input. The glTF exporter cannot recognize custom Multiply node setups and will silently drop the AO. Baking AO into the BaseColor pixels guarantees it survives export.

### Step 1: Original Wiring -> `*_textured.blend`

Import model and connect textures matching the original sample pattern:

- **Import**: OBJ via `bpy.ops.wm.obj_import()` or FBX via `bpy.ops.import_scene.fbx(use_custom_normals=True, automatic_bone_orientation=True)`
- **Material**: Principled BSDF with Metallic=1.0, Specular IOR Level=1.0
- **Base Color**: AAAX(sRGB) × MROX.B(AO) via Mix(Multiply) node
- **Metallic**: MROX → Separate Color → Red
- **Roughness**: MROX → Separate Color → Green
- **Normal**: NNNX(Non-Color) → Separate Color → swizzle(R→Z, G→X, B→Y) via Combine XYZ → Normal Map → Normal
- **Render** a comparison image (Cycles, 45-degree angle, transparent background)

### Step 2: Processed -> `*_processed.blend`

Simplified version with baked normal map:

- Same as Step 1, but use `NNNX_fixed.png` (blue/purple, standard layout)
- Normal map connects directly to Normal Map node (no Separate Color / Combine XYZ)
- No render needed for this step

### Step 3: GLB Export -> `*.glb`

glTF-compatible material setup:

- **Base Color**: `BaseColor.png` (AAAX×AO baked) direct to Principled BSDF — no Mix nodes
- **ORM**: `ORM.png`(Non-Color) → Separate Color → G=Roughness, B=Metallic
- **Normal**: `NNNX_fixed.png`(Non-Color) → Normal Map → Normal
- Export via `bpy.ops.export_scene.gltf(export_format='GLB')`

### Step 4: GLB Verification Render

- Re-import the GLB into a fresh Blender scene
- Set up identical camera/lighting
- Render comparison image
- Compare with Step 1 render to verify visual consistency

## Render Settings

- Engine: Cycles (GPU if available)
- Samples: 256, Denoising: On
- Resolution: 2560×1440
- Camera: 45-degree angle to the right, 85mm lens
- Lighting: 4 area lights (Key 300, Fill 100, Rim 200, Top 150)
- Background: Transparent (film_transparent=True, RGBA PNG)
- World: Light gray (0.8) at strength 0.5 for environment reflections (does not appear in output due to film_transparent)

## Key Gotchas

1. **sRGB vs Linear**: MROX loaded as sRGB in Blender gets auto-linearized. When creating ORM for glTF, must bake sRGB→Linear into pixels since it loads as Non-Color.
2. **glTF exporter limitations**: Cannot recognize custom node operations (Multiply, Separate+Combine). All connections must be direct Image→Principled BSDF patterns.
3. **AO loss in GLB**: Principled BSDF has no Occlusion input. Must bake AO into BaseColor pixels before export.
4. **Custom normals**: OBJ import preserves them by default. FBX needs `use_custom_normals=True`.
5. **FBX bone orientation**: Use `automatic_bone_orientation=True` for correct skeleton import.
6. **Dark models**: Deep black metallic models (e.g., Buster Sword) need sufficient environment lighting. With transparent background, World strength should still be >0 for metal reflections.

## Output Files (per model)

| File | Description |
|------|-------------|
| `*_textured.blend` | Original wiring with swizzle nodes |
| `*_processed.blend` | Simplified with baked normal |
| `*.glb` | glTF export with baked BaseColor+AO |
| `*_textured.png` | Render from textured blend |
| `*_glb.png` | Render from re-imported GLB |

## Reference Scripts

- `batch_process.py` — Texture conversion (Python + PIL/numpy)
- `batch_blender.py` — Blender pipeline (import, wire, render, export)
- `process_weapon.py` — Single model full pipeline (generates per-step Blender scripts)

## Batch Usage

To process multiple models, modify `MODELS` list in `batch_process.py`, then run `batch_blender.py` per model in parallel:

```bash
python batch_process.py
blender --background --python batch_blender.py -- 001 &
blender --background --python batch_blender.py -- 002 &
blender --background --python batch_blender.py -- 003 &
```
