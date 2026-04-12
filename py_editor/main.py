import sys
import json
from pathlib import Path
import faulthandler
import signal
import os
import threading
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QFileDialog,
    QToolBar,
    QDockWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QComboBox,
    QLineEdit,
    QMessageBox,
    QTabWidget,
    QInputDialog,
    QMenu,
    QScrollArea,
    QDialog,
    QDoubleSpinBox,
    QDialogButtonBox,
    QFormLayout,
    QListWidget,
    QListWidgetItem,
    QColorDialog,
    QPlainTextEdit,
    QTextBrowser,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsItem,
    QCheckBox,
    QSizePolicy,
)
from PyQt6.QtGui import QIcon, QAction, QColor, QDrag, QFont, QTextCursor, QPainter
from PyQt6.QtCore import Qt, QTimer, QMimeData, pyqtSignal

try:
    # prefer package imports when available
    from py_editor.ui import LogicEditor, CanvasView, NodeEditorDialog, NodeSettingsDialog, CodeGenDialog, UIBuilderWidget, WidgetPaletteWidget, PropertyEditor, ScreenListWidget, WidgetListWidget, SceneEditorWidget, SceneExplorerPanel, ObjectPropertiesPanel
    from py_editor.core import load_templates
except Exception:
    try:
        from .ui import LogicEditor, CanvasView, NodeEditorDialog, NodeSettingsDialog, CodeGenDialog, UIBuilderWidget, WidgetPaletteWidget, PropertyEditor, ScreenListWidget, WidgetListWidget, SceneEditorWidget, SceneExplorerPanel, ObjectPropertiesPanel
        from .core import load_templates
    except Exception:
        import sys
        from pathlib import Path
        # Add parent of the py_editor package to path so "py_editor" imports work
        parent_dir = Path(__file__).resolve().parent.parent
        if str(parent_dir) not in sys.path:
            sys.path.insert(0, str(parent_dir))
        from py_editor.ui import LogicEditor, CanvasView, NodeEditorDialog, NodeSettingsDialog, CodeGenDialog, UIBuilderWidget, WidgetPaletteWidget, PropertyEditor, ScreenListWidget, WidgetListWidget, SceneEditorWidget, SceneExplorerPanel, ObjectPropertiesPanel
        from py_editor.core import load_templates

ASSET_PATH = Path(__file__).resolve().parents[1] / "assets" / "sample_positions.json"
WORKSPACE_ROOT = Path(__file__).resolve().parents[1]


class CollapsibleSection(QWidget):
    """VS Code-style collapsible section with arrow indicator"""
    
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.is_collapsed = False
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header button
        self.header = QPushButton(f"▼ {title}")
        self.header.setStyleSheet("""
            QPushButton {
                background-color: #252526;
                color: #e0e0e0;
                border: none;
                text-align: left;
                padding: 6px 8px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #2a2d2e;
            }
        """)
        self.header.clicked.connect(self.toggle)
        self.title = title
        layout.addWidget(self.header)
        
        # Content container
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        layout.addWidget(self.content)
    
    def toggle(self):
        self.is_collapsed = not self.is_collapsed
        self.content.setVisible(not self.is_collapsed)
        arrow = "▶" if self.is_collapsed else "▼"
        self.header.setText(f"{arrow} {self.title}")
    
    def add_widget(self, widget):
        self.content_layout.addWidget(widget)


