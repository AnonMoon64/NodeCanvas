import re

file_path = r"C:\Users\AnonM\Desktop\NodeCanvas\py_editor\ui\canvas.py"
with open(file_path, "r", encoding="utf-8") as f:
    code = f.read()

# Fix 1: mouseReleaseEvent line ghosting artifact
old_mouse_release = """        if event.button() == Qt.MouseButton.LeftButton:
            if self._is_connecting:
                self._is_connecting = False
                self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)"""

new_mouse_release = """        if event.button() == Qt.MouseButton.LeftButton:
            if self._is_connecting:
                self._cancel_pending_connection()"""

code = code.replace(old_mouse_release, new_mouse_release)

# Fix 2: Compact label alignment
old_input_label = """            label.setDefaultTextColor(QColor(200, 200, 200))
            label.setFont(QFont("Segoe UI", 9))
            label.setPos(-self.node_width/2 + 8, y - 6)
            self.pin_labels.append(label)"""

new_input_label = """            label.setDefaultTextColor(QColor(200, 200, 200))
            label.setFont(QFont("Segoe UI", 9))
            if getattr(self, 'is_compact', False):
                label.setPos(-self.node_width/2 - label.boundingRect().width() - 16, y - 6)
            else:
                label.setPos(-self.node_width/2 + 8, y - 6)
            self.pin_labels.append(label)"""

code = code.replace(old_input_label, new_input_label)


# Fix 3: Widget layout tweaking
old_proxy_pos = """            # Create proxy widget and position it
            proxy = QGraphicsProxyWidget(self)
            proxy.setWidget(widget)
            # Position to the right of the pin label
            proxy.setPos(-50, y_pos - 10)"""

new_proxy_pos = """            # Create proxy widget and position it
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

code = code.replace(old_proxy_pos, new_proxy_pos)


with open(file_path, "w", encoding="utf-8") as f:
    f.write(code)

print("UX Patches Applied")
