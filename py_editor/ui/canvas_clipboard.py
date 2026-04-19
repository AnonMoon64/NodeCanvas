"""
canvas_clipboard.py

Clipboard + undo/redo for LogicEditor. Copy/paste goes through the system
clipboard as JSON so nodes can be shared across editor instances (UE5-style).
Undo snapshots call ``export_graph`` / ``load_graph`` from the graph IO mixin,
so this sits cleanly on top of that layer.

Split out of ``canvas.py`` because the clipboard/history logic is
self-contained — touches ``nodes``, ``connections``, ``_scene`` only via the
existing node/connection API, never wires up input events or painting.
"""
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QCursor
from PyQt6.QtCore import QTimer

from py_editor.ui.connection_item import ConnectionItem


class ClipboardMixin:
    """Mixin providing copy/cut/paste/duplicate/delete + undo/redo.

    Depends on LogicEditor state: ``nodes``, ``connections``, ``_scene``,
    ``clipboard_data``, ``undo_stack``, ``redo_stack``, ``max_undo_stack``,
    ``_is_undoing``, ``value_changed``, and methods ``add_node``,
    ``add_node_from_template``, ``mark_nodes_for_removal``,
    ``update_all_connections``, ``load_graph``, ``export_graph``.
    """

    def copy_selected(self):
        """Copy selected nodes and their internal connections to system clipboard"""
        selected_nodes = [n for n in self.nodes if n.isSelected()]
        if not selected_nodes:
            print("No nodes selected to copy")
            return

        # Build clipboard data
        selected_ids = {n.id for n in selected_nodes}
        nodes_data = []
        connections_data = []

        for node in selected_nodes:
            node_data = {
                "id": node.id,
                "template": getattr(node, "template_name", None),
                "title": node.title.toPlainText(),
                "pos": [node.pos().x(), node.pos().y()],
                "inputs": node.inputs,
                "outputs": node.outputs,
                "pin_values": getattr(node, "pin_values", {})
            }
            nodes_data.append(node_data)

        # Copy connections that are between selected nodes
        for conn in self.connections:
            if (hasattr(conn, 'from_node') and hasattr(conn, 'to_node') and
                conn.from_node in selected_nodes and conn.to_node in selected_nodes):
                conn_data = {
                    "from_id": conn.from_node.id,
                    "from_pin": getattr(conn, 'from_pin', None),
                    "to_id": conn.to_node.id,
                    "to_pin": getattr(conn, 'to_pin', None)
                }
                connections_data.append(conn_data)

        self.clipboard_data = {
            "nodes": nodes_data,
            "connections": connections_data
        }

        # Also copy to system clipboard as JSON text (like UE5)
        import json
        clipboard_text = json.dumps(self.clipboard_data, indent=2)
        clipboard = QApplication.clipboard()
        clipboard.setText(clipboard_text)

        print(f"Copied {len(nodes_data)} nodes and {len(connections_data)} connections (text format)")

    def paste(self):
        """Paste nodes from clipboard (internal or system) with new IDs"""
        # Try to load from system clipboard first (for cross-editor paste)
        clipboard = QApplication.clipboard()
        clipboard_text = clipboard.text()

        data_to_paste = None

        if clipboard_text:
            try:
                import json
                parsed_data = json.loads(clipboard_text)
                # Validate it looks like our node data format
                if isinstance(parsed_data, dict) and 'nodes' in parsed_data:
                    data_to_paste = parsed_data
                    print("Pasting from system clipboard (text format)")
            except Exception as e:
                print(f"System clipboard doesn't contain valid node data: {e}")

        # Fall back to internal clipboard
        if not data_to_paste:
            if not self.clipboard_data:
                print("Clipboard is empty")
                return
            data_to_paste = self.clipboard_data
            print("Pasting from internal clipboard")

        # Map old IDs to new IDs
        id_map = {}
        pasted_nodes = []

        # Create nodes with new IDs
        for node_data in data_to_paste["nodes"]:
            old_id = node_data["id"]
            template_name = node_data.get("template")

            if template_name:
                new_node = self.add_node_from_template(template_name)
            else:
                new_node = self.add_node(node_data.get("title", "Node"))

            # Position with offset
            pos = node_data.get("pos", [0, 0])
            new_node.setPos(pos[0] + 50, pos[1] + 50)

            # Restore pin values if present
            if "pin_values" in node_data:
                new_node.pin_values = node_data["pin_values"].copy()

            id_map[old_id] = new_node
            pasted_nodes.append(new_node)

        # Recreate connections
        for conn_data in data_to_paste["connections"]:
            old_from = conn_data["from_id"]
            old_to = conn_data["to_id"]

            if old_from in id_map and old_to in id_map:
                new_from = id_map[old_from]
                new_to = id_map[old_to]

                conn = ConnectionItem(new_from, new_to, self)
                conn.from_pin = conn_data.get("from_pin")
                conn.to_pin = conn_data.get("to_pin")
                conn.add_to_scene(self._scene)
                self.connections.append(conn)
                try:
                    # Refresh visuals immediately and after the event loop
                    try:
                        self.update_all_connections()
                    except Exception:
                        pass
                    try:
                        QTimer.singleShot(0, self.update_all_connections)
                    except Exception:
                        pass
                except Exception:
                    pass

        # Select the pasted nodes
        for node in self.nodes:
            node.setSelected(False)
        for node in pasted_nodes:
            node.setSelected(True)

        print(f"Pasted {len(pasted_nodes)} nodes")

    def cut_selected(self):
        """Cut selected nodes (copy then delete)"""
        self.copy_selected()
        self.delete_selected()

    def delete_selected(self):
        """Delete all selected nodes"""
        selected_nodes = [n for n in self.nodes if n.isSelected()]
        if not selected_nodes:
            print("No nodes selected to delete")
            return

        try:
            # Save state for undo
            self.save_state()

            # Use the existing safe removal mechanism
            self.mark_nodes_for_removal(list(selected_nodes))
            print(f"Deleted {len(selected_nodes)} node(s)")
        except Exception as e:
            print(f"Error deleting nodes: {e}")
            import traceback
            traceback.print_exc()

    def duplicate_selected(self):
        """Duplicate currently selected nodes"""
        self.copy_selected()
        self.paste()

    def add_comment_box(self):
        """Add a comment box to group nodes."""
        try:
            from py_editor.ui.node_item import CommentBoxItem
        except ImportError:
            return

        nodes = [n for n in self.nodes if n.isSelected()]
        if nodes:
            # Wrap selected nodes
            min_x = min(n.pos().x() for n in nodes) - 40
            min_y = min(n.pos().y() for n in nodes) - 60
            max_r = max(n.pos().x() + n.node_width for n in nodes) + 40
            max_b = max(n.pos().y() + n.node_height for n in nodes) + 40
            box = CommentBoxItem(min_x, min_y, max_r - min_x, max_b - min_y)
        else:
            # Place at mouse or center
            scene_pt = self.mapToScene(self.mapFromGlobal(QCursor.pos())) if self.underMouse() else self.mapToScene(self.viewport().rect().center())
            box = CommentBoxItem(scene_pt.x() - 150, scene_pt.y() - 100, 300, 200)

        self._scene.addItem(box)
        self.value_changed.emit()

    def save_state(self):
        """Save the current graph state to the undo stack"""
        if self._is_undoing:
            return  # Don't save state during undo/redo operations

        # Export current graph state
        state = self.export_graph()

        # Add to undo stack
        self.undo_stack.append(state)

        # Limit stack size
        if len(self.undo_stack) > self.max_undo_stack:
            self.undo_stack.pop(0)

        # Clear redo stack when new action is performed
        self.redo_stack.clear()

        print(f"State saved (undo stack: {len(self.undo_stack)} items)")

    def undo(self):
        """Undo the last action"""
        if not self.undo_stack:
            print("Nothing to undo")
            return

        # Save current state to redo stack before undoing
        current_state = self.export_graph()
        self.redo_stack.append(current_state)

        # Get the previous state
        previous_state = self.undo_stack.pop()

        # Restore the previous state
        self._is_undoing = True
        try:
            self.load_graph(previous_state)
            print(f"Undo performed (undo stack: {len(self.undo_stack)} items)")
        finally:
            self._is_undoing = False

    def redo(self):
        """Redo the last undone action"""
        if not self.redo_stack:
            print("Nothing to redo")
            return

        # Save current state to undo stack before redoing
        current_state = self.export_graph()
        self.undo_stack.append(current_state)

        # Get the next state
        next_state = self.redo_stack.pop()

        # Restore the next state
        self._is_undoing = True
        try:
            self.load_graph(next_state)
            print(f"Redo performed (redo stack: {len(self.redo_stack)} items)")
        finally:
            self._is_undoing = False