class FileExplorerWidget(QWidget):
    """VS Code-style file explorer with collapsible sections"""
    
    file_selected = pyqtSignal(str)  # Emits file path when selected
    
    def __init__(self, root_path, parent=None):
        super().__init__(parent)
        self.root_path = Path(root_path)
        self.main_window = parent
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Explorer header
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(8, 6, 8, 6)
        
        header_label = QLabel("EXPLORER")
        header_label.setStyleSheet("color: #888; font-size: 11px; font-weight: bold;")
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        
        # Action buttons
        open_folder_btn = QPushButton("📁")
        open_folder_btn.setFixedSize(20, 20)
        open_folder_btn.setToolTip("Open Folder (Set Workspace)")
        open_folder_btn.setStyleSheet("QPushButton { background: transparent; color: #888; border: none; } QPushButton:hover { color: #fff; }")
        open_folder_btn.clicked.connect(self._open_folder)
        header_layout.addWidget(open_folder_btn)
        
        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedSize(20, 20)
        refresh_btn.setToolTip("Refresh")
        refresh_btn.setStyleSheet("QPushButton { background: transparent; color: #888; border: none; } QPushButton:hover { color: #fff; }")
        refresh_btn.clicked.connect(self.refresh)
        header_layout.addWidget(refresh_btn)
        
        new_file_btn = QPushButton("+")
        new_file_btn.setFixedSize(20, 20)
        new_file_btn.setToolTip("New File")
        new_file_btn.setStyleSheet("QPushButton { background: transparent; color: #888; border: none; } QPushButton:hover { color: #fff; }")
        new_file_btn.clicked.connect(self._new_file)
        header_layout.addWidget(new_file_btn)
        
        layout.addWidget(header_widget)
        
        # Scroll area for sections
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { 
                border: none; 
                background-color: #252526;
            }
            QScrollBar:vertical {
                background: #252526;
                width: 10px;
            }
            QScrollBar::handle:vertical {
                background: #424242;
                border-radius: 5px;
            }
        """)
        
        scroll_content = QWidget()
        self.sections_layout = QVBoxLayout(scroll_content)
        self.sections_layout.setContentsMargins(0, 0, 0, 0)
        self.sections_layout.setSpacing(0)
        
        # Project Files section
        self.files_section = CollapsibleSection("PROJECT FILES")
        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderHidden(True)
        self.file_tree.setStyleSheet("""
            QTreeWidget {
                background-color: #252526;
                color: #cccccc;
                border: none;
                outline: none;
            }
            QTreeWidget::item {
                padding: 2px 0;
            }
            QTreeWidget::item:selected {
                background-color: #094771;
            }
            QTreeWidget::item:hover:!selected {
                background-color: #2a2d2e;
            }
            QTreeWidget::branch {
                background-color: #252526;
            }
        """)
        self.file_tree.itemDoubleClicked.connect(self._on_file_double_click)
        self.file_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_tree.customContextMenuRequested.connect(self._show_context_menu)
        
        # Enable drag for graph files
        self.file_tree.setDragEnabled(True)
        self.file_tree.setDragDropMode(QTreeWidget.DragDropMode.DragOnly)
        self.file_tree.startDrag = self._start_drag
        
        self.files_section.add_widget(self.file_tree)
        self.sections_layout.addWidget(self.files_section)
        
        # Open Graphs section
        self.graphs_section = CollapsibleSection("OPEN GRAPHS")
        self.graphs_list = QListWidget()
        self.graphs_list.setStyleSheet("""
            QListWidget {
                background-color: #252526;
                color: #cccccc;
                border: none;
            }
            QListWidget::item {
                padding: 4px 8px;
            }
            QListWidget::item:selected {
                background-color: #094771;
            }
            QListWidget::item:hover:!selected {
                background-color: #2a2d2e;
            }
        """)
        self.graphs_list.setMaximumHeight(100)
        self.graphs_section.add_widget(self.graphs_list)
        self.sections_layout.addWidget(self.graphs_section)
        
        # Outline section (for current graph nodes)
        self.outline_section = CollapsibleSection("OUTLINE")
        self.outline_tree = QTreeWidget()
        self.outline_tree.setHeaderHidden(True)
        self.outline_tree.setStyleSheet(self.file_tree.styleSheet())
        self.outline_tree.setMaximumHeight(150)
        self.outline_section.add_widget(self.outline_tree)
        self.sections_layout.addWidget(self.outline_section)
        
        self.sections_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)
        
        # Populate file tree
        self._populate_tree()
    
    def _get_file_icon(self, path: Path):
        """Get icon for file type"""
        if path.is_dir():
            return "📁"
        ext = path.suffix.lower()
        icons = {
            # NodeCanvas graph types
            ".logic": "🔷",   # Logic graph
            ".anim": "🎬",    # Animation graph
            ".ui": "🖼️",      # UI layout
            # Legacy and common types
            ".json": "📄",
            ".py": "🐍",
            ".md": "📝",
            ".txt": "📃",
            ".png": "🖼️",
            ".jpg": "🖼️",
            ".jpeg": "🖼️",
            ".ncpkg": "📦",
            ".wav": "🔊",
            ".mp3": "🔊",
            ".ogg": "🔊",
        }
        return icons.get(ext, "📄")
    
    def _populate_tree(self):
        """Populate the file tree"""
        self.file_tree.clear()
        root_item = QTreeWidgetItem([f"📁 {self.root_path.name}"])
        root_item.setData(0, Qt.ItemDataRole.UserRole, str(self.root_path))
        self.file_tree.addTopLevelItem(root_item)
        self._add_children(root_item, self.root_path, depth=3)
        root_item.setExpanded(True)
    
    def _add_children(self, parent_item, path: Path, depth: int):
        if depth <= 0:
            return
        try:
            # Filter out hidden files and common ignore patterns
            ignore = {'.git', '__pycache__', '.venv', 'node_modules', '.env'}
            entries = sorted(
                [e for e in path.iterdir() if e.name not in ignore and not e.name.startswith('.')],
                key=lambda p: (not p.is_dir(), p.name.lower())
            )
        except Exception:
            return
        
        for entry in entries:
            icon = self._get_file_icon(entry)
            child = QTreeWidgetItem([f"{icon} {entry.name}"])
            child.setData(0, Qt.ItemDataRole.UserRole, str(entry))
            parent_item.addChild(child)
            if entry.is_dir():
                self._add_children(child, entry, depth - 1)
    
    def _on_file_double_click(self, item, column):
        """Handle double-click on file - opens in appropriate tab"""
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path:
            p = Path(path)
            if p.is_file():
                self.file_selected.emit(path)
                ext = p.suffix.lower()
                
                # NodeCanvas file types
                if ext in ('.logic', '.anim', '.json'):
                    self._open_graph_file(p, ext)
                elif ext == '.ui':
                    self._open_ui_file(p)
    
    def _open_graph_file(self, path: Path, ext: str):
        """Open a graph file (.logic, .anim, .json) in the Logic tab"""
        if not self.main_window:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Load into canvas
            if 'nodes' in data:
                self.main_window.canvas.load_graph(data)
                if hasattr(self.main_window, 'variable_panel'):
                    self.main_window.variable_panel.load_variables(data.get('variables', {}))
            
            # Also load UI if present
            if 'ui' in data and hasattr(self.main_window, 'ui_builder'):
                self.main_window.ui_builder.canvas.load_ui(data['ui'])
            
            # Switch to appropriate tab
            if ext == '.anim':
                # Switch to Anim tab (index 2)
                self.main_window.tabs.setCurrentIndex(2)
            else:
                # Switch to Logic tab (index 0)
                self.main_window.tabs.setCurrentIndex(0)
            
            self.main_window.current_file = str(path)
            self.main_window.setWindowTitle(f"NodeCanvas - {path.name}")
            
            # Add to open graphs list
            self.add_open_graph(str(path))
            
            print(f"Opened: {path}")
            
        except Exception as e:
            print(f"Could not load file: {e}")
            import traceback
            traceback.print_exc()
    
    def _open_ui_file(self, path: Path):
        """Open a .ui file in the UI Builder tab"""
        if not self.main_window:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Load UI data
            if hasattr(self.main_window, 'ui_builder'):
                ui_data = data.get('ui', data)  # Support both wrapped and raw formats
                self.main_window.ui_builder.canvas.load_ui(ui_data)
                
                # Refresh screen list
                if hasattr(self.main_window, 'screen_list'):
                    self.main_window.screen_list.refresh_list()
            
            # Switch to Viewport tab (index 1) in UI mode
            self.main_window.tabs.setCurrentIndex(1)
            if hasattr(self.main_window, 'scene_editor'):
                self.main_window.scene_editor.toolbar.mode_combo.setCurrentText('UI')
            
            self.main_window.current_file = str(path)
            self.main_window.setWindowTitle(f"NodeCanvas - {path.name}")
            
            # Add to open graphs list
            self.add_open_graph(str(path))
            
            print(f"Opened UI: {path}")
            
        except Exception as e:
            print(f"Could not load UI file: {e}")
            import traceback
            traceback.print_exc()
    
    def _show_context_menu(self, pos):
        """Show context menu for file tree"""
        item = self.file_tree.itemAt(pos)
        menu = QMenu(self)
        
        if item:
            path = Path(item.data(0, Qt.ItemDataRole.UserRole))
            if path.is_file():
                open_action = menu.addAction("Open")
                open_action.triggered.connect(lambda: self._on_file_double_click(item, 0))
                menu.addSeparator()
            
            rename_action = menu.addAction("Rename")
            delete_action = menu.addAction("Delete")
            menu.addSeparator()
        
        new_file_action = menu.addAction("New File")
        new_file_action.triggered.connect(self._new_file)
        new_folder_action = menu.addAction("New Folder")
        new_folder_action.triggered.connect(self._new_folder)
        menu.addSeparator()
        
        open_folder_action = menu.addAction("Open Folder...")
        open_folder_action.triggered.connect(self._open_folder)
        
        refresh_action = menu.addAction("Refresh")
        refresh_action.triggered.connect(self.refresh)
        
        menu.exec(self.file_tree.mapToGlobal(pos))
    
    def _new_file(self):
        """Create new file"""
        name, ok = QInputDialog.getText(self, "New File", "File name:")
        if ok and name:
            # Get selected folder or use root
            item = self.file_tree.currentItem()
            if item:
                path = Path(item.data(0, Qt.ItemDataRole.UserRole))
                if path.is_file():
                    path = path.parent
            else:
                path = self.root_path
            
            new_path = path / name
            try:
                new_path.touch()
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not create file: {e}")
    
    def _new_folder(self):
        """Create new folder"""
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name:
            item = self.file_tree.currentItem()
            if item:
                path = Path(item.data(0, Qt.ItemDataRole.UserRole))
                if path.is_file():
                    path = path.parent
            else:
                path = self.root_path
            
            new_path = path / name
            try:
                new_path.mkdir(parents=True, exist_ok=True)
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not create folder: {e}")
    
    def refresh(self):
        """Refresh the file tree"""
        self._populate_tree()
    
    def _open_folder(self):
        """Open folder dialog to set workspace"""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Open Folder (Set Workspace)",
            str(self.root_path),
            QFileDialog.Option.ShowDirsOnly
        )
        if folder:
            self.set_workspace(folder)
    
    def set_workspace(self, folder_path: str):
        """Set the workspace to a new folder"""
        self.root_path = Path(folder_path)
        self.refresh()
        
        # Update window title to show project
        if self.main_window:
            self.main_window.setWindowTitle(f"NodeCanvas - {self.root_path.name}")
            self.main_window.project_root = str(self.root_path)
        
        print(f"Workspace set to: {folder_path}")
    
    def _start_drag(self, actions):
        """Start drag operation for graph files"""
        item = self.file_tree.currentItem()
        if not item:
            return
        
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if not path:
            return
        
        p = Path(path)
        ext = p.suffix.lower()
        
        # Only allow dragging of graph-type files
        if ext not in ('.logic', '.anim', '.ui', '.json'):
            return
        
        # Create drag with file path as data
        drag = QDrag(self.file_tree)
        mime_data = QMimeData()
        
        # Store as graph reference for canvas to create LogicReference node
        mime_data.setData("application/x-nodecanvas-graph", str(path).encode('utf-8'))
        mime_data.setText(p.name)
        
        drag.setMimeData(mime_data)
        drag.exec(Qt.DropAction.CopyAction)
    
    def update_outline(self, nodes):
        """Update the outline with current graph nodes"""
        self.outline_tree.clear()
        for node in nodes:
            node_type = getattr(node, 'node_type', 'Unknown')
            icon = "🔷" if 'Event' in node_type else "⬡"
            item = QTreeWidgetItem([f"{icon} {node_type}"])
            item.setData(0, Qt.ItemDataRole.UserRole, node)
            self.outline_tree.addTopLevelItem(item)
    
    def add_open_graph(self, file_path: str):
        """Add a graph to the open graphs list"""
        from pathlib import Path
        p = Path(file_path)
        
        # Check if already in list
        for i in range(self.graphs_list.count()):
            item = self.graphs_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == file_path:
                # Already open, just select it
                self.graphs_list.setCurrentItem(item)
                return
        
        # Add new entry
        icon = "🔷" if p.suffix == '.logic' else ("🎬" if p.suffix == '.anim' else "🖼️")
        item = QListWidgetItem(f"{icon} {p.name}")
        item.setData(Qt.ItemDataRole.UserRole, file_path)
        self.graphs_list.addItem(item)
        self.graphs_list.setCurrentItem(item)
    
    def clear_open_graphs(self):
        """Clear all open graphs"""
        self.graphs_list.clear()


class AIChatWidget(QWidget):
    """AI chat panel for NodeCanvas assistant - can view and modify graphs/UI"""
    
    # Signals for thread-safe UI updates
    response_received = pyqtSignal(str)
    error_received = pyqtSignal(str)
    
    AVAILABLE_MODELS = [
        "gpt-4o-mini",
        "gpt-4o", 
        "gpt-4-turbo",
        "gpt-3.5-turbo",
        "o1-mini",
        "o1-preview"
    ]
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.chat_history = []
        self.thought_history = []
        self.api_key = None
        self.model = "gpt-4o-mini"
        self.is_thinking = False
        
        self._load_env()
        self._setup_ui()
        
        # Connect signals
        self.response_received.connect(self._process_response)
        self.error_received.connect(self._show_error)
    
    def _load_env(self):
        """Load API key from .env file"""
        env_path = Path(__file__).resolve().parents[1] / ".env"
        if env_path.exists():
            try:
                with open(env_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            key = key.strip()
                            value = value.strip()
                            if key == 'OPENAI_API_KEY':
                                self.api_key = value
                            elif key == 'OPENAI_MODEL':
                                self.model = value
            except Exception as e:
                print(f"Error loading .env: {e}")
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header (Minimalist)
        header = QWidget()
        header.setStyleSheet("background-color: #2b2d30; border-bottom: 1px solid #3e4145;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 12, 8)
        
        # Model selector
        self.model_combo = QComboBox()
        self.model_combo.addItems(self.AVAILABLE_MODELS)
        if self.model in self.AVAILABLE_MODELS:
            self.model_combo.setCurrentText(self.model)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        self.model_combo.setStyleSheet("""
            QComboBox {
                background-color: #3c3f41;
                color: #bbbbbb;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 3px 8px;
                min-width: 120px;
                font-size: 12px;
            }
            QComboBox:hover { border-color: #0078d4; }
            QComboBox::drop-down { border: none; }
            QComboBox::down-arrow { image: none; border: none; }
        """)
        header_layout.addWidget(self.model_combo)
        
        header_layout.addStretch()
        
        # Status indicator
        is_connected = self.api_key and self.api_key != 'your-api-key-here' and len(self.api_key) > 20
        self.status_label = QLabel("●" + (" API Ready" if is_connected else " No API Key"))
        self.status_label.setStyleSheet(f"color: {'#629755' if is_connected else '#cc5555'}; font-size: 11px;")
        header_layout.addWidget(self.status_label)
        
        # Settings button
        settings_btn = QPushButton("⚙")
        settings_btn.setFixedSize(24, 24)
        settings_btn.clicked.connect(self._open_settings)
        settings_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #888; border: none; font-size:14px; }
            QPushButton:hover { color: #ddd; }
        """)
        header_layout.addWidget(settings_btn)
        
        # Clear chat button
        clear_btn = QPushButton("✕")
        clear_btn.setFixedSize(24, 24)
        clear_btn.setToolTip("Clear chat")
        clear_btn.clicked.connect(self._clear_chat)
        clear_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #888; border: none; font-size:12px; }
            QPushButton:hover { color: #ddd; }
        """)
        header_layout.addWidget(clear_btn)
        
        layout.addWidget(header)
        
        # Chat display area - Cleaner, less "matte", more standard IDE feel
        self.chat_display = QTextBrowser()
        self.chat_display.setOpenExternalLinks(False)
        self.chat_display.anchorClicked.connect(self._on_link_clicked)
        # Using a slightly lighter background than #121212 to match typical VS Code sidebars
        self.chat_display.setStyleSheet("""
            QTextBrowser {
                background-color: #252526; 
                color: #cccccc;
                border: none;
                padding: 10px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 13px;
                line-height: 1.5;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 10px;
            }
            QScrollBar::handle:vertical {
                background: #424242;
                border-radius: 5px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover { background: #505050; }
        """)
        self._show_welcome()
        layout.addWidget(self.chat_display)
        
        # Input area - Clean separation
        input_container = QWidget()
        input_container.setStyleSheet("background-color: #2b2d30; border-top: 1px solid #3e3e42;")
        input_layout = QVBoxLayout(input_container)
        input_layout.setContentsMargins(10, 10, 10, 10)
        input_layout.setSpacing(6)
        
        # Input field
        self.input_field = ChatInputField()
        self.input_field.setPlaceholderText("Type a message to edit your graph...")
        self.input_field.setMaximumHeight(80)
        self.input_field.setStyleSheet("""
            QPlainTextEdit {
                background-color: #3c3c3c;
                color: #f0f0f0;
                border: 1px solid #555;
                border-radius: 2px;
                padding: 6px 8px;
                font-size: 13px;
                font-family: 'Segoe UI', sans-serif;
            }
            QPlainTextEdit:focus { border-color: #0078d4; background-color: #1e1e1e; }
        """)
        self.input_field.enter_pressed.connect(self._send_message)
        input_layout.addWidget(self.input_field)
        
        # Send button aligned right
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        
        self.send_btn = QPushButton("Send")
        self.send_btn.setFixedSize(80, 24)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 2px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #1177bb; }
            QPushButton:pressed { background-color: #094770; }
            QPushButton:disabled { background-color: #333; color: #666; }
        """)
        self.send_btn.clicked.connect(self._send_message)
        btn_row.addWidget(self.send_btn)
        
        input_layout.addLayout(btn_row)
        layout.addWidget(input_container)
    
    def _on_model_changed(self, model):
        self.model = model
    
    def _open_settings(self):
        """Open the .env file"""
        env_path = Path(__file__).resolve().parents[1] / ".env"
        import subprocess
        import sys
        if sys.platform == 'win32':
            subprocess.run(['notepad', str(env_path)])
        else:
            subprocess.run(['open', str(env_path)])
    
    
    def _clear_chat(self):
        self.chat_history = []
        self.thought_history = []
        self._show_welcome()
    
    def _show_welcome(self):
        # Empty welcome as requested (- minimal "Ready")
        self.chat_display.setHtml("")
        self._append_system_message("NodeCanvas Assistant Ready.")

    def _on_link_clicked(self, url):
        """Handle thought links"""
        if url.scheme() == 'thought':
            try:
                idx = int(url.path())
                if 0 <= idx < len(self.thought_history):
                    thought = self.thought_history[idx]
                    QMessageBox.information(self, "Thinking Process", thought)
            except:
                pass
    
    def _get_current_project_context(self):
        """Get the current graph and UI as JSON"""
        context = {"nodes": [], "connections": [], "variables": {}, "ui": {}}
        
        if not self.main_window:
            return context
        
        try:
            if hasattr(self.main_window, 'canvas') and self.main_window.canvas:
                graph_data = self.main_window.canvas.export_graph()
                context["nodes"] = graph_data.get("nodes", [])
                context["connections"] = graph_data.get("connections", [])
                if hasattr(self.main_window.canvas, 'graph_variables'):
                    context["variables"] = dict(self.main_window.canvas.graph_variables)
            
            if hasattr(self.main_window, 'ui_builder') and self.main_window.ui_builder:
                if hasattr(self.main_window.ui_builder, 'canvas'):
                    context["ui"] = self.main_window.ui_builder.canvas.export_ui()
        except Exception as e:
            print(f"Error getting project context: {e}")
        
        return context
    
    def _apply_changes(self, changes_json):
        """Apply changes from AI to the graph/UI/variables"""
        try:
            if not self.main_window:
                return False, "No main window"
            applied = []

            # Apply variable changes
            if "variables" in changes_json and self.main_window.canvas:
                variables = changes_json["variables"]
                if hasattr(self.main_window.canvas, "graph_variables"):
                    # Validate and set variables into canvas.graph_variables in expected format
                    for var_name, var_data in variables.items():
                        # Ensure var_data is a dict with at least 'value'
                        if isinstance(var_data, dict):
                            vtype = var_data.get('type')
                            vval = var_data.get('value')
                            self.main_window.canvas.graph_variables[var_name] = {"type": vtype, "value": vval}
                        else:
                            # If value provided directly, wrap into expected format
                            self.main_window.canvas.graph_variables[var_name] = {"type": None, "value": var_data}
                    applied.append(f"Updated variables: {', '.join(variables.keys())}")
                    # Persist canvas state and refresh variable panel if present
                    try:
                        if hasattr(self.main_window.canvas, 'save_state'):
                            self.main_window.canvas.save_state()
                    except Exception:
                        pass
                    if hasattr(self.main_window, 'variable_panel'):
                        try:
                            self.main_window.variable_panel.load_variables(self.main_window.canvas.graph_variables)
                        except Exception:
                            pass

            # Apply node changes
            if "nodes" in changes_json and self.main_window.canvas:
                # Support AI node formats: {type|template, x|pos, y|pos, properties|values, id}
                ai_to_real = {}      # map AI-provided id -> real canvas id
                new_node_order = []  # list of real ids in insertion order
                try:
                    from py_editor.core.node_templates import get_template, list_templates
                except Exception:
                    from core.node_templates import get_template, list_templates

                for idx, node_data in enumerate(changes_json["nodes"]):
                    try:
                        # Determine AI id (may be absent)
                        ai_id = node_data.get('id') if isinstance(node_data, dict) else None

                        # Template/type handling
                        node_type = node_data.get('type') or node_data.get('template') or node_data.get('node_type') or ""
                        # Position handling: prefer pos array [x,y] or x/y fields
                        pos = node_data.get('pos') or node_data.get('position')
                        if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                            x, y = pos[0], pos[1]
                        else:
                            x = node_data.get('x', 0)
                            y = node_data.get('y', 0)

                        # Try to resolve template name
                        tmpl = get_template(node_type)
                        if not tmpl:
                            names = list_templates()
                            match = next((n for n in names if n.lower() == str(node_type).lower()), None)
                            if match:
                                node_type = match
                                tmpl = get_template(node_type)

                        if not tmpl:
                            msg = f"Skipping unknown node type: {node_type or '<empty>'}"
                            print(msg)
                            applied.append(msg)
                            ai_to_real[ai_id] = None
                            new_node_order.append(None)
                            continue

                        node_item = self.main_window.canvas.add_node_from_palette(node_type, x, y)

                        real_id = getattr(node_item, 'id', None)
                        if ai_id is not None:
                            ai_to_real[ai_id] = real_id
                        else:
                            # Map by insertion index (1-based) for backwards compatibility
                            ai_to_real[idx + 1] = real_id

                        new_node_order.append(real_id)

                        # Apply properties/values (support both 'properties' and 'values')
                        props = node_data.get('properties') or node_data.get('values') or {}
                        if isinstance(props, dict) and props:
                            # If node_item stores pin_values, try to set them
                            try:
                                for k, v in props.items():
                                    if hasattr(node_item, 'pin_values'):
                                        node_item.pin_values[k] = v
                                    # Try updating corresponding widget if present
                                    proxy = getattr(node_item, 'value_widgets', {}).get(k)
                                    if proxy and proxy.widget():
                                        w = proxy.widget()
                                        try:
                                            if hasattr(w, 'setText'):
                                                w.setText(str(v))
                                            elif hasattr(w, 'setValue'):
                                                w.setValue(v)
                                            elif hasattr(w, 'setCurrentText'):
                                                w.setCurrentText(str(v))
                                        except Exception:
                                            pass
                            except Exception:
                                pass

                        applied.append(f"Added node: {node_type} (id={real_id})")
                    except Exception as e:
                        print(f"Error adding node: {e}")
                        applied.append(f"Error adding node: {e}")

            # Apply connection changes
            if "connections" in changes_json and self.main_window.canvas:
                for conn in changes_json["connections"]:
                    try:
                        # Accept keys 'from'/'to' or 'from_node'/'to_node'
                        raw_from = conn.get("from") if conn.get("from") is not None else conn.get("from_node")
                        raw_to = conn.get("to") if conn.get("to") is not None else conn.get("to_node")
                        from_pin = conn.get("from_pin") or conn.get("fromPort") or conn.get("fromPin")
                        to_pin = conn.get("to_pin") or conn.get("toPort") or conn.get("toPin")

                        def resolve(raw):
                            # If it's an AI id that we mapped earlier
                            try:
                                if raw in ai_to_real:
                                    return ai_to_real.get(raw)
                            except Exception:
                                pass
                            # If raw is numeric and matches insertion order index
                            try:
                                n = int(raw)
                                # check ai_to_real mapping for this numeric key
                                if n in ai_to_real:
                                    return ai_to_real[n]
                                # fall back to new_node_order positional mapping (1-based)
                                if 1 <= n <= len(new_node_order):
                                    return new_node_order[n - 1]
                                return n
                            except Exception:
                                return raw

                        from_node_id = resolve(raw_from)
                        to_node_id = resolve(raw_to)

                        if from_node_id is None or to_node_id is None:
                            applied.append(f"Skipped connection with unresolved node refs: {raw_from} -> {raw_to}")
                            continue

                        conn_item = self.main_window.canvas.add_connection_by_id(
                            from_node_id, from_pin, to_node_id, to_pin
                        )
                        if conn_item:
                            applied.append(f"Connected {from_node_id}.{from_pin} -> {to_node_id}.{to_pin}")
                        else:
                            applied.append(f"Failed to connect {from_node_id}.{from_pin} -> {to_node_id}.{to_pin}")
                    except Exception as e:
                        print(f"Error adding connection: {e}")

            # Apply UI changes
            if "ui_widgets" in changes_json and hasattr(self.main_window, 'ui_builder'):
                canvas = self.main_window.ui_builder.canvas
                for widget_data in changes_json["ui_widgets"]:
                    try:
                        widget_type = widget_data.get("type", "Label")
                        props = widget_data.get("properties", {})
                        x = widget_data.get("x", None)
                        y = widget_data.get("y", None)
                        pos = None
                        if x is not None and y is not None:
                            # Convert to QPointF via canvas API expectations
                            from PyQt6.QtCore import QPointF
                            pos = QPointF(x, y)
                        canvas.add_widget(widget_type, props, pos)
                        applied.append(f"Added UI: {widget_type}")
                    except Exception as e:
                        print(f"Error adding widget: {e}")
                # Refresh UI builder lists and scene
                try:
                    if hasattr(self.main_window, 'screen_list'):
                        self.main_window.screen_list.refresh_list()
                    if hasattr(self.main_window, 'widget_list'):
                        self.main_window.widget_list.refresh_list()
                    if hasattr(self.main_window.ui_builder, 'canvas'):
                        self.main_window.ui_builder.canvas.scene().update()
                except Exception:
                    pass

            if applied:
                return True, ", ".join(applied)
            return False, "No changes to apply"
        except Exception as e:
            return False, str(e)
    
    def _send_message(self):
        """Send message to OpenAI API"""
        if self.is_thinking:
            return
            
        message = self.input_field.toPlainText().strip()
        if not message:
            return
        
        self._append_user_message(message)
        self.input_field.clear()
        
        if not self.api_key or self.api_key == 'your-api-key-here' or len(self.api_key) < 20:
            self._append_system_message("Please add your OpenAI API key to the .env file.\n\nClick the ⚙ button to open settings.", "error")
            return
        
        project_context = self._get_current_project_context()
        
        context_json = json.dumps(project_context, indent=2, default=str)
        if len(context_json) > 5000:
            context_json = context_json[:5000] + "\n... (truncated)"
        
        context_summary = f"""Current Project:
- Nodes: {len(project_context.get('nodes', []))}
- Connections: {len(project_context.get('connections', []))}
- Variables: {list(project_context.get('variables', {}).keys())}

JSON:
{context_json}

Request: {message}"""
        
        self.chat_history.append({"role": "user", "content": context_summary})
        
        self.is_thinking = True
        self.send_btn.setEnabled(False)
        self.send_btn.setText("●●●")
        self._append_thinking()
        
        import threading
        thread = threading.Thread(target=self._call_api, daemon=True)
        thread.start()
    
    def _call_api(self):
        """Call OpenAI API in background thread"""
        try:
            import urllib.request
            import urllib.error
            
            system_prompt = """You are NodeCanvas Assistant, an expert agentic coder.
Your goal is to help the user build working, high-quality node graphs.

CRITICAL RULES:
1. **NO CODE IN CHAT**: Never output Python code or code blocks in your text response. The user cannot see code. Describe your actions in plain English.
2. **USE THOUGHTS**: You MUST think step-by-step before answering. Wrap your reasoning in <thought>...</thought> tags.
3. **SELF-CORRECTION**: Before outputting the JSON, review your plan. valid connections? logic sound?
   - If user asks for a graph, ensure ALL nodes are connected. Do not create disconnected islands.
   - Verify pin names exist (e.g. 'result', 'value').

To make changes, output a JSON block wrapped in ```apply ... ```:
```apply
{
  "nodes": [{"type": "Add", "x": 100, "y": 100}],
  "connections": [{"from_node": 1, "from_pin": "result", "to_node": 2, "to_pin": "value"}],
  "ui_widgets": [{"type": "Button", "x": 0, "y": 0, "properties": {"text": "Click Me"}}]
}
```"""
            
            messages = [{"role": "system", "content": system_prompt}] + self.chat_history[-6:]
            
            data = json.dumps({
                "model": self.model,
                "messages": messages,
                "max_tokens": 2000,
                "temperature": 0.7
            }).encode('utf-8')
            
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                }
            )
            
            with urllib.request.urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode('utf-8'))
                assistant_message = result['choices'][0]['message']['content']
                self.chat_history.append({"role": "assistant", "content": assistant_message})
                self.response_received.emit(assistant_message)
                
        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode('utf-8')
            except:
                pass
            self.error_received.emit(f"API Error {e.code}: {e.reason}\n{error_body[:200]}")
        except urllib.error.URLError as e:
            self.error_received.emit(f"Connection Error: {e.reason}")
        except Exception as e:
            self.error_received.emit(f"Error: {str(e)}")
    
    def _process_response(self, response):
        """Process the AI response and apply any changes"""
        self._remove_thinking()
        
        import re
        apply_pattern = r'```apply\s*\n(.*?)\n```'
        matches = re.findall(apply_pattern, response, re.DOTALL)
        if matches:
            parsed_changes = []
            for match in matches:
                try:
                    changes = json.loads(match)
                    parsed_changes.append(changes)
                except json.JSONDecodeError:
                    # invalid JSON - include raw block in assistant message
                    parsed_changes.append({"_raw": match})

            # Auto-apply mode (no confirmation) with validation and clear reporting
            auto_apply = True
            for changes in parsed_changes:
                if not isinstance(changes, dict) or '_raw' in changes:
                    self._append_system_message("Assistant provided invalid or unparsable apply block.", "error")
                    continue

                # Validate nodes and ui/widgets up-front
                try:
                    # Apply changes and collect result message
                    success, result = self._apply_changes(changes)
                    if success:
                        self._append_system_message(f"✓ Applied: {result}", "success")
                    else:
                        self._append_system_message(f"No changes applied: {result}", "info")
                except Exception as e:
                    self._append_system_message(f"Error applying changes: {e}", "error")

        # Extract thoughts
        thoughts = ""
        thought_matches = re.findall(r'<thought>(.*?)</thought>', response, re.DOTALL)
        for t in thought_matches:
            thoughts += t.strip() + "\n"
        
        # Remove thoughts from display message
        display_message = re.sub(r'<thought>.*?</thought>', '', response, flags=re.DOTALL)
        
        # Remove apply block from display message
        display_message = re.sub(apply_pattern, '', display_message, flags=re.DOTALL).strip()
        
        if thoughts:
            self._append_thought_message(thoughts)

        if display_message:
            self._append_assistant_message(display_message)

        self._reset_state()
    
    def _show_error(self, error):
        self._remove_thinking()
        self._append_system_message(error, "error")
        self._reset_state()
    
    def _reset_state(self):
        self.is_thinking = False
        self.send_btn.setEnabled(True)
        self.send_btn.setText("Send")
    
    def _append_thought_message(self, thought):
        # Store thought and show link
        idx = len(self.thought_history)
        self.thought_history.append(thought)
        
        html = f"""
        <div style="margin:8px 0; font-size:11px;">
             <a href="thought:{idx}" style="color:#666; text-decoration:none;">▶ Show Thinking Process</a>
        </div>
        """
        self._append_html(html)

    def _append_user_message(self, message):
        escaped = message.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
        html = f"""
        <div style="margin:16px 0; text-align:right;">
            <div style="display:inline-block; background-color:#0078d4; color:#ffffff; padding:8px 12px; border-radius:4px; max-width:90%; font-size:13px; text-align:left;">
                {escaped}
            </div>
        </div>
        """
        self._append_html(html)

    def _append_assistant_message(self, message):
        escaped = message.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
        html = f"""
        <div style="margin:16px 0; text-align:left;">
             <div style="font-size:13px; color:#cccccc; line-height:1.5;">
                {escaped}
            </div>
        </div>
        <hr style="border:0; height:1px; background:#333; margin:10px 0;">
        """
        self._append_html(html)
    
    def _append_system_message(self, message, msg_type="info"):
        colors = {"success": "#4caf50", "error": "#f44336", "info": "#888"}
        color = colors.get(msg_type, "#888")
        escaped = message.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
        # System badges with subtle background
        html = f"""
        <div style="margin:10px 0; display:flex; justify-content:center;">
          <div style="padding:8px 12px; background: rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.03); color:{color}; border-radius:10px; font-size:12px;">{escaped}</div>
        </div>
        """
        self._append_html(html)
    
    def _append_thinking(self):
        html = """
        <div id="thinking" style="margin:12px 0; display:flex; gap:10px; align-items:center;">
          <div style="width:36px; height:36px; border-radius:18px; background:#123244; display:flex; align-items:center; justify-content:center; color:#6bdcff;">…</div>
          <div style="padding:10px 12px; background:#071029; border:1px solid #123244; border-radius:12px; color:#89cbe6;">●●● Thinking...</div>
        </div>
        """
        self._append_html(html)
    
    def _remove_thinking(self):
        # Remove the thinking indicator by replacing the HTML
        html = self.chat_display.toHtml()
        # Simple removal - just get content up to "Thinking..."
        if '●●● Thinking...' in html:
            # Replace the thinking div
            import re
            html = re.sub(r'<div[^>]*>.*?●●● Thinking\.\.\.</span>.*?</div>\s*</div>', '', html, flags=re.DOTALL)
            self.chat_display.setHtml(html)
    
    def _append_html(self, html):
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.chat_display.setTextCursor(cursor)
        self.chat_display.insertHtml(html)
        sb = self.chat_display.verticalScrollBar()
        if sb:
            sb.setValue(sb.maximum())


