import re

file_path = r"C:\Users\AnonM\Desktop\NodeCanvas\py_editor\ui\canvas.py"
with open(file_path, "r", encoding="utf-8") as f:
    code = f.read()

# Fix 1: Compact width to 180 (from 160) to give a bit more room
# It's set in setup_pins: `self.node_width = 160 if self.is_compact else 240`
code = code.replace(
    "self.node_width = 160 if self.is_compact else 240",
    "self.node_width = 180 if self.is_compact else 240"
)

# Fix 2: Restore input label to INSIDE the node
old_input_label = """            label.setDefaultTextColor(QColor(200, 200, 200))
            label.setFont(QFont("Segoe UI", 9))
            if getattr(self, 'is_compact', False):
                label.setPos(-self.node_width/2 - label.boundingRect().width() - 16, y - 6)
            else:
                label.setPos(-self.node_width/2 + 8, y - 6)
            self.pin_labels.append(label)"""

new_input_label = """            label.setDefaultTextColor(QColor(200, 200, 200))
            label.setFont(QFont("Segoe UI", 9))
            label.setPos(-self.node_width/2 + 10, y - 8)
            self.pin_labels.append(label)"""
code = code.replace(old_input_label, new_input_label)


# Fix 3: Restore output label slightly inwards so it rests inside the node nicely on the right
old_output_label = """            label.setDefaultTextColor(QColor(200, 200, 200))
            label.setFont(QFont("Segoe UI", 9))
            label.setPos(self.node_width/2 + 16, y - 6)
            self.pin_labels.append(label)"""

# For output labels, we need to subtract their bounding box width so they right-align inside
new_output_label = """            label.setDefaultTextColor(QColor(200, 200, 200))
            label.setFont(QFont("Segoe UI", 9))
            # Calculate width to right-align
            label_rect = label.boundingRect()
            label.setPos(self.node_width/2 - label_rect.width() - 10, y - 8)
            self.pin_labels.append(label)"""
code = code.replace(old_output_label, new_output_label)


# Fix 4: Restore widget to INSIDE the node
old_proxy_pos = """            # Create proxy widget and position it
            proxy = QGraphicsProxyWidget(self)
            proxy.setWidget(widget)
            # Prevent clipping by dynamically spacing layout
            if getattr(self, 'is_compact', False):
                proxy.setPos(-self.node_width/2 - widget.width() - 16, y_pos - 10)
                # Correct corresponding label
                for lbl in self.pin_labels:
                    if lbl.toPlainText() == pin_name:
                        lbl.setPos(-self.node_width/2 - widget.width() - lbl.boundingRect().width() - 22, y_pos - 6)
            else:
                proxy.setPos(-10, y_pos - 10)  # Pulled right out of the label's typical bounds"""

# We'll put it at x = -20 for compact, -10 for standard.
new_proxy_pos = """            # Create proxy widget and position it
            proxy = QGraphicsProxyWidget(self)
            proxy.setWidget(widget)
            
            # Position safely inside the box
            if getattr(self, 'is_compact', False):
                proxy.setPos(-15, y_pos - 12)
            else:
                proxy.setPos(0, y_pos - 12)"""
code = code.replace(old_proxy_pos, new_proxy_pos)


with open(file_path, "w", encoding="utf-8") as f:
    f.write(code)

print("Layout Refactored")
