import sys
import re

file_path = r"C:\Users\AnonM\Desktop\NodeCanvas\py_editor\ui\canvas.py"
with open(file_path, "r", encoding="utf-8") as f:
    code = f.read()

# Fix 1: Backspace KeyPress bug
old_key_press = """        # Delete key removes selected nodes
        if event.key() == Qt.Key.Key_Delete or event.key() == Qt.Key.Key_Backspace:
            self.delete_selected()
            event.accept()
            return"""

new_key_press = """        # Delete key removes selected nodes
        if event.key() == Qt.Key.Key_Delete or event.key() == Qt.Key.Key_Backspace:
            focus_item = self.scene().focusItem()
            if focus_item and hasattr(focus_item, 'widget'):
                super().keyPressEvent(event)
                return
            self.delete_selected()
            event.accept()
            return"""
code = code.replace(old_key_press, new_key_press)


# Fix 2: Add QRectF import
import_line = "from PyQt6.QtCore import Qt, QPointF, QTimer, pyqtSignal, QObject"
new_import_line = "from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer, pyqtSignal, QObject"
code = code.replace(import_line, new_import_line)


# Fix 3: NodeItem.__init__
old_init = """    def __init__(self, id_, title="Node", canvas=None):
        super().__init__(-120, -48, 240, 96)
        self.id = id_
        gradient = QLinearGradient(-120, -48, 120, 48)
        gradient.setColorAt(0, QColor(28, 33, 43))
        gradient.setColorAt(1, QColor(45, 55, 75))
        self.setBrush(QBrush(gradient))
        self.setPen(QPen(QColor(80, 120, 190), 2))
            # Revert to simple styling"""

new_init = """    def __init__(self, id_, title="Node", canvas=None):
        super().__init__(-120, -48, 240, 96)
        self.id = id_
        self.setPen(Qt.PenStyle.NoPen)
        self.setBrush(Qt.BrushStyle.NoBrush)
        self.is_compact = False
        self.header_color = QColor(40, 45, 55)
        self.node_width = 240
        self.node_height = 96
            # Revert to simple styling"""
code = code.replace(old_init, new_init)


# Fix 4: setup_pins logic replacement
old_setup = """        # center pins vertically around the node midline so they don't overlap the title
        spacing = 20
        if input_defs:
            start_input = -((len(input_defs) - 1) * spacing) / 2
        else:
            start_input = 0
        if output_defs:
            start_output = -((len(output_defs) - 1) * spacing) / 2
        else:
            start_output = 0

        for idx, name in enumerate(input_defs):
            y = start_input + idx * spacing"""

new_setup = """        has_exec = False
        for p_dict in [self.inputs, self.outputs]:
            for p_name, p_val in p_dict.items():
                p_type = p_val if isinstance(p_val, str) else p_val.get('type')
                if p_type == 'exec':
                    has_exec = True

        self.is_compact = not has_exec
        self.node_width = 160 if self.is_compact else 240
        spacing = 20 if self.is_compact else 24
        header_height = 0 if self.is_compact else 26
        
        max_pins = max(len(input_defs), len(output_defs))
        self.node_height = max(32 if self.is_compact else 64, header_height + (max_pins * spacing) + 16)
        self.setRect(-self.node_width/2, -self.node_height/2, self.node_width, self.node_height)

        # Update title position and style
        if self.is_compact:
            self.title.setFont(QFont("Segoe UI Semibold", 8))
            self.title.setPos(-self.node_width/2 + 8, -self.node_height/2 + 2)
            self.title.setDefaultTextColor(QColor(180, 180, 180))
        else:
            self.title.setFont(QFont("Segoe UI Semibold", 10))
            self.title.setPos(-self.node_width/2 + 8, -self.node_height/2 + 1)
            self.title.setDefaultTextColor(QColor(255, 255, 255))

        y_offset = -self.node_height/2 + header_height + 14

        for idx, name in enumerate(input_defs):
            y = y_offset + idx * spacing"""
code = code.replace(old_setup, new_setup)