class ChatInputField(QPlainTextEdit):
    """Custom input field that sends on Enter"""
    enter_pressed = pyqtSignal()
    
    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Return and not e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.enter_pressed.emit()
            return
        super().keyPressEvent(e)


class ClickableLabel(QLabel):
    """Label that emits clicked signal for inline editing (on double-click)"""
    clicked = pyqtSignal()
    
    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseDoubleClickEvent(event)


class VariableRowWidget(QWidget):
    """UE5-style variable row with drag support and inline editing"""
    deleted = pyqtSignal(str)  # Emits var_name when deleted
    changed = pyqtSignal()  # Emits when any property changes
    
    # Type colors for visual distinction
    TYPE_COLORS = {
        "int": "#FFB73B",
        "float": "#51ADFF", 
        "string": "#81C784",
        "bool": "#FF7093",
        "list": "#E879F9",      # Purple for lists
        "dict": "#F97316",      # Orange for dicts
        "struct": "#22D3EE",    # Cyan for structs
        "vector2": "#A78BFA",   # Light purple
        "vector3": "#818CF8",   # Indigo
        "color": "#F472B6",     # Pink
        "image": "#34D399",     # Green for image paths
        "audio": "#FB923C",     # Orange for audio paths
    }
    
    # All supported base types
    BASE_TYPES = ["int", "float", "string", "bool", "image", "audio"]
    # Types that can be elements of lists/dicts (including nested complex types)
    ELEMENT_TYPES = ["int", "float", "string", "bool", "vector2", "vector3", "color", "struct", "list", "dict", "image", "audio"]
    # All types including complex ones
    ALL_TYPES = ["int", "float", "string", "bool", "list", "dict", "struct", "vector2", "vector3", "color", "image", "audio"]
    
    def __init__(self, var_name, var_type, value, element_type=None, struct_def=None, parent=None):
        super().__init__(parent)
        self.var_name = var_name
        self.var_type = var_type
        self.value = value
        self.element_type = element_type  # For list/dict: the type of elements
        self.struct_def = struct_def or {}  # For struct: {field_name: field_type}
        self.panel = parent
        
        self.setMinimumHeight(36)
        self._setup_ui()
        self._update_style()
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        
        # Color indicator (type color bar)
        self.color_bar = QLabel()
        self.color_bar.setFixedWidth(4)
        self.color_bar.setMinimumHeight(28)
        layout.addWidget(self.color_bar)
        
        # Name label (double-click to edit)
        self.name_label = ClickableLabel(self.var_name)
        self.name_label.setMinimumWidth(60)
        self.name_label.setStyleSheet("color: #fff; font-weight: bold; padding: 2px;")
        self.name_label.clicked.connect(self._edit_name)
        layout.addWidget(self.name_label)
        
        # Type label (double-click to change type)
        self.type_label = ClickableLabel(self._get_type_display())
        self.type_label.setMinimumWidth(50)
        self.type_label.setStyleSheet("color: #aaa; font-size: 10px; padding: 2px;")
        self.type_label.clicked.connect(self._edit_type)
        layout.addWidget(self.type_label)
        
        # Value label (double-click to edit value)
        self.value_label = ClickableLabel(self._get_value_display())
        self.value_label.setMinimumWidth(40)
        self.value_label.setStyleSheet("color: #888; font-size: 10px; padding: 2px;")
        self.value_label.clicked.connect(self._edit_value)
        layout.addWidget(self.value_label, 1)
        
        # Delete button
        del_btn = QPushButton("×")
        del_btn.setFixedSize(20, 20)
        del_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #888; border: none; font-size: 14px; }
            QPushButton:hover { color: #ff6666; }
        """)
        del_btn.clicked.connect(self._delete)
        layout.addWidget(del_btn)
    
    def _get_type_display(self):
        """Get display string for type including element type"""
        if self.var_type == "list":
            return f"List<{self.element_type or 'any'}>"
        elif self.var_type == "dict":
            return f"Dict<{self.element_type or 'any'}>"
        elif self.var_type == "struct":
            return f"Struct"
        elif self.var_type == "vector2":
            return "Vec2"
        elif self.var_type == "vector3":
            return "Vec3"
        return self.var_type
    
    def _get_value_display(self):
        """Get display string for value"""
        if self.var_type == "list":
            if isinstance(self.value, list):
                return f"[{len(self.value)} items]"
            return "[]"
        elif self.var_type == "dict":
            if isinstance(self.value, dict):
                return f"{{{len(self.value)} keys}}"
            return "{}"
        elif self.var_type == "struct":
            if isinstance(self.value, dict):
                return f"({len(self.value)} fields)"
            return "()"
        elif self.var_type == "vector2":
            if isinstance(self.value, (list, tuple)) and len(self.value) >= 2:
                return f"({self.value[0]}, {self.value[1]})"
            return "(0, 0)"
        elif self.var_type == "vector3":
            if isinstance(self.value, (list, tuple)) and len(self.value) >= 3:
                return f"({self.value[0]}, {self.value[1]}, {self.value[2]})"
            return "(0, 0, 0)"
        elif self.var_type == "color":
            if isinstance(self.value, (list, tuple)) and len(self.value) >= 3:
                return f"#{self.value[0]:02x}{self.value[1]:02x}{self.value[2]:02x}"
            return "#000000"
        elif self.var_type == "bool":
            return "True" if self.value else "False"
        elif self.var_type in ("image", "audio"):
            # Show just the filename, not full path
            if self.value and isinstance(self.value, str):
                import os
                basename = os.path.basename(self.value)
                if len(basename) > 18:
                    return basename[:15] + "..."
                return basename or "(none)"
            return "(none)"
        else:
            val_str = str(self.value) if self.value is not None else ""
            if len(val_str) > 15:
                return val_str[:12] + "..."
            return val_str
    
    def _update_style(self):
        color = self.TYPE_COLORS.get(self.var_type, "#666")
        self.color_bar.setStyleSheet(f"background-color: {color}; border-radius: 2px;")
        self.setStyleSheet(f"""
            VariableRowWidget {{
                background: #2a2a2a;
                border: 1px solid #3a3a3a;
                border-left: 3px solid {color};
                border-radius: 3px;
            }}
            VariableRowWidget:hover {{
                background: #353535;
                border: 1px solid #4a4a4a;
                border-left: 3px solid {color};
            }}
        """)
        self.type_label.setText(self._get_type_display())
        self.value_label.setText(self._get_value_display())
    
    def _edit_name(self):
        """Inline edit the variable name"""
        new_name, ok = QInputDialog.getText(self, "Rename Variable", "Name:", text=self.var_name)
        if ok and new_name.strip() and new_name != self.var_name:
            new_name = new_name.strip()
            # Check for duplicates in parent panel
            if self.panel and hasattr(self.panel, 'variables') and new_name in self.panel.variables:
                QMessageBox.warning(self, "Duplicate", f"Variable '{new_name}' already exists")
                return
            old_name = self.var_name
            self.var_name = new_name
            self.name_label.setText(new_name)
            # Update panel's variables dict
            if self.panel and hasattr(self.panel, '_rename_variable_internal'):
                self.panel._rename_variable_internal(old_name, new_name)
            self.changed.emit()
    
    def _edit_type(self):
        """Change the variable type"""
        current_idx = self.ALL_TYPES.index(self.var_type) if self.var_type in self.ALL_TYPES else 0
        new_type, ok = QInputDialog.getItem(self, "Change Type", "Type:", 
                                           self.ALL_TYPES, current_idx, False)
        if ok and new_type != self.var_type:
            old_type = self.var_type
            self.var_type = new_type
            
            # For list/dict, ask for element type
            if new_type in ("list", "dict"):
                elem_type, ok2 = QInputDialog.getItem(self, "Element Type", 
                    f"Type of {new_type} elements:", self.ELEMENT_TYPES, 0, False)
                if ok2:
                    self.element_type = elem_type
                else:
                    self.element_type = "string"
            
            # Reset value to default for new type
            self.value = self._get_default_for_type(new_type)
            self._update_style()
            
            if self.panel and hasattr(self.panel, '_update_variable_internal'):
                self.panel._update_variable_internal(self.var_name)
            self.changed.emit()
    
    def _edit_value(self):
        """Edit the variable value"""
        if self.var_type == "bool":
            items = ["False", "True"]
            current = 1 if self.value else 0
            val, ok = QInputDialog.getItem(self, "Edit Value", "Value:", items, current, False)
            if ok:
                self.value = (val == "True")
        elif self.var_type == "int":
            val, ok = QInputDialog.getInt(self, "Edit Value", "Value:", int(self.value or 0))
            if ok:
                self.value = val
        elif self.var_type == "float":
            val, ok = QInputDialog.getDouble(self, "Edit Value", "Value:", float(self.value or 0), decimals=4)
            if ok:
                self.value = val
        elif self.var_type == "string":
            val, ok = QInputDialog.getText(self, "Edit Value", "Value:", text=str(self.value or ""))
            if ok:
                self.value = val
        elif self.var_type == "image":
            self._edit_file("image")
        elif self.var_type == "audio":
            self._edit_file("audio")
        elif self.var_type == "vector2":
            self._edit_vector(2)
        elif self.var_type == "vector3":
            self._edit_vector(3)
        elif self.var_type == "color":
            self._edit_color()
        elif self.var_type == "list":
            self._edit_list()
        elif self.var_type == "dict":
            self._edit_dict()
        elif self.var_type == "struct":
            self._edit_struct()
        
        self.value_label.setText(self._get_value_display())
        if self.panel and hasattr(self.panel, '_update_variable_internal'):
            self.panel._update_variable_internal(self.var_name)
        self.changed.emit()
    
    def _edit_file(self, file_type):
        """Edit file path with file picker dialog"""
        from PyQt6.QtWidgets import QFileDialog
        import os
        
        if file_type == "image":
            filter_str = "Image Files (*.png *.jpg *.jpeg *.gif *.bmp *.webp);;All Files (*)"
            title = "Select Image"
        else:  # audio
            filter_str = "Audio Files (*.wav *.mp3 *.ogg *.flac);;All Files (*)"
            title = "Select Audio File"
        
        # Start in current file's directory or user's home
        start_dir = ""
        if self.value and isinstance(self.value, str):
            if os.path.exists(self.value):
                start_dir = os.path.dirname(self.value)
        
        file_path, _ = QFileDialog.getOpenFileName(self, title, start_dir, filter_str)
        if file_path:
            self.value = file_path
    
    def _edit_vector(self, dims):
        """Edit vector2 or vector3 value"""
        from PyQt6.QtWidgets import QDialog, QFormLayout, QDoubleSpinBox, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Edit Vector{dims}")
        layout = QFormLayout(dlg)
        
        current = self.value if isinstance(self.value, (list, tuple)) else [0] * dims
        spins = []
        labels = ["X", "Y", "Z"][:dims]
        for i, label in enumerate(labels):
            spin = QDoubleSpinBox()
            spin.setRange(-999999, 999999)
            spin.setDecimals(4)
            spin.setValue(float(current[i]) if i < len(current) else 0)
            spins.append(spin)
            layout.addRow(label, spin)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addRow(buttons)
        
        if dlg.exec():
            self.value = [s.value() for s in spins]
    
    def _edit_color(self):
        """Edit color value using color picker"""
        from PyQt6.QtWidgets import QColorDialog
        current = self.value if isinstance(self.value, (list, tuple)) else [0, 0, 0]
        color = QColorDialog.getColor(QColor(*current[:3]), self, "Select Color")
        if color.isValid():
            self.value = [color.red(), color.green(), color.blue()]
    
    def _edit_list(self):
        """Edit list value with a dialog"""
        dlg = ListEditorDialog(self.value or [], self.element_type or "string", self)
        if dlg.exec():
            self.value = dlg.get_value()
    
    def _edit_dict(self):
        """Edit dict value with a dialog"""
        dlg = DictEditorDialog(self.value or {}, self.element_type or "string", self)
        if dlg.exec():
            self.value = dlg.get_value()
    
    def _edit_struct(self):
        """Edit struct definition and values"""
        print(f"DEBUG: _edit_struct called, struct_def={self.struct_def}, value={self.value}")
        dlg = StructEditorDialog(self.struct_def, self.value or {}, self)
        print(f"DEBUG: StructEditorDialog created, calling exec()")
        if dlg.exec():
            self.struct_def, self.value = dlg.get_result()
            print(f"DEBUG: Dialog accepted, struct_def={self.struct_def}, value={self.value}")
    
    def _get_default_for_type(self, var_type):
        """Get default value for a type"""
        defaults = {
            "int": 0, "float": 0.0, "string": "", "bool": False,
            "list": [], "dict": {}, "struct": {},
            "vector2": [0.0, 0.0], "vector3": [0.0, 0.0, 0.0],
            "color": [255, 255, 255],
            "image": "",  # File path to image
            "audio": "",  # File path to audio
        }
        return defaults.get(var_type, None)
    
    def _delete(self):
        """Delete this variable"""
        self.deleted.emit(self.var_name)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.pos()
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            if hasattr(self, '_drag_start'):
                if (event.pos() - self._drag_start).manhattanLength() > 10:
                    drag = QDrag(self)
                    mime_data = QMimeData()
                    # Include element_type for list/dict
                    drag_text = f"variable:{self.var_name}:{self.var_type}"
                    if self.element_type:
                        drag_text += f":{self.element_type}"
                    mime_data.setText(drag_text)
                    drag.setMimeData(mime_data)
                    drag.exec(Qt.DropAction.CopyAction)
    
    def get_data(self):
        """Get variable data for saving"""
        data = {
            'type': self.var_type,
            'value': self.value,
        }
        if self.element_type:
            data['element_type'] = self.element_type
        if self.struct_def:
            data['struct_def'] = self.struct_def
        return data


class ListEditorDialog(QDialog):
    """Dialog for editing list values"""
    def __init__(self, value, element_type, parent=None):
        super().__init__(parent)
        self.value = list(value) if value else []
        self.element_type = element_type
        
        # Infer actual element type from existing items if they don't match declared type
        if self.value:
            first_item = self.value[0]
            inferred = self._infer_type_static(first_item)
            # If declared type is generic or doesn't match, use inferred type
            if element_type in ("any", "string", None) and inferred != "string":
                self.element_type = inferred
        
        self.setWindowTitle(f"Edit List<{self.element_type}>")
        self.setMinimumSize(400, 450)
        # For struct elements, store struct definitions per item
        self.struct_defs = []  # List of struct_def dicts for each struct item
        
        layout = QVBoxLayout(self)
        
        # List widget
        self.list_widget = QListWidget()
        self._refresh_list()
        self.list_widget.itemDoubleClicked.connect(self._edit_item)
        layout.addWidget(self.list_widget)
        
        # Buttons
        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ Add")
        add_btn.setStyleSheet("background: #3a5a3a; border: 1px solid #4a7a4a; padding: 4px 12px;")
        add_btn.clicked.connect(self._add_item)
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._remove_item)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        
        # OK/Cancel
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def _refresh_list(self):
        """Refresh list display"""
        self.list_widget.clear()
        for i, item in enumerate(self.value):
            display = self._format_item(item)
            self.list_widget.addItem(f"[{i}] {display}")
    
    @staticmethod
    def _infer_type_static(value):
        """Infer the type of a value (static method for use before instance is fully initialized)"""
        if isinstance(value, bool):
            return "bool"
        elif isinstance(value, int):
            return "int"
        elif isinstance(value, float):
            return "float"
        elif isinstance(value, str):
            return "string"
        elif isinstance(value, dict):
            return "struct"
        elif isinstance(value, (list, tuple)):
            if len(value) == 2 and all(isinstance(x, (int, float)) for x in value):
                return "vector2"
            elif len(value) == 3 and all(isinstance(x, (int, float)) for x in value):
                # Could be vector3 or color - check if values are in color range
                if all(isinstance(x, int) and 0 <= x <= 255 for x in value):
                    return "color"
                return "vector3"
            return "list"
        return "string"
    
    def _format_item(self, item):
        """Format an item for display"""
        if self.element_type == "struct":
            if isinstance(item, dict):
                # Show struct fields summary
                if len(item) == 0:
                    return "(empty struct)"
                parts = [f"{k}={v}" for k, v in list(item.items())[:3]]
                if len(item) > 3:
                    parts.append("...")
                return "{" + ", ".join(parts) + "}"
            return str(item)
        elif self.element_type == "vector2":
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                return f"({item[0]}, {item[1]})"
            return "(0, 0)"
        elif self.element_type == "vector3":
            if isinstance(item, (list, tuple)) and len(item) >= 3:
                return f"({item[0]}, {item[1]}, {item[2]})"
            return "(0, 0, 0)"
        elif self.element_type == "color":
            if isinstance(item, (list, tuple)) and len(item) >= 3:
                return f"#{item[0]:02x}{item[1]:02x}{item[2]:02x}"
            return "#000000"
        elif self.element_type == "list":
            if isinstance(item, list):
                return f"[{len(item)} items]"
            return "[]"
        elif self.element_type == "dict":
            if isinstance(item, dict):
                return f"{{{len(item)} keys}}"
            return "{}"
        elif self.element_type == "bool":
            return "True" if item else "False"
        return str(item)
    
    def _add_item(self):
        val = self._get_default_value()
        
        # For structs, try to inherit struct_def from existing items
        if self.element_type == "struct" and self.value:
            # Find first existing struct to get its definition
            for i, existing in enumerate(self.value):
                if isinstance(existing, dict) and existing:
                    # Use this item's struct_def if available, or infer from value
                    if i < len(self.struct_defs) and self.struct_defs[i]:
                        # We have a stored struct_def, use it as template
                        inherited_def = dict(self.struct_defs[i])
                        # Create default values for each field
                        val = {}
                        for field_name, field_type in inherited_def.items():
                            val[field_name] = self._get_default_for_type(field_type)
                        # Pre-populate struct_defs for new item
                        self.struct_defs.append(inherited_def)
                        break
                    else:
                        # Infer from existing value
                        val = {}
                        inferred_def = {}
                        for k, v in existing.items():
                            inferred_def[k] = self._infer_type(v)
                            val[k] = self._get_default_for_type(inferred_def[k])
                        self.struct_defs.append(inferred_def)
                        break
        
        new_val = self._prompt_value(val, is_new=True)
        if new_val is not None:
            self.value.append(new_val)
            self._refresh_list()
    
    def _get_default_for_type(self, type_name):
        """Get default value for a given type name"""
        defaults = {
            "int": 0, "float": 0.0, "string": "", "bool": False,
            "struct": {}, "vector2": [0.0, 0.0], "vector3": [0.0, 0.0, 0.0],
            "color": [255, 255, 255], "list": [], "dict": {}
        }
        return defaults.get(type_name, "")
    
    def _edit_item(self, item):
        idx = self.list_widget.row(item)
        if idx < 0 or idx >= len(self.value):
            return
        new_val = self._prompt_value(self.value[idx], is_new=False, idx=idx)
        if new_val is not None:
            self.value[idx] = new_val
            self._refresh_list()
    
    def _remove_item(self):
        row = self.list_widget.currentRow()
        if row >= 0 and row < len(self.value):
            self.list_widget.takeItem(row)
            del self.value[row]
            if row < len(self.struct_defs):
                del self.struct_defs[row]
            self._refresh_list()
    
    def _get_default_value(self):
        defaults = {
            "int": 0, "float": 0.0, "string": "", "bool": False,
            "struct": {}, "vector2": [0.0, 0.0], "vector3": [0.0, 0.0, 0.0],
            "color": [255, 255, 255], "list": [], "dict": {}
        }
        return defaults.get(self.element_type, "")
    
    def _prompt_value(self, current, is_new=False, idx=None):
        """Prompt for a value based on element type"""
        if self.element_type == "int":
            val, ok = QInputDialog.getInt(self, "Value", "Enter integer:", int(current or 0))
            return val if ok else None
        elif self.element_type == "float":
            val, ok = QInputDialog.getDouble(self, "Value", "Enter float:", float(current or 0), decimals=4)
            return val if ok else None
        elif self.element_type == "bool":
            val, ok = QInputDialog.getItem(self, "Value", "Select:", ["False", "True"], 1 if current else 0, False)
            return (val == "True") if ok else None
        elif self.element_type == "string":
            val, ok = QInputDialog.getText(self, "Value", "Enter string:", text=str(current or ""))
            return val if ok else None
        elif self.element_type == "struct":
            # Get or create struct_def for this item
            if idx is not None and idx < len(self.struct_defs) and self.struct_defs[idx]:
                struct_def = self.struct_defs[idx]
            else:
                # Infer struct_def from current value if possible
                struct_def = {}
                if isinstance(current, dict):
                    for k, v in current.items():
                        struct_def[k] = self._infer_type(v)
            
            dlg = StructEditorDialog(struct_def, current or {}, self)
            if dlg.exec():
                new_def, new_val = dlg.get_result()
                # Store the struct_def
                while len(self.struct_defs) <= (idx if idx is not None else len(self.value)):
                    self.struct_defs.append({})
                if idx is not None:
                    self.struct_defs[idx] = new_def
                else:
                    self.struct_defs.append(new_def)
                return new_val
            return None
        elif self.element_type == "vector2":
            return self._prompt_vector(current, 2)
        elif self.element_type == "vector3":
            return self._prompt_vector(current, 3)
        elif self.element_type == "color":
            return self._prompt_color(current)
        elif self.element_type == "list":
            dlg = ListEditorDialog(current or [], "any", self)
            if dlg.exec():
                return dlg.get_value()
            return None
        elif self.element_type == "dict":
            dlg = DictEditorDialog(current or {}, "any", self)
            if dlg.exec():
                return dlg.get_value()
            return None
        else:
            # Default to string
            val, ok = QInputDialog.getText(self, "Value", "Enter value:", text=str(current or ""))
            return val if ok else None
    
    def _infer_type(self, value):
        """Infer the type of a value for struct field definitions"""
        if isinstance(value, bool):
            return "bool"
        elif isinstance(value, int):
            return "int"
        elif isinstance(value, float):
            return "float"
        elif isinstance(value, str):
            return "string"
        elif isinstance(value, list):
            # Check if it looks like a vector
            if len(value) == 2 and all(isinstance(x, (int, float)) for x in value):
                return "vector2"
            elif len(value) == 3 and all(isinstance(x, (int, float)) for x in value):
                # Could be vector3 or color - check range for color
                if all(isinstance(x, int) and 0 <= x <= 255 for x in value):
                    return "color"  # Assume color if all are 0-255 ints
                return "vector3"
            return "list"
        elif isinstance(value, dict):
            return "struct"
        return "string"
    
    def _prompt_vector(self, current, dims):
        """Prompt for vector2 or vector3"""
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Edit Vector{dims}")
        layout = QFormLayout(dlg)
        
        if not isinstance(current, (list, tuple)):
            current = [0.0] * dims
        
        spins = []
        labels = ["X", "Y", "Z"][:dims]
        for i, label in enumerate(labels):
            spin = QDoubleSpinBox()
            spin.setRange(-999999, 999999)
            spin.setDecimals(4)
            spin.setValue(float(current[i]) if i < len(current) else 0)
            spins.append(spin)
            layout.addRow(label, spin)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addRow(buttons)
        
        if dlg.exec():
            return [s.value() for s in spins]
        return None
    
    def _prompt_color(self, current):
        """Prompt for color"""
        if not isinstance(current, (list, tuple)):
            current = [255, 255, 255]
        color = QColorDialog.getColor(QColor(*current[:3]), self, "Select Color")
        if color.isValid():
            return [color.red(), color.green(), color.blue()]
        return None
    
    def get_value(self):
        return self.value


class DictEditorDialog(QDialog):
    """Dialog for editing dict values"""
    def __init__(self, value, element_type, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Edit Dict<{element_type}>")
        self.setMinimumSize(350, 400)
        self.element_type = element_type
        self.value = dict(value) if value else {}
        
        layout = QVBoxLayout(self)
        
        # Table widget
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Key", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._refresh_table()
        self.table.cellDoubleClicked.connect(self._edit_cell)
        layout.addWidget(self.table)
        
        # Buttons
        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add Key")
        add_btn.clicked.connect(self._add_key)
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._remove_key)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        
        # OK/Cancel
        from PyQt6.QtWidgets import QDialogButtonBox
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def _refresh_table(self):
        self.table.setRowCount(len(self.value))
        for i, (k, v) in enumerate(self.value.items()):
            self.table.setItem(i, 0, QTableWidgetItem(str(k)))
            self.table.setItem(i, 1, QTableWidgetItem(str(v)))
    
    def _add_key(self):
        key, ok = QInputDialog.getText(self, "Add Key", "Key name:")
        if ok and key:
            if key in self.value:
                QMessageBox.warning(self, "Duplicate", f"Key '{key}' already exists")
                return
            defaults = {"int": 0, "float": 0.0, "string": "", "bool": False}
            self.value[key] = defaults.get(self.element_type, "")
            self._refresh_table()
    
    def _edit_cell(self, row, col):
        keys = list(self.value.keys())
        if row >= len(keys):
            return
        key = keys[row]
        
        if col == 0:  # Edit key
            new_key, ok = QInputDialog.getText(self, "Edit Key", "Key:", text=key)
            if ok and new_key and new_key != key:
                if new_key in self.value:
                    QMessageBox.warning(self, "Duplicate", f"Key '{new_key}' exists")
                    return
                self.value[new_key] = self.value.pop(key)
                self._refresh_table()
        else:  # Edit value
            current = self.value[key]
            if self.element_type == "int":
                val, ok = QInputDialog.getInt(self, "Value", "Integer:", int(current or 0))
                if ok: self.value[key] = val
            elif self.element_type == "float":
                val, ok = QInputDialog.getDouble(self, "Value", "Float:", float(current or 0), decimals=4)
                if ok: self.value[key] = val
            elif self.element_type == "bool":
                val, ok = QInputDialog.getItem(self, "Value", "Bool:", ["False", "True"], 1 if current else 0, False)
                if ok: self.value[key] = (val == "True")
            else:
                val, ok = QInputDialog.getText(self, "Value", "String:", text=str(current or ""))
                if ok: self.value[key] = val
            self._refresh_table()
    
    def _remove_key(self):
        row = self.table.currentRow()
        if row >= 0:
            keys = list(self.value.keys())
            if row < len(keys):
                del self.value[keys[row]]
                self._refresh_table()
    
    def get_value(self):
        return self.value


class StructEditorDialog(QDialog):
    """Dialog for editing struct definition and values"""
    
    # All types available for struct fields
    FIELD_TYPES = ["int", "float", "string", "bool", "vector2", "vector3", "color", "list", "dict", "struct"]
    
    def __init__(self, struct_def, value, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Struct")
        self.setMinimumSize(500, 500)
        self.struct_def = dict(struct_def) if struct_def else {}
        self.value = dict(value) if value else {}
        
        layout = QVBoxLayout(self)
        
        # Info label
        info = QLabel("Define struct fields (name, type) and set default values:")
        info.setStyleSheet("color: #888;")
        layout.addWidget(info)
        
        # Table for struct fields
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Field Name", "Type", "Default Value"])
        header = self.table.horizontalHeader()
        if header:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._refresh_table()
        self.table.cellDoubleClicked.connect(self._edit_cell)
        layout.addWidget(self.table)
        
        # Buttons
        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ Add Field")
        add_btn.setStyleSheet("background: #3a5a3a; border: 1px solid #4a7a4a; padding: 4px 8px;")
        add_btn.clicked.connect(self._add_field)
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._remove_field)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        
        # OK/Cancel
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def _refresh_table(self):
        self.table.setRowCount(len(self.struct_def))
        for i, (field, ftype) in enumerate(self.struct_def.items()):
            self.table.setItem(i, 0, QTableWidgetItem(field))
            self.table.setItem(i, 1, QTableWidgetItem(ftype))
            val = self.value.get(field, self._get_default(ftype))
            self.table.setItem(i, 2, QTableWidgetItem(self._format_value(val, ftype)))
    
    def _format_value(self, val, ftype):
        """Format value for display"""
        if ftype == "vector2" and isinstance(val, (list, tuple)):
            return f"({val[0]}, {val[1]})" if len(val) >= 2 else "(0, 0)"
        elif ftype == "vector3" and isinstance(val, (list, tuple)):
            return f"({val[0]}, {val[1]}, {val[2]})" if len(val) >= 3 else "(0, 0, 0)"
        elif ftype == "color" and isinstance(val, (list, tuple)):
            return f"#{val[0]:02x}{val[1]:02x}{val[2]:02x}" if len(val) >= 3 else "#000000"
        elif ftype == "list":
            return f"[{len(val)} items]" if isinstance(val, list) else "[]"
        elif ftype == "dict":
            return f"{{{len(val)} keys}}" if isinstance(val, dict) else "{}"
        elif ftype == "struct":
            return f"({len(val)} fields)" if isinstance(val, dict) else "()"
        elif ftype == "bool":
            return "True" if val else "False"
        return str(val)
    
    def _get_default(self, ftype):
        defaults = {
            "int": 0, "float": 0.0, "string": "", "bool": False,
            "vector2": [0.0, 0.0], "vector3": [0.0, 0.0, 0.0],
            "color": [255, 255, 255], "list": [], "dict": {}, "struct": {}
        }
        return defaults.get(ftype, "")
    
    def _add_field(self):
        print("DEBUG: _add_field called")
        name, ok = QInputDialog.getText(self, "Add Field", "Field name:")
        print(f"DEBUG: name={name}, ok={ok}")
        if ok and name:
            if name in self.struct_def:
                QMessageBox.warning(self, "Duplicate", f"Field '{name}' already exists")
                return
            print(f"DEBUG: Showing type dialog with FIELD_TYPES={self.FIELD_TYPES}")
            ftype, ok2 = QInputDialog.getItem(self, "Field Type", "Select type for field:",
                self.FIELD_TYPES, 0, False)
            print(f"DEBUG: ftype={ftype}, ok2={ok2}")
            if ok2:
                self.struct_def[name] = ftype
                self.value[name] = self._get_default(ftype)
                self._refresh_table()
                # Immediately prompt for value
                self._edit_field_value(name, ftype)
    
    def _edit_cell(self, row, col):
        fields = list(self.struct_def.keys())
        if row >= len(fields):
            return
        field = fields[row]
        ftype = self.struct_def[field]
        
        if col == 0:  # Edit field name
            new_name, ok = QInputDialog.getText(self, "Rename Field", "Name:", text=field)
            if ok and new_name and new_name != field:
                if new_name in self.struct_def:
                    QMessageBox.warning(self, "Duplicate", f"Field '{new_name}' exists")
                    return
                # Rename in both dicts - preserve order
                new_def = {}
                new_val = {}
                for k, v in self.struct_def.items():
                    new_def[new_name if k == field else k] = v
                for k, v in self.value.items():
                    new_val[new_name if k == field else k] = v
                self.struct_def = new_def
                self.value = new_val
                self._refresh_table()
        elif col == 1:  # Edit type
            try:
                idx = self.FIELD_TYPES.index(ftype)
            except ValueError:
                idx = 0
            new_type, ok = QInputDialog.getItem(self, "Change Type", "Type:",
                self.FIELD_TYPES, idx, False)
            if ok and new_type != ftype:
                self.struct_def[field] = new_type
                self.value[field] = self._get_default(new_type)
                self._refresh_table()
        else:  # Edit value
            self._edit_field_value(field, ftype)
    
    def _edit_field_value(self, field, ftype):
        """Edit a field's value based on its type"""
        current = self.value.get(field, self._get_default(ftype))
        
        if ftype == "int":
            val, ok = QInputDialog.getInt(self, "Value", f"{field} (int):", int(current or 0))
            if ok: self.value[field] = val
        elif ftype == "float":
            val, ok = QInputDialog.getDouble(self, "Value", f"{field} (float):", float(current or 0), decimals=4)
            if ok: self.value[field] = val
        elif ftype == "bool":
            val, ok = QInputDialog.getItem(self, "Value", f"{field} (bool):", ["False", "True"], 1 if current else 0, False)
            if ok: self.value[field] = (val == "True")
        elif ftype == "string":
            val, ok = QInputDialog.getText(self, "Value", f"{field} (string):", text=str(current or ""))
            if ok: self.value[field] = val
        elif ftype == "vector2":
            self._edit_vector_value(field, 2, current)
        elif ftype == "vector3":
            self._edit_vector_value(field, 3, current)
        elif ftype == "color":
            self._edit_color_value(field, current)
        elif ftype == "list":
            dlg = ListEditorDialog(current or [], "any", self)
            if dlg.exec(): self.value[field] = dlg.get_value()
        elif ftype == "dict":
            dlg = DictEditorDialog(current or {}, "any", self)
            if dlg.exec(): self.value[field] = dlg.get_value()
        elif ftype == "struct":
            # Nested struct - just use simple dict editor for now
            dlg = DictEditorDialog(current or {}, "any", self)
            if dlg.exec(): self.value[field] = dlg.get_value()
        
        self._refresh_table()
    
    def _edit_vector_value(self, field, dims, current):
        """Edit vector2 or vector3 value"""
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Edit {field} (Vector{dims})")
        layout = QFormLayout(dlg)
        
        if not isinstance(current, (list, tuple)):
            current = [0.0] * dims
        
        spins = []
        labels = ["X", "Y", "Z"][:dims]
        for i, label in enumerate(labels):
            spin = QDoubleSpinBox()
            spin.setRange(-999999, 999999)
            spin.setDecimals(4)
            spin.setValue(float(current[i]) if i < len(current) else 0)
            spins.append(spin)
            layout.addRow(label, spin)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addRow(buttons)
        
        if dlg.exec():
            self.value[field] = [s.value() for s in spins]
    
    def _edit_color_value(self, field, current):
        """Edit color value using color picker"""
        if not isinstance(current, (list, tuple)):
            current = [255, 255, 255]
        color = QColorDialog.getColor(QColor(*current[:3]), self, f"Select Color for {field}")
        if color.isValid():
            self.value[field] = [color.red(), color.green(), color.blue()]
    
    def _remove_field(self):
        row = self.table.currentRow()
        if row >= 0:
            fields = list(self.struct_def.keys())
            if row < len(fields):
                field = fields[row]
                del self.struct_def[field]
                if field in self.value:
                    del self.value[field]
                self._refresh_table()
    
    def get_result(self):
        return self.struct_def, self.value


class VariablePanelWidget(QWidget):
    """UE5-style variable panel with inline editing and complex types"""
    
    # All supported types
    ALL_TYPES = ["int", "float", "string", "bool", "list", "dict", "struct", "vector2", "vector3", "color"]
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.variables = {}  # name -> VariableRowWidget
        self._var_counter = 0  # For auto-naming
        self._last_type = "int"  # Remember last type used
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        
        header = QLabel("Variables", self)
        header.setStyleSheet("font-weight: bold; color: #e0e0e0; font-size: 12pt;")
        layout.addWidget(header)
        
        hint = QLabel("Drag to canvas • Double-click to edit", self)
        hint.setStyleSheet("color: #888; font-size: 9pt; font-style: italic;")
        layout.addWidget(hint)
        
        # Add button
        add_btn = QPushButton("+ Variable")
        add_btn.setStyleSheet("""
            QPushButton {
                background: #3a5a3a;
                border: 1px solid #4a7a4a;
                border-radius: 3px;
                padding: 6px 12px;
                color: #e0e0e0;
                font-weight: bold;
            }
            QPushButton:hover { background: #4a6a4a; }
        """)
        add_btn.clicked.connect(self._add_variable)
        layout.addWidget(add_btn)
        
        # Scroll area for variable rows
        scroll_widget = QWidget()
        self.var_layout = QVBoxLayout(scroll_widget)
        self.var_layout.setSpacing(4)
        self.var_layout.setContentsMargins(0, 4, 0, 4)
        self.var_layout.addStretch()
        
        scroll_area = QScrollArea()
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        layout.addWidget(scroll_area)
    
    def _generate_unique_name(self):
        """Generate a unique variable name like NewVar_1, NewVar_2, etc."""
        while True:
            self._var_counter += 1
            name = f"NewVar_{self._var_counter}"
            if name not in self.variables:
                return name
    
    def _add_variable(self):
        """Add a new variable with auto-generated name and last used type"""
        var_name = self._generate_unique_name()
        var_type = self._last_type
        
        # Get default value for type
        defaults = {
            "int": 0, "float": 0.0, "string": "", "bool": False,
            "list": [], "dict": {}, "struct": {},
            "vector2": [0.0, 0.0], "vector3": [0.0, 0.0, 0.0],
            "color": [255, 255, 255]
        }
        value = defaults.get(var_type, None)
        element_type = "string" if var_type in ("list", "dict") else None
        
        self._create_variable_row(var_name, var_type, value, element_type)
    
    def _create_variable_row(self, var_name, var_type, value, element_type=None, struct_def=None):
        """Create and register a variable row widget"""
        row = VariableRowWidget(var_name, var_type, value, element_type, struct_def, self)
        row.deleted.connect(self._delete_variable)
        row.changed.connect(lambda: self._on_variable_changed(row))
        
        # Insert before the trailing stretch
        self.var_layout.insertWidget(self.var_layout.count() - 1, row)
        self.variables[var_name] = row
        
        # Sync to canvas
        self._sync_to_canvas(var_name, row)
        
        # Remember type for next add
        self._last_type = var_type
        
        return row
    
    def _sync_to_canvas(self, var_name, row):
        """Sync variable to canvas graph_variables"""
        if hasattr(self.main_window, 'canvas'):
            if not hasattr(self.main_window.canvas, 'graph_variables'):
                self.main_window.canvas.graph_variables = {}
            self.main_window.canvas.graph_variables[var_name] = row.get_data()
    
    def _rename_variable_internal(self, old_name, new_name):
        """Handle variable rename from row widget"""
        if old_name in self.variables:
            row = self.variables.pop(old_name)
            self.variables[new_name] = row
            # Update canvas
            if hasattr(self.main_window, 'canvas') and hasattr(self.main_window.canvas, 'graph_variables'):
                if old_name in self.main_window.canvas.graph_variables:
                    data = self.main_window.canvas.graph_variables.pop(old_name)
                    self.main_window.canvas.graph_variables[new_name] = data
    
    def _update_variable_internal(self, var_name):
        """Handle variable update from row widget"""
        if var_name in self.variables:
            row = self.variables[var_name]
            self._sync_to_canvas(var_name, row)
    
    def _on_variable_changed(self, row):
        """Called when any variable property changes"""
        self._sync_to_canvas(row.var_name, row)
    
    def _delete_variable(self, var_name):
        """Delete a variable"""
        if var_name in self.variables:
            row = self.variables.pop(var_name)
            self.var_layout.removeWidget(row)
            row.deleteLater()
            
            # Remove from canvas
            if hasattr(self.main_window, 'canvas') and hasattr(self.main_window.canvas, 'graph_variables'):
                if var_name in self.main_window.canvas.graph_variables:
                    del self.main_window.canvas.graph_variables[var_name]
    
    def load_variables(self, variables):
        """Load variables from saved graph data"""
        # Remove existing rows
        for row in list(self.variables.values()):
            self.var_layout.removeWidget(row)
            row.deleteLater()
        self.variables.clear()
        
        if hasattr(self.main_window, 'canvas'):
            self.main_window.canvas.graph_variables = {}
        
        if not isinstance(variables, dict):
            return
        
        for var_name, info in variables.items():
            if not isinstance(info, dict):
                continue
            var_type = info.get('type', 'string')
            if var_type not in self.ALL_TYPES:
                var_type = 'string'
            value = info.get('value')
            element_type = info.get('element_type')
            struct_def = info.get('struct_def')
            self._create_variable_row(var_name, var_type, value, element_type, struct_def)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NodeCanvas Professional")
        self.setWindowIcon(QIcon(os.path.join(os.path.dirname(__file__), "images", "icon.ico")))
        self.resize(1600, 1000)

        # ensure templates are loaded from disk (consistent registry)
        try:
            load_templates()
        except Exception:
            pass

        # Create tab widget for main content
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: none; }
            QTabBar::tab {
                background: #2a2a2a; color: #888; padding: 8px 18px;
                border: none; border-bottom: 2px solid transparent;
                font-size: 12px; font-weight: bold;
            }
            QTabBar::tab:selected { color: #4fc3f7; border-bottom: 2px solid #4fc3f7; background: #1e1e1e; }
            QTabBar::tab:hover { color: #ccc; background: #333; }
        """)
        # Ensure the main tab widget expands with the window
        try:
            self.tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        except Exception:
            pass
        self.setCentralWidget(self.tabs)
        
        # Logic tab (formerly Canvas) - Node graph editor
        self.canvas = LogicEditor()
        self.canvas.main_window = self
        self.tabs.addTab(self.canvas, "Logic")
        
        # Global Docks (persistent across tabs)
        self.explorer = SceneExplorerPanel(self)
        self.explorer.set_workspace_root(WORKSPACE_ROOT) # Set default project root
        self.explorer.file_selected.connect(self._on_explorer_file_selected)
        self.properties = ObjectPropertiesPanel(self)
        
        # UI Builder (created early, injected into Viewport tab)
        self.ui_builder = UIBuilderWidget()
        self.ui_builder.set_main_window(self)
        
        # Viewport tab (replaces old Game + UI tabs)
        self.scene_editor = SceneEditorWidget(self, self.explorer, self.properties)
        # Injected global panels - redundant but kept for back-compat with older methods
        self.scene_editor.explorer = self.explorer
        self.scene_editor.properties = self.properties
        
        self.scene_editor.set_ui_builder(self.ui_builder)
        self.scene_editor.mode_changed.connect(self._on_viewport_mode_changed)
        self.game_tab = self.scene_editor
        self.tabs.addTab(self.game_tab, "Viewport")
        
        # Anim tab - Timeline editor
        self.anim_tab = self._create_anim_tab()
        self.tabs.addTab(self.anim_tab, "Anim")
        
        # Connect tab change to dock switching
        self.tabs.currentChanged.connect(self.on_tab_changed)

        toolbar = QToolBar("Main")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

        save_act = QAction("Save", self)
        save_act.triggered.connect(self.save)
        toolbar.addAction(save_act)

        load_act = QAction("Load", self)
        load_act.triggered.connect(self.load)
        toolbar.addAction(load_act)

        create_act = QAction("Create Node", self)
        create_act.triggered.connect(self.create_node)
        toolbar.addAction(create_act)

        run_act = QAction("Run Graph", self)
        run_act.triggered.connect(self.run_graph)
        toolbar.addAction(run_act)
        
        # Add step execution controls
        toolbar.addSeparator()
        
        step_act = QAction("Step", self)
        step_act.setToolTip("Execute next node (Step-by-step mode)")
        step_act.triggered.connect(self.step_execution)
        toolbar.addAction(step_act)
        
        reset_act = QAction("Reset", self)
        reset_act.setToolTip("Reset execution state")
        reset_act.triggered.connect(self.reset_execution)
        toolbar.addAction(reset_act)
        
        toolbar.addSeparator()
        
        # Live execution toggle
        self.live_mode_act = QAction("🔴 Live Mode", self)
        self.live_mode_act.setCheckable(True)
        self.live_mode_act.setToolTip("Auto-execute graph when values change")
        self.live_mode_act.toggled.connect(self.toggle_live_mode)
        toolbar.addAction(self.live_mode_act)
        
        toolbar.addSeparator()
        
        # Code generation
        codegen_act = QAction("Generate Code", self)
        codegen_act.setToolTip("Generate standalone code from graph")
        codegen_act.triggered.connect(self.generate_code)
        toolbar.addAction(codegen_act)
        
        toolbar.addSeparator()

        settings_act = QAction("Settings", self)
        settings_act.triggered.connect(self.open_settings)
        toolbar.addAction(settings_act)
        
        # Execution state
        self.execution_context = None
        self.execution_backend = None
        self.is_stepping = False
        self.live_mode_enabled = False
        
        # Debounce timer for live execution
        self.live_exec_timer = QTimer()
        self.live_exec_timer.setSingleShot(True)
        self.live_exec_timer.timeout.connect(self.execute_live)

        self._setup_docks()

    def _create_game_tab(self) -> QWidget:
        """Create the Game tab — delegates to SceneEditorWidget (kept for compatibility)."""
        return SceneEditorWidget()
    
    def _create_anim_tab(self) -> QWidget:
        """Create the Anim tab - Animation DATA editor.
        
        NOT a duplicate graph canvas. This edits:
        - State machines (visual state nodes + transitions)
        - Blend spaces
        - Animation properties
        
        Logic tab controls playback via Play/Stop/Blend nodes.
        """
        widget = QWidget()
        main_layout = QHBoxLayout(widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Left panel - State list
        left_panel = QWidget()
        # Allow left panel to be resized by using a minimum width rather than fixed
        left_panel.setMinimumWidth(160)
        left_panel.setStyleSheet("background: #252525; border-right: 1px solid #444;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        
        # Mode tabs
        mode_tabs = QTabWidget()
        mode_tabs.setStyleSheet("""
            QTabWidget::pane { border: none; }
            QTabBar::tab { 
                background: #333; color: #888; padding: 8px 15px; 
                border: none; border-bottom: 2px solid transparent;
            }
            QTabBar::tab:selected { color: #4fc3f7; border-bottom: 2px solid #4fc3f7; }
        """)
        
        # States list
        states_widget = QWidget()
        states_layout = QVBoxLayout(states_widget)
        states_layout.setContentsMargins(0, 10, 0, 0)
        
        self.anim_state_list = QListWidget()
        self.anim_state_list.setStyleSheet("""
            QListWidget { background: #1e1e1e; border: none; color: #e0e0e0; }
            QListWidget::item { padding: 8px; border-radius: 4px; }
            QListWidget::item:selected { background: #3a5a7a; }
            QListWidget::item:hover { background: #333; }
        """)
        self.anim_state_list.addItems(["Idle", "Walk", "Run", "Jump"])
        self.anim_state_list.itemClicked.connect(self._on_anim_state_selected)
        states_layout.addWidget(self.anim_state_list)
        
        add_state_btn = QPushButton("+ Add State")
        add_state_btn.setStyleSheet("""
            QPushButton { background: #4CAF50; color: white; border: none; 
                         padding: 8px; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background: #66BB6A; }
        """)
        add_state_btn.clicked.connect(self._add_anim_state)
        states_layout.addWidget(add_state_btn)
        
        del_state_btn = QPushButton("- Delete State")
        del_state_btn.setStyleSheet("""
            QPushButton { background: #f44336; color: white; border: none; 
                         padding: 8px; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background: #e53935; }
        """)
        del_state_btn.clicked.connect(self._delete_anim_state)
        states_layout.addWidget(del_state_btn)
        
        mode_tabs.addTab(states_widget, "States")
        
        # Blend spaces list
        blend_widget = QWidget()
        blend_layout = QVBoxLayout(blend_widget)
        blend_layout.setContentsMargins(0, 10, 0, 0)
        
        self.blend_list = QListWidget()
        self.blend_list.setStyleSheet(self.anim_state_list.styleSheet())
        self.blend_list.addItems(["Locomotion", "AimOffset"])
        blend_layout.addWidget(self.blend_list)
        
        add_blend_btn = QPushButton("+ Add Blend Space")
        add_blend_btn.setStyleSheet(add_state_btn.styleSheet())
        blend_layout.addWidget(add_blend_btn)
        
        mode_tabs.addTab(blend_widget, "Blend")
        
        left_layout.addWidget(mode_tabs)
        main_layout.addWidget(left_panel)
        
        # Center - State Machine View (visual graph of states)
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        
        # Toolbar
        toolbar = QWidget()
        toolbar.setFixedHeight(40)
        toolbar.setStyleSheet("background: #2a2a2a; border-bottom: 1px solid #444;")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 5, 10, 5)
        
        preview_btn = QPushButton("▶ Preview")
        preview_btn.setStyleSheet("""
            QPushButton { background: #3a3a3a; border: 1px solid #555; 
                         border-radius: 4px; color: #e0e0e0; padding: 5px 15px; }
            QPushButton:hover { background: #4a4a4a; }
        """)
        toolbar_layout.addWidget(preview_btn)
        toolbar_layout.addStretch()
        
        info_label = QLabel("State Machine View • Click states to edit")
        info_label.setStyleSheet("color: #666; font-size: 11px;")
        toolbar_layout.addWidget(info_label)
        
        center_layout.addWidget(toolbar)
        
        # State machine canvas (simple QGraphicsView for state visualization)
        self.state_machine_view = QGraphicsView()
        self.state_machine_scene = QGraphicsScene()
        self.state_machine_view.setScene(self.state_machine_scene)
        self.state_machine_view.setStyleSheet("background: #1a1a1a; border: none;")
        self.state_machine_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Initialize animation data BEFORE drawing
        self._anim_data = {
            "states": {
                "Idle": {"clip": "idle_anim", "speed": 1.0, "loop": True},
                "Walk": {"clip": "walk_anim", "speed": 1.0, "loop": True},
                "Run": {"clip": "run_anim", "speed": 1.5, "loop": True},
                "Jump": {"clip": "jump_anim", "speed": 1.0, "loop": False}
            },
            "transitions": [
                {"from": "Idle", "to": "Walk", "condition": "speed > 0.1"},
                {"from": "Walk", "to": "Run", "condition": "speed > 0.5"},
                {"from": "Any", "to": "Jump", "condition": "isJumping"}
            ]
        }
        self._current_anim_state = None
        
        # Draw state machine
        self._draw_state_machine()
        
        center_layout.addWidget(self.state_machine_view)
        main_layout.addWidget(center_widget, 1)
        
        # Right panel - Properties
        right_panel = QWidget()
        # Use minimum width so layouts can still shrink/grow
        right_panel.setMinimumWidth(200)
        right_panel.setStyleSheet("background: #252525; border-left: 1px solid #444;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 10, 10, 10)
        
        props_label = QLabel("Properties")
        props_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #e0e0e0;")
        right_layout.addWidget(props_label)
        
        # State properties form
        form_widget = QWidget()
        form_layout = QFormLayout(form_widget)
        form_layout.setSpacing(10)
        form_layout.setContentsMargins(0, 10, 0, 0)
        
        self.state_name_edit = QLineEdit("Idle")
        self.state_name_edit.setStyleSheet("background: #333; color: #e0e0e0; border: 1px solid #555; padding: 5px;")
        form_layout.addRow("Name:", self.state_name_edit)
        
        self.state_clip_combo = QComboBox()
        self.state_clip_combo.addItems(["idle_anim", "walk_anim", "run_anim", "jump_anim"])
        self.state_clip_combo.setStyleSheet("background: #333; color: #e0e0e0; border: 1px solid #555; padding: 5px;")
        form_layout.addRow("Clip:", self.state_clip_combo)
        
        self.state_speed_spin = QDoubleSpinBox()
        self.state_speed_spin.setRange(0.1, 10.0)
        self.state_speed_spin.setValue(1.0)
        self.state_speed_spin.setStyleSheet("background: #333; color: #e0e0e0; border: 1px solid #555; padding: 5px;")
        form_layout.addRow("Speed:", self.state_speed_spin)
        
        self.state_loop_check = QCheckBox()
        self.state_loop_check.setChecked(True)
        form_layout.addRow("Loop:", self.state_loop_check)
        
        # Connect property change signals
        self.state_name_edit.editingFinished.connect(self._on_state_name_changed)
        self.state_clip_combo.currentTextChanged.connect(self._on_state_clip_changed)
        self.state_speed_spin.valueChanged.connect(self._on_state_speed_changed)
        self.state_loop_check.stateChanged.connect(self._on_state_loop_changed)
        
        right_layout.addWidget(form_widget)
        
        # Transitions section
        trans_label = QLabel("Transitions")
        trans_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #888; margin-top: 20px;")
        right_layout.addWidget(trans_label)
        
        self.transitions_list = QListWidget()
        self.transitions_list.setMaximumHeight(150)
        self.transitions_list.setStyleSheet(self.anim_state_list.styleSheet())
        right_layout.addWidget(self.transitions_list)
        
        add_trans_btn = QPushButton("+ Add Transition")
        add_trans_btn.setStyleSheet("""
            QPushButton { background: #555; color: #e0e0e0; border: none; 
                         padding: 6px; border-radius: 4px; }
            QPushButton:hover { background: #666; }
        """)
        add_trans_btn.clicked.connect(self._add_anim_transition)
        right_layout.addWidget(add_trans_btn)
        
        right_layout.addStretch()
        main_layout.addWidget(right_panel)
        
        return widget
    
    def _draw_state_machine(self):
        """Draw visual state machine nodes based on actual animation data"""
        from PyQt6.QtCore import QRectF
        from PyQt6.QtGui import QBrush, QPen, QColor, QFont
        import math
        
        self.state_machine_scene.clear()
        
        # Get states from actual data
        state_names = list(self._anim_data.get("states", {}).keys())
        if not state_names:
            return
        
        # Auto-layout states in a circle
        center_x, center_y = 0, 0
        radius = 120
        states = {}
        for i, name in enumerate(state_names):
            angle = (2 * math.pi * i) / len(state_names) - math.pi / 2
            x = center_x + radius * math.cos(angle)
            y = center_y + radius * math.sin(angle)
            states[name] = (x, y)
        
        # Draw transitions (arrows with direction)
        trans_pen = QPen(QColor("#888"), 2)
        arrow_brush = QBrush(QColor("#888"))
        for trans in self._anim_data.get("transitions", []):
            from_state = trans.get("from")
            to_state = trans.get("to")
            if from_state in states and to_state in states:
                fx, fy = states[from_state]
                tx, ty = states[to_state]
                
                # Calculate direction
                dx = tx - fx
                dy = ty - fy
                length = math.sqrt(dx*dx + dy*dy)
                if length == 0:
                    continue
                    
                # Normalize
                dx, dy = dx/length, dy/length
                
                # Offset from center to edge of ellipse (40 width, 30 height approx)
                start_x = fx + dx * 40
                start_y = fy + dy * 30
                end_x = tx - dx * 40
                end_y = ty - dy * 30
                
                # Draw line
                self.state_machine_scene.addLine(start_x, start_y, end_x, end_y, trans_pen)
                
                # Draw arrowhead
                arrow_size = 10
                angle = math.atan2(dy, dx)
                arrow_p1_x = end_x - arrow_size * math.cos(angle - math.pi/6)
                arrow_p1_y = end_y - arrow_size * math.sin(angle - math.pi/6)
                arrow_p2_x = end_x - arrow_size * math.cos(angle + math.pi/6)
                arrow_p2_y = end_y - arrow_size * math.sin(angle + math.pi/6)
                
                # Draw arrow lines
                self.state_machine_scene.addLine(end_x, end_y, arrow_p1_x, arrow_p1_y, trans_pen)
                self.state_machine_scene.addLine(end_x, end_y, arrow_p2_x, arrow_p2_y, trans_pen)
        
        # Draw state nodes
        for name, pos in states.items():
            # Highlight current state
            is_current = (name == self._current_anim_state)
            border_color = "#4fc3f7" if not is_current else "#ff9800"
            fill_color = "#2a4a5a" if not is_current else "#5a4a2a"
            
            # Circle
            ellipse = self.state_machine_scene.addEllipse(
                pos[0]-40, pos[1]-30, 80, 60,
                QPen(QColor(border_color), 3 if is_current else 2),
                QBrush(QColor(fill_color))
            )
            ellipse.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
            ellipse.setData(0, name)  # Store state name
            
            # Label
            text = self.state_machine_scene.addText(name, QFont("Segoe UI", 10))
            text.setDefaultTextColor(QColor("#ffffff"))
            text.setPos(pos[0] - text.boundingRect().width()/2, pos[1] - 10)
    
    def _on_anim_state_selected(self, item):
        """Handle state selection from list"""
        state_name = item.text()
        self._select_anim_state(state_name)
    
    def _select_anim_state(self, state_name):
        """Select and show state properties"""
        self._current_anim_state = state_name
        if state_name in self._anim_data.get("states", {}):
            state = self._anim_data["states"][state_name]
            self.state_name_edit.setText(state_name)
            idx = self.state_clip_combo.findText(state.get("clip", ""))
            if idx >= 0:
                self.state_clip_combo.setCurrentIndex(idx)
            self.state_speed_spin.setValue(state.get("speed", 1.0))
            self.state_loop_check.setChecked(state.get("loop", True))
            
            # Update transitions list for this state
            self.transitions_list.clear()
            for trans in self._anim_data.get("transitions", []):
                if trans.get("from") == state_name or trans.get("from") == "Any":
                    self.transitions_list.addItem(f"→ {trans['to']} ({trans.get('condition', '')})")
    
    def _on_state_name_changed(self):
        """Handle state name edit"""
        if not hasattr(self, '_current_anim_state'):
            return
        old_name = self._current_anim_state
        new_name = self.state_name_edit.text()
        if old_name != new_name and old_name in self._anim_data.get("states", {}):
            # Rename state
            self._anim_data["states"][new_name] = self._anim_data["states"].pop(old_name)
            self._current_anim_state = new_name
            # Update list
            for i in range(self.anim_state_list.count()):
                if self.anim_state_list.item(i).text() == old_name:
                    self.anim_state_list.item(i).setText(new_name)
                    break
            self._draw_state_machine()
    
    def _on_state_clip_changed(self, clip):
        """Handle clip selection change"""
        if hasattr(self, '_current_anim_state') and self._current_anim_state:
            if self._current_anim_state in self._anim_data.get("states", {}):
                self._anim_data["states"][self._current_anim_state]["clip"] = clip
    
    def _on_state_speed_changed(self, speed):
        """Handle speed change"""
        if hasattr(self, '_current_anim_state') and self._current_anim_state:
            if self._current_anim_state in self._anim_data.get("states", {}):
                self._anim_data["states"][self._current_anim_state]["speed"] = speed
    
    def _on_state_loop_changed(self, checked):
        """Handle loop toggle"""
        if hasattr(self, '_current_anim_state') and self._current_anim_state:
            if self._current_anim_state in self._anim_data.get("states", {}):
                self._anim_data["states"][self._current_anim_state]["loop"] = checked
    
    def _add_anim_state(self):
        """Add a new animation state"""
        name, ok = QInputDialog.getText(self, "Add State", "State name:")
        if ok and name:
            self.anim_state_list.addItem(name)
            self._anim_data.setdefault("states", {})[name] = {
                "clip": "", "speed": 1.0, "loop": True
            }
            self._draw_state_machine()
    
    def _delete_anim_state(self):
        """Delete the selected animation state"""
        current_item = self.anim_state_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Select a state to delete")
            return
        
        state_name = current_item.text()
        
        # Confirm deletion
        reply = QMessageBox.question(self, "Delete State", 
            f"Delete state '{state_name}' and all its transitions?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            # Remove from data
            if state_name in self._anim_data.get("states", {}):
                del self._anim_data["states"][state_name]
            
            # Remove transitions involving this state
            self._anim_data["transitions"] = [
                t for t in self._anim_data.get("transitions", [])
                if t.get("from") != state_name and t.get("to") != state_name
            ]
            
            # Remove from list
            row = self.anim_state_list.row(current_item)
            self.anim_state_list.takeItem(row)
            
            # Clear selection
            self._current_anim_state = None
            self.transitions_list.clear()
            
            # Redraw
            self._draw_state_machine()
    
    def _add_anim_transition(self):
        """Add a transition from current state"""
        if not hasattr(self, '_current_anim_state') or not self._current_anim_state:
            QMessageBox.warning(self, "No State", "Select a state first")
            return
        
        # Get target state
        states = list(self._anim_data.get("states", {}).keys())
        target, ok = QInputDialog.getItem(self, "Add Transition", "To state:", states, 0, False)
        if ok and target:
            condition, ok2 = QInputDialog.getText(self, "Condition", "Condition (e.g., speed > 0.1):")
            if ok2:
                self._anim_data.setdefault("transitions", []).append({
                    "from": self._current_anim_state,
                    "to": target,
                    "condition": condition,
                    "duration": 0.2
                })
                self.transitions_list.addItem(f"→ {target} ({condition})")
                self._draw_state_machine()
    
    def get_anim_data(self):
        """Get animation data for saving"""
        return self._anim_data if hasattr(self, '_anim_data') else {}
    
    def load_anim_data(self, data):
        """Load animation data"""
        self._anim_data = data or {}
        # Update state list
        self.anim_state_list.clear()
        for state_name in self._anim_data.get("states", {}).keys():
            self.anim_state_list.addItem(state_name)
        self._draw_state_machine()

    def save(self):
        # Determine default directory
        default_dir = getattr(self, 'project_root', str(WORKSPACE_ROOT / "py_editor" / "nodes" / "graphs"))
        
        current_tab = self.tabs.currentIndex()
        if current_tab == 2: # Anim tab
            default_filter = "Animation Files (*.anim)"
        elif current_tab == 1:
            if hasattr(self, 'scene_editor') and self.scene_editor._current_mode == 'UI':
                default_filter = "UI Layout Files (*.ui)"
            else:
                default_filter = "Scene Files (*.scene)"
        else:  # Logic tab (0)
            default_filter = "Logic Files (*.logic)"
        
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save Project",
            default_dir,
            "Logic Files (*.logic);;Scene Files (*.scene);;Animation Files (*.anim);;UI Layout Files (*.ui);;JSON Files (*.json);;All Files (*)",
            default_filter
        )
        if not file_path:
            return
        
        # Add extension if not present
        p = Path(file_path)
        if not p.suffix:
            if "*.logic" in selected_filter:
                file_path += ".logic"
            elif "*.anim" in selected_filter:
                file_path += ".anim"
            elif "*.ui" in selected_filter:
                file_path += ".ui"
            elif "*.scene" in selected_filter:
                file_path += ".scene"
            else:
                file_path += ".json"
        
        # --- Handle .scene Save ---
        if file_path.endswith('.scene'):
            scene_data = {
                'objects': [obj.to_dict() for obj in self.scene_editor.viewport.scene_objects],
                'camera': {
                    'pos': self.scene_editor.viewport._cam3d.pos,
                    'pitch': self.scene_editor.viewport._cam3d.pitch,
                    'yaw': self.scene_editor.viewport._cam3d.yaw
                }
            }
            try:
                with open(file_path, 'w') as f:
                    json.dump(scene_data, f, indent=4)
                QMessageBox.information(self, "Success", f"Scene saved to {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save scene: {e}")
            return
        
        # Export the full graph from canvas
        graph_data = self.canvas.export_graph()
        
        # Also include UI data
        ui_data = self.ui_builder.canvas.export_ui()
        graph_data['ui'] = ui_data
        
        # Include animation data
        anim_data = self.get_anim_data()
        if anim_data:
            graph_data['animation'] = anim_data
        
        # Infer interface from semantic entry/exit nodes
        # Events: OnStart, OnTick, Custom Event (with visibility)
        # Exit points: Return nodes define outputs
        events = {}  # Dict of event name -> {visibility, nodeId}
        outputs = {}  # Return values become outputs
        
        for node_data in graph_data.get('nodes', []):
            template_name = node_data.get('template')
            pin_values = node_data.get('pin_values', node_data.get('values', {}))
            
            # Built-in events (always public)
            if template_name in ('OnStart', 'OnTick', 'Event_Tick'):
                events[template_name] = {'visibility': 'public', 'nodeId': node_data.get('id')}
            elif template_name and template_name.startswith('OnEvent'):
                events[template_name] = {'visibility': 'public', 'nodeId': node_data.get('id')}
            
            # Custom Events with visibility
            elif template_name == 'Custom Event':
                event_name = pin_values.get('name', 'MyEvent')
                visibility = pin_values.get('visibility', 'public')
                events[event_name] = {
                    'visibility': visibility,
                    'nodeId': node_data.get('id')
                }
            
            # Return nodes define outputs
            elif template_name == 'Return':
                node_id = node_data.get('id', 0)
                output_name = 'return' if node_id == 0 else f'return_{node_id}'
                outputs[output_name] = {
                    'type': 'any',
                    'nodeId': node_id
                }
        
        # Build interface section - events are the interface
        graph_data['interface'] = {
            'name': Path(file_path).stem,
            'type': 'anim' if '.anim' in file_path else ('ui' if '.ui' in file_path else 'logic'),
            'version': '1.0',
            'events': events,
            'outputs': outputs,
        }
        
        try:
            import os
            
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
            temp_path = file_path + ".tmp"
            
            # Write to temporary file first (ensure strict disk flush)
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(graph_data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
                
            # Final safety check: ensure the file isn't empty before replacing
            if Path(temp_path).stat().st_size == 0:
                raise IOError(f"Refusing to save zero-byte file (serialization error): {temp_path}")
                
            # Perform atomic replacement to prevent zero-byte corruptions
            os.replace(temp_path, file_path)
            
            self.current_file = file_path
            self.setWindowTitle(f"NodeCanvas - {Path(file_path).name}")
            
            # Refresh explorer if file is in workspace
            if hasattr(self, 'explorer'):
                self.explorer.refresh_assets()
            
            print(f"Saved project to {file_path}")
            QMessageBox.information(self, "Success", f"Project saved to:\n{file_path}")
        except Exception as e:
            print(f"Error saving project: {e}")
            QMessageBox.warning(self, "Error", f"Failed to save project:\n{e}")

    def load(self):
        # Determine default directory
        default_dir = getattr(self, 'project_root', str(WORKSPACE_ROOT / "py_editor" / "nodes" / "graphs"))
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Project",
            default_dir,
            "All NodeCanvas Files (*.logic *.anim *.ui *.scene *.json);;Logic Files (*.logic);;Scene Files (*.scene);;Animation Files (*.anim);;UI Layout Files (*.ui);;JSON Files (*.json);;All Files (*)"
        )
        if not file_path:
            return
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                graph_data = json.load(f)
            
            # --- Handle .scene Load ---
            if file_path.endswith('.scene'):
                self.scene_editor.load_scene_data(graph_data)
                self.tabs.setCurrentIndex(1) # Switch to viewport
                self.current_file = file_path
                self.setWindowTitle(f"NodeCanvas - {Path(file_path).name}")
                QMessageBox.information(self, "Success", f"Scene loaded from:\n{file_path}")
                return

            self.canvas.load_graph(graph_data)
            if hasattr(self, 'variable_panel'):
                self.variable_panel.load_variables(graph_data.get('variables', {}))
            
            # Also load UI data if present
            if 'ui' in graph_data:
                self.ui_builder.canvas.load_ui(graph_data['ui'])
                # Refresh the screen list
                if hasattr(self, 'screen_list'):
                    self.screen_list.refresh_list()
                # Sync the form size dropdown
                if hasattr(self, 'ui_props'):
                    self.ui_props.sync_form_size()
            
            # Load animation data if present
            if 'animation' in graph_data:
                self.load_anim_data(graph_data['animation'])
            
            # Switch to appropriate tab based on file type
            ext = Path(file_path).suffix.lower()
            if ext == '.anim':
                self.tabs.setCurrentIndex(2)  # Anim tab
            elif ext == '.ui':
                self.tabs.setCurrentIndex(1)  # Viewport tab in UI mode
                if hasattr(self, 'scene_editor'):
                    self.scene_editor.toolbar.mode_combo.setCurrentText('UI')
            else:
                self.tabs.setCurrentIndex(0)  # Logic tab
            
            # Update Master Explorer
            if hasattr(self, 'explorer'):
                self.explorer.refresh_assets()
            
            self.current_file = file_path
            self.setWindowTitle(f"NodeCanvas - {Path(file_path).name}")
            

            
            print(f"Loaded project from {file_path}")
            QMessageBox.information(self, "Success", f"Project loaded from:\n{file_path}")
        except Exception as e:
            print(f"Error loading project: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self, "Error", f"Failed to load project:\n{e}")

    def _on_explorer_file_selected(self, file_path):
        """Handle file selection from Master Explorer"""
        p = Path(file_path)
        ext = p.suffix.lower()
        if ext == '.scene':
            # Fast-path for scene loading
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.scene_editor.load_scene_data(data)
                self.tabs.setCurrentIndex(1)
                self.current_file = file_path
                self.setWindowTitle(f"NodeCanvas - {p.name}")
            except Exception as e: print(f"Failed to load scene: {e}")
        elif ext in ('.logic', '.anim', '.ui', '.json'):
            # Use existing Load logic (refactor to avoid dialog)
            self._load_file_direct(file_path)

    def _load_file_direct(self, file_path):
        """Internal helper to load a project file without a dialog"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.canvas.load_graph(data)
            if hasattr(self, 'variable_panel'):
                self.variable_panel.load_variables(data.get('variables', {}))
            
            if 'ui' in data:
                self.ui_builder.canvas.load_ui(data['ui'])
                if hasattr(self, 'screen_list'): self.screen_list.refresh_list()
            if 'animation' in data:
                self.load_anim_data(data['animation'])
            
            ext = Path(file_path).suffix.lower()
            if ext == '.anim': self.tabs.setCurrentIndex(2)
            elif ext == '.ui':
                self.tabs.setCurrentIndex(1)
                self.scene_editor.toolbar.mode_combo.setCurrentText('UI')
            else: self.tabs.setCurrentIndex(0)
            
            self.current_file = file_path
            self.setWindowTitle(f"NodeCanvas - {Path(file_path).name}")
            self.explorer.refresh_assets()
            
        except Exception as e:
            print(f"Error loading {file_path}: {e}")

    def create_node(self):
        # open node editor dialog to create a template
        d = NodeEditorDialog(self)
        if d.exec():
            # reload templates so menu updates
            load_templates()
            print('Saved new node template')

    def run_graph(self):
        """Execute the current graph or Preview UI"""
        # If UI Builder is active (Viewport tab in UI mode), preview the UI
        if self.tabs.currentIndex() == 1 and hasattr(self, 'scene_editor') and self.scene_editor._current_mode == 'UI':
            self.preview_ui()
            return
            
        try:
            # Use relative imports since we're running from within py_editor
            try:
                from core.backend import execute_canvas_graph
                from core.node_templates import _templates
            except ImportError:
                from py_editor.core.backend import execute_canvas_graph
                from py_editor.core.node_templates import _templates
            
            # Clear any existing errors on nodes
            for node in self.canvas.nodes:
                node.clear_error()
            
            # Export current graph
            graph_data = self.canvas.export_graph()
            
            # Collect breakpoints from canvas nodes
            canvas_breakpoints = {node.id for node in self.canvas.nodes if getattr(node, 'has_breakpoint', False)}
            
            # Execute the graph with variable default values
            print("Executing graph...")
            results = execute_canvas_graph(graph_data, _templates, canvas_breakpoints, self.canvas.graph_variables, source_path=getattr(self, 'current_file', None))
            
            # Get the canvas-to-IR mapping, node errors, and computed values
            canvas_to_ir_map = results.pop('_canvas_to_ir_map', {})
            node_errors = results.pop('_node_errors', {})
            computed_values = results.pop('_computed_values', {})
            
            # Create reverse mapping: IR ID -> canvas ID
            ir_to_canvas_map = {ir_id: canvas_id for canvas_id, ir_id in canvas_to_ir_map.items()}
            
            # Map computed values to canvas nodes for hover inspection
            for ir_node_id, value in computed_values.items():
                canvas_node_id = ir_to_canvas_map.get(ir_node_id)
                if canvas_node_id is not None:
                    for node in self.canvas.nodes:
                        if node.id == canvas_node_id:
                            node.set_execution_state("completed", value)
                            break
            
            if node_errors:
                # Map IR node IDs back to canvas node IDs and display errors
                for ir_node_id, error_msg in node_errors.items():
                    canvas_node_id = ir_to_canvas_map.get(ir_node_id)
                    if canvas_node_id is not None:
                        # Find the canvas node with this ID
                        for node in self.canvas.nodes:
                            if node.id == canvas_node_id:
                                node.set_error(error_msg)
                                break
            
            # Display results
            result_text = "Graph Execution Results:\n\n"
            if results:
                for key, value in results.items():
                    result_text += f"{key}: {value}\n"
            else:
                result_text += "No results returned (graph may not have a Return node)"
            
            if node_errors:
                result_text += f"\n{len(node_errors)} node(s) had errors (check red nodes in canvas)"
            
            # Check if execution was halted by breakpoint
            if '_breakpoint_hit' in results:
                breakpoint_ir_id = results.pop('_breakpoint_hit')
                canvas_node_id = ir_to_canvas_map.get(breakpoint_ir_id)
                result_text += f"\n\n⚠️ Execution halted at breakpoint (Node ID: {canvas_node_id})"
                result_text += "\nUse Step execution to continue from breakpoints."
            
            print(result_text)
            QMessageBox.information(self, "Execution Complete", result_text)
        except Exception as e:
            error_msg = f"Error executing graph:\n{e}"
            print(error_msg)
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self, "Execution Error", error_msg)

    def preview_ui(self):
        """Preview the built UI using the runtime loader"""
        print("=== PREVIEW_UI CALLED ===")
        from py_editor.ui.runtime_loader import RuntimeUILoader
        try:
            ui_data = self.ui_builder.canvas.export_ui()
            print(f"UI data has {len(ui_data.get('widgets', []))} widgets")
            print(f"UI data: {ui_data}")
            
            # Get graph variables for binding
            graph_vars = {}
            if hasattr(self.canvas, 'graph_variables'):
                for var_name, var_info in self.canvas.graph_variables.items():
                    if isinstance(var_info, dict):
                        graph_vars[var_name] = var_info.get('value')
                    else:
                        graph_vars[var_name] = var_info
            print(f"Graph variables for UI binding: {graph_vars}")
            
            preview_window = RuntimeUILoader.load_ui(
                ui_data, 
                self, 
                on_button_click=self._on_ui_button_clicked,
                on_slider_changed=self._on_ui_slider_changed,
                on_checkbox_changed=self._on_ui_checkbox_changed,
                on_text_changed=self._on_ui_text_changed,
                variables=graph_vars
            )
            print("Preview window created, calling exec()")
            # Store reference to preview window for event handling
            self._preview_window = preview_window
            preview_window.exec()
            print("Preview window closed")
        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Preview Error", f"Failed to preview UI:\n{e}")
    
    def _execute_ui_event(self, event_type: str, event_id: str, event_value=None):
        """Execute node graph for UI events"""
        try:
            from py_editor.core.backend import IRBackend, ExecutionContext
            from py_editor.core.node_templates import _templates
        except ImportError:
            from core.backend import IRBackend, ExecutionContext
            from core.node_templates import _templates
        
        try:
            # Export the current graph
            graph_data = self.canvas.export_graph()
            print(f"\n=== UI EVENT: {event_type} ===")
            print(f"Event ID: '{event_id}', Value: {event_value}")
            print(f"Graph has {len(graph_data.get('nodes', []))} nodes, {len(graph_data.get('connections', []))} connections")
            
            # Get graph variables
            graph_variables = graph_data.get('variables', {})
            print(f"Graph variables: {list(graph_variables.keys())}")
            
            # Execute the full graph with event context
            backend = IRBackend()
            ir_module = backend.canvas_to_ir(graph_data, _templates)
            ir_module.source_path = getattr(self, 'current_file', None)
            
            # Create execution context with variables loaded
            ctx = ExecutionContext()
            if graph_variables:
                # Load graph variables into context
                ctx.variables = {name: info.get('value') if isinstance(info, dict) else info 
                                for name, info in graph_variables.items()}
                print(f"Loaded variables into context: {ctx.variables}")
            
            # Inject the event context
            ir_module.event_context['event_type'] = event_type
            ir_module.event_context['triggered_id'] = event_id
            ir_module.event_context['event_value'] = event_value
            
            # Also set specific fields for each event type
            if event_type == 'button':
                ir_module.event_context['triggered_button_id'] = event_id
                ir_module.event_context['triggered_button_name'] = event_value or event_id
            elif event_type == 'slider':
                ir_module.event_context['triggered_slider_id'] = event_id
                ir_module.event_context['slider_value'] = event_value
            elif event_type == 'checkbox':
                ir_module.event_context['triggered_checkbox_id'] = event_id
                ir_module.event_context['checkbox_checked'] = event_value
            elif event_type == 'text':
                ir_module.event_context['triggered_input_id'] = event_id
                ir_module.event_context['input_text'] = event_value
            
            print(f"Event context: {ir_module.event_context}")
            print(f"Widget values: {ir_module.widget_values}")
            
            results = backend.execute_ir(ir_module, ctx=ctx)
            print(f"UI event '{event_type}' execution results: {results}")
            
            # Handle screen switching if requested
            switch_to = ir_module.event_context.get('switch_to_screen')
            if switch_to and hasattr(self, '_preview_window') and hasattr(self._preview_window, 'switch_screen'):
                print(f"Switching to screen: {switch_to}")
                self._preview_window.switch_screen(switch_to)
            
            # Show result popup if there's a return value
            if results and 'return' in results:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(
                    self._preview_window if hasattr(self, '_preview_window') else self, 
                    "Event Result", 
                    f"Return value: {results['return']}"
                )
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Error executing UI event: {e}")
    
    def _on_ui_button_clicked(self, button_id: str, button_name: str):
        """Handle button clicks from the UI preview - triggers OnUIButtonPressed nodes"""
        print(f"UI Button clicked: id={button_id}, name={button_name}")
        self._execute_ui_event('button', button_id, button_name)
    
    def _on_ui_slider_changed(self, slider_id: str, value: int):
        """Handle slider changes from the UI preview - triggers OnUISliderChanged nodes"""
        print(f"UI Slider changed: id={slider_id}, value={value}")
        self._execute_ui_event('slider', slider_id, value)
    
    def _on_ui_checkbox_changed(self, checkbox_id: str, checked: bool):
        """Handle checkbox changes from the UI preview - triggers OnUICheckboxChanged nodes"""
        print(f"UI Checkbox changed: id={checkbox_id}, checked={checked}")
        self._execute_ui_event('checkbox', checkbox_id, checked)
    
    def _on_ui_text_changed(self, input_id: str, text: str):
        """Handle text input changes from the UI preview - triggers OnUITextChanged nodes"""
        print(f"UI Text changed: id={input_id}, text={text}")
        self._execute_ui_event('text', input_id, text)

    def open_settings(self):
        dlg = NodeSettingsDialog(self)
        dlg.exec()
    
    def generate_code(self):
        """Generate standalone code from the current graph"""
        try:
            from core.backend import IRBackend
            from core.node_templates import _templates
        except ImportError:
            from py_editor.core.backend import IRBackend
            from py_editor.core.node_templates import _templates
        
        # Convert canvas to IR first
        try:
            graph_data = self.canvas.export_graph()
            backend = IRBackend()
            ir_module = backend.canvas_to_ir(graph_data, _templates)
            ir_module.source_path = getattr(self, 'current_file', None)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to create IR:\n{e}")
            import traceback
            traceback.print_exc()
            ir_module = None
        
        # Get UI data from UI Builder
        ui_data = {}
        if hasattr(self, 'ui_builder') and self.ui_builder:
            try:
                ui_data = self.ui_builder.canvas.export_ui()
            except Exception:
                pass
        
        # Get variables
        variables = graph_data.get('variables', {}) if graph_data else {}
        
        # Open the code generation dialog
        dialog = CodeGenDialog(self, ir_module=ir_module, canvas=self.canvas, 
                               ui_data=ui_data, variables=variables)
        dialog.exec()
    
    def step_execution(self):
        """Execute one node step in step-by-step mode"""
        try:
            from core.backend import IRBackend, ExecutionContext
            from core.node_templates import _templates
        except ImportError:
            from py_editor.core.backend import IRBackend, ExecutionContext
            from py_editor.core.node_templates import _templates
        
        # Initialize if starting fresh
        if not self.is_stepping or self.execution_backend is None:
            # Clear previous execution states
            for node in self.canvas.nodes:
                node.clear_execution_state()
                node.clear_error()
            
            # Export graph and create backend
            graph_data = self.canvas.export_graph()
            self.execution_backend = IRBackend()
            ir_module = self.execution_backend.canvas_to_ir(graph_data, _templates)
            ir_module.source_path = getattr(self, 'current_file', None)
            
            # Collect breakpoints from canvas nodes
            breakpoints = set()
            for node in self.canvas.nodes:
                if node.has_breakpoint:
                    # Map canvas ID to IR ID
                    ir_id = self.execution_backend.canvas_to_ir_map.get(node.id)
                    if ir_id is not None:
                        breakpoints.add(ir_id)
            
            # Create execution context
            self.execution_context = ExecutionContext()
            self.execution_context.ir_module = ir_module
            self.execution_context.breakpoints = breakpoints
            self.execution_context.step_mode = True
            
            # Get execution order
            sorted_nodes = self.execution_backend._topological_sort(ir_module)
            self.execution_context.execution_order = sorted_nodes
            
            self.is_stepping = True
            print("Started step-by-step execution")
        
        # Execute one step
        ctx, node, result, is_complete = self.execution_backend.execute_ir_step(
            self.execution_context.ir_module,
            self.execution_context
        )
        
        self.execution_context = ctx
        
        if node:
            # Update visual state on canvas
            ir_to_canvas = {ir_id: canvas_id for canvas_id, ir_id 
                           in self.execution_backend.canvas_to_ir_map.items()}
            canvas_id = ir_to_canvas.get(node.id.id)
            
            if canvas_id is not None:
                for canvas_node in self.canvas.nodes:
                    if canvas_node.id == canvas_id:
                        if ctx.paused_at == node.id.id:
                            canvas_node.set_execution_state("breakpoint", result)
                            QMessageBox.information(self, "Breakpoint Hit", 
                                f"Execution paused at node: {canvas_node.title.toPlainText()}")
                        else:
                            canvas_node.set_execution_state("completed", result)
                        break
            
            print(f"Stepped: Node {node.id.id}, Result: {result}")
        
        if is_complete:
            self.is_stepping = False
            QMessageBox.information(self, "Execution Complete", 
                "Step-by-step execution finished!")
    
    def reset_execution(self):
        """Reset execution state"""
        self.execution_context = None
        self.execution_backend = None
        self.is_stepping = False
        
        # Clear visual states
        for node in self.canvas.nodes:
            node.clear_execution_state()
            node.clear_error()
        
        print("Execution state reset")
        QMessageBox.information(self, "Reset", "Execution state has been reset")
    
    def toggle_live_mode(self, enabled):
        """Toggle live execution mode."""
        self.live_mode_enabled = enabled
        if enabled:
            self.live_mode_act.setText("🟢 Live Mode")
            print("Live execution mode enabled")
            # Connect canvas value changes to live execution
            self.canvas.value_changed.connect(self.on_value_changed)
            # Execute immediately to show current state
            self.execute_live()
        else:
            self.live_mode_act.setText("🔴 Live Mode")
            print("Live execution mode disabled")
            # Disconnect value change signal
            try:
                self.canvas.value_changed.disconnect(self.on_value_changed)
            except:
                pass
    
    def on_value_changed(self):
        """Handle value changes in live mode - debounce execution."""
        if self.live_mode_enabled:
            # Restart timer to debounce rapid changes
            self.live_exec_timer.stop()
            self.live_exec_timer.start(300)  # 300ms delay
    
    def execute_live(self):
        """Execute graph in live mode (silently, no dialogs)."""
        if not self.live_mode_enabled:
            return
        
        try:
            try:
                from py_editor.core.backend import execute_canvas_graph
                from py_editor.core.node_templates import _templates
            except ModuleNotFoundError:
                from core.backend import execute_canvas_graph
                from core.node_templates import _templates
            
            # Clear any existing errors
            for node in self.canvas.nodes:
                node.clear_error()
            
            # Export and execute
            graph_data = self.canvas.export_graph()
            results = execute_canvas_graph(graph_data, _templates, set(), source_path=getattr(self, 'current_file', None))
            
            # Get mappings and computed values
            canvas_to_ir_map = results.pop('_canvas_to_ir_map', {})
            node_errors = results.pop('_node_errors', {})
            computed_values = results.pop('_computed_values', {})
            
            # Create reverse mapping
            ir_to_canvas_map = {ir_id: canvas_id for canvas_id, ir_id in canvas_to_ir_map.items()}
            
            # Display computed values on nodes
            for ir_node_id, value in computed_values.items():
                canvas_node_id = ir_to_canvas_map.get(ir_node_id)
                if canvas_node_id is not None:
                    for node in self.canvas.nodes:
                        if node.id == canvas_node_id:
                            node.set_execution_state("completed", value)
                            break
            
            # Display errors if any
            if node_errors:
                for ir_node_id, error_msg in node_errors.items():
                    canvas_node_id = ir_to_canvas_map.get(ir_node_id)
                    if canvas_node_id is not None:
                        for node in self.canvas.nodes:
                            if node.id == canvas_node_id:
                                node.set_error(error_msg)
                                break
        except Exception as e:
            print(f"Live execution error: {e}")

    def _setup_docks(self):
        # --- Shared Global Docks ---
        self.file_dock = QDockWidget("Explorer", self)
        self.file_dock.setWidget(self.explorer)
        self.file_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea)
        # Allow docks to be moved and floated by the user so layouts remain resizable
        try:
            self.file_dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        except Exception:
            pass
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.file_dock)
        
        self.var_panel = VariablePanelWidget(self)
        self.var_dock = QDockWidget("Variables", self)
        self.var_dock.setWidget(self.var_panel)
        self.var_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        try:
            self.var_dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        except Exception:
            pass
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.var_dock)
        self.variable_panel = self.var_panel

        self.prop_dock = QDockWidget("Properties", self)
        self.prop_dock.setWidget(self.properties)
        self.prop_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        try:
            self.prop_dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        except Exception:
            pass
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.prop_dock)
        
        # Stack vars above properties
        self.splitDockWidget(self.var_dock, self.prop_dock, Qt.Orientation.Vertical)
        
        # AI Chat dock (below Explorer)
        self.ai_chat = AIChatWidget(self)
        self.chat_dock = QDockWidget("AI Assistant", self)
        self.chat_dock.setWidget(self.ai_chat)
        self.chat_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.BottomDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.chat_dock)
        # Stack chat below explorer
        self.splitDockWidget(self.file_dock, self.chat_dock, Qt.Orientation.Vertical)

        # --- UI Builder Mode Docks ---
        self.ui_palette = WidgetPaletteWidget(self)
        self.ui_palette_dock = QDockWidget("Widget Palette", self)
        self.ui_palette_dock.setWidget(self.ui_palette)
        self.ui_palette_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.ui_palette_dock)
        self.ui_palette_dock.hide()

        self.ui_props = PropertyEditor(self)
        self.ui_props.set_main_window(self)
        self.ui_props_dock = QDockWidget("UI Properties", self)
        self.ui_props_dock.setWidget(self.ui_props)
        self.ui_props_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.ui_props_dock)
        # Ensure it's below screen list if both are visible (UI mode)
        # We'll set up the split explicitly after adding both
        self.ui_props_dock.hide()
        
        # Screen List dock (for managing multiple UI screens)
        self.screen_list = ScreenListWidget(self)
        self.screen_list.set_canvas(self.ui_builder.canvas)
        self.screen_list_dock = QDockWidget("Screens", self)
        self.screen_list_dock.setWidget(self.screen_list)
        self.screen_list_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.screen_list_dock)
        self.screen_list_dock.hide()
        
        # Widget List dock (for seeing all widgets on current screen)
        self.widget_list = WidgetListWidget(self)
        self.widget_list.set_canvas(self.ui_builder.canvas)
        self.widget_list_dock = QDockWidget("Widget Hierarchy", self)
        self.widget_list_dock.setWidget(self.widget_list)
        self.widget_list_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.widget_list_dock)
        self.widget_list_dock.hide()
        
        # Explicitly stack Screens (Top Left) above Palette
        self.splitDockWidget(self.screen_list_dock, self.ui_palette_dock, Qt.Orientation.Vertical)
        
        # Explicitly stack Widget List (Top Right) and Properties (Bottom Right)
        self.splitDockWidget(self.widget_list_dock, self.ui_props_dock, Qt.Orientation.Vertical)
        
        # Connect widget list selection to property editor
        self.widget_list.widget_selected.connect(self.ui_props.set_widget)
        
        # Connect UI Builder signals
        self.ui_builder.canvas.widget_selected.connect(self.ui_props.set_widget)
        self.ui_builder.canvas.widget_selected.connect(lambda w: self.widget_list.refresh_list())
        # Update canvas when properties change (to refresh preview if needed)
        # Ensuring property editor changes trigger updates on the item
        def update_item_visuals(prop, val):
            if self.ui_props.current_widget:
                # Trigger property update logic on widget item if it exists
                # For now just update Scene to trigger repaint
                self.ui_props.current_widget.update()
                
                # Update visual style if it's a visual property
                if hasattr(self.ui_props.current_widget, 'update_style'):
                    self.ui_props.current_widget.update_style()
                
                # Also verify preview size/content update
                if hasattr(self.ui_props.current_widget, '_update_preview_size'):
                    self.ui_props.current_widget._update_preview_size()
                    
                    if prop == 'text' and hasattr(self.ui_props.current_widget, '_create_preview'):
                         # Reaping preview to update text
                         # This is a bit hacky, ideally WidgetItem handles this, but sticking to logic
                         self.ui_props.current_widget._create_preview()
                
                self.ui_builder.canvas.scene().update()

        self.ui_props.property_changed.connect(update_item_visuals)

        # Ensure explorer sizes are consistent
        self.file_dock.setMinimumWidth(260)

        # Group docks for switching (Note: file_dock, var_dock and prop_dock are shared and stay visible)
        self.canvas_docks = [self.chat_dock]
        self.viewport_docks = []
        self.ui_docks = [self.ui_palette_dock, self.ui_props_dock, self.screen_list_dock, self.widget_list_dock]
        self.shared_docks = [self.file_dock, self.var_dock, self.prop_dock]
        self._viewport_ui_mode = False
        # Set initial proportions for stacked right docks (Variables half height)
        self.resizeDocks([self.var_dock, self.prop_dock], [500, 500], Qt.Orientation.Vertical)

    def _on_viewport_mode_changed(self, mode):
        """Called when the Viewport tab's mode changes."""
        self._viewport_ui_mode = (mode == 'UI')
        # Trigger dock update
        self.on_tab_changed(self.tabs.currentIndex())

    def on_tab_changed(self, index):
        """Switch visible docks based on active tab"""
        # Tab indices: 0=Logic, 1=Viewport, 2=Anim
        
        # Manage scene editor render loop
        if hasattr(self, 'scene_editor'):
            if index != 1:
                self.scene_editor.on_tab_deactivated()
            else:
                self.scene_editor.on_tab_activated()
        
        # Hide all context-specific docks first by default
        for d in self.canvas_docks + self.ui_docks + self.viewport_docks:
            d.hide()
        
        # Always show shared docks
        if hasattr(self, 'shared_docks'):
            for d in self.shared_docks: d.show()

        # Logic tab (0) - show canvas docks
        if index == 0:
            for d in self.canvas_docks:
                d.show()
            if hasattr(self, 'explorer'):
                self.explorer._primitives_section.set_collapsed(True)
        # Viewport tab (1) - show Viewport docks, or UI docks if in UI mode
        elif index == 1:
            if self._viewport_ui_mode:
                for d in self.ui_docks:
                    d.show()
            else:
                for d in self.viewport_docks:
                    d.show()
        # Anim tab (2) - specialized docks managed in anim module, or none for now
        elif index == 2:
            pass
            for d in self.ui_docks:
                d.hide()

if __name__ == '__main__':
    # Enable faulthandler to get native crash tracebacks (segfaults, aborts)
    try:
        faulthandler.enable(all_threads=True)
    except Exception:
        try:
            faulthandler.enable()
        except Exception:
            pass
    # register common fatal signals when available
    for sig_name in ('SIGSEGV', 'SIGFPE', 'SIGABRT', 'SIGILL', 'SIGBUS'):
        try:
            sig = getattr(signal, sig_name)
            try:
                faulthandler.register(sig, all_threads=True)
            except Exception:
                pass
        except Exception:
            pass

    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    # Optional debug: auto-open SimulationWindow when env var NODECANVAS_AUTO_PLAY=1
    try:
        if os.environ.get('NODECANVAS_AUTO_PLAY') == '1':
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(500, lambda: w.scene_editor._on_play_clicked())
    except Exception:
        pass
    # Debug hooks: global exception logging and quit/destroy notifications
    import traceback as _traceback
    def _excepthook(exc_type, exc_value, exc_tb):
        print("UNCAUGHT EXCEPTION:")
        _traceback.print_exception(exc_type, exc_value, exc_tb)
    sys.excepthook = _excepthook

    def _on_about_to_quit():
        print("DEBUG: QApplication.aboutToQuit triggered")
        # perform final cleanup on all CanvasView instances so we can safely
        # remove QGraphicsItems from scenes without risking lifetime races.
        try:
            import traceback as _tb
            from PyQt6.QtWidgets import QApplication as _A
            app_inst = _A.instance()
            if app_inst:
                for wgt in app_inst.topLevelWidgets():
                    try:
                        # Use canvas module directly since we're already in the py_editor package
                        try:
                            from ui.canvas import CanvasView
                        except Exception:
                            try:
                                from py_editor.ui.canvas import CanvasView
                            except ImportError:
                                continue
                        canvases = wgt.findChildren(CanvasView)
                        for cv in canvases:
                            try:
                                if getattr(cv, 'final_cleanup_now', None):
                                    cv.final_cleanup_now()
                            except Exception:
                                _tb.print_exc()
                    except Exception:
                        _tb.print_exc()
        except Exception:
            try:
                _tb.print_exc()
            except Exception:
                pass
    try:
        app.aboutToQuit.connect(_on_about_to_quit)
    except Exception:
        pass

    try:
        w.destroyed.connect(lambda: print("DEBUG: MainWindow.destroyed signal emitted"))
    except Exception:
        pass
    # Monitor lastWindowClosed and print exec() return value for debugging
    try:
        app.lastWindowClosed.connect(lambda: print("DEBUG: QApplication.lastWindowClosed emitted"))
    except Exception:
        pass

    try:
        rc = app.exec()
        print(f"DEBUG: app.exec() returned {rc}")
    except Exception:
        import traceback as _tb
        print("UNCAUGHT EXCEPTION in app.exec():")
        _tb.print_exc()
        rc = 1
    sys.exit(rc)
