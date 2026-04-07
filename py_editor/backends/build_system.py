"""
Build System for NodeCanvas

Creates deployable packages from graphs with:
- Composite node inlining
- Asset collection and bundling
- Python GUI wrapper that loads compiled backends

Build output structure:
    build/
      app/
        main.py           # Entry point
        gui/              # PyQt6 UI (from UI Builder)
        backend/          # Compiled logic (DLL/Python/WASM)
        assets/           # Audio, images, etc.
"""
import os
import shutil
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Any
from dataclasses import dataclass, field


@dataclass
class BuildConfig:
    """Configuration for build process"""
    target: str = "python"  # python, c, cpp, wasm
    output_dir: str = ""
    app_name: str = "NodeCanvasApp"
    include_gui: bool = True
    include_assets: bool = True
    single_exe: bool = False  # Bundle into single executable
    debug: bool = False


@dataclass
class AssetInfo:
    """Information about a collected asset"""
    source_path: str
    relative_path: str  # Path relative to assets/
    asset_type: str  # audio, image, data
    referenced_by: List[int] = field(default_factory=list)  # Node IDs


class CompositeInliner:
    """Flattens composite nodes into the main graph for codegen"""
    
    def __init__(self, ir_module, composite_templates: Dict):
        self.ir = ir_module
        self.composite_templates = composite_templates
        self.next_id = max((n.id.id for n in ir_module.nodes), default=0) + 1000
    
    def inline_all(self):
        """
        Inline all composite nodes recursively.
        Returns a new IR module with composites expanded.
        """
        try:
            from py_editor.core.ir import IRModule, IRNode, NodeId, Custom
        except ImportError:
            from ..core.ir import IRModule, IRNode, NodeId, Custom
        
        # Create a copy of the IR
        new_nodes = []
        nodes_to_process = list(self.ir.nodes)
        
        while nodes_to_process:
            node = nodes_to_process.pop(0)
            kind = node.kind
            
            # Check if this is a composite node
            if isinstance(kind, Custom):
                template = self.composite_templates.get(node.id.id)
                if template and template.get('type') == 'composite':
                    # Inline this composite
                    inlined_nodes = self._inline_composite(node, template)
                    nodes_to_process.extend(inlined_nodes)
                    continue
            
            new_nodes.append(node)
        
        # Create new IR module with inlined nodes
        new_ir = IRModule()
        new_ir.nodes = new_nodes
        new_ir.widget_values = dict(self.ir.widget_values)
        new_ir.source_pin_map = dict(getattr(self.ir, 'source_pin_map', {}))
        
        return new_ir
    
    def _inline_composite(self, composite_node, template) -> List:
        """Inline a single composite node, returning new nodes to add"""
        try:
            from py_editor.core.ir import IRNode, NodeId, Custom, ConstValue, Value, ValueType
        except ImportError:
            from ..core.ir import IRNode, NodeId, Custom, ConstValue, Value, ValueType
        
        internal_graph = template.get('graph', {})
        if not internal_graph:
            return []
        
        internal_nodes = internal_graph.get('nodes', [])
        input_mapping = template.get('inputs', {})
        output_mapping = template.get('outputs', {})
        
        # Map old internal IDs to new IDs
        id_remap = {}
        new_nodes = []
        
        for int_node in internal_nodes:
            old_id = int_node.get('id')
            new_id = self.next_id
            self.next_id += 1
            id_remap[old_id] = new_id
            
            # Create new IR node with remapped ID
            template_name = int_node.get('template')
            
            # Skip composite I/O nodes - they become pass-throughs
            if template_name in ('__composite_input__', '__composite_output__'):
                continue
            
            # Create the node
            node_kind = Custom(name=template_name, inputs=[])
            new_node = IRNode(id=NodeId(new_id), kind=node_kind)
            new_nodes.append(new_node)
            
            # Copy widget values
            widget_vals = int_node.get('widgetValues', {})
            self.ir.widget_values[new_id] = widget_vals
        
        # Remap connections
        for conn in internal_graph.get('connections', []):
            from_id = id_remap.get(conn.get('from_node'))
            to_id = id_remap.get(conn.get('to_node'))
            
            if from_id and to_id:
                # Find the target node and add input reference
                for node in new_nodes:
                    if node.id.id == to_id:
                        if hasattr(node.kind, 'inputs'):
                            # Extend inputs array if needed
                            to_pin = conn.get('to_pin', 0)
                            while len(node.kind.inputs) <= to_pin:
                                node.kind.inputs.append(None)
                            node.kind.inputs[to_pin] = NodeId(from_id)
        
        return new_nodes


