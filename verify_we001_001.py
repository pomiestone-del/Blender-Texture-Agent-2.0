import bpy, json

bpy.ops.wm.open_mainfile(filepath=r"C:\Users\Administrator\Documents\sample\we001_001_textured.blend")

for mat in bpy.data.materials:
    if not mat.use_nodes:
        continue
    print(f"\n=== Material: {mat.name} ===")
    print("Nodes:")
    for n in mat.node_tree.nodes:
        extra = ""
        if n.type == 'TEX_IMAGE' and n.image:
            extra = f" | image={n.image.name} colorspace={n.image.colorspace_settings.name}"
        elif n.type == 'MIX':
            extra = f" | blend_type={n.blend_type}"
        print(f"  {n.name} ({n.type}){extra}")
    print("Links:")
    for l in mat.node_tree.links:
        print(f"  {l.from_node.name}[{l.from_socket.name}] -> {l.to_node.name}[{l.to_socket.name}]")

print("\nObjects:")
for o in bpy.data.objects:
    mats = [m.name for m in o.data.materials] if hasattr(o, 'data') and hasattr(o.data, 'materials') else []
    print(f"  {o.name} (type={o.type}) materials={mats}")
