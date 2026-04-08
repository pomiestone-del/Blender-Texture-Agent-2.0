import bpy

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=r"C:\Users\Administrator\Documents\sample\we001_001.glb")

print("\n=== Objects ===")
for obj in bpy.data.objects:
    if obj.type == 'MESH':
        mesh = obj.data
        mats = [m.name for m in mesh.materials]
        print(f"  {obj.name} | verts={len(mesh.vertices)} | has_custom_normals={mesh.has_custom_normals} | materials={mats}")

print("\n=== Materials ===")
for mat in bpy.data.materials:
    if not mat.use_nodes:
        continue
    print(f"\n  Material: {mat.name}")
    for node in mat.node_tree.nodes:
        extra = ""
        if node.type == 'TEX_IMAGE' and node.image:
            extra = f" | image={node.image.name} cs={node.image.colorspace_settings.name}"
        print(f"    {node.name} ({node.type}){extra}")
    for link in mat.node_tree.links:
        print(f"    {link.from_node.name}[{link.from_socket.name}] -> {link.to_node.name}[{link.to_socket.name}]")

print("\n=== Images ===")
for img in bpy.data.images:
    print(f"  {img.name} | size={img.size[0]}x{img.size[1]} | packed={img.packed_file is not None}")
