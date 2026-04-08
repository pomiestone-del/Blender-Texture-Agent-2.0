import bpy
import json

# Open the sample file
bpy.ops.wm.open_mainfile(filepath=r"C:\Users\Administrator\Documents\sample\we001_039.blend")

result = {}

for mat in bpy.data.materials:
    if not mat.use_nodes:
        continue
    mat_info = {"nodes": [], "links": []}
    for node in mat.node_tree.nodes:
        node_data = {
            "name": node.name,
            "type": node.type,
            "label": node.label,
            "location": list(node.location),
        }
        # For image texture nodes, record image info
        if node.type == 'TEX_IMAGE' and node.image:
            node_data["image_name"] = node.image.name
            node_data["image_filepath"] = node.image.filepath
            node_data["colorspace"] = node.image.colorspace_settings.name if node.image.colorspace_settings else None
        # For all nodes, record non-default inputs
        if hasattr(node, 'inputs'):
            inputs_info = {}
            for inp in node.inputs:
                if hasattr(inp, 'default_value'):
                    try:
                        val = list(inp.default_value) if hasattr(inp.default_value, '__iter__') else inp.default_value
                        inputs_info[inp.name] = val
                    except:
                        pass
            if inputs_info:
                node_data["inputs"] = inputs_info
        # For Separate/Combine nodes
        if hasattr(node, 'mode'):
            node_data["mode"] = node.mode if isinstance(node.mode, str) else str(node.mode)
        # For math/mix nodes
        if hasattr(node, 'operation'):
            node_data["operation"] = node.operation
        if hasattr(node, 'blend_type'):
            node_data["blend_type"] = node.blend_type

        mat_info["nodes"].append(node_data)

    for link in mat.node_tree.links:
        link_data = {
            "from_node": link.from_node.name,
            "from_socket": link.from_socket.name,
            "to_node": link.to_node.name,
            "to_socket": link.to_socket.name,
        }
        mat_info["links"].append(link_data)

    result[mat.name] = mat_info

# Print as JSON
print("===INSPECT_START===")
print(json.dumps(result, indent=2, default=str))
print("===INSPECT_END===")
