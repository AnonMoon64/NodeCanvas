"""
Code Generation and Export Module for NodeCanvas
Exports graphs to Python, C, C++, WASM and optionally builds to EXE
"""

import sys
import subprocess
import tempfile
import shutil
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QTextEdit, QComboBox, QCheckBox, QProgressBar,
    QMessageBox, QGroupBox, QLineEdit, QTabWidget, QWidget, QSplitter
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont


class BuildWorker(QThread):
    """Background worker for building executables"""
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)
    
    def __init__(self, config: dict):
        super().__init__()
        self.config = config
    
    def run(self):
        try:
            build_type = self.config.get('type', 'python')
            
            if build_type == 'python':
                self._build_python()
            elif build_type == 'c':
                self._build_c()
            elif build_type == 'cpp':
                self._build_cpp()
            elif build_type == 'wasm':
                self._build_wasm()
            else:
                self.finished.emit(False, f"Unknown build type: {build_type}")
                
        except Exception as e:
            import traceback
            self.finished.emit(False, f"Build error: {str(e)}\n{traceback.format_exc()}")
    
    def _build_python(self):
        """Build Python EXE with PyInstaller"""
        script_path = self.config['script_path']
        output_dir = self.config['output_dir']
        one_file = self.config.get('one_file', True)
        
        self.progress.emit("Starting PyInstaller build...")
        
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--noconfirm", "--clean",
            f"--distpath={output_dir}",
        ]
        
        if one_file:
            cmd.append("--onefile")
        
        cmd.append(script_path)
        
        self.progress.emit(f"Running: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            cwd=str(Path(script_path).parent)
        )
        
        if result.returncode == 0:
            self.finished.emit(True, f"Build successful!\nOutput: {output_dir}")
        else:
            self.finished.emit(False, f"Build failed:\n{result.stderr or result.stdout}")
    
    def _build_c(self):
        """Build C code with GCC or MSVC"""
        source_path = self.config['script_path']
        output_path = self.config['output_path']
        
        self.progress.emit("Compiling C code...")
        
        # Try GCC first
        compiler = self._find_compiler(['gcc', 'clang', 'cl'])
        if not compiler:
            self.finished.emit(False, "No C compiler found (gcc, clang, or cl)")
            return
        
        if 'cl' in compiler:
            # MSVC
            cmd = [compiler, source_path, '/Fe:' + output_path, '/link', 'SDL2.lib', 'SDL2_mixer.lib']
        else:
            # GCC/Clang
            cmd = [compiler, source_path, '-o', output_path, '-lSDL2', '-lSDL2_mixer', '-lm']
        
        self.progress.emit(f"Running: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            self.finished.emit(True, f"Build successful!\nOutput: {output_path}")
        else:
            self.finished.emit(False, f"Build failed:\n{result.stderr or result.stdout}")
    
    def _build_cpp(self):
        """Build C++ code with G++ or MSVC"""
        source_path = self.config['script_path']
        output_path = self.config['output_path']
        
        self.progress.emit("Compiling C++ code...")
        
        compiler = self._find_compiler(['g++', 'clang++', 'cl'])
        if not compiler:
            self.finished.emit(False, "No C++ compiler found (g++, clang++, or cl)")
            return
        
        if 'cl' in compiler:
            cmd = [compiler, '/EHsc', source_path, '/Fe:' + output_path, '/link', 'SDL2.lib', 'SDL2_mixer.lib']
        else:
            cmd = [compiler, '-std=c++17', source_path, '-o', output_path, '-lSDL2', '-lSDL2_mixer']
        
        self.progress.emit(f"Running: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            self.finished.emit(True, f"Build successful!\nOutput: {output_path}")
        else:
            self.finished.emit(False, f"Build failed:\n{result.stderr or result.stdout}")
    
    def _build_wasm(self):
        """Build WASM with Emscripten"""
        source_path = self.config['script_path']
        output_dir = self.config['output_dir']
        func_name = self.config.get('func_name', 'execute_graph')
        
        self.progress.emit("Compiling to WebAssembly with Emscripten...")
        
        emcc = shutil.which('emcc')
        if not emcc:
            self.finished.emit(False, "Emscripten (emcc) not found.\nInstall from: https://emscripten.org")
            return
        
        output_path = str(Path(output_dir) / f"{func_name}.js")
        
        cmd = [
            emcc, source_path,
            '-o', output_path,
            '-s', 'WASM=1',
            '-s', f'EXPORTED_FUNCTIONS=["_main","_{func_name}"]',
            '-s', 'EXPORTED_RUNTIME_METHODS=["ccall","cwrap"]',
            '-O2'
        ]
        
        self.progress.emit(f"Running: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            self.finished.emit(True, f"Build successful!\nOutput: {output_dir}\nOpen index.html in a web server.")
        else:
            self.finished.emit(False, f"Build failed:\n{result.stderr or result.stdout}")
    
    def _find_compiler(self, names):
        """Find first available compiler"""
        for name in names:
            path = shutil.which(name)
            if path:
                return path
        return None


class CodeGenDialog(QDialog):
    """Dialog for exporting graph to code and building executables"""
    
    LANGUAGES = ["Python", "C", "C++", "WASM"]
    
    def __init__(self, parent=None, ir_module=None, canvas=None, variables=None):
        super().__init__(parent)
        self.ir_module = ir_module
        self.canvas = canvas
        self.variables = variables or {}
        self.generated_code = ""
        self.temp_script_path = None
        self.worker = None
        
        self.setWindowTitle("Export & Build")
        self.resize(1000, 700)
        self.setup_ui()
        
        # Generate code on open if IR available
        if self.ir_module:
            self.generate_code()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Main tabs
        tabs = QTabWidget()
        layout.addWidget(tabs)
        
        # === Code Export Tab ===
        code_tab = QWidget()
        code_layout = QVBoxLayout(code_tab)
        
        # Options row
        options_layout = QHBoxLayout()
        
        options_layout.addWidget(QLabel("Language:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(self.LANGUAGES)
        self.lang_combo.currentTextChanged.connect(self.generate_code)
        options_layout.addWidget(self.lang_combo)
        
        options_layout.addWidget(QLabel("Function:"))
        self.func_name_edit = QLineEdit("execute_graph")
        self.func_name_edit.setMaximumWidth(150)
        options_layout.addWidget(self.func_name_edit)
        
        self.include_audio_cb = QCheckBox("Audio")
        self.include_audio_cb.setChecked(True)
        self.include_audio_cb.stateChanged.connect(self.generate_code)
        options_layout.addWidget(self.include_audio_cb)
        
        self.standalone_cb = QCheckBox("Standalone")
        self.standalone_cb.setChecked(True)
        self.standalone_cb.stateChanged.connect(self.generate_code)
        options_layout.addWidget(self.standalone_cb)
        
        options_layout.addStretch()
        
        regen_btn = QPushButton("Regenerate")
        regen_btn.clicked.connect(self.generate_code)
        options_layout.addWidget(regen_btn)
        
        code_layout.addLayout(options_layout)
        
        # Splitter for code preview and UI code
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Main code preview
        code_group = QGroupBox("Logic Code")
        code_group_layout = QVBoxLayout(code_group)
        self.code_preview = QTextEdit()
        self.code_preview.setFont(QFont("Consolas", 10))
        self.code_preview.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #333;
            }
        """)
        code_group_layout.addWidget(self.code_preview)
        layout.addWidget(code_group)
        
        
        # Export buttons
        export_layout = QHBoxLayout()
        
        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.clicked.connect(self.copy_to_clipboard)
        export_layout.addWidget(copy_btn)
        
        save_btn = QPushButton("Save Code")
        save_btn.clicked.connect(self.save_code)
        export_layout.addWidget(save_btn)
        
        export_layout.addStretch()
        code_layout.addLayout(export_layout)
        
        tabs.addTab(code_tab, "Code Export")
        
        # === Build Tab ===
        build_tab = QWidget()
        build_layout = QVBoxLayout(build_tab)
        
        # Build options
        build_options = QGroupBox("Build Options")
        build_opts_layout = QVBoxLayout(build_options)
        
        # Output directory
        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("Output Directory:"))
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText("Select output directory...")
        output_row.addWidget(self.output_dir_edit)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_output_dir)
        output_row.addWidget(browse_btn)
        build_opts_layout.addLayout(output_row)
        
        # Build type options
        type_row = QHBoxLayout()
        self.onefile_cb = QCheckBox("Single executable (Python)")
        self.onefile_cb.setChecked(True)
        type_row.addWidget(self.onefile_cb)
        type_row.addStretch()
        build_opts_layout.addLayout(type_row)
        
        build_layout.addWidget(build_options)
        
        # Build progress
        self.progress_text = QTextEdit()
        self.progress_text.setReadOnly(True)
        self.progress_text.setMaximumHeight(200)
        self.progress_text.setStyleSheet("""
            QTextEdit {
                background-color: #1a1a1a;
                color: #00ff00;
                font-family: Consolas;
                font-size: 10px;
            }
        """)
        build_layout.addWidget(self.progress_text)
        
        # Build button
        build_btn_layout = QHBoxLayout()
        build_btn_layout.addStretch()
        
        self.build_btn = QPushButton("Build")
        self.build_btn.setMinimumWidth(150)
        self.build_btn.clicked.connect(self.build)
        build_btn_layout.addWidget(self.build_btn)
        
        build_layout.addLayout(build_btn_layout)
        build_layout.addStretch()
        
        tabs.addTab(build_tab, "Build")
        
        # Close button
        close_layout = QHBoxLayout()
        close_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_layout.addWidget(close_btn)
        layout.addLayout(close_layout)
    
    def generate_code(self):
        """Generate code based on selected language"""
        if not self.ir_module:
            self.code_preview.setText("# No graph to export\n# Run the graph first")
            return
        
        try:
            lang = self.lang_combo.currentText()
            func_name = self.func_name_edit.text() or "execute_graph"
            include_audio = self.include_audio_cb.isChecked()
            standalone = self.standalone_cb.isChecked()
            
            # Import from clean backends API
            try:
                from py_editor.backends import PythonCodegen, CCodegen, CppCodegen, WasmCodegen
                from py_editor.backends.c import CodeGenConfig
            except ImportError:
                from backends import PythonCodegen, CCodegen, CppCodegen, WasmCodegen
                from backends.c import CodeGenConfig
            
            config = CodeGenConfig(
                function_name=func_name,
                include_audio=include_audio,
                variables=self.variables,
                standalone=standalone
            )
            
            if lang == "Python":
                backend = PythonCodegen(self.ir_module, func_name)
                self.generated_code = backend.generate()
            elif lang == "C":
                backend = CCodegen(self.ir_module, config)
                self.generated_code = backend.generate()
            elif lang == "C++":
                backend = CppCodegen(self.ir_module, config)
                self.generated_code = backend.generate()
            elif lang == "WASM":
                backend = WasmCodegen(self.ir_module, config)
                self.generated_code = backend.generate()
            
            self.code_preview.setText(self.generated_code)
            
        except Exception as e:
            import traceback
            self.code_preview.setText(f"# Error generating code:\n# {str(e)}\n# {traceback.format_exc()}")
    
    
    def copy_to_clipboard(self):
        """Copy generated code to clipboard"""
        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(self.code_preview.toPlainText())
        QMessageBox.information(self, "Copied", "Code copied to clipboard!")
    
    def save_code(self):
        """Save generated code to file"""
        lang = self.lang_combo.currentText()
        
        if lang == "Python":
            ext = "Python Files (*.py)"
        elif lang in ("C", "WASM"):
            ext = "C Files (*.c)"
        elif lang == "C++":
            ext = "C++ Files (*.cpp)"
        else:
            ext = "All Files (*.*)"
        
        path, _ = QFileDialog.getSaveFileName(self, "Save Code", "", ext)
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(self.code_preview.toPlainText())
                self.temp_script_path = path
                
                # Also save HTML for WASM
                if lang == "WASM":
                    try:
                        from py_editor.backends import WasmCodegen
                        from py_editor.backends.codegen_common import CodeGenConfig
                    except ImportError:
                        from backends import WasmCodegen
                        from backends.codegen_common import CodeGenConfig
                    
                    config = CodeGenConfig(function_name=self.func_name_edit.text() or "execute_graph")
                    backend = WasmCodegen(self.ir_module, config)
                    html_path = str(Path(path).parent / "index.html")
                    with open(html_path, 'w') as f:
                        f.write(backend.generate_html())
                    QMessageBox.information(self, "Saved", f"Code saved to:\n{path}\n\nHTML wrapper:\n{html_path}")
                else:
                    QMessageBox.information(self, "Saved", f"Code saved to:\n{path}")
                    
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save:\n{str(e)}")
    
    def browse_output_dir(self):
        """Browse for output directory"""
        path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if path:
            self.output_dir_edit.setText(path)
    
    def build(self):
        """Build executable from generated code using the full build system"""
        if not self.ir_module:
            QMessageBox.warning(self, "No Graph", "No graph to build!")
            return
        
        output_dir = self.output_dir_edit.text()
        if not output_dir:
            QMessageBox.warning(self, "No Output", "Select an output directory!")
            return
        
        lang = self.lang_combo.currentText().lower()
        func_name = self.func_name_edit.text() or "execute_graph"
        
        self.progress_text.clear()
        self.progress_text.append(f"Building {lang.upper()} app with full build system...")
        self.build_btn.setEnabled(False)
        
        try:
            # Import the new build system
            try:
                from py_editor.backends.build_system import BuildSystem, BuildConfig
            except ImportError:
                from backends.build_system import BuildSystem, BuildConfig
            
            # Get project root for asset resolution
            project_root = ""
            if self.canvas:
                try:
                    project_root = str(Path(self.canvas.current_file).parent) if hasattr(self.canvas, 'current_file') and self.canvas.current_file else ""
                except:
                    pass
            
            # Get composite templates
            composite_templates = {}
            if hasattr(self.ir_module, 'composite_templates'):
                composite_templates = self.ir_module.composite_templates
            
            # Create build config
            config = BuildConfig(
                target=lang if lang != 'cpp' else 'cpp',
                output_dir=output_dir,
                app_name=func_name + "_app",
                include_gui=False,
                include_assets=True,
                single_exe=self.onefile_cb.isChecked(),
                debug=False
            )
            
            # Run build in thread to not block UI
            import threading
            
            def do_build():
                try:
                    builder = BuildSystem(config)
                    result_path = builder.build(
                        self.ir_module,
                        ui_data=None,
                        variables=self.variables,
                        composite_templates=composite_templates,
                        project_root=project_root
                    )
                    
                    # Signal completion via Qt thread-safe mechanism
                    from PyQt6.QtCore import QMetaObject, Qt
                    QMetaObject.invokeMethod(
                        self, "_on_build_complete",
                        Qt.ConnectionType.QueuedConnection,
                        result_path
                    )
                except Exception as e:
                    import traceback
                    error_msg = f"Build error: {str(e)}\n{traceback.format_exc()}"
                    print(error_msg)
                    # Use simpler approach
                    self._build_error = error_msg
            
            # Start build thread
            thread = threading.Thread(target=do_build)
            thread.start()
            
            # For now, wait for completion with timeout
            thread.join(timeout=60)
            
            if thread.is_alive():
                self.progress_text.append("\nBuild still running... check output directory.")
            elif hasattr(self, '_build_error'):
                self.progress_text.append(f"\n{self._build_error}")
                QMessageBox.warning(self, "Build Failed", self._build_error)
                del self._build_error
            else:
                self.progress_text.append(f"\n✓ Build complete!")
                self.progress_text.append(f"Output: {output_dir}")
                QMessageBox.information(self, "Build Complete", 
                    f"Build successful!\n\nOutput: {output_dir}\n\nRun main.py to launch the app.")
            
        except Exception as e:
            import traceback
            error_msg = f"Build failed: {str(e)}\n{traceback.format_exc()}"
            self.progress_text.append(error_msg)
            QMessageBox.critical(self, "Build Error", error_msg)
        
        finally:
            self.build_btn.setEnabled(True)
    
    def on_build_progress(self, msg):
        self.progress_text.append(msg)
    
    def on_build_finished(self, success, msg):
        self.build_btn.setEnabled(True)
        self.progress_text.append("\n" + msg)
        
        if success:
            QMessageBox.information(self, "Build Complete", msg)
        else:
            QMessageBox.warning(self, "Build Failed", msg)