# Update hardcoded pin positions
code = code.replace("QPointF(-132, y - 6)", "QPointF(-self.node_width/2 - 12, y - 6)")
code = code.replace("QPointF(-120, y)", "QPointF(-self.node_width/2, y)")
code = code.replace("QPointF(-132, y + 6)", "QPointF(-self.node_width/2 - 12, y + 6)")
code = code.replace("QGraphicsEllipseItem(-132, y - 6, 12, 12", "QGraphicsEllipseItem(-self.node_width/2 - 12, y - 6, 12, 12")
code = code.replace("label.setPos(-112, y - 6)", "label.setPos(-self.node_width/2 + 8, y - 6)")

code = code.replace("QPointF(120, y - 6)", "QPointF(self.node_width/2, y - 6)")
code = code.replace("QPointF(132, y)", "QPointF(self.node_width/2 + 12, y)")
code = code.replace("QPointF(120, y + 6)", "QPointF(self.node_width/2, y + 6)")
code = code.replace("QGraphicsEllipseItem(120, y - 6, 12, 12", "QGraphicsEllipseItem(self.node_width/2, y - 6, 12, 12")
code = code.replace("label.setPos(136, y - 6)", "label.setPos(self.node_width/2 + 16, y - 6)")

code = code.replace("start_output + idx * spacing", "y_offset + idx * spacing")


# Fix 5: Inject Paint Override into NodeItem
paint_func = """
    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()

        # 1. Shadow
        painter.setPen(Qt.PenStyle.NoPen)
        shadow_rect = rect.translated(2, 4)
        painter.setBrush(QColor(0, 0, 0, 80))
        painter.drawRoundedRect(shadow_rect, 6, 6)

        # 2. Main Body Gradient
        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0, QColor(28, 33, 43, 230))
        grad.setColorAt(1, QColor(20, 24, 32, 230))
        painter.setBrush(QBrush(grad))
        
        # 3. Border Color
        if self.isSelected():
            painter.setPen(QPen(QColor(255, 200, 50, 240), 2))
        elif self.has_error:
            painter.setPen(QPen(QColor(220, 50, 50), 2))
        elif self.execution_state == "executing":
            painter.setPen(QPen(QColor(255, 200, 50), 2))
        elif self.execution_state == "completed":
            painter.setPen(QPen(QColor(50, 220, 120), 2))
        else:
            painter.setPen(QPen(QColor(45, 55, 65, 255), 1))
            
        painter.drawRoundedRect(rect, 6, 6)
        
        # 4. Header Bar (if not compact)
        if not self.is_compact:
            header_rect = QRectF(rect.x(), rect.y(), rect.width(), 26)
            header_path = QPainterPath()
            header_path.setFillRule(Qt.FillRule.WindingFill)
            header_path.addRoundedRect(header_rect, 6, 6)
            bottom_rect = QRectF(rect.x(), rect.y() + 13, rect.width(), 13)
            header_path.addRect(bottom_rect)
            
            painter.setPen(Qt.PenStyle.NoPen)
            # Use specific header color from brushes
            if hasattr(self, 'header_color'):
                h_grad = QLinearGradient(header_rect.topLeft(), header_rect.bottomLeft())
                h_grad.setColorAt(0, self.header_color.lighter(110))
                h_grad.setColorAt(1, self.header_color)
                painter.setBrush(h_grad)
                painter.drawPath(header_path.simplified())

    def itemChange(self, change, value):"""

code = code.replace("    def itemChange(self, change, value):", paint_func)

# Fix 6: Colors based on category
old_brush = "node.setBrush(QBrush(QColor(\"#6B5B95\")))"
old_brush_2 = "node.setBrush(QBrush(gradient))"
old_brush_3 = "node.setBrush(QBrush(QColor(\"#7E57C2\")))"

code = code.replace(old_brush, "node.header_color = QColor(\"#6B5B95\")")
code = code.replace(old_brush_2, "node.header_color = color1")
code = code.replace(old_brush_3, "node.header_color = QColor(\"#7E57C2\")")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(code)

print("UI Replaced cleanly!")
