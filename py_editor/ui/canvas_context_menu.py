"""
canvas_context_menu.py

The big right-click handler for LogicEditor: scene-reference menu when
scene objects are selected, multi-select menu (copy/paste/collapse into
composite/delete), single-node menu (rename/edit/duplicate/delete plus
contextual actions for composite IO, Sequence, SelectInt/StringAppend,
and variable nodes), and the UE5-style searchable "Add Node" dialog on
empty-space right click. Split out of ``canvas.py`` because this single
function was ~650 lines.
"""
import importlib
import traceback

from PyQt6.QtWidgets import (
    QMenu, QApplication, QInputDialog, QMessageBox, QLineEdit,
)
from PyQt6.QtGui import QAction, QColor
from PyQt6.QtCore import QTimer

from py_editor.ui.node_item import NodeItem

try:
    from py_editor.core.node_templates import (
        get_template, get_all_templates, save_template, load_templates,
    )
    from py_editor.ui.node_editor import NodeEditorDialog
except ImportError:
    from core.node_templates import (
        get_template, get_all_templates, save_template, load_templates,
    )
    from ui.node_editor import NodeEditorDialog


class ContextMenuMixin:
    """Mixin providing the right-click context menu for LogicEditor."""

    def on_context_menu(self, point):
        # If there's a pending connection, show the node menu for compatible nodes
        if self.pending_from:
            scene_pt = self.mapToScene(point)
            self._show_connection_node_menu(scene_pt, point)
            return
        
        scene_pt = self.mapToScene(point)
        items = self.items(point)
        target_node = None
        for item in items:
            if isinstance(item, NodeItem):
                target_node = item
                break
            parent = item.parentItem()
            if parent and isinstance(parent, NodeItem):
                target_node = parent
                break

        selected_nodes = [i for i in self._scene.selectedItems() if isinstance(i, NodeItem)]

        # --- Scene Reference Logic ---
        has_sel_objs = False
        sel_objs = []
        if not target_node and not selected_nodes:
            if hasattr(self, 'main_window') and self.main_window.scene_editor:
                sel_objs = [o for o in self.main_window.scene_editor.viewport.scene_objects if o.selected]
                has_sel_objs = len(sel_objs) > 0

        if has_sel_objs:
             menu = QMenu()
             for obj in sel_objs:
                  a = menu.addAction(f"Create Reference to {obj.name}")
                  a.triggered.connect(lambda _, o=obj: self._create_scene_object_reference(o.id, o.name, scene_pt))
             menu.addSeparator()
             all_nodes_act = menu.addAction("All Nodes...")
             action = menu.exec(self.mapToGlobal(point))
             if action == all_nodes_act:
                  pass # proceed to search dialog
             else:
                  return # Reference created
        # -----------------------------

        if len(selected_nodes) > 1:
            menu = QMenu()
            copy_action = QAction("Copy (Ctrl+C)", menu)
            paste_action = QAction("Paste (Ctrl+V)", menu)
            duplicate_action = QAction("Duplicate (Ctrl+D)", menu)
            menu.addAction(copy_action)
            menu.addAction(paste_action)
            menu.addAction(duplicate_action)
            menu.addSeparator()
            delete_sel_action = QAction("Delete", menu)
            collapse_action = QAction("Collapse Into Node", menu)
            menu.addAction(delete_sel_action)
            menu.addAction(collapse_action)
            action = menu.exec(self.mapToGlobal(point))
            if action == copy_action:
                self.copy_selected()
                return
            if action == paste_action:
                self.paste()
                return
            if action == duplicate_action:
                self.duplicate_selected()
                return
            if action == delete_sel_action:
                try:
                    # close the menu and let Qt finish menu processing before removing items
                    try:
                        menu.close()
                        QApplication.processEvents()
                    except Exception:
                        pass
                    # defer removal to avoid deleting QGraphicsItems while menu still holds refs
                    try:
                        print("DEBUG: context-menu multi-delete scheduling removal")
                        QTimer.singleShot(0, lambda: self.mark_nodes_for_removal(list(selected_nodes)))
                    except Exception:
                        print("DEBUG: context-menu multi-delete running mark_nodes_for_removal directly")
                        self.mark_nodes_for_removal(list(selected_nodes))
                    print("DEBUG: context-menu multi-delete scheduled/ran removal, returning")
                except Exception:
                    traceback.print_exc()
                return
            if action == collapse_action:
                sel_set = set(selected_nodes)
                nodes_data = [
                    {
                        "id": node.id,
                        "template": getattr(node, "template_name", None),
                        "pos": [node.pos().x(), node.pos().y()],
                    }
                    for node in selected_nodes
                ]
                conn_data = [
                    {
                        "from": conn.from_node.id,
                        "from_pin": getattr(conn, "from_pin", None),
                        "to": conn.to_node.id,
                        "to_pin": getattr(conn, "to_pin", None),
                    }
                    for conn in self.connections
                    if conn.from_node in sel_set and conn.to_node in sel_set
                ]
                inputs = {}
                outputs = {}
                for conn in self.connections:
                    if conn.from_node not in sel_set and conn.to_node in sel_set:
                        node_id = getattr(conn.to_node, "id", None)
                        pin = getattr(conn, "to_pin", None)
                        if node_id is None or pin is None:
                            continue
                        key = pin
                        if key in inputs:
                            key = f"in_{node_id}_{pin}"
                        inputs[key] = {"node": node_id, "pin": pin, "type": "any"}
                    if conn.from_node in sel_set and conn.to_node not in sel_set:
                        node_id = getattr(conn.from_node, "id", None)
                        pin = getattr(conn, "from_pin", None)
                        if node_id is None or pin is None:
                            continue
                        key = pin
                        if key in outputs:
                            key = f"out_{node_id}_{pin}"
                        outputs[key] = {"node": node_id, "pin": pin, "type": "any"}
                try:
                    input_defaults = [
                        {
                            "external": name,
                            "node": info["node"],
                            "pin": info["pin"],
                        }
                        for name, info in inputs.items()
                    ]
                    output_defaults = [
                        {
                            "external": name,
                            "node": info["node"],
                            "pin": info["pin"],
                        }
                        for name, info in outputs.items()
                    ]
                    # auto-prompt for composite name and use detected inputs/outputs
                    try:
                        comp_name, ok = QInputDialog.getText(self, "Composite Name", "Composite name:")
                        if not ok or not comp_name.strip():
                            QMessageBox.warning(None, "Error", "Composite nodes must have a name.")
                        else:
                            comp = {
                                "type": "composite",
                                "name": comp_name.strip(),
                                "graph": {"nodes": nodes_data, "connections": conn_data},
                                "inputs": inputs,
                                "outputs": outputs,
                            }
                            save_template(comp)
                            load_templates()
                    except Exception as err:
                        traceback.print_exc()
                        QMessageBox.warning(None, "Error", f"Failed to save composite: {err}")
                except Exception as err:
                    QMessageBox.warning(
                        None,
                        "Error",
                        f"Failed to save composite: {err}",
                    )

        elif target_node:
            menu = QMenu()
            rename_action = QAction("Rename", menu)
            edit_action = QAction("Edit Node", menu)
            copy_action = QAction("Copy", menu)
            paste_action = QAction("Paste", menu)
            duplicate_action = QAction("Duplicate", menu)
            delete_action = QAction("Delete", menu)
            
            menu.addAction(rename_action)
            menu.addAction(edit_action)
            menu.addSeparator()
            menu.addAction(copy_action)
            menu.addAction(paste_action)
            menu.addAction(duplicate_action)
            menu.addSeparator()
            menu.addAction(delete_action)
            
            # Add "Set Pin Type" for composite I/O nodes
            tname = getattr(target_node, "template_name", None)
            set_type_action = None
            if tname in ('__composite_input__', '__composite_output__'):
                menu.addSeparator()
                set_type_action = QAction("Set Pin Type", menu)
                menu.addAction(set_type_action)
            
            # Add "Add Output" and "Remove Output" for Sequence nodes (dynamic outputs)
            add_output_action = None
            remove_output_action = None
            if tname == 'Sequence':
                menu.addSeparator()
                add_output_action = QAction("Add Output Pin", menu)
                menu.addAction(add_output_action)
                # Only show remove if more than 2 outputs
                if len(target_node.output_pins) > 2:
                    remove_output_action = QAction("Remove Output Pin", menu)
                    menu.addAction(remove_output_action)

            # Variadic Input Logic (SelectInt, StringAppend)
            add_input_action = None
            remove_input_action = None
            is_variadic_node = tname in ('SelectInt', 'StringAppend')
            if is_variadic_node:
                menu.addSeparator()
                add_input_action = QAction("Add Input Pin", menu)
                menu.addAction(add_input_action)
                # Count current dynamic pins
                prefix = 'option' if tname == 'SelectInt' else 'str'
                dyn_pins = [p for p in target_node.inputs if p.startswith(prefix)]
                if len(dyn_pins) > 1:
                    remove_input_action = QAction("Remove Input Pin", menu)
                    menu.addAction(remove_input_action)
            
            # Add "Change Variable" for variable nodes
            change_var_action = None
            if tname in ('GetVariable', 'SetVariable'):
                menu.addSeparator()
                change_var_action = QAction("Change Variable...", menu)
                menu.addAction(change_var_action)
            
            # Add breakpoint toggle for debugging
            menu.addSeparator()
            breakpoint_text = "Remove Breakpoint" if target_node.has_breakpoint else "Add Breakpoint"
            breakpoint_action = QAction(breakpoint_text, menu)
            menu.addAction(breakpoint_action)
            
            action = menu.exec(self.mapToGlobal(point))
            if action == set_type_action and set_type_action:
                try:
                    # Show dialog to pick pin type
                    current_type = getattr(target_node, 'pin_type', 'any')
                    types = ["any", "int", "float", "string", "bool"]
                    new_type, ok = QInputDialog.getItem(self, "Set Pin Type", "Type:", types, types.index(current_type), False)
                    if ok and new_type:
                        target_node.pin_type = new_type
                        # Update the pins with the new type
                        if tname == '__composite_input__':
                            pin_name = list(target_node.output_pins.keys())[0] if target_node.output_pins else 'out0'
                            target_node.outputs = {pin_name: new_type}
                            target_node.setup_pins(target_node.inputs, target_node.outputs)
                        elif tname == '__composite_output__':
                            pin_name = list(target_node.input_pins.keys())[0] if target_node.input_pins else 'in0'
                            target_node.inputs = {pin_name: new_type}
                            target_node.setup_pins(target_node.inputs, target_node.outputs)
                        self.update_connections_for_node(target_node)
                except Exception:
                    traceback.print_exc()
            if action == add_input_action and add_input_action:
                prefix = 'option' if tname == 'SelectInt' else 'str'
                pin_type = 'any' if tname == 'SelectInt' else 'string'
                idx = 0
                while f"{prefix}{idx}" in target_node.inputs:
                    idx += 1
                target_node.inputs[f"{prefix}{idx}"] = pin_type
                target_node.setup_pins(target_node.inputs, target_node.outputs)
                self.update_connections_for_node(target_node)
                self.value_changed.emit()

            if action == remove_input_action and remove_input_action:
                prefix = 'option' if tname == 'SelectInt' else 'str'
                dyn_pins = sorted([p for p in target_node.inputs if p.startswith(prefix)], 
                               key=lambda x: int(x.replace(prefix, '')))
                if dyn_pins:
                    last_pin = dyn_pins[-1]
                    # Disconnect all connections to this pin
                    for conn in list(self.connections):
                        if conn.to_node == target_node and conn.to_pin == last_pin:
                            conn.remove()
                            if conn in self.connections:
                                self.connections.remove(conn)
                    del target_node.inputs[last_pin]
                    target_node.setup_pins(target_node.inputs, target_node.outputs)
                    self.update_connections_for_node(target_node)
                    self.value_changed.emit()

            if action == add_output_action and add_output_action:
                new_pin = f"then{len(target_node.output_pins)}"
                target_node.outputs[new_pin] = "exec"
                target_node.setup_pins(target_node.inputs, target_node.outputs)
                self.update_connections_for_node(target_node)
                self.value_changed.emit()
            
            if action == remove_output_action and remove_output_action:
                # Remove last thenN pin
                pins = sorted([p for p in target_node.outputs if p.startswith('then')], 
                            key=lambda x: int(x.replace('then', '')))
                if pins:
                    last_pin = pins[-1]
                    # disconnect
                    for conn in list(self.connections):
                        if conn.from_node == target_node and conn.from_pin == last_pin:
                            conn.remove()
                            if conn in self.connections:
                                self.connections.remove(conn)
                    del target_node.outputs[last_pin]
                    target_node.setup_pins(target_node.inputs, target_node.outputs)
                    self.update_connections_for_node(target_node)
                    self.value_changed.emit()

            if action == change_var_action and change_var_action:
                vars = list(getattr(self, 'graph_variables', {}).keys())
                if vars:
                    new_var, ok = QInputDialog.getItem(self, "Change Variable", "Select Variable:", vars, 0, False)
                    if ok and new_var:
                        # Find the 'name' input widget and update it
                        if hasattr(target_node, 'value_widgets') and 'name' in target_node.value_widgets:
                            proxy = target_node.value_widgets['name']
                            widget = proxy.widget()
                            if isinstance(widget, QLineEdit):
                                widget.setText(new_var)
                                # Force update of pin_values
                                target_node.pin_values['name'] = new_var
                                self.value_changed.emit()
                else:
                    QMessageBox.information(self, "Change Variable", "No variables defined in graph.")
            if action == duplicate_action:
                self.duplicate_selected()
                return
            if action == copy_action:
                self.copy_selected()
                return
            if action == paste_action:
                self.paste()
                return
            if action == rename_action:
                try:
                    tname = getattr(target_node, "template_name", None)
                    current = target_node.title.toPlainText() if getattr(target_node, 'title', None) else ''
                    new_text, ok = QInputDialog.getText(self, "Rename Node", "Name:", text=current)
                    if ok and new_text and new_text.strip():
                        new_name = new_text.strip()
                        # rename pin on composite IO nodes
                        if tname == '__composite_input__':
                            old_pins = list(target_node.output_pins.keys())
                            old = old_pins[0] if old_pins else None
                            if old:
                                # preserve metadata if present
                                meta = target_node.outputs.get(old, {})
                                target_node.outputs = {new_name: meta}
                            else:
                                target_node.outputs = {new_name: {}}
                            target_node.setup_pins(target_node.inputs, target_node.outputs)
                            # update connections referencing old pin
                            for conn in list(self.connections):
                                if getattr(conn, 'from_node', None) is target_node and getattr(conn, 'from_pin', None) == old:
                                    conn.from_pin = new_name
                                if getattr(conn, 'to_node', None) is target_node and getattr(conn, 'to_pin', None) == old:
                                    conn.to_pin = new_name
                        elif tname == '__composite_output__':
                            old_pins = list(target_node.input_pins.keys())
                            old = old_pins[0] if old_pins else None
                            if old:
                                meta = target_node.inputs.get(old, {})
                                target_node.inputs = {new_name: meta}
                            else:
                                target_node.inputs = {new_name: {}}
                            target_node.setup_pins(target_node.inputs, target_node.outputs)
                            for conn in list(self.connections):
                                if getattr(conn, 'from_node', None) is target_node and getattr(conn, 'from_pin', None) == old:
                                    conn.from_pin = new_name
                                if getattr(conn, 'to_node', None) is target_node and getattr(conn, 'to_pin', None) == old:
                                    conn.to_pin = new_name
                        # update title text
                        try:
                            target_node.title.setPlainText(new_name)
                        except Exception:
                            pass
                        # refresh visuals
                        self.update_connections_for_node(target_node)
                except Exception:
                    traceback.print_exc()
            if action == edit_action:
                tname = getattr(target_node, "template_name", None)
                template = None
                if tname:
                    template = get_template(tname)
                if template and template.get("type") == "composite":
                    CompositeEditorDialog = None
                    # Try multiple import strategies so the dialog loads whether
                    # running as a package or as a script.
                    import sys
                    from pathlib import Path
                    parent_dir = Path(__file__).resolve().parent.parent
                    if str(parent_dir) not in sys.path:
                        sys.path.insert(0, str(parent_dir))
                    
                    for modname in ("py_editor.ui.composite_editor", "ui.composite_editor", "composite_editor"):
                        try:
                            mod = importlib.import_module(modname)
                            CompositeEditorDialog = getattr(mod, "CompositeEditorDialog", None)
                            if CompositeEditorDialog:
                                break
                        except Exception:
                            pass

                    if not CompositeEditorDialog:
                        QMessageBox.warning(
                            None,
                            "Composite Editor Unavailable",
                            "Could not import CompositeEditorDialog. See console for details.",
                        )
                    else:
                        # use the top-level window as parent so the modal dialog behaves correctly
                        parent_window = self.window() if hasattr(self, "window") else None
                        try:
                            dlg = CompositeEditorDialog(parent_window, template=template)
                        except Exception:
                            traceback.print_exc()
                            QMessageBox.critical(
                                None,
                                "Error",
                                "Failed to create composite editor dialog. See console for details.",
                            )
                            dlg = None

                        if dlg:
                            try:
                                if dlg.exec():
                                    try:
                                        load_templates()
                                    except Exception:
                                        traceback.print_exc()
                                    if tname:
                                        self.reload_nodes_from_template(tname)
                            except Exception:
                                traceback.print_exc()
                                QMessageBox.critical(
                                    None,
                                    "Error",
                                    "Composite editor crashed while running. See console for details.",
                                )
                else:
                    dlg = NodeEditorDialog(self, template=template)
                    if dlg.exec():
                        try:
                            load_templates()
                        except Exception:
                            pass
                        if tname:
                            self.reload_nodes_from_template(tname)
            
            # Handle breakpoint toggle
            if action == breakpoint_action:
                is_set = target_node.toggle_breakpoint()
                status = "added" if is_set else "removed"
                print(f"Breakpoint {status} on node {target_node.id}: {target_node.title.toPlainText()}")
            
            # Handle Sequence add/remove output pins
            if action == add_output_action and add_output_action:
                try:
                    # Find next available output number
                    existing_nums = []
                    for pin_name in target_node.output_pins.keys():
                        if pin_name.startswith('then'):
                            try:
                                existing_nums.append(int(pin_name[4:]))
                            except ValueError:
                                pass
                    next_num = max(existing_nums) + 1 if existing_nums else 0
                    new_pin_name = f"then{next_num}"
                    
                    # Add the new output pin
                    target_node.outputs[new_pin_name] = "exec"
                    target_node.setup_pins(target_node.inputs, target_node.outputs)
                    self.update_connections_for_node(target_node)
                    print(f"Added output pin '{new_pin_name}' to Sequence node")
                except Exception:
                    traceback.print_exc()
            
            if action == remove_output_action and remove_output_action:
                try:
                    # Remove the last output pin (highest number)
                    existing_nums = []
                    for pin_name in target_node.output_pins.keys():
                        if pin_name.startswith('then'):
                            try:
                                existing_nums.append(int(pin_name[4:]))
                            except ValueError:
                                pass
                    if existing_nums and len(existing_nums) > 2:
                        last_num = max(existing_nums)
                        last_pin = f"then{last_num}"
                        
                        # Remove any connections to this pin
                        for conn in list(self.connections):
                            if getattr(conn, 'from_node', None) is target_node and getattr(conn, 'from_pin', None) == last_pin:
                                self.remove_connection(conn)
                        
                        # Remove the pin
                        if last_pin in target_node.outputs:
                            del target_node.outputs[last_pin]
                        target_node.setup_pins(target_node.inputs, target_node.outputs)
                        self.update_connections_for_node(target_node)
                        print(f"Removed output pin '{last_pin}' from Sequence node")
                except Exception:
                    traceback.print_exc()
            
            # per-user request: delete action removed to avoid crashes
            if action == delete_action:
                try:
                    try:
                        menu.close()
                        QApplication.processEvents()
                    except Exception:
                        pass
                    try:
                        print(f"DEBUG: context-menu single-delete scheduling mark_nodes_for_removal for node id={getattr(target_node,'id',None)}")
                        QTimer.singleShot(0, lambda: self.mark_nodes_for_removal([target_node]))
                    except Exception:
                        print("DEBUG: context-menu single-delete running mark_nodes_for_removal directly")
                        self.mark_nodes_for_removal([target_node])
                    print("DEBUG: context-menu single-delete scheduled/ran removal, returning")
                except Exception:
                    traceback.print_exc()
                return

        else:
            # Right-clicked on empty space - show add node menu with search
            templates = get_all_templates()
            if not templates:
                return
            
            # Show searchable node menu dialog
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QTreeWidget, QTreeWidgetItem
            from PyQt6.QtCore import Qt
            
            dialog = QDialog(self)
            dialog.setWindowTitle("Add Node")
            dialog.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
            dialog.resize(350, 400)
            # Position dialog at cursor
            dialog.move(self.mapToGlobal(point))
            
            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(4)
            
            # Search box at top (like UE5 blueprints)
            search_box = QLineEdit(dialog)
            search_box.setPlaceholderText("Search for nodes...")
            search_box.setStyleSheet("""
                QLineEdit {
                    padding: 6px;
                    font-size: 13px;
                    border: 2px solid #555;
                    border-radius: 4px;
                    background-color: #2b2b2b;
                    color: #fff;
                }
                QLineEdit:focus {
                    border-color: #0d7dd1;
                }
            """)
            layout.addWidget(search_box)
            
            # Tree widget for categorized nodes
            tree = QTreeWidget(dialog)
            tree.setHeaderHidden(True)
            tree.setStyleSheet("""
                QTreeWidget {
                    background-color: #2b2b2b;
                    border: 1px solid #555;
                    color: #fff;
                    font-size: 12px;
                }
                QTreeWidget::item {
                    padding: 4px;
                }
                QTreeWidget::item:hover {
                    background-color: #3a3a3a;
                }
                QTreeWidget::item:selected {
                    background-color: #0d7dd1;
                }
            """)
            layout.addWidget(tree)
            
            # Group templates by category
            categories = {}
            for template_name, template in templates.items():
                category = template.get('category', 'Other')
                if category not in categories:
                    categories[category] = []
                display_name = template.get('name', template_name)
                categories[category].append((template_name, display_name))
            
            def populate_tree(filter_text=''):
                tree.clear()
                filter_lower = filter_text.lower()
                has_filter = bool(filter_text.strip())
                
                for category in sorted(categories.keys()):
                    # Filter nodes in this category
                    filtered_nodes = []
                    for template_name, display_name in categories[category]:
                        if not filter_text or filter_lower in display_name.lower() or filter_lower in template_name.lower():
                            filtered_nodes.append((template_name, display_name))
                    
                    # Only show category if it has matching nodes
                    if filtered_nodes:
                        category_item = QTreeWidgetItem([category])
                        category_item.setFlags(category_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                        category_item.setForeground(0, QColor(150, 150, 150))
                        tree.addTopLevelItem(category_item)
                        
                        for template_name, display_name in sorted(filtered_nodes, key=lambda x: x[1]):
                            node_item = QTreeWidgetItem([display_name])
                            node_item.setData(0, Qt.ItemDataRole.UserRole, template_name)
                            category_item.addChild(node_item)
                        
                        # Expand only if there's a search filter
                        category_item.setExpanded(has_filter)
            
            # Initial population
            populate_tree()
            
            # Connect search box to filter
            search_box.textChanged.connect(populate_tree)
            
            # Handle selection
            selected_template = [None]
            
            def on_item_activated(item, column):
                template_name = item.data(0, Qt.ItemDataRole.UserRole)
                if template_name:
                    selected_template[0] = template_name
                    dialog.accept()
            
            def on_item_double_clicked(item, column):
                on_item_activated(item, column)
            
            tree.itemActivated.connect(on_item_activated)
            tree.itemDoubleClicked.connect(on_item_double_clicked)
            
            # Focus search box immediately
            search_box.setFocus()
            
            # Show dialog
            if dialog.exec() == QDialog.DialogCode.Accepted and selected_template[0]:
                self.add_node_from_template(selected_template[0], pos=scene_pt)

