from PyQt6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsEllipseItem,
    QGraphicsPathItem,
    QGraphicsTextItem,
    QGraphicsProxyWidget,
    QGraphicsPolygonItem,
    QMenu,
    QMessageBox,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QLineEdit,
    QInputDialog,
    QWidgetAction,
    QComboBox,
    QGraphicsDropShadowEffect,
    QApplication,
    QWidget,
)
from PyQt6.QtGui import QPainterPath, QPen, QBrush, QColor, QPainter, QFont, QAction, QLinearGradient, QPolygonF
from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer, pyqtSignal, QObject
import traceback
import importlib

# Debug: when True, run deferred removals immediately to surface exceptions
# Set to True to force synchronous removal (useful for debugging crashes).
DEBUG_FORCE_IMMEDIATE_REMOVAL = False

try:
    from py_editor.ui.node_editor import NodeEditorDialog
    from py_editor.core.node_templates import (
        list_templates,
        get_template,
        save_template,
        load_templates,
        get_all_templates,
    )
except Exception:
    try:
        from .node_editor import NodeEditorDialog
        from ..core.node_templates import (
            list_templates,
            get_template,
            save_template,
            load_templates,
            get_all_templates,
        )
    except Exception:
        import sys
        from pathlib import Path
        parent_dir = Path(__file__).resolve().parent.parent
        if str(parent_dir) not in sys.path:
            sys.path.insert(0, str(parent_dir))
        from ui.node_editor import NodeEditorDialog
        from core.node_templates import (
            list_templates,
            get_template,
            save_template,
            load_templates,
            get_all_templates,
        )



class CompositePinRow(QWidget):
    def __init__(self, options, remove_callback, default=None, parent=None):
        super().__init__(parent)
        self._options = list(options)
        self._remove_callback = remove_callback
        layout = QHBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(0, 0, 0, 0)

        self.combo = QComboBox(self)
        self.combo.addItem("Select internal pin...", None)
        for option in self._options:
            self.combo.addItem(option["label"], option)
        self.combo.setMinimumWidth(220)

        self.name_edit = QLineEdit(self)
        self.name_edit.setPlaceholderText("External name")
        remove_btn = QPushButton("Remove", self)
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.clicked.connect(self._on_remove)

        layout.addWidget(self.combo)
        layout.addWidget(self.name_edit)
        layout.addWidget(remove_btn)

        if default:
            self.name_edit.setText(default.get("external", ""))
            self._select_default(default)

    def _select_default(self, default):
        target_key = (default.get("node"), default.get("pin"))
        for idx in range(self.combo.count()):
            data = self.combo.itemData(idx)
            if data and (data.get("node"), data.get("pin")) == target_key:
                self.combo.setCurrentIndex(idx)
                return
        label = default.get("label") or f"Node {target_key[0]} - {target_key[1]}"
        self.combo.addItem(label, {"node": target_key[0], "pin": target_key[1], "label": label})
        self.combo.setCurrentIndex(self.combo.count() - 1)

    def _on_remove(self):
        if self._remove_callback:
            self._remove_callback(self)

    def get_mapping(self):
        data = self.combo.currentData()
        name = self.name_edit.text().strip()
        if not data or not name:
            return None
        return {"external": name, "node": data.get("node"), "pin": data.get("pin")}


class CompositePinSection(QWidget):
    def __init__(self, title, options, parent=None):
        super().__init__(parent)
        self._options = list(options)
        self._rows = []
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QLabel(title, self)
        header.setStyleSheet("font-weight: bold; color: #e8e8e8;")
        layout.addWidget(header)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self._add_button = QPushButton(f"Add {title[:-1]}", self)
        self._add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        button_row.addWidget(self._add_button)
        layout.addLayout(button_row)

        self._rows_container = QWidget(self)
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setSpacing(4)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._rows_container)

        self._empty_label = QLabel("No pins available to expose.", self)
        self._empty_label.setStyleSheet("color: #999; font-style: italic;")
        layout.addWidget(self._empty_label)

        self._add_button.clicked.connect(self.add_row)
        self._refresh_state()

    def add_row(self, default=None, allow_empty=False):
        if not self._options and not allow_empty:
            return
        row = CompositePinRow(self._options, self._remove_row, default=default, parent=self)
        self._rows.append(row)
        self._rows_layout.addWidget(row)
        self._refresh_state()
        return row

    
        cancel_btn.clicked.connect(self.reject)

    @staticmethod
    def _ensure_defaults(options, defaults):
        seen = {(opt["node"], opt["pin"]) for opt in options}
        for entry in defaults:
            key = (entry.get("node"), entry.get("pin"))
            if key in seen:
                continue
            seen.add(key)
            label = entry.get("label") or f"Node {key[0]} - {key[1]}"
            options.append({"node": key[0], "pin": key[1], "label": label})

    def get_name(self):
        return self.name_edit.text().strip()

    def _build_map(self, entries):
        result = {}
        for entry in entries:
            external = entry.get("external")
            if not external:
                continue
            result[external] = {
                "node": entry.get("node"),
                "pin": entry.get("pin"),
                "type": "any",
            }
        return result

    def get_mappings(self):
        return self._build_map(self.input_section.get_mappings()), self._build_map(
            self.output_section.get_mappings()
        )


