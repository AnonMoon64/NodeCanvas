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
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt

# Local imports
from py_editor.ui.panels.explorer_panel import FileExplorerWidget
from py_editor.ui.panels.ai_chat_panel import AIChatWidget
from py_editor.ui.panels.variable_panel import VariablePanel
from py_editor.ui.scene.hierarchy_dock import HierarchyDock
from py_editor.ui.scene.properties_panel import ObjectPropertiesPanel
from py_editor.ui import (
    LogicEditor, UIBuilderWidget, SceneEditorWidget, NodeEditorDialog, NodeSettingsDialog
)
from py_editor.core import load_templates

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NodeCanvas — Procedural Engine")
        self.resize(1600, 1000)
        self.project_root = str(Path.cwd())
        
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        
        self.logic_editor = LogicEditor(self)
        self.tabs.addTab(self.logic_editor, "Logic")
        
        self.scene_editor = SceneEditorWidget(self)
        self.tabs.addTab(self.scene_editor, "Viewport")
        
        self.ui_builder = UIBuilderWidget(self)
        self.tabs.addTab(self.ui_builder, "UI Builder")
        
        self._setup_toolbar()
        self._setup_docks()
        self.tabs.currentChanged.connect(self.on_tab_changed)
        
        # Wire global signals
        self.scene_editor.viewport.object_selected.connect(self._on_object_selected)
        self.hierarchy.outliner.object_selected.connect(self._on_object_selected)
        self.explorer.file_opened.connect(self._on_explorer_file_opened)
        self.properties.property_changed.connect(self._on_property_changed)

    def _setup_toolbar(self):
        self.toolbar = QToolBar("Main Toolbar")
        self.toolbar.setMovable(False)
        self.addToolBar(self.toolbar)
        
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

    def _on_play_standalone(self):
        """Save current state to temp and launch standalone runtime as a separate process."""
        data = self.scene_editor.export_scene_data()
        temp_path = Path.cwd() / "temp_play.scene"
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        
        import subprocess
        python_exe = sys.executable
        standalone_script = Path(__file__).parent / "runtime" / "standalone.py"
        
        print(f"[MAIN] Launching standalone process: {python_exe} {standalone_script}")
        subprocess.Popen([python_exe, str(standalone_script), str(temp_path)], 
                         creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0)
        
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
                    # ensure the properties dock is visible when editing a prefab
                    try:
                        self.properties_dock.setVisible(True)
                    except Exception:
                        pass
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
        
        # 2. Right Column
        self.variables = VariablePanel(self.logic_editor, self)
        self.variables_dock = QDockWidget("Variables", self)
        self.variables_dock.setWidget(self.variables)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.variables_dock)
        
        self.properties = ObjectPropertiesPanel(self)
        self.properties_dock = QDockWidget("Properties", self)
        self.properties_dock.setWidget(self.properties)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.properties_dock)
        # Hide properties dock until an object or prefab is selected/opened
        self.properties_dock.setVisible(False)
        
        # Stack Properties below Variables
        self.splitDockWidget(self.variables_dock, self.properties_dock, Qt.Orientation.Vertical)
        
        self.chat_panel = AIChatWidget(self)
        self.chat_dock = QDockWidget("AI Assistant", self)
        self.chat_dock.setWidget(self.chat_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.chat_dock)
        
        # Stack Chat below Properties
        self.splitDockWidget(self.properties_dock, self.chat_dock, Qt.Orientation.Vertical)
        
        self.hierarchy.outliner.object_selected.connect(self._on_object_selected)
        self.hierarchy.outliner.object_deleted.connect(self._on_object_deleted)
        self.hierarchy.outliner.object_renamed.connect(self._on_object_renamed)
        self.hierarchy.outliner.object_duplicated.connect(self._duplicate_object)
        
        # Connect variables to logic updates
        self.logic_editor._scene.changed.connect(self.variables.refresh)

    def _on_object_selected(self, objs):
        if not isinstance(objs, list):
            objs = [objs] if objs else []
            
        if hasattr(self, '_selection_updating') and self._selection_updating: return
        self._selection_updating = True
        
        self.properties.set_objects(objs)
        # Show or hide the properties dock depending on selection
        try:
            self.properties_dock.setVisible(True if objs else False)
        except Exception:
            pass
        self.hierarchy.outliner.set_objects(self.scene_editor.viewport.scene_objects)
        self.scene_editor.viewport.update()
        self._selection_updating = False

    def _on_object_deleted(self, obj):
        if not obj: return
        self.scene_editor.viewport.scene_objects.remove(obj)
        self._on_object_selected(None)

    def _on_object_renamed(self, obj, new_name):
        obj.name = new_name
        self._on_object_selected(obj)
    
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

    def _on_play_standalone(self):
        """Export current scene and launch standalone runtime."""
        try:
            # 1. Export scene to temp file
            scene_data = {
                "objects": [obj.to_dict() for obj in self.scene_editor.viewport.scene_objects],
                "camera_3d": {
                    "pos": self.scene_editor.viewport._cam3d.pos,
                    "yaw": self.scene_editor.viewport._cam3d.yaw,
                    "pitch": self.scene_editor.viewport._cam3d.pitch
                }
            }
            
            # Use project root for temp file
            temp_path = os.path.join(self.project_root, "temp_play.scene")
            with open(temp_path, 'w') as f:
                json.dump(scene_data, f, indent=4)
            
            # 2. Launch Standalone
            # We assume py_editor/runtime/standalone.py exists
            standalone_script = os.path.join(self.project_root, "py_editor", "runtime", "standalone.py")
            if not os.path.exists(standalone_script):
                QMessageBox.critical(self, "Error", f"Standalone script not found at: {standalone_script}")
                return
            
            # Launch as separate process with correct environment
            env = os.environ.copy()
            env["PYTHONPATH"] = self.project_root
            
            subprocess.Popen(
                [sys.executable, standalone_script, temp_path],
                cwd=self.project_root,
                env=env
            )
            print(f"[MAIN] Launched standalone with {temp_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to launch standalone: {e}")

    def on_tab_changed(self, index):
        if index == 1: # Viewport
             self.scene_editor.on_tab_activated()
        else:
             self.scene_editor.on_tab_deactivated()

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

            # Fallback for other tabs
            return f"tab://{idx}"
        except Exception:
            return "unknown_graph"

if __name__ == '__main__':
    faulthandler.enable()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
