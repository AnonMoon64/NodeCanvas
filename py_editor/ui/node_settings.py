from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QListWidget, QPushButton, QHBoxLayout, 
                             QMessageBox, QTabWidget, QWidget, QLabel, QFileDialog, QTextEdit,
                             QTreeWidget, QTreeWidgetItem)
from PyQt6.QtCore import Qt
import sys
from pathlib import Path
import shutil
import json

# Add parent directories to path for imports
if __name__ == '__main__' or 'py_editor' not in sys.modules:
    parent_dir = Path(__file__).resolve().parent.parent
    if str(parent_dir) not in sys.path:
        sys.path.insert(0, str(parent_dir))

try:
    # prefer package import
    from py_editor.core import node_templates
    from py_editor.ui.node_editor import NodeEditorDialog
    from py_editor.ui.canvas import CanvasView
except Exception:
    try:
        from ..core import node_templates
        from .node_editor import NodeEditorDialog
        from .canvas import CanvasView
    except Exception:
        from core import node_templates
        from ui.node_editor import NodeEditorDialog
        from ui.canvas import CanvasView

class NodeSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Settings')
        self.resize(700, 500)
        
        # Main layout with tab widget
        main_layout = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        main_layout.addWidget(self.tabs)
        
        # Close button at bottom
        close_layout = QHBoxLayout()
        close_layout.addStretch()
        self.close_btn = QPushButton('Close')
        self.close_btn.clicked.connect(self.accept)
        close_layout.addWidget(self.close_btn)
        main_layout.addLayout(close_layout)
        
        # Create tabs
        self._create_templates_tab()
        self._create_plugins_tab()
        self._create_export_tab()
        
    def _create_templates_tab(self):
        """Create the Node Templates tab"""
        templates_widget = QWidget()
        v = QVBoxLayout(templates_widget)
        
        self.list = QListWidget()
        v.addWidget(self.list)
        
        hl = QHBoxLayout()
        self.edit_btn = QPushButton('Edit')
        self.delete_btn = QPushButton('Delete')
        hl.addWidget(self.edit_btn)
        hl.addWidget(self.delete_btn)
        hl.addStretch()
        v.addLayout(hl)

        self.edit_btn.clicked.connect(self.on_edit)
        self.delete_btn.clicked.connect(self.on_delete)
        
        self.tabs.addTab(templates_widget, "Node Templates")
        self.reload()
        
    def _create_plugins_tab(self):
        """Create the Plugins tab"""
        plugins_widget = QWidget()
        layout = QVBoxLayout(plugins_widget)
        
        # Plugin tree (shows packages and their nodes)
        list_layout = QVBoxLayout()
        list_layout.addWidget(QLabel("Installed Plugin Packages:"))
        self.plugin_tree = QTreeWidget()
        self.plugin_tree.setHeaderLabels(["Plugin / Node", "Type"])
        self.plugin_tree.currentItemChanged.connect(self._on_plugin_selected)
        list_layout.addWidget(self.plugin_tree)
        layout.addLayout(list_layout)
        
        # Plugin info panel
        self.plugin_info = QTextEdit()
        self.plugin_info.setReadOnly(True)
        self.plugin_info.setMaximumHeight(120)
        layout.addWidget(QLabel("Plugin Details:"))
        layout.addWidget(self.plugin_info)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.add_plugin_btn = QPushButton('Add Plugin...')
        self.remove_plugin_btn = QPushButton('Remove Plugin')
        self.refresh_plugin_btn = QPushButton('Refresh')
        self.remove_plugin_btn.setEnabled(False)
        
        btn_layout.addWidget(self.add_plugin_btn)
        btn_layout.addWidget(self.remove_plugin_btn)
        btn_layout.addWidget(self.refresh_plugin_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        # Connect signals
        self.add_plugin_btn.clicked.connect(self._add_plugin)
        self.remove_plugin_btn.clicked.connect(self._remove_plugin)
        self.refresh_plugin_btn.clicked.connect(self._refresh_plugins)
        
        self.tabs.addTab(plugins_widget, "Plugins")
        self._refresh_plugins()
    
    def _create_export_tab(self):
        """Create the Export Plugin Package tab"""
        export_widget = QWidget()
        layout = QVBoxLayout(export_widget)
        
        # Package info section
        info_layout = QVBoxLayout()
        info_layout.addWidget(QLabel("<b>Package Information:</b>"))
        
        from PyQt6.QtWidgets import QLineEdit, QTextEdit as QTextEditWidget
        
        pkg_form = QHBoxLayout()
        pkg_form.addWidget(QLabel("Package Name:"))
        self.export_pkg_name = QLineEdit()
        self.export_pkg_name.setPlaceholderText("My Node Package")
        pkg_form.addWidget(self.export_pkg_name)
        info_layout.addLayout(pkg_form)
        
        desc_layout = QVBoxLayout()
        desc_layout.addWidget(QLabel("Description:"))
        self.export_pkg_desc = QTextEditWidget()
        self.export_pkg_desc.setMaximumHeight(60)
        self.export_pkg_desc.setPlaceholderText("Description of your plugin package...")
        desc_layout.addWidget(self.export_pkg_desc)
        info_layout.addLayout(desc_layout)
        
        author_layout = QHBoxLayout()
        author_layout.addWidget(QLabel("Author:"))
        self.export_pkg_author = QLineEdit()
        self.export_pkg_author.setPlaceholderText("Your Name")
        author_layout.addWidget(self.export_pkg_author)
        author_layout.addWidget(QLabel("Version:"))
        self.export_pkg_version = QLineEdit()
        self.export_pkg_version.setText("1.0")
        self.export_pkg_version.setMaximumWidth(80)
        author_layout.addWidget(self.export_pkg_version)
        info_layout.addLayout(author_layout)
        
        layout.addLayout(info_layout)
        
        # Node selection section
        layout.addWidget(QLabel("<b>Select Nodes to Include:</b>"))
        
        from PyQt6.QtWidgets import QListWidget as QListWidgetClass
        self.export_node_list = QListWidgetClass()
        self.export_node_list.setSelectionMode(QListWidgetClass.SelectionMode.MultiSelection)
        layout.addWidget(self.export_node_list)
        
        # Populate with available custom nodes
        self._refresh_export_nodes()
        
        # Python module option
        module_layout = QHBoxLayout()
        module_layout.addWidget(QLabel("Python Module (optional):"))
        self.export_module_path = QLineEdit()
        self.export_module_path.setPlaceholderText("Leave empty or select .py file...")
        self.export_module_path.setReadOnly(True)
        module_layout.addWidget(self.export_module_path)
        
        browse_module_btn = QPushButton("Browse...")
        browse_module_btn.clicked.connect(self._browse_python_module)
        module_layout.addWidget(browse_module_btn)
        
        clear_module_btn = QPushButton("Clear")
        clear_module_btn.clicked.connect(lambda: self.export_module_path.clear())
        module_layout.addWidget(clear_module_btn)
        layout.addLayout(module_layout)
        
        # Export button
        export_btn_layout = QHBoxLayout()
        export_btn_layout.addStretch()
        export_btn = QPushButton("Export as .ncpkg")
        export_btn.clicked.connect(self._export_plugin_package)
        export_btn_layout.addWidget(export_btn)
        layout.addLayout(export_btn_layout)
        
        self.tabs.addTab(export_widget, "Export Package")

    def reload(self):
        node_templates.load_templates()
        self.list.clear()
        for name in node_templates.list_templates():
            self.list.addItem(name)

    def on_edit(self):
        item = self.list.currentItem()
        if not item:
            return
        name = item.text()
        tmpl = node_templates.get_template(name)
        dlg = NodeEditorDialog(self, template=tmpl)
        if dlg.exec():
            node_templates.load_templates()
            self.reload()

    def on_delete(self):
        item = self.list.currentItem()
        if not item:
            return
        name = item.text()
        if QMessageBox.question(self, 'Delete', f'Delete template "{name}"?') != QMessageBox.StandardButton.Yes:
            return
        node_templates.delete_template(name)
        node_templates.load_templates()
        self.reload()

        # Remove any instances of this template from open canvases using CanvasView's safe removal
        try:
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
        except Exception:
            app = None
        if app:
            for w in app.topLevelWidgets():
                try:
                    canvases = []
                    if CanvasView is not None:
                        canvases = w.findChildren(CanvasView)
                    for cv in canvases:
                        try:
                            # ask the canvas to remove nodes safely
                            if getattr(cv, 'remove_nodes_by_template', None):
                                cv.remove_nodes_by_template(name)
                        except Exception:
                            pass
                except Exception:
                    pass
    
    def _refresh_plugins(self):
        """Refresh the plugin tree"""
        self.plugin_tree.clear()
        self.plugin_info.clear()
        
        # Get plugin packages from node_templates
        try:
            plugin_packages = node_templates.get_plugin_packages()
        except AttributeError:
            plugin_packages = {}
        
        if not plugin_packages:
            self.plugin_info.setText("No plugins installed. Click 'Add Plugin...' to install one.")
            return
        
        # Build tree structure
        for package_name, package_info in plugin_packages.items():
            # Create package item
            package_item = QTreeWidgetItem(self.plugin_tree)
            package_path = Path(package_info['path'])
            
            if package_path.suffix == '.ncpkg':
                package_item.setText(0, f"📦 {package_name}")
                package_item.setText(1, "Archive")
            else:
                package_item.setText(0, f"📦 {package_name}")
                package_item.setText(1, "Package")
            
            package_item.setData(0, Qt.ItemDataRole.UserRole, package_info)
            
            # Add child nodes
            for node_name in package_info.get('nodes', []):
                node_item = QTreeWidgetItem(package_item)
                node_item.setText(0, f"  • {node_name}")
                node_item.setText(1, "Node")
                node_item.setData(0, Qt.ItemDataRole.UserRole, {'node_name': node_name, 'package': package_name})
        
        self.plugin_tree.expandAll()
    
    def _on_plugin_selected(self, current, previous):
        """Handle plugin selection in tree"""
        if not current:
            self.plugin_info.clear()
            self.remove_plugin_btn.setEnabled(False)
            return
        
        data = current.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            self.remove_plugin_btn.setEnabled(False)
            return
        
        # Check if it's a package or a node
        if 'path' in data:
            # Package selected
            self.remove_plugin_btn.setEnabled(True)
            package_path = Path(data['path'])
            
            info_text = f"<b>Package:</b> {current.text(0).replace('📦 ', '')}<br>"
            info_text += f"<b>File:</b> {package_path.name}<br>"
            info_text += f"<b>Type:</b> {current.text(1)}<br>"
            info_text += f"<b>Description:</b> {data.get('description', 'N/A')}<br>"
            info_text += f"<b>Nodes:</b> {len(data.get('nodes', []))}<br>"
            
            self.plugin_info.setHtml(info_text)
        else:
            # Node selected - show node details
            self.remove_plugin_btn.setEnabled(False)
            node_name = data.get('node_name')
            
            try:
                node_template = node_templates.get_template(node_name)
                
                info_text = f"<b>Node:</b> {node_name}<br>"
                info_text += f"<b>Package:</b> {data.get('package', 'N/A')}<br>"
                info_text += f"<b>Description:</b> {node_template.get('description', 'N/A')}<br>"
                info_text += f"<b>Category:</b> {node_template.get('category', 'N/A')}<br>"
                
                inputs = node_template.get('inputs', {})
                outputs = node_template.get('outputs', {})
                info_text += f"<b>Inputs:</b> {len(inputs)} | <b>Outputs:</b> {len(outputs)}"
                
                self.plugin_info.setHtml(info_text)
            except Exception as e:
                self.plugin_info.setText(f"Error reading node: {e}")
    
    def _add_plugin(self):
        """Add a new plugin from file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Plugin File", "", "Plugin Files (*.json *.ncpkg);;JSON Packages (*.json);;Archive Packages (*.ncpkg);;All Files (*.*)"
        )
        
        if not file_path:
            return
        
        source = Path(file_path)
        
        try:
            # Validate based on file type
            if source.suffix == '.json':
                # Validate JSON file
                with open(file_path, 'r') as f:
                    plugin_data = json.load(f)
                
                # Check if it's a package (has 'nodes' array) or single node
                if 'nodes' in plugin_data:
                    # Package format - validate it has package_name
                    if 'package_name' not in plugin_data:
                        QMessageBox.warning(self, "Invalid Plugin Package", 
                                          "Plugin package must contain a 'package_name' field.")
                        return
                else:
                    # Single node format - validate it has 'name'
                    if 'name' not in plugin_data:
                        QMessageBox.warning(self, "Invalid Plugin", 
                                          "Plugin file must contain a 'name' field.")
                        return
            elif source.suffix == '.ncpkg':
                # Validate it's a valid zip archive
                import zipfile
                if not zipfile.is_zipfile(file_path):
                    QMessageBox.warning(self, "Invalid Archive", 
                                      "File is not a valid .ncpkg archive.")
                    return
            else:
                QMessageBox.warning(self, "Invalid File Type", 
                                  "Plugin must be a .json or .ncpkg file.")
                return
            
            # Get plugins directory
            try:
                plugins_dir = node_templates.PLUGINS_DIR
            except AttributeError:
                root = Path(__file__).resolve().parent.parent
                plugins_dir = root / "plugins"
            
            plugins_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy file to plugins directory
            dest = plugins_dir / source.name
            
            if dest.exists():
                reply = QMessageBox.question(
                    self, "Plugin Exists", 
                    f"Plugin '{source.name}' already exists. Overwrite?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
            
            shutil.copy2(file_path, dest)
            
            # Reload templates to include new plugin
            node_templates.load_templates()
            self.reload()  # Refresh template list
            self._refresh_plugins()  # Refresh plugin list
            
            QMessageBox.information(self, "Success", 
                                  f"Plugin '{source.name}' installed successfully!")
        
        except json.JSONDecodeError:
            QMessageBox.warning(self, "Invalid File", 
                              "Selected file is not a valid JSON file.")
        except Exception as e:
            QMessageBox.critical(self, "Error", 
                               f"Failed to install plugin: {e}")
    
    def _remove_plugin(self):
        """Remove selected plugin package"""
        current = self.plugin_tree.currentItem()
        if not current:
            return
        
        # Get package data
        data = current.data(0, Qt.ItemDataRole.UserRole)
        if not data or 'path' not in data:
            QMessageBox.warning(self, "Selection Error", "Please select a plugin package to remove.")
            return
        
        package_name = current.text(0).replace('📦 ', '')
        plugin_path = Path(data['path'])
        
        reply = QMessageBox.question(
            self, "Remove Plugin", 
            f"Are you sure you want to remove plugin package '{package_name}'?\n\nThis will remove {len(data.get('nodes', []))} nodes.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        try:
            plugin_path.unlink()
            
            # Reload templates
            node_templates.load_templates()
            self.reload()
            self._refresh_plugins()
            
            QMessageBox.information(self, "Success", 
                                  f"Plugin package '{package_name}' removed successfully!")
        
        except Exception as e:
            QMessageBox.critical(self, "Error", 
                               f"Failed to remove plugin: {e}")
    
    def _refresh_export_nodes(self):
        """Refresh the list of nodes available for export"""
        self.export_node_list.clear()
        
        # Get all custom nodes (type='base' or 'plugin' but not composites)
        for name in node_templates.list_templates():
            template = node_templates.get_template(name)
            if template and template.get('type') in ('base', 'plugin'):
                # Skip internal nodes
                if name.startswith('__'):
                    continue
                self.export_node_list.addItem(name)
    
    def _browse_python_module(self):
        """Browse for a Python module file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Python Module", "", "Python Files (*.py);;All Files (*.*)"
        )
        
        if file_path:
            self.export_module_path.setText(file_path)
    
    def _export_plugin_package(self):
        """Export selected nodes as a .ncpkg file"""
        import zipfile
        import tempfile
        
        # Validate inputs
        package_name = self.export_pkg_name.text().strip()
        if not package_name:
            QMessageBox.warning(self, "Missing Information", "Please enter a package name.")
            return
        
        selected_items = self.export_node_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "No Nodes Selected", "Please select at least one node to export.")
            return
        
        # Get save location
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Save Plugin Package", f"{package_name}.ncpkg", 
            "NodeCanvas Plugin Package (*.ncpkg);;All Files (*.*)"
        )
        
        if not save_path:
            return
        
        try:
            # Create .ncpkg (zip archive)
            with zipfile.ZipFile(save_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # Add package metadata
                package_meta = {
                    "name": package_name,
                    "description": self.export_pkg_desc.toPlainText().strip(),
                    "author": self.export_pkg_author.text().strip(),
                    "version": self.export_pkg_version.text().strip()
                }
                zf.writestr("package.json", json.dumps(package_meta, indent=2))
                
                # Add each selected node
                for item in selected_items:
                    node_name = item.text()
                    template = node_templates.get_template(node_name)
                    
                    if template:
                        # Remove internal keys
                        export_template = {k: v for k, v in template.items() 
                                         if not k.startswith('_')}
                        
                        node_filename = f"nodes/{node_name}.json"
                        zf.writestr(node_filename, json.dumps(export_template, indent=2))
                
                # Add Python module if specified
                module_path = self.export_module_path.text().strip()
                if module_path and Path(module_path).exists():
                    module_name = Path(module_path).name
                    with open(module_path, 'r', encoding='utf-8') as f:
                        module_content = f.read()
                    zf.writestr(f"modules/{module_name}", module_content)
            
            QMessageBox.information(
                self, "Export Successful", 
                f"Plugin package exported successfully!\n\n"
                f"Nodes: {len(selected_items)}\n"
                f"File: {Path(save_path).name}"
            )
            
            # Clear form
            self.export_pkg_name.clear()
            self.export_pkg_desc.clear()
            self.export_pkg_author.clear()
            self.export_pkg_version.setText("1.0")
            self.export_module_path.clear()
            self.export_node_list.clearSelection()
        
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Failed to export plugin package:\n{e}")