class AssetCollector:
    """Collects and organizes assets referenced by the graph"""
    
    # File extensions by type
    AUDIO_EXTENSIONS = {'.wav', '.mp3', '.ogg', '.flac', '.aac'}
    IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'}
    
    def __init__(self, ir_module, project_root: str = ""):
        self.ir = ir_module
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.assets: Dict[str, AssetInfo] = {}  # source_path -> AssetInfo
    
    def collect(self) -> Dict[str, AssetInfo]:
        """Scan IR for asset references and collect them"""
        try:
            from py_editor.core.ir import Custom, ConstValue
        except ImportError:
            from ..core.ir import Custom, ConstValue
        
        for node in self.ir.nodes:
            nid = node.id.id
            kind = node.kind
            widget_vals = self.ir.widget_values.get(nid, {})
            
            # Check for audio paths in PlaySound nodes
            if isinstance(kind, Custom) and kind.name == 'PlaySound':
                file_path = widget_vals.get('file_path', '')
                if file_path:
                    self._add_asset(file_path, 'audio', nid)
            
            # Check for image paths in various nodes
            if isinstance(kind, Custom):
                # Check common image properties
                for key in ['image', 'source', 'imagePath', 'background']:
                    if key in widget_vals:
                        path = widget_vals[key]
                        if path and self._looks_like_path(path):
                            self._add_asset(path, 'image', nid)
            
            # Check ConstString nodes that might be paths
            if isinstance(kind, ConstValue):
                value = kind.value.data if hasattr(kind.value, 'data') else None
                if isinstance(value, str) and self._looks_like_path(value):
                    asset_type = self._guess_asset_type(value)
                    if asset_type:
                        self._add_asset(value, asset_type, nid)
        
        return self.assets
    
    def _add_asset(self, path: str, asset_type: str, node_id: int):
        """Add an asset to the collection"""
        # Resolve to absolute path
        abs_path = self._resolve_path(path)
        
        if abs_path in self.assets:
            self.assets[abs_path].referenced_by.append(node_id)
        else:
            # Create relative path for build
            rel_path = self._create_relative_path(abs_path, asset_type)
            self.assets[abs_path] = AssetInfo(
                source_path=abs_path,
                relative_path=rel_path,
                asset_type=asset_type,
                referenced_by=[node_id]
            )
    
    def _resolve_path(self, path: str) -> str:
        """Resolve a path to absolute, trying project root first"""
        p = Path(path)
        if p.is_absolute() and p.exists():
            return str(p)
        
        # Try relative to project root
        project_path = self.project_root / path
        if project_path.exists():
            return str(project_path.resolve())
        
        # Try as-is
        if p.exists():
            return str(p.resolve())
        
        return path  # Return original if not found
    
    def _create_relative_path(self, abs_path: str, asset_type: str) -> str:
        """Create a relative path for the build folder"""
        filename = Path(abs_path).name
        return f"assets/{asset_type}/{filename}"
    
    def _looks_like_path(self, value: str) -> bool:
        """Check if a string looks like a file path"""
        if not isinstance(value, str):
            return False
        if len(value) < 3:
            return False
        
        # Check for path separators
        if '/' in value or '\\' in value:
            return True
        
        # Check for file extension
        ext = Path(value).suffix.lower()
        return ext in (self.AUDIO_EXTENSIONS | self.IMAGE_EXTENSIONS | {'.json', '.txt', '.xml'})
    
    def _guess_asset_type(self, path: str) -> Optional[str]:
        """Guess asset type from file extension"""
        ext = Path(path).suffix.lower()
        if ext in self.AUDIO_EXTENSIONS:
            return 'audio'
        if ext in self.IMAGE_EXTENSIONS:
            return 'image'
        return None
    
    def copy_to_build(self, build_dir: str) -> Dict[str, str]:
        """
        Copy all collected assets to build directory.
        Returns mapping of original paths to new paths.
        """
        path_mapping = {}
        build_path = Path(build_dir)
        
        for source_path, info in self.assets.items():
            dest_path = build_path / info.relative_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            if Path(source_path).exists():
                shutil.copy2(source_path, dest_path)
                path_mapping[source_path] = info.relative_path
                print(f"  Copied: {info.relative_path}")
            else:
                print(f"  Warning: Asset not found: {source_path}")
        
        return path_mapping


