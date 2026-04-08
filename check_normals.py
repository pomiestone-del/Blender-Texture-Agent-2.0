import bpy

bpy.ops.wm.open_mainfile(filepath=r"C:\Users\Administrator\Documents\sample\we001_001_textured.blend")

for obj in bpy.data.objects:
    if obj.type == 'MESH':
        mesh = obj.data
        print(f"Object: {obj.name}")
        print(f"  has_custom_normals: {mesh.has_custom_normals}")
        print(f"  use_auto_smooth: {hasattr(mesh, 'use_auto_smooth')}")
        print(f"  vertices: {len(mesh.vertices)}, polygons: {len(mesh.polygons)}, loops: {len(mesh.loops)}")
