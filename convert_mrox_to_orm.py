from PIL import Image
import numpy as np

def srgb_to_linear(c):
    """Convert sRGB [0,1] to linear [0,1]"""
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)

tex_dir = r"\\172.16.8.156\art-data-intern\FF7EC\model\weapon\001\model\001\materials"
mrox_path = f"{tex_dir}\\tex_we001_001_MROX.png"
orm_path = f"{tex_dir}\\tex_we001_001_ORM.png"

img = np.array(Image.open(mrox_path)).astype(np.float64) / 255.0

# Current: R=Metallic, G=Roughness, B=Occlusion (sRGB encoded)
# Apply sRGB->Linear conversion (matching what Blender does when colorspace=sRGB)
r = srgb_to_linear(img[:,:,0])  # Metallic
g = srgb_to_linear(img[:,:,1])  # Roughness
b = srgb_to_linear(img[:,:,2])  # Occlusion

# Rearrange to glTF ORM: R=Occlusion, G=Roughness, B=Metallic
out = np.stack([b, g, r], axis=2)
out = np.clip(out * 255.0, 0, 255).astype(np.uint8)

# Handle alpha if present
if img.shape[2] == 4:
    alpha = (img[:,:,3] * 255).astype(np.uint8)
    out = np.dstack([out, alpha])

Image.fromarray(out).save(orm_path)
print(f"ORM texture (linearized) saved: {orm_path}")
