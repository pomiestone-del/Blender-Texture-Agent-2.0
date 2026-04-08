"""
Batch process weapon models 001-003:
  1. Convert textures (normal swizzle bake, MROX->ORM linearize)
  2. Generate Blender script for each model
"""
import os
import numpy as np
from PIL import Image

OUTPUT_DIR = r"C:\Users\Administrator\Documents\outputTest"
BASE_DIR = r"\\172.16.8.156\art-data-intern\FF7EC\model\weapon\001\model"
MODELS = ["001", "002", "003"]

def srgb_to_linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)

for mid in MODELS:
    prefix = f"we001_{mid}"
    tex_dir = os.path.join(BASE_DIR, mid, "materials")

    # Normal map swizzle bake
    nnnx = np.array(Image.open(os.path.join(tex_dir, f"tex_{prefix}_NNNX.png")))
    r, g, b = nnnx[:,:,0].copy(), nnnx[:,:,1].copy(), nnnx[:,:,2].copy()
    nnnx[:,:,0], nnnx[:,:,1], nnnx[:,:,2] = g, b, r
    fixed_path = os.path.join(tex_dir, f"tex_{prefix}_NNNX_fixed.png")
    Image.fromarray(nnnx).save(fixed_path)

    # MROX -> ORM (linearized)
    mrox = np.array(Image.open(os.path.join(tex_dir, f"tex_{prefix}_MROX.png"))).astype(np.float64) / 255.0
    rm, gm, bm = srgb_to_linear(mrox[:,:,0]), srgb_to_linear(mrox[:,:,1]), srgb_to_linear(mrox[:,:,2])
    orm = np.clip(np.stack([bm, gm, rm], axis=2) * 255.0, 0, 255).astype(np.uint8)
    Image.fromarray(orm).save(os.path.join(tex_dir, f"tex_{prefix}_ORM.png"))

    # AAAX * AO -> BaseColor for GLB (bake AO into base color in sRGB space)
    aaax = np.array(Image.open(os.path.join(tex_dir, f"tex_{prefix}_AAAX.png"))).astype(np.float64) / 255.0
    ao = srgb_to_linear(mrox[:,:,2])  # AO is Blue channel of MROX (already loaded as float)
    aaax_linear = np.stack([srgb_to_linear(aaax[:,:,i]) for i in range(3)], axis=2)
    baked = aaax_linear * ao[:,:,np.newaxis]  # multiply in linear space
    # Convert back to sRGB for storage
    baked_srgb = np.where(baked <= 0.0031308, baked * 12.92, 1.055 * np.power(baked, 1.0/2.4) - 0.055)
    baked_srgb = np.clip(baked_srgb * 255.0, 0, 255).astype(np.uint8)
    # Preserve alpha if present
    if aaax.shape[2] == 4:
        alpha = (aaax[:,:,3] * 255).astype(np.uint8)
        baked_srgb = np.dstack([baked_srgb, alpha])
    Image.fromarray(baked_srgb).save(os.path.join(tex_dir, f"tex_{prefix}_BaseColor.png"))

    print(f"[{mid}] Textures processed")

print("\n[Done] All textures converted.")