class BuildSystem:
    """
    Main build system that creates deployable packages.
    
    Architecture:
        Python GUI (PyQt6) → Backend Library (Python/C DLL/WASM)
        
    The GUI is always Python/PyQt. The backend is compiled to the target.
    """
    
    def __init__(self, config: BuildConfig):
        self.config = config
        self.ir_module = None
        self.ui_data = None
        self.variables = {}
        self.composite_templates = {}
        self.project_root = ""
    
    def build(self, ir_module, ui_data: Dict = None, variables: Dict = None,
              composite_templates: Dict = None, project_root: str = "") -> str:
        """
        Build a deployable package.
        
        Returns the path to the build output directory.
        """
        self.ir_module = ir_module
        self.ui_data = ui_data or {}
        self.variables = variables or {}
        self.composite_templates = composite_templates or {}
        self.project_root = project_root
        
        # Setup output directory
        output_dir = Path(self.config.output_dir or tempfile.mkdtemp())
        app_dir = output_dir / self.config.app_name
        
        if app_dir.exists():
            shutil.rmtree(app_dir)
        app_dir.mkdir(parents=True)
        
        print(f"Building {self.config.app_name} ({self.config.target})...")
        print(f"Output: {app_dir}")
        
        # Step 1: Inline composites
        print("\n[1/5] Inlining composite nodes...")
        inliner = CompositeInliner(ir_module, self.composite_templates)
        flat_ir = inliner.inline_all()
        print(f"  Nodes after inlining: {len(flat_ir.nodes)}")
        
        # Step 2: Collect assets
        print("\n[2/5] Collecting assets...")
        collector = AssetCollector(flat_ir, project_root)
        assets = collector.collect()
        print(f"  Found {len(assets)} assets")
        
        # Step 3: Copy assets to build
        if self.config.include_assets and assets:
            print("\n[3/5] Copying assets...")
            path_mapping = collector.copy_to_build(str(app_dir))
            # Update IR with new paths
            self._remap_asset_paths(flat_ir, path_mapping)
        else:
            print("\n[3/5] Skipping asset copy")
        
        # Step 4: Generate backend code
        print(f"\n[4/5] Generating {self.config.target} backend...")
        backend_dir = app_dir / "backend"
        backend_dir.mkdir()
        self._generate_backend(flat_ir, backend_dir)
        
        # Step 5: Generate GUI wrapper
        if self.config.include_gui:
            print("\n[5/5] Generating GUI wrapper...")
            gui_dir = app_dir / "gui"
            gui_dir.mkdir()
            self._generate_gui(gui_dir)
            self._generate_entry_point(app_dir)
        else:
            print("\n[5/5] Skipping GUI generation")
        
        # Step 6: Compile if needed (C/C++)
        if self.config.target in ('c', 'cpp'):
            print("\n[Compile] Building native library...")
            self._compile_native(backend_dir)
        
        print(f"\n[OK] Build complete: {app_dir}")
        return str(app_dir)
    
    def _remap_asset_paths(self, ir_module, path_mapping: Dict[str, str]):
        """Update asset paths in IR to use new relative paths"""
        for nid, widget_vals in ir_module.widget_values.items():
            for key, value in list(widget_vals.items()):
                if isinstance(value, str) and value in path_mapping:
                    widget_vals[key] = path_mapping[value]
    
    def _generate_backend(self, ir_module, backend_dir: Path):
        """Generate backend code for the target"""
        try:
            from py_editor.backends import PythonCodegen, CCodegen, CppCodegen, WasmCodegen
            from py_editor.backends.codegen_common import CodeGenConfig
        except ImportError:
            from .python import PythonCodegen
            from .c import CCodegen
            from .cpp import CppCodegen
            from .wasm import WasmCodegen
            from .codegen_common import CodeGenConfig
        
        config = CodeGenConfig(
            function_name="execute_graph",
            include_audio=True,
            include_ui=bool(self.ui_data),
            ui_data=self.ui_data,
            variables=self.variables,
            standalone=False  # We use our own entry point
        )
        
        if self.config.target == "python":
            backend = PythonCodegen(ir_module, "execute_graph")
            code = backend.generate()
            (backend_dir / "logic.py").write_text(code)
            print(f"  Generated: backend/logic.py")
            
        elif self.config.target == "c":
            backend = CCodegen(ir_module, config)
            code = backend.generate()
            # Add DLL export wrapper
            code = self._add_dll_exports(code)
            (backend_dir / "logic.c").write_text(code)
            print(f"  Generated: backend/logic.c")
            
        elif self.config.target == "cpp":
            backend = CppCodegen(ir_module, config)
            code = backend.generate()
            code = self._add_dll_exports(code, cpp=True)
            (backend_dir / "logic.cpp").write_text(code)
            print(f"  Generated: backend/logic.cpp")
            
        elif self.config.target == "wasm":
            backend = WasmCodegen(ir_module, config)
            code = backend.generate()
            html = backend.generate_html()
            (backend_dir / "logic.c").write_text(code)
            (backend_dir / "index.html").write_text(html)
            print(f"  Generated: backend/logic.c, backend/index.html")
    
    def _add_dll_exports(self, code: str, cpp: bool = False) -> str:
        """Add DLL export declarations for ctypes compatibility"""
        exports = '''
#ifdef _WIN32
    #define EXPORT __declspec(dllexport)
#else
    #define EXPORT __attribute__((visibility("default")))
#endif

'''
        if cpp:
            exports += 'extern "C" {\n'
        
        # Find the execute_graph function and add EXPORT
        code = code.replace('void execute_graph()', 'EXPORT void execute_graph()')
        
        if cpp:
            code += '\n}  // extern "C"\n'
        
        return exports + code
    
    def _compile_native(self, backend_dir: Path):
        """Compile C/C++ to shared library"""
        import platform
        
        is_windows = platform.system() == "Windows"
        ext = ".dll" if is_windows else ".so"
        
        if self.config.target == "c":
            src = backend_dir / "logic.c"
            out = backend_dir / f"logic{ext}"
            
            # Try different compilers
            compilers = ["gcc", "clang", "cl"]
            for cc in compilers:
                if shutil.which(cc):
                    if cc == "cl":
                        cmd = [cc, "/LD", "/Fe:" + str(out), str(src)]
                    else:
                        cmd = [cc, "-shared", "-fPIC", "-o", str(out), str(src)]
                        if not self.config.debug:
                            cmd.insert(1, "-O2")
                    
                    try:
                        result = subprocess.run(cmd, capture_output=True, text=True)
                        if result.returncode == 0:
                            print(f"  Compiled with {cc}: {out.name}")
                            return
                        else:
                            print(f"  {cc} failed: {result.stderr}")
                    except Exception as e:
                        print(f"  {cc} error: {e}")
            
            print("  Warning: No compiler found, library not built")
        
        elif self.config.target == "cpp":
            src = backend_dir / "logic.cpp"
            out = backend_dir / f"logic{ext}"
            
            compilers = ["g++", "clang++", "cl"]
            for cc in compilers:
                if shutil.which(cc):
                    if cc == "cl":
                        cmd = [cc, "/LD", "/EHsc", "/Fe:" + str(out), str(src)]
                    else:
                        cmd = [cc, "-shared", "-fPIC", "-o", str(out), str(src)]
                        if not self.config.debug:
                            cmd.insert(1, "-O2")
                    
                    try:
                        result = subprocess.run(cmd, capture_output=True, text=True)
                        if result.returncode == 0:
                            print(f"  Compiled with {cc}: {out.name}")
                            return
                        else:
                            print(f"  {cc} failed: {result.stderr}")
                    except Exception as e:
                        print(f"  {cc} error: {e}")
            
            print("  Warning: No C++ compiler found, library not built")
    
    def _generate_gui(self, gui_dir: Path):
        """Generate PyQt6 GUI from UI data"""
        if not self.ui_data:
            # Generate minimal GUI
            gui_code = '''"""Auto-generated GUI - No UI data provided"""
from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QLabel

class MainWindow(QMainWindow):
    def __init__(self, backend):
        super().__init__()
        self.backend = backend
        self.setWindowTitle("NodeCanvas App")
        self.resize(800, 600)
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.addWidget(QLabel("Running..."))
        
        # Execute backend
        if hasattr(backend, 'execute_graph'):
            backend.execute_graph()
'''
        else:
            gui_code = self._generate_ui_code()
        
        (gui_dir / "main_window.py").write_text(gui_code)
        (gui_dir / "__init__.py").write_text("from .main_window import MainWindow\n")
        print(f"  Generated: gui/main_window.py")
    
    def _generate_ui_code(self) -> str:
        """Generate PyQt6 code from UI Builder data"""
        # Start with imports
        code = '''"""Auto-generated GUI from NodeCanvas UI Builder"""
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QSlider, QCheckBox, QLineEdit, QProgressBar,
    QStackedWidget, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap


class MainWindow(QMainWindow):
    def __init__(self, backend):
        super().__init__()
        self.backend = backend
        self.variables = {}
        self.widgets = {}
        
        self.setWindowTitle("NodeCanvas App")
        self.resize(800, 600)
        
        central = QWidget()
        self.setCentralWidget(central)
        self.main_layout = QVBoxLayout(central)
        
        self._build_ui()
        self._setup_bindings()
        
        # Execute backend on start
        if hasattr(backend, 'execute_graph'):
            backend.execute_graph()
    
    def _build_ui(self):
        """Build UI from definition"""
'''
        
        # Generate widget creation code
        screens = self.ui_data.get('screens', [])
        if screens:
            code += '        self.screens = QStackedWidget()\n'
            code += '        self.main_layout.addWidget(self.screens)\n\n'
            
            for screen in screens:
                screen_name = screen.get('name', 'screen')
                code += f'        # Screen: {screen_name}\n'
                code += f'        screen_{screen_name} = QWidget()\n'
                code += f'        layout_{screen_name} = QVBoxLayout(screen_{screen_name})\n'
                code += f'        self.screens.addWidget(screen_{screen_name})\n\n'
                
                for widget in screen.get('widgets', []):
                    code += self._generate_widget_code(widget, f'layout_{screen_name}')
        else:
            code += '        # No screens defined\n'
            code += '        self.main_layout.addWidget(QLabel("No UI defined"))\n'
        
        code += '''
    def _setup_bindings(self):
        """Setup data bindings"""
        pass  # TODO: Generate from bindings data
    
    def set_screen(self, name):
        """Switch to a screen by name"""
        # Find screen index
        for i in range(self.screens.count()):
            widget = self.screens.widget(i)
            if widget.objectName() == name:
                self.screens.setCurrentIndex(i)
                break
'''
        
        return code
    
    def _generate_widget_code(self, widget: Dict, parent_layout: str) -> str:
        """Generate code for a single widget"""
        widget_type = widget.get('type', 'Label')
        widget_id = widget.get('id', 'widget')
        props = widget.get('properties', {})
        
        safe_id = ''.join(c if c.isalnum() else '_' for c in str(widget_id))
        
        if widget_type == 'Label':
            text = props.get('text', 'Label')
            return f'        self.widgets["{widget_id}"] = QLabel("{text}")\n' \
                   f'        {parent_layout}.addWidget(self.widgets["{widget_id}"])\n'
        
        elif widget_type == 'Button':
            text = props.get('text', 'Button')
            return f'        self.widgets["{widget_id}"] = QPushButton("{text}")\n' \
                   f'        {parent_layout}.addWidget(self.widgets["{widget_id}"])\n'
        
        elif widget_type == 'Slider':
            return f'        self.widgets["{widget_id}"] = QSlider(Qt.Orientation.Horizontal)\n' \
                   f'        {parent_layout}.addWidget(self.widgets["{widget_id}"])\n'
        
        elif widget_type == 'Checkbox':
            text = props.get('text', 'Checkbox')
            return f'        self.widgets["{widget_id}"] = QCheckBox("{text}")\n' \
                   f'        {parent_layout}.addWidget(self.widgets["{widget_id}"])\n'
        
        elif widget_type == 'TextInput':
            return f'        self.widgets["{widget_id}"] = QLineEdit()\n' \
                   f'        {parent_layout}.addWidget(self.widgets["{widget_id}"])\n'
        
        elif widget_type == 'ProgressBar':
            return f'        self.widgets["{widget_id}"] = QProgressBar()\n' \
                   f'        {parent_layout}.addWidget(self.widgets["{widget_id}"])\n'
        
        elif widget_type == 'Image':
            source = props.get('source', '')
            return f'        img_label = QLabel()\n' \
                   f'        img_label.setPixmap(QPixmap("{source}"))\n' \
                   f'        self.widgets["{widget_id}"] = img_label\n' \
                   f'        {parent_layout}.addWidget(img_label)\n'
        
        else:
            return f'        # Unknown widget type: {widget_type}\n'
    
    def _generate_entry_point(self, app_dir: Path):
        """Generate main.py entry point"""
        if self.config.target == "python":
            entry_code = '''#!/usr/bin/env python3
"""Auto-generated entry point for NodeCanvas App"""
import sys
import os

# Add app directory to path
app_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, app_dir)

from PyQt6.QtWidgets import QApplication
from gui import MainWindow
from backend import logic

def main():
    app = QApplication(sys.argv)
    
    # Create backend
    backend = logic
    
    # Create and show window
    window = MainWindow(backend)
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
'''
        else:  # C/C++ with ctypes
            ext = ".dll" if os.name == 'nt' else ".so"
            entry_code = f'''#!/usr/bin/env python3
"""Auto-generated entry point for NodeCanvas App (Native backend)"""
import sys
import os
import ctypes

# Add app directory to path
app_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, app_dir)

from PyQt6.QtWidgets import QApplication
from gui import MainWindow

class NativeBackend:
    """Wrapper for native library"""
    
    def __init__(self):
        lib_path = os.path.join(app_dir, "backend", "logic{ext}")
        if not os.path.exists(lib_path):
            print(f"Warning: Native library not found: {{lib_path}}")
            self.lib = None
            return
        
        self.lib = ctypes.CDLL(lib_path)
        
        # Setup function signatures
        if hasattr(self.lib, 'execute_graph'):
            self.lib.execute_graph.argtypes = []
            self.lib.execute_graph.restype = None
    
    def execute_graph(self):
        if self.lib and hasattr(self.lib, 'execute_graph'):
            self.lib.execute_graph()
        else:
            print("Warning: execute_graph not available")

def main():
    app = QApplication(sys.argv)
    
    # Create native backend
    backend = NativeBackend()
    
    # Create and show window
    window = MainWindow(backend)
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
'''
        
        (app_dir / "main.py").write_text(entry_code)
        (app_dir / "backend" / "__init__.py").write_text("")
        print(f"  Generated: main.py")


# Convenience function
def build_app(ir_module, config: BuildConfig, **kwargs) -> str:
    """Build a deployable app from IR"""
    builder = BuildSystem(config)
    return builder.build(ir_module, **kwargs)


__all__ = [
    'BuildConfig',
    'BuildSystem', 
    'AssetCollector',
    'CompositeInliner',
    'AssetInfo',
    'build_app',
]
