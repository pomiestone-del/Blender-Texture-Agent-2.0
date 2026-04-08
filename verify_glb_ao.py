import bpy
import os

OUTPUT_DIR = r"C:\Users\Administrator\Documents\outputTest"

for mid in ["001", "002", "003"]:
    prefix = f"we001_{mid}"
    glb_path = os.path.join(OUTPUT_DIR, f"{prefix}.glb")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=glb_path)

    print(f"\n{'='*50}")
    print(f"[{mid}] GLB material inspection")
    print(f"{'='*50}")

    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        print(f"\nMaterial: {mat.name}")
        print("Nodes:")
        for node in mat.node_tree.nodes:
            extra = ""
            if node.type == 'TEX_IMAGE' and node.image:
                extra = f" | image={node.image.name} cs={node.image.colorspace_settings.name}"
            elif node.type == 'MIX':
                extra = f" | blend_type={node.blend_type} data_type={node.data_type}"
            print(f"  {node.name} ({node.type}){extra}")
        print("Links:")
        for link in mat.node_tree.links:
            print(f"  {link.from_node.name}[{link.from_socket.name}] -> {link.to_node.name}[{link.to_socket.name}]")
