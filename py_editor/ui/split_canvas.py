import os

# Base paths
ui_dir = r"c:\Users\AnonM\Desktop\NodeCanvas\py_editor\ui"
canvas_path = os.path.join(ui_dir, "canvas.py")

with open(canvas_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Find break points accurately
def find_line(pattern):
    for i, line in enumerate(lines):
        if line.startswith(pattern):
            return i
    return -1

node_start = find_line("class NodeItem(")
composite_start = find_line("class CompositePinRow(")
connection_start = find_line("class ConnectionItem(")
editor_start = find_line("class LogicEditor(")

if -1 in (node_start, composite_start, connection_start, editor_start):
    print("Error finding exact split markers!")
    exit(1)

imports_block = "".join(lines[:node_start])
node_block = "".join(lines[node_start:composite_start])
composite_block = "".join(lines[composite_start:connection_start])
connection_block = "".join(lines[connection_start:editor_start])
editor_block = "".join(lines[editor_start:])

# 1. Update node_item.py with caching
node_block_lines = node_block.split('\n')
for i, line in enumerate(node_block_lines):
    if "super().__init__()" in line:
        node_block_lines.insert(i+1, "        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)")
        break
node_item_code = imports_block + "\n" + "\n".join(node_block_lines)

# 2. Write composite_pins.py
composite_code = imports_block + "\n" + composite_block

# 3. Write connection_item.py
connection_code = imports_block + "\n" + connection_block

# 4. Re-assemble canvas.py with LogicEditor + Cache Flags
editor_block_lines = editor_block.split('\n')
for i, line in enumerate(editor_block_lines):
    if "self.setRenderHint(QPainter.RenderHint.Antialiasing)" in line:
        editor_block_lines.insert(i+1, "        self.setCacheMode(QGraphicsView.CacheModeFlag.CacheBackground)")
        editor_block_lines.insert(i+2, "        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)")
        break

new_canvas_code = imports_block + "\n" + \
"from py_editor.ui.node_item import NodeItem\n" + \
"from py_editor.ui.composite_pins import CompositePinRow, CompositePinSection\n" + \
"from py_editor.ui.connection_item import ConnectionItem\n\n" + \
"\n".join(editor_block_lines)


# Execute writes
with open(os.path.join(ui_dir, "node_item.py"), "w", encoding="utf-8") as f:
    f.write(node_item_code)

with open(os.path.join(ui_dir, "composite_pins.py"), "w", encoding="utf-8") as f:
    f.write(composite_code)

with open(os.path.join(ui_dir, "connection_item.py"), "w", encoding="utf-8") as f:
    f.write(connection_code)

with open(canvas_path, "w", encoding="utf-8") as f:
    f.write(new_canvas_code)

print("Split and Cached successfully!")
