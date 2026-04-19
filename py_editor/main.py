import sys
import json
import os
import signal
import subprocess
import faulthandler
from pathlib import Path

# Add project root to sys.path so 'py_editor' imports work
parent_dir = Path(__file__).resolve().parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QDockWidget, QFileDialog, QMessageBox,
    QToolBar
)
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtCore import Qt

# Local imports
from py_editor.ui.panels.explorer_panel import FileExplorerWidget
from py_editor.ui.panels.ai_chat_panel import AIChatWidget
from py_editor.ui.panels.variable_panel import VariablePanel
from py_editor.ui.panels.node_properties import NodePropertiesPanel
from py_editor.ui.scene.hierarchy_dock import HierarchyDock
from py_editor.ui.scene.properties_panel import ObjectPropertiesPanel
from py_editor.ui import (
    LogicEditor, SceneEditorWidget, NodeEditorDialog, NodeSettingsDialog
)
from py_editor.core import load_templates
from py_editor.core import paths as asset_paths

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pulse Engine — Procedural Systems")
        
        # Set window icon
        icon_path = os.path.join(os.path.dirname(__file__), "images", "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            
        self.resize(1600, 1000)
        self.project_root = str(Path.cwd())
        asset_paths.set_project_root(self.project_root)
        
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        
        self.logic_editor = LogicEditor(self)
        self.tabs.addTab(self.logic_editor, "Logic")
        
        self.scene_editor = SceneEditorWidget(self)
        self.tabs.addTab(self.scene_editor, "Viewport")
        
        self._setup_toolbar()
        self._setup_docks()
        self.tabs.currentChanged.connect(self.on_tab_changed)
        
        # Wire global signals
        self.scene_editor.viewport.object_selected.connect(self._on_object_selected)
        self.hierarchy.outliner.object_selected.connect(self._on_object_selected)
        self.hierarchy.outliner.object_focused.connect(self._on_object_focused)
        self.explorer.file_opened.connect(self._on_explorer_file_opened)
        self.properties.property_changed.connect(self._on_property_changed)
        self.scene_editor.viewport.objects_changed.connect(
            lambda: self.hierarchy.outliner.set_objects(self.scene_editor.viewport.scene_objects))

    def _setup_toolbar(self):
        self.toolbar = QToolBar("Main Toolbar")
        self.toolbar.setMovable(False)
        self.addToolBar(self.toolbar)

        # File menu (toolbar drop-down)
        from PyQt6.QtWidgets import QToolButton, QMenu
        file_btn = QToolButton()
        file_btn.setText("File")
        file_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        file_menu = QMenu(file_btn)
        set_root_act = QAction("Set Current Project…", self)
        set_root_act.triggered.connect(self._on_set_project_root)
        file_menu.addAction(set_root_act)
        file_menu.addSeparator()
        show_root_act = QAction("Show Project Root", self)
        show_root_act.triggered.connect(
            lambda: QMessageBox.information(self, "Project Root", self.project_root)
        )
        file_menu.addAction(show_root_act)
        file_btn.setMenu(file_menu)
        self.toolbar.addWidget(file_btn)
        self.toolbar.addSeparator()

        # Save / Load
        save_act = QAction("Save", self); save_act.setShortcut("Ctrl+S")
        save_act.triggered.connect(self._save_project)
        self.toolbar.addAction(save_act)
        
        load_act = QAction("Load", self); load_act.setShortcut("Ctrl+O")
        load_act.triggered.connect(self._load_project)
        self.toolbar.addAction(load_act)
        
        self.toolbar.addSeparator()
        
        # Simulation (Logic context)
        run_act = QAction("Run Logic", self); run_act.setShortcut("F5")
        run_act.triggered.connect(self.logic_editor.run_graph)
        self.toolbar.addAction(run_act)
        
        step_act = QAction("Step Logic", self); step_act.setShortcut("F10")
        step_act.triggered.connect(self.logic_editor.step_graph)
        self.toolbar.addAction(step_act)
        
        standalone_act = QAction("Play Standalone", self); standalone_act.setShortcut("Shift+F5")
        standalone_act.triggered.connect(self._on_play_standalone)
        self.toolbar.addAction(standalone_act)
        
        compile_act = QAction("Compile", self); compile_act.setShortcut("F7")
        self.toolbar.addAction(compile_act)

        self.toolbar.addSeparator()

        # Settings
        settings_act = QAction("Settings", self)
        settings_act.triggered.connect(self._on_open_settings)
        self.toolbar.addAction(settings_act)

        self.toolbar.addSeparator()

        reload_shaders_act = QAction("Reload Shaders", self)
        reload_shaders_act.setShortcut("F4")
        reload_shaders_act.triggered.connect(self._on_reload_shaders)
        self.toolbar.addAction(reload_shaders_act)

    def _on_reload_shaders(self):
        from py_editor.ui.shader_manager import clear_shader_cache
        clear_shader_cache()
        self.scene_editor.viewport.update()
        QMessageBox.information(self, "Shaders", "Shader cache cleared. Viewport will recompile on next draw.")

    def _on_play_standalone(self):
        """Export current scene and launch standalone runtime as a separate process."""
        try:
            # 1. Export scene data to a temporary file in the project root
            scene_data = {
                "objects": [obj.to_dict() for obj in self.scene_editor.viewport.scene_objects],
                "camera_3d": {
                    "pos": self.scene_editor.viewport._cam3d.pos,
                    "yaw": self.scene_editor.viewport._cam3d.yaw,
                    "pitch": self.scene_editor.viewport._cam3d.pitch
                }
            }
            temp_path = os.path.join(self.project_root, "temp_play.scene")
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(scene_data, f, indent=4)
            
            # 2. Identify the standalone script
            standalone_script = os.path.join(self.project_root, "py_editor", "runtime", "standalone.py")
            if not os.path.exists(standalone_script):
                QMessageBox.critical(self, "Error", f"Standalone script not found at: {standalone_script}")
                return

            # 3. Launch as a separate process with its own console and PYTHONPATH
            env = os.environ.copy()
            env["PYTHONPATH"] = self.project_root
            
            # Use sys.executable to ensure we use the same Python environment
            subprocess.Popen(
                [sys.executable, standalone_script, temp_path],
                cwd=self.project_root,
                env=env,
                # creationflags ensures it pops up in a separate process window on Windows
                creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
            )
            print(f"[MAIN] Launched standalone window from {temp_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to launch standalone: {e}")
        
    def _save_project(self):
        # Save logic or scene depending on tab
        idx = self.tabs.currentIndex()
        if idx == 0: # Logic
             data = self.logic_editor.export_graph()
             path, _ = QFileDialog.getSaveFileName(self, "Save Logic", self.project_root, "Logic Files (*.logic)")
             if path:
                 with open(path, 'w') as f: json.dump(data, f, indent=4)
        elif idx == 1: # Viewport
             data = self.scene_editor.export_scene_data()
             path, _ = QFileDialog.getSaveFileName(self, "Save Scene", self.project_root, "Scene Files (*.scene)")
             if path:
                 data = asset_paths.normalize_for_save(data)
                 with open(path, 'w') as f: json.dump(data, f, indent=4)
        else:
             QMessageBox.information(self, "Save", "Standard tab save not implemented.")

    def _load_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open File", self.project_root, "All Files (*.logic *.scene)")
        if not path: return
        self._load_file_path(path)

    def _load_file_path(self, path):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
                data = asset_paths.resolve_on_load(data)
                if path.endswith('.logic'):
                    self.tabs.setCurrentIndex(0)
                    self.logic_editor.load_graph(data)
                elif path.endswith('.scene'):
                    self.tabs.setCurrentIndex(1)
                    self.scene_editor.load_scene_data(data)
                    # Refresh outliner sync
                    self._on_scene_loaded()
                elif path.endswith('.prefab'):
                    self.properties.set_prefab(path, data)
                    try: self.properties_dock.setVisible(True)
                    except: pass
                elif path.endswith('.material'):
                    self.properties.set_standalone_material(path, data)
                    try:
                        self.properties_dock.setVisible(True)
                        self.properties_dock.raise_()
                    except: pass
                elif path.endswith('.spawner'):
                    self.properties.set_spawner(path, data)
                    try:
                        self.properties_dock.setVisible(True)
                        self.properties_dock.raise_()
                    except: pass
                else:
                    # Generic fallback to Text Editor
                    dlg = NodeEditorDialog(self)
                    dlg.setWindowTitle(f"Edit: {os.path.basename(path)}")
                    dlg.text_edit.setText(f.read() if not data else json.dumps(data, indent=4))
                    dlg.exec()
        except Exception as e:
             # If JSON loading failed, try raw text
             try:
                 with open(path, 'r') as f:
                     dlg = NodeEditorDialog(self)
                     dlg.setWindowTitle(f"Edit: {os.path.basename(path)}")
                     dlg.text_edit.setPlainText(f.read())
                     dlg.exec()
             except:
                 QMessageBox.critical(self, "Error", f"Failed to load: {e}")

    def _on_set_project_root(self):
        """Prompt user to pick a new project root, update explorer + asset resolver."""
        path = QFileDialog.getExistingDirectory(self, "Select Project Root", self.project_root)
        if not path:
            return
        self.project_root = path
        asset_paths.set_project_root(path)
        try:
            self.explorer.set_root_path(path)
        except Exception as e:
            print(f"[MAIN] Explorer refresh failed: {e}")
        self.setWindowTitle(f"Pulse Engine — {os.path.basename(path)}")
        print(f"[MAIN] Project root set to {path}")

    def _on_open_settings(self):
        """Open the global settings dialog."""
        dlg = NodeSettingsDialog(self)
        dlg.exec()
        # Refresh logic templates if they were changed
        if hasattr(self, 'logic_editor') and hasattr(self.logic_editor, 'refresh_templates'):
             self.logic_editor.refresh_templates()

    def _on_property_changed(self):
        # Notify components to redraw
        self.scene_editor.viewport.update()
        # Potentially update outliner if names changed
        # self.hierarchy.outliner.refresh()

    def _on_scene_loaded(self):
        """Sync all UI components when a new scene is active."""
        objects = self.scene_editor.viewport.scene_objects
        self.hierarchy.outliner.set_objects(objects)
        print(f"[MAIN] Synced outliner with {len(objects)} objects")

    def _setup_docks(self):
        # 1. Left Column
        self.explorer = FileExplorerWidget(self.project_root, self)
        self.explorer_dock = QDockWidget("Explorer", self)
        self.explorer_dock.setWidget(self.explorer)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.explorer_dock)
        
        self.hierarchy = HierarchyDock(self)
        self.hierarchy_dock = QDockWidget("Hierarchy", self)
        self.hierarchy_dock.setWidget(self.hierarchy)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.hierarchy_dock)
        
        # Stack Hierarchy below Explorer
        self.splitDockWidget(self.explorer_dock, self.hierarchy_dock, Qt.Orientation.Vertical)
        
        self.node_props = NodePropertiesPanel(self.logic_editor, self)
        self.node_props_dock = QDockWidget("Node Properties", self)
        self.node_props_dock.setWidget(self.node_props)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.node_props_dock)
        
        self.variables = VariablePanel(self.logic_editor, self)
        self.variables_dock = QDockWidget("Variables", self)
        self.variables_dock.setWidget(self.variables)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.variables_dock)
        
        self.properties = ObjectPropertiesPanel(self)
        self.properties_dock = QDockWidget("Properties", self)
        self.properties_dock.setWidget(self.properties)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.properties_dock)
        
        self.chat_panel = AIChatWidget(self)
        self.chat_dock = QDockWidget("AI Assistant", self)
        self.chat_dock.setWidget(self.chat_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.chat_dock)
        
        # Hide properties docks until relevant selection
        self.properties_dock.setVisible(False)
        self.node_props_dock.setVisible(False)
        
        # Stack Node Properties at top, Variables below it, Chat at bottom
        # We use splitDockWidget to establish the vertical relationship
        self.splitDockWidget(self.node_props_dock, self.variables_dock, Qt.Orientation.Vertical)
        self.splitDockWidget(self.variables_dock, self.chat_dock, Qt.Orientation.Vertical)
        # Put object properties in the same position as node properties (they toggle anyway)
        self.tabifyDockWidget(self.node_props_dock, self.properties_dock)
         
        self.hierarchy.outliner.object_selected.connect(self._on_object_selected)
        self.hierarchy.outliner.object_deleted.connect(self._on_object_deleted)
        self.hierarchy.outliner.object_renamed.connect(self._on_object_renamed)
        self.hierarchy.outliner.object_duplicated.connect(self._duplicate_object)
        
        # Connect viewport selection to the same handler
        self.scene_editor.object_selected.connect(self._on_object_selected)
        
        # Connect variables to logic updates
        self.logic_editor._scene.changed.connect(self.variables.refresh)
        self.logic_editor._scene.selectionChanged.connect(self._on_node_selection_changed)

    def _on_node_selection_changed(self):
        selected = [i for i in self.logic_editor._scene.selectedItems() if hasattr(i, 'id')]
        if len(selected) == 1:
            self.node_props.set_node(selected[0])
            self.node_props_dock.setVisible(True)
        else:
            self.node_props.set_node(None)
            self.node_props_dock.setVisible(False)

    def _on_object_selected(self, objs):
        if not isinstance(objs, list):
            objs = [objs] if objs else []
            
        if hasattr(self, '_selection_updating') and self._selection_updating: return
        self._selection_updating = True
        
        # Update selection state on all objects
        for obj in self.scene_editor.viewport.scene_objects:
            obj.selected = (obj in objs)
            
        self.properties.set_objects(objs)
        # Show or hide the properties dock depending on selection
        try:
            show = len(objs) > 0
            self.properties_dock.setVisible(show)
            if show:
                 self.properties_dock.raise_()
        except Exception:
            pass
            
        # Defer Outliner sync to prevent recursive "clear()" inside selection events (Avoids Access Violation)
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, lambda: self.hierarchy.outliner.select_objects(objs))
        
        self.scene_editor.viewport.update()
        self._selection_updating = False

    def _on_object_deleted(self, obj):
        if not obj: return
        self.scene_editor.viewport.scene_objects.remove(obj)
        self.scene_editor.viewport.objects_changed.emit() # Refresh Outliner
        self._on_object_selected(None)

    def _on_object_renamed(self, obj, new_name):
        obj.name = new_name
        self._on_object_selected(obj)
    
    def _on_object_focused(self, obj):
        if not obj: return
        # Center camera on object
        radius = max(obj.scale) if hasattr(obj, 'scale') else 1.0
        self.scene_editor.viewport._cam3d.focus_on(obj.position, radius)
        self.scene_editor.viewport.update()
    
    def _duplicate_object(self, obj):
        if not obj: return
        import copy
        new_obj = copy.copy(obj) # Shallow copy is enough for SceneObject state
        new_obj.name = f"{obj.name}_Copy"
        # Ensure unique name
        it = 1
        names = [o.name for o in self.scene_editor.viewport.scene_objects]
        while new_obj.name in names:
            new_obj.name = f"{obj.name}_Copy_{it}"
            it += 1
            
        self.scene_editor.viewport.scene_objects.append(new_obj)
        self._on_object_selected(new_obj)

    def _on_explorer_file_opened(self, path, type):
        self._load_file_path(path)

    def on_tab_changed(self, index):
        if index == 1: # Viewport
            self.scene_editor.on_tab_activated()
            self.node_props_dock.setVisible(False)
            # Show properties if there was a selection
            objs = self.scene_editor.viewport.get_selected_objects()
            self.properties_dock.setVisible(True if objs else False)
        elif index == 0: # Logic
             self.scene_editor.on_tab_deactivated()
             self.properties_dock.setVisible(False)
             # Show node properties if there is a selection
             self._on_node_selection_changed()

    def get_active_graph_identifier(self) -> str:
        """Return a short identifier for the currently active graph or scene.

        For logic graphs this returns a short SHA-based id plus node count.
        For scenes this returns a short SHA-based id plus object count.
        This is intentionally lightweight and does not require files to be saved.
        """
        try:
            idx = self.tabs.currentIndex()
            import json, hashlib
            # Logic tab
            if idx == 0 and hasattr(self, 'logic_editor'):
                try:
                    g = self.logic_editor.export_graph()
                    s = json.dumps(g, sort_keys=True, separators=(',', ':'))
                    h = hashlib.sha256(s.encode('utf-8')).hexdigest()[:8]
                    node_count = len(g.get('nodes', [])) if isinstance(g, dict) else 0
                    return f"logic://{node_count}nodes-{h}"
                except Exception:
                    return "logic://unsaved"

            # Viewport / Scene tab
            if idx == 1 and hasattr(self, 'scene_editor'):
                try:
                    sdata = self.scene_editor.export_scene_data()
                    sstr = json.dumps(sdata, sort_keys=True, separators=(',', ':'))
                    h = hashlib.sha256(sstr.encode('utf-8')).hexdigest()[:8]
                    obj_count = 0
                    if isinstance(sdata, dict):
                        obj_count = len(sdata.get('nodes', sdata.get('objects', [])) or [])
                    return f"scene://{obj_count}objs-{h}"
                except Exception:
                    return "scene://unsaved"

            # Fallback
            return f"tab://{idx}"
        except Exception:
            return "unknown_graph"

if __name__ == '__main__':
    faulthandler.enable()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
