from PIL import Image
import numpy as np

src = r"\\172.16.8.156\art-data-intern\FF7EC\model\weapon\001\model\001\materials\tex_we001_001_NNNX.png"
dst = r"\\172.16.8.156\art-data-intern\FF7EC\model\weapon\001\model\001\materials\tex_we001_001_NNNX.png"

img = np.array(Image.open(src))

# Current swizzle in shader: R->Z, G->X, B->Y
# So to bake it: new_R = old_G, new_G = old_B, new_B = old_R
r, g, b = img[:,:,0].copy(), img[:,:,1].copy(), img[:,:,2].copy()

img[:,:,0] = g  # new R = old G
img[:,:,1] = b  # new G = old B
img[:,:,2] = r  # new B = old R

# Preserve alpha if exists
out = Image.fromarray(img)
out.save(dst)
print(f"Converted and saved to: {dst}")
