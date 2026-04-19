"""
canvas_removal.py

Node-and-connection removal for LogicEditor. Split out of ``canvas.py``
because the deferred cleanup machinery (hide, detach, stash in
``_recently_removed``, schedule final cleanup) is self-contained and
~400 lines — it never touches input events, painting, or serialisation.

Qt lifetime is delicate here: nodes are hidden and detached first, then
final ``removeItem`` is deferred to ``final_cleanup_now`` at shutdown to
avoid invalidating Qt-owned references mid-event.
"""
import traceback

from PyQt6.QtCore import QTimer


DEBUG_FORCE_IMMEDIATE_REMOVAL = False


class RemovalMixin:
    """Mixin providing node/connection removal and cleanup on LogicEditor."""

    def _collect_pin_options(self, nodes, is_input=True):
        options = []
        seen = set()
        for node in nodes:
            pin_dict = node.input_pins if is_input else node.output_pins
            label_prefix = node.title.toPlainText() or f"Node {node.id}"
            for pin_name in pin_dict.keys():
                key = (node.id, pin_name)
                if key in seen:
                    continue
                seen.add(key)
                options.append(
                    {
                        "node": node.id,
                        "pin": pin_name,
                        "label": f"{label_prefix} ({node.id}) - {pin_name}",
                    }
                )
        return options

    def _clear_pending_preview(self, nodes):
        if not self.pending_from:
            return
        primary = self.pending_from[0] if isinstance(self.pending_from, tuple) else self.pending_from
        if primary not in nodes:
            return
        if self.pending_line:
            try:
                self._scene.removeItem(self.pending_line)
            except Exception:
                pass
        self.pending_line = None
        self.pending_from = None

    def _collect_connections_for_nodes(self, nodes):
        to_remove = set()
        for conn in list(self.connections):
            if conn.from_node in nodes or conn.to_node in nodes:
                to_remove.add(conn)
        return to_remove

    def _delete_connections(self, connections):
        # deletion disabled: noop to avoid crashes; leave function for compatibility
        return

    def _perform_node_deletion(self, nodes, error_context):
        # deletion disabled temporarily per user request; function retained for compatibility
        return

    def _queue_node_deletion(self, nodes, error_context):
        # deletion disabled temporarily per user request; function retained for compatibility
        return

    def update_connections_for_node(self, node_item):
        for conn in list(self.connections):
            if getattr(conn, "_removed", False):
                continue
            if conn.from_node is None or conn.to_node is None:
                try:
                    conn.remove()
                except Exception:
                    pass
                continue
            if conn.from_node is node_item or conn.to_node is node_item:
                conn.update_path()

    def update_all_connections(self):
        """Force an update of all connection visuals and refresh the scene/view."""
        try:
            for conn in list(getattr(self, 'connections', [])):
                try:
                    conn.update_path()
                except Exception:
                    pass
            try:
                if self._scene:
                    self._scene.update()
            except Exception:
                pass
            try:
                self.viewport().update()
            except Exception:
                pass
        except Exception:
            traceback.print_exc()

    def reload_nodes_from_template(self, template_name):
        from core.node_templates import get_template
        tmpl = get_template(template_name)
        if not tmpl:
            return
        for node in self.nodes:
            if getattr(node, "template_name", None) == template_name:
                try:
                    if tmpl.get('type') == 'composite':
                        node.inputs = tmpl.get('inputs', {}) or {}
                        node.outputs = tmpl.get('outputs', {}) or {}
                        node.composite_graph = tmpl.get('graph')
                        node.process = None
                        node.setup_pins(node.inputs, node.outputs)
                    else:
                        ns = {}
                        exec(tmpl.get("code", ""), {}, ns)
                        node.inputs = (
                            ns.get("inputs", {}) if isinstance(ns.get("inputs", {}), dict) else {}
                        )
                        node.outputs = (
                            ns.get("outputs", {}) if isinstance(ns.get("outputs", {}), dict) else {}
                        )
                        node.process = ns.get("process")
                        node.setup_pins(node.inputs, node.outputs)
                except Exception:
                    pass

    def remove_nodes_by_template(self, template_name):
        """Safely remove all nodes on this canvas from `template_name`."""
        nodes = [n for n in list(self.nodes) if getattr(n, 'template_name', None) == template_name]
        if nodes:
            try:
                print(f"DEBUG: remove_nodes_by_template called for '{template_name}', found {len(nodes)} nodes")
                for n in nodes:
                    try:
                        nid = getattr(n, 'id', None)
                        tname = getattr(n, 'template_name', None)
                        title = getattr(n, 'title', None)
                        ttext = title.toPlainText() if title is not None and getattr(title, 'toPlainText', None) else ''
                        print(f"DEBUG: node id={nid} template={tname} title={ttext} scene={bool(n.scene())}")
                    except Exception:
                        traceback.print_exc()
                self.remove_nodes(nodes)
            except Exception:
                print("ERROR: exception in remove_nodes_by_template")
                traceback.print_exc()

    def remove_nodes(self, nodes):
        """Safely remove the given list of NodeItem instances from this canvas."""
        if not nodes:
            return

        nodes = list(nodes)

        try:
            print(f"DEBUG: remove_nodes called with {len(nodes)} nodes")
            for n in nodes:
                try:
                    nid = getattr(n, 'id', None)
                    tname = getattr(n, 'template_name', None)
                    title = getattr(n, 'title', None)
                    ttext = title.toPlainText() if title is not None and getattr(title, 'toPlainText', None) else ''
                    print(f"DEBUG: preparing to remove node id={nid} template={tname} title={ttext} scene={bool(n.scene())}")
                except Exception:
                    traceback.print_exc()
            try:
                self._clear_pending_preview(nodes)
            except Exception:
                print("WARNING: _clear_pending_preview failed")
                traceback.print_exc()
        except Exception:
            print("ERROR: exception while starting remove_nodes")
            traceback.print_exc()

        try:
            conns = self._collect_connections_for_nodes(nodes)
            print(f"DEBUG: collected {len(conns)} connections touching nodes")
            for c in list(conns):
                try:
                    cid = getattr(c, 'id', None)
                    fn = getattr(c, 'from_node', None)
                    tn = getattr(c, 'to_node', None)
                    print(f"DEBUG: removing connection id={cid} from={getattr(fn,'id',None)} to={getattr(tn,'id',None)}")
                    c.remove()
                except Exception:
                    print("WARNING: connection.remove() raised")
                    try:
                        traceback.print_exc()
                    except Exception:
                        pass
        except Exception:
            print("WARNING: _collect_connections_for_nodes failed")
            traceback.print_exc()

        for node in nodes:
            try:
                print(f"DEBUG: calling cleanup() for node id={getattr(node,'id',None)}")
                if getattr(node, 'cleanup', None):
                    node.cleanup()
            except Exception:
                print(f"WARNING: node.cleanup() raised for id={getattr(node,'id',None)}")
                traceback.print_exc()

        def _do_removal(rem_nodes=list(nodes)):
            try:
                for node in rem_nodes:
                    try:
                        print(f"DEBUG: _do_removal processing node id={getattr(node,'id',None)} scene={bool(getattr(node,'scene',lambda:None)())}")
                    except Exception:
                        pass
                    try:
                        try:
                            print(f"DEBUG: _do_removal hiding node id={getattr(node,'id',None)} instead of immediate removal")
                            try:
                                node.setVisible(False)
                            except Exception:
                                pass
                            try:
                                node.setEnabled(False)
                            except Exception:
                                pass
                            try:
                                node.setParentItem(None)
                            except Exception:
                                pass
                            try:
                                self._recently_removed.append(node)
                            except Exception:
                                pass
                        except Exception:
                            print(f"WARNING: _do_removal failed to prepare node id={getattr(node,'id',None)} for deferred removal")
                            traceback.print_exc()
                    except Exception:
                        print(f"WARNING: _do_removal checking node.scene() failed for id={getattr(node,'id',None)}")
                        traceback.print_exc()
                    try:
                        if node in self.nodes:
                            try:
                                self.nodes.remove(node)
                                print(f"DEBUG: _do_removal removed node id={getattr(node,'id',None)} from canvas.nodes")
                            except Exception:
                                print(f"WARNING: _do_removal failed to remove node id={getattr(node,'id',None)} from canvas.nodes")
                                traceback.print_exc()
                    except Exception:
                        pass
                for conn in list(getattr(self, 'connections', [])):
                    try:
                        print(f"DEBUG: _do_removal updating connection id={getattr(conn,'id',None)} from={getattr(getattr(conn,'from_node',None),'id',None)} to={getattr(getattr(conn,'to_node',None),'id',None)}")
                        conn.update_path()
                    except Exception:
                        print(f"WARNING: _do_removal failed during conn.update_path id={getattr(conn,'id',None)}")
                        traceback.print_exc()
            except Exception:
                print("ERROR: _do_removal top-level exception")
                traceback.print_exc()
            try:
                self._schedule_final_cleanup()
            except Exception:
                pass

        try:
            if DEBUG_FORCE_IMMEDIATE_REMOVAL:
                print("DEBUG: DEBUG_FORCE_IMMEDIATE_REMOVAL enabled — running _do_removal() synchronously")
                _do_removal()
            else:
                print("DEBUG: scheduling deferred scene removal via QTimer.singleShot(0, ...) ")
                QTimer.singleShot(0, _do_removal)
        except Exception:
            print("WARNING: scheduled removal failed, running immediate removal")
            try:
                _do_removal()
            except Exception:
                print("ERROR: immediate _do_removal failed")
                traceback.print_exc()

    def _schedule_final_cleanup(self, delay=200):
        if getattr(self, '_final_cleanup_pending', False):
            return
        self._final_cleanup_pending = True

        def _final():
            try:
                self._final_cleanup_pending = False
                nodes_to_drop = list(getattr(self, '_recently_removed', []))
                try:
                    self._recently_removed.clear()
                except Exception:
                    pass
                for n in nodes_to_drop:
                    try:
                        if getattr(n, 'cleanup', None):
                            try:
                                n.cleanup()
                            except Exception:
                                traceback.print_exc()
                    except Exception:
                        pass
                    try:
                        pass
                    except Exception:
                        pass
                for conn in list(getattr(self, 'connections', [])):
                    try:
                        conn.update_path()
                    except Exception:
                        pass
            except Exception:
                traceback.print_exc()

        try:
            QTimer.singleShot(delay, _final)
        except Exception:
            _final()

    def mark_nodes_for_removal(self, nodes):
        """Mark nodes for deferred removal without calling cleanup() immediately."""
        if not nodes:
            return
        nodes = list(nodes)
        try:
            self._clear_pending_preview(nodes)
        except Exception:
            pass
        try:
            conns = self._collect_connections_for_nodes(nodes)
            for c in list(conns):
                try:
                    c.remove()
                except Exception:
                    traceback.print_exc()
        except Exception:
            traceback.print_exc()

        for node in nodes:
            try:
                try:
                    node.setVisible(False)
                except Exception:
                    pass
                try:
                    node.setEnabled(False)
                except Exception:
                    pass
                try:
                    node.setParentItem(None)
                except Exception:
                    pass
            except Exception:
                traceback.print_exc()
            try:
                if node in self.nodes:
                    try:
                        self.nodes.remove(node)
                    except Exception:
                        traceback.print_exc()
            except Exception:
                pass
            try:
                self._recently_removed.append(node)
            except Exception:
                pass

        try:
            self._schedule_final_cleanup()
        except Exception:
            traceback.print_exc()

    def final_cleanup_now(self):
        """Perform final removal of any recently removed nodes immediately."""
        try:
            nodes_to_drop = list(getattr(self, '_recently_removed', []))
            try:
                self._recently_removed.clear()
            except Exception:
                pass
            for n in nodes_to_drop:
                try:
                    if getattr(n, 'cleanup', None):
                        try:
                            n.cleanup()
                        except Exception:
                            traceback.print_exc()
                except Exception:
                    pass
                try:
                    if n.scene():
                        try:
                            n.scene().removeItem(n)
                        except Exception:
                            traceback.print_exc()
                except Exception:
                    pass
            for conn in list(getattr(self, 'connections', [])):
                try:
                    conn.update_path()
                except Exception:
                    pass
        except Exception:
            traceback.print_exc()
