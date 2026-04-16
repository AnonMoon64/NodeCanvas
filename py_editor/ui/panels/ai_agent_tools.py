"""
ai_agent_tools.py

Formal tool executor for the Atom agentic AI assistant.

Each tool is a method on AgentToolExecutor and returns a JSON-serialisable
dict so the result can be fed straight back into the LLM conversation.

Supported tools (24):
  get_graph, get_node, list_templates, search_templates,
  add_node, delete_node, connect, disconnect, batch_connect,
  set_value, move_node, rename_node,
  arrange_nodes, clear_graph, find_nodes,
  create_template, add_variable, get_variables,
  run_graph, undo, redo, duplicate_node,
  select_nodes, get_connections
"""

import math
import json
import re
from typing import Any, Dict, List, Optional
from PyQt6.QtCore import QPointF, QTimer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node_to_dict(node) -> dict:
    """Serialize a NodeItem to a minimal JSON-safe dict."""
    try:
        title = node.title.toPlainText() if hasattr(node.title, 'toPlainText') else str(node.title)
    except Exception:
        title = str(getattr(node, 'template_name', ''))
    return {
        "id": node.id,
        "template": getattr(node, 'template_name', title),
        "label": title,
        "pos": [round(node.pos().x(), 1), round(node.pos().y(), 1)],
        "inputs":  dict(getattr(node, 'inputs', {}) or {}),
        "outputs": dict(getattr(node, 'outputs', {}) or {}),
        "values":  dict(getattr(node, 'pin_values', {}) or {}),
    }


def _conn_to_dict(conn) -> dict:
    """Serialize a ConnectionItem to dict."""
    return {
        "from_id":   getattr(conn.from_node, 'id', None),
        "from_pin":  conn.from_pin,
        "to_id":     getattr(conn.to_node, 'id', None),
        "to_pin":    conn.to_pin,
    }


def _find_node(le, ref) -> Optional[Any]:
    """Resolve an id (int), numeric-string, or template-name / label ref to a NodeItem."""
    if ref is None:
        return None
    nodes = getattr(le, 'nodes', []) or []

    # integer id
    if isinstance(ref, int):
        for n in nodes:
            if n.id == ref:
                return n
        return None

    s = str(ref).strip()

    # numeric string
    try:
        nid = int(s)
        for n in nodes:
            if n.id == nid:
                return n
    except ValueError:
        pass

    sl = s.lower()

    # exact template match
    for n in nodes:
        t = getattr(n, 'template_name', '') or ''
        if t.lower() == sl:
            return n

    # exact label match
    for n in nodes:
        try:
            lbl = n.title.toPlainText() if hasattr(n.title, 'toPlainText') else str(n.title)
        except Exception:
            lbl = ''
        if lbl.lower() == sl:
            return n

    # substring match (last one wins → most-recently-created)
    for n in reversed(nodes):
        t = getattr(n, 'template_name', '') or ''
        lbl = ''
        try:
            lbl = n.title.toPlainText() if hasattr(n.title, 'toPlainText') else str(n.title)
        except Exception:
            pass
        if sl in t.lower() or sl in lbl.lower():
            return n

    return None


# Flow-control pin names, ordered by commonness.
# The agent prefers these when no explicit pin is specified.
# NOTE: includes both modern names ('exec', 'out') AND legacy names ('exec_out', 'exec_in')
# so auto-detection works for all node templates.
_FLOW_OUT = ('out', 'exec', 'exec_out', 'then', 'flow', 'trigger', 'done', 'next', 'run', 'output', 'result')
_FLOW_IN  = ('in',  'exec', 'exec_in',  'flow', 'trigger', 'input', 'run',  'receive', 'enter')


def _auto_pin(node, direction: str, prefer_flow: bool = True) -> Optional[str]:
    """Return the best pin name for the given direction ('in'|'out').

    Priority (when prefer_flow=True):
      1. A well-known flow-control pin name (out/exec/in/exec …)
      2. First available pin (alphabetical fallback)
    """
    if direction == 'out':
        pins = getattr(node, 'output_pins', {}) or getattr(node, 'outputs', {}) or {}
        priority = _FLOW_OUT
    else:
        pins = getattr(node, 'input_pins', {}) or getattr(node, 'inputs', {}) or {}
        priority = _FLOW_IN

    if not pins:
        return None

    pin_names = list(pins.keys())
    if prefer_flow:
        pin_lower = [p.lower() for p in pin_names]
        for fp in priority:
            if fp in pin_lower:
                return pin_names[pin_lower.index(fp)]

    return pin_names[0]


def _ordered_pins(node, direction: str) -> list:
    """Return pin names ordered: flow-priority names first, then others."""
    if direction == 'out':
        pins = getattr(node, 'output_pins', {}) or getattr(node, 'outputs', {}) or {}
        priority = _FLOW_OUT
    else:
        pins = getattr(node, 'input_pins', {}) or getattr(node, 'inputs', {}) or {}
        priority = _FLOW_IN

    names = list(pins.keys())
    low   = [p.lower() for p in names]
    flow  = [names[low.index(fp)] for fp in priority if fp in low]
    rest  = [p for p in names if p not in flow]
    return flow + rest


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------

class AgentToolExecutor:
    """Executes all agent tools against the live logic editor."""

    def __init__(self, main_window):
        self.mw = main_window
        # ref_map: alias → node_id (set during add_node with a 'ref' param)
        self._ref_map: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _le(self):
        """Return the active logic editor (canvas) or raise."""
        le = getattr(self.mw, 'logic_editor', None)
        if le is None:
            raise RuntimeError("Logic editor not available")
        return le

    def _resolve(self, ref):
        """Resolve ref → NodeItem, checking alias map first."""
        if isinstance(ref, str) and ref in self._ref_map:
            return _find_node(self._le(), self._ref_map[ref])
        return _find_node(self._le(), ref)

    def _register_ref(self, ref: Optional[str], node_id: int):
        if ref:
            self._ref_map[str(ref)] = node_id

    # ------------------------------------------------------------------
    # Tool: get_graph
    # ------------------------------------------------------------------

    def get_graph(self) -> dict:
        """Return full graph state: nodes + connections."""
        le = self._le()
        nodes = [_node_to_dict(n) for n in (getattr(le, 'nodes', []) or [])]
        conns = [_conn_to_dict(c) for c in (getattr(le, 'connections', []) or [])]
        return {
            "ok": True,
            "node_count": len(nodes),
            "connection_count": len(conns),
            "nodes": nodes,
            "connections": conns,
        }

    # ------------------------------------------------------------------
    # Tool: get_node
    # ------------------------------------------------------------------

    def get_node(self, node) -> dict:
        n = self._resolve(node)
        if n is None:
            return {"ok": False, "error": f"Node not found: {node!r}"}
        d = _node_to_dict(n)
        le = self._le()
        # Add connections involving this node
        conns = [_conn_to_dict(c) for c in (getattr(le, 'connections', []) or [])
                 if getattr(c.from_node, 'id', None) == n.id
                 or getattr(c.to_node, 'id', None) == n.id]
        d["connections"] = conns
        d["ok"] = True
        return d

    # ------------------------------------------------------------------
    # Tool: list_templates
    # ------------------------------------------------------------------

    def list_templates(self) -> dict:
        """Return all templates grouped by category, with pin info."""
        try:
            from py_editor.core.node_templates import get_all_templates
            all_tmpl = get_all_templates()
        except Exception as e:
            return {"ok": False, "error": str(e)}

        categories: Dict[str, list] = {}
        for name, data in sorted(all_tmpl.items()):
            if not isinstance(data, dict):
                continue
            cat = data.get('category', 'Uncategorized')
            inp = data.get('inputs', {}) or {}
            out = data.get('outputs', {}) or {}
            # Normalize to {pin: type} format
            def _norm(d):
                if isinstance(d, dict):
                    return {k: (v if isinstance(v, str) else v.get('type', 'any') if isinstance(v, dict) else 'any')
                            for k, v in d.items()}
                return {}
            categories.setdefault(cat, []).append({
                "name": name,
                "inputs":  _norm(inp),
                "outputs": _norm(out),
                "description": data.get('description', ''),
            })
        return {"ok": True, "categories": categories}

    # ------------------------------------------------------------------
    # Tool: search_templates
    # ------------------------------------------------------------------

    def search_templates(self, query: str) -> dict:
        """Fuzzy-search templates by name, category, or description."""
        try:
            from py_editor.core.node_templates import get_all_templates
            all_tmpl = get_all_templates()
        except Exception as e:
            return {"ok": False, "error": str(e), "results": []}

        q = str(query).lower().strip()
        results = []
        for name, data in all_tmpl.items():
            if not isinstance(data, dict):
                continue
            haystack = " ".join([
                name.lower(),
                data.get('category', '').lower(),
                data.get('description', '').lower(),
            ])
            # Score: number of query words found
            words = q.split()
            score = sum(1 for w in words if w in haystack) + (1 if q in name.lower() else 0)
            if score > 0:
                inp = data.get('inputs', {}) or {}
                out = data.get('outputs', {}) or {}
                results.append({
                    "name": name,
                    "category": data.get('category', ''),
                    "inputs":  {k: (v if isinstance(v, str) else 'any') for k, v in inp.items()},
                    "outputs": {k: (v if isinstance(v, str) else 'any') for k, v in out.items()},
                    "score": score,
                })
        results.sort(key=lambda x: -x['score'])
        return {"ok": True, "query": query, "results": results[:15]}

    # ------------------------------------------------------------------
    # Tool: add_node
    # ------------------------------------------------------------------

    def add_node(self, template: str, x: float = 0, y: float = 0,
                 ref: Optional[str] = None, label: Optional[str] = None) -> dict:
        """Create a node from a template.

        Position is determined by ai_node_placer.suggest_position():
          - If (x, y) are both 0 → full auto-placement based on graph topology.
          - Otherwise  → use (x, y) as a hint; collision-checked and adjusted.

        Never call arrange_nodes — placement is handled here automatically.
        """
        le = self._le()

        # ---- resolve template (case-insensitive fallback) ----
        try:
            from py_editor.core.node_templates import get_template, get_all_templates
            tmpl_data = get_template(template)
            if not tmpl_data:
                all_t = get_all_templates()
                match = next((k for k in all_t if k.lower() == template.lower()), None)
                if match:
                    template  = match
                    tmpl_data = get_template(match)
                else:
                    return {"ok": False,
                            "error": f"Template '{template}' not found. "
                                     "Use search_templates to find the right name."}
        except Exception as e:
            return {"ok": False, "error": f"Template lookup failed: {e}"}

        # ---- smart placement ----
        try:
            from py_editor.ui.panels.ai_node_placer import suggest_position
            td = tmpl_data if isinstance(tmpl_data, dict) else {}
            category = td.get('category', '')
            # Pass pin dicts so pure-function nodes (e.g. Chance) with no exec
            # pins are reliably placed to the LEFT of their consumer.
            tmpl_inputs  = td.get('inputs')  or td.get('input_pins')  or None
            tmpl_outputs = td.get('outputs') or td.get('output_pins') or None
            px, py = suggest_position(
                le=le,
                template_name=template,
                category=category,
                hint_x=float(x) if (float(x) != 0.0 or float(y) != 0.0) else None,
                hint_y=float(y) if (float(x) != 0.0 or float(y) != 0.0) else None,
                inputs=tmpl_inputs,
                outputs=tmpl_outputs,
            )
        except Exception:
            px, py = float(x), float(y)

        pos = QPointF(px, py)

        # ---- create node ----
        try:
            node = le.add_node_from_template(template, pos)
        except Exception as e:
            return {"ok": False, "error": f"add_node failed: {e}"}

        if label:
            try:
                node.title.setPlainText(label)
            except Exception:
                pass

        nid = getattr(node, 'id', None)
        self._register_ref(ref, nid)
        self._register_ref(template, nid)   # auto-register by template name too

        return {
            "ok":      True,
            "id":      nid,
            "template": template,
            "ref":     ref or template,
            "pos":     [round(px, 1), round(py, 1)],
            "inputs":  dict(getattr(node, 'inputs',  {}) or {}),
            "outputs": dict(getattr(node, 'outputs', {}) or {}),
        }

    # ------------------------------------------------------------------
    # Tool: delete_node
    # ------------------------------------------------------------------

    def delete_node(self, node) -> dict:
        """Delete a node by id, ref, or template name. Accepts 'all:TemplateName' to delete all of a type."""
        le = self._le()

        if isinstance(node, str) and node.startswith("all:"):
            tname = node[4:].strip()
            le.remove_nodes_by_template(tname)
            return {"ok": True, "deleted": True, "all_of_template": tname}

        n = self._resolve(node)
        if n is None:
            return {"ok": False, "error": f"Node not found: {node!r}"}

        nid = n.id
        try:
            le.remove_nodes([n])
        except Exception as e:
            return {"ok": False, "error": str(e)}

        # Remove from ref map
        self._ref_map = {k: v for k, v in self._ref_map.items() if v != nid}
        return {"ok": True, "deleted": True, "id": nid}

    # ------------------------------------------------------------------
    # Tool: connect
    # ------------------------------------------------------------------

    def connect(self, from_node, to_node,
                from_pin: Optional[str] = None, to_pin: Optional[str] = None) -> dict:
        """Connect two nodes.

        If from_pin/to_pin are omitted the tool tries combinations in this
        priority order: flow-control pins first, then data pins.  It attempts
        up to 9 combinations before giving up and returning a detailed error.
        """
        le = self._le()
        fn = self._resolve(from_node)
        tn = self._resolve(to_node)
        if fn is None:
            return {"ok": False, "error": f"Source node not found: {from_node!r}"}
        if tn is None:
            return {"ok": False, "error": f"Destination node not found: {to_node!r}"}

        out_ordered = _ordered_pins(fn, 'out')
        in_ordered  = _ordered_pins(tn, 'in')

        if not out_ordered:
            return {"ok": False, "error": f"Node {fn.id} ({getattr(fn,'template_name','?')}) has no output pins"}
        if not in_ordered:
            return {"ok": False, "error": f"Node {tn.id} ({getattr(tn,'template_name','?')}) has no input pins"}

        # Build candidate lists.
        # If a pin was explicitly specified, put it first but also append aliases so
        # we can recover from legacy naming mismatches (exec_out↔exec, etc.).
        _OUT_ALIAS = {
            'exec_out': ['exec', 'out', 'then', 'done'],
            'out':      ['exec', 'exec_out', 'then', 'done'],
            'exec':     ['exec_out', 'out', 'then', 'done'],
        }
        _IN_ALIAS = {
            'exec_in':  ['exec', 'in', 'input'],
            'in':       ['exec', 'exec_in', 'input'],
            'exec':     ['exec_in', 'in', 'input'],
        }

        if from_pin:
            fp_candidates = [from_pin] + [a for a in _OUT_ALIAS.get(from_pin.lower(), []) if a in out_ordered]
        else:
            fp_candidates = out_ordered[:4]

        if to_pin:
            tp_candidates = [to_pin] + [a for a in _IN_ALIAS.get(to_pin.lower(), []) if a in in_ordered]
        else:
            tp_candidates = in_ordered[:4]

        last_error = ""
        tried = []
        for fp in fp_candidates:
            for tp in tp_candidates:
                pair = f"{fp}→{tp}"
                if pair in tried:
                    continue
                tried.append(pair)

                # Pre-screen: skip exec↔data mismatches before hitting the engine.
                # This avoids wasted attempts when the AI omits explicit pin names.
                try:
                    out_type = le._ai_pin_type(fn, fp, 'out')
                    in_type  = le._ai_pin_type(tn, tp, 'in')
                    if not le._ai_pins_compatible(out_type, in_type):
                        last_error = (
                            f"type mismatch: {fp}({out_type}) cannot connect to "
                            f"{tp}({in_type}) — exec pins only connect to exec pins"
                        )
                        continue
                except Exception:
                    pass  # If type check fails, let the engine decide

                try:
                    ok = le.add_connection_by_id(fn.id, fp, tn.id, tp)
                except Exception as e:
                    last_error = str(e)
                    continue
                if ok:
                    return {
                        "ok": True,
                        "from_id": fn.id, "from_pin": fp,
                        "to_id":   tn.id, "to_pin":   tp,
                    }
                last_error = f"engine rejected {pair}"

        # Nothing worked — give the AI enough info to self-correct
        return {
            "ok": False,
            "error": (
                f"Could not connect node {fn.id} ({getattr(fn,'template_name','?')}) "
                f"→ node {tn.id} ({getattr(tn,'template_name','?')}). "
                f"Tried: {tried[:6]}. Last result: {last_error}. "
                f"Node {fn.id} available outputs: {out_ordered}. "
                f"Node {tn.id} available inputs: {in_ordered}. "
                "Retry specifying exact pin names from those lists."
            ),
        }

    # ------------------------------------------------------------------
    # Tool: disconnect
    # ------------------------------------------------------------------

    def disconnect(self, from_node, to_node,
                   from_pin: Optional[str] = None, to_pin: Optional[str] = None) -> dict:
        """Remove a connection between two nodes."""
        le = self._le()
        fn = self._resolve(from_node)
        tn = self._resolve(to_node)
        if fn is None:
            return {"ok": False, "error": f"Source node not found: {from_node!r}"}
        if tn is None:
            return {"ok": False, "error": f"Destination not found: {to_node!r}"}

        removed = 0
        conns_to_remove = []
        for c in list(getattr(le, 'connections', []) or []):
            fid = getattr(c.from_node, 'id', None)
            tid = getattr(c.to_node, 'id', None)
            if fid == fn.id and tid == tn.id:
                if from_pin and c.from_pin != from_pin:
                    continue
                if to_pin and c.to_pin != to_pin:
                    continue
                conns_to_remove.append(c)

        for c in conns_to_remove:
            try:
                c.remove_from_scene()
            except Exception:
                pass
            try:
                le.connections.remove(c)
                removed += 1
            except Exception:
                pass

        if removed:
            try:
                le.save_state()
            except Exception:
                pass

        return {"ok": True, "removed": removed}

    # ------------------------------------------------------------------
    # Tool: set_value
    # ------------------------------------------------------------------

    def set_value(self, node, pin: str, value: Any) -> dict:
        """Set a pin's value on a node (for unconnected inputs)."""
        n = self._resolve(node)
        if n is None:
            return {"ok": False, "error": f"Node not found: {node!r}"}

        # Coerce strings to numbers where sensible
        val = value
        if isinstance(value, str):
            if value.strip().endswith('%'):
                try:
                    val = float(value.strip().rstrip('%')) / 100.0
                except Exception:
                    pass
            else:
                for cast in (int, float):
                    try:
                        val = cast(value)
                        break
                    except Exception:
                        pass

        # Set in pin_values dict
        if not hasattr(n, 'pin_values') or n.pin_values is None:
            n.pin_values = {}
        n.pin_values[pin] = val

        # Update UI widget if present
        try:
            proxy = (getattr(n, 'value_widgets', {}) or {}).get(pin)
            if proxy:
                w = proxy.widget()
                if w is not None:
                    from PyQt6.QtWidgets import QComboBox, QLineEdit
                    if isinstance(w, QComboBox):
                        t = str(val)
                        idx = w.findText(t)
                        if idx >= 0:
                            w.setCurrentIndex(idx)
                        elif t.lower() in ('true', 'false'):
                            w.setCurrentIndex(1 if t.lower() == 'true' else 0)
                    elif hasattr(w, 'setValue'):
                        try:
                            w.setValue(float(val))
                        except Exception:
                            pass
                    elif isinstance(w, QLineEdit):
                        w.setText(str(val))
        except Exception:
            pass

        try:
            le = self._le()
            if hasattr(le, 'value_changed'):
                le.value_changed.emit()
        except Exception:
            pass

        return {"ok": True, "id": n.id, "pin": pin, "value": val}

    # ------------------------------------------------------------------
    # Tool: move_node
    # ------------------------------------------------------------------

    def move_node(self, node, x: float, y: float) -> dict:
        """Move a node to canvas position (x, y)."""
        n = self._resolve(node)
        if n is None:
            return {"ok": False, "error": f"Node not found: {node!r}"}
        try:
            n.setPos(QPointF(float(x), float(y)))
        except Exception as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "id": n.id, "pos": [float(x), float(y)]}

    # ------------------------------------------------------------------
    # Tool: rename_node
    # ------------------------------------------------------------------

    def rename_node(self, node, name: str) -> dict:
        """Change a node's display label."""
        n = self._resolve(node)
        if n is None:
            return {"ok": False, "error": f"Node not found: {node!r}"}
        try:
            n.title.setPlainText(str(name))
        except Exception as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "id": n.id, "name": name}

    # ------------------------------------------------------------------
    # Tool: duplicate_node
    # ------------------------------------------------------------------

    def duplicate_node(self, node, offset_x: float = 200, offset_y: float = 0,
                       ref: Optional[str] = None) -> dict:
        """Duplicate a node, placing the copy at an offset."""
        n = self._resolve(node)
        if n is None:
            return {"ok": False, "error": f"Node not found: {node!r}"}
        tname = getattr(n, 'template_name', None)
        if not tname:
            return {"ok": False, "error": "Cannot duplicate: node has no template_name"}
        nx = n.pos().x() + float(offset_x)
        ny = n.pos().y() + float(offset_y)
        result = self.add_node(tname, nx, ny, ref=ref)
        if result.get('ok'):
            # Copy pin values
            for pin, val in (getattr(n, 'pin_values', {}) or {}).items():
                self.set_value(result['id'], pin, val)
        return result

    # ------------------------------------------------------------------
    # Tool: arrange_nodes
    # ------------------------------------------------------------------

    def arrange_nodes(self, style: str = "flow") -> dict:
        """Re-layout ALL nodes on the canvas.

        NOTE: The AI should NOT call this — add_node places nodes automatically.
        This tool exists for manual user requests ("tidy the graph").

        All canvas operations (setPos) are dispatched to the main thread via
        QTimer to avoid PyQt6 scene corruption from background threads.

        Styles: 'flow' (topological left→right), 'grid', 'tree'.
        """
        import threading as _threading
        from PyQt6.QtCore import QTimer as _QTimer

        le    = self._le()
        nodes = list(getattr(le, 'nodes', []) or [])
        if not nodes:
            return {"ok": True, "message": "No nodes to arrange"}

        conns = list(getattr(le, 'connections', []) or [])

        # ---- Compute target positions (pure data, no Qt calls) -----------
        positions: Dict[int, tuple] = {}   # node_id → (x, y)

        if style == "grid":
            cols = max(1, math.ceil(math.sqrt(len(nodes))))
            W, H = 220, 140
            for i, n in enumerate(nodes):
                r, c = divmod(i, cols)
                positions[n.id] = (c * W, r * H)

        elif style in ("flow", "tree"):
            in_degree: Dict[int, int] = {n.id: 0 for n in nodes}
            adj: Dict[int, list]      = {n.id: [] for n in nodes}
            for c in conns:
                fid = getattr(c.from_node, 'id', None)
                tid = getattr(c.to_node,   'id', None)
                if fid in adj and tid in in_degree:
                    adj[fid].append(tid)
                    in_degree[tid] += 1

            col: Dict[int, int] = {}
            queue = [nid for nid, deg in in_degree.items() if deg == 0]
            while queue:
                nid = queue.pop(0)
                c   = col.get(nid, 0)
                for nxt in adj.get(nid, []):
                    col[nxt] = max(col.get(nxt, 0), c + 1)
                    in_degree[nxt] -= 1
                    if in_degree[nxt] == 0:
                        queue.append(nxt)

            cols_map: Dict[int, list] = {}
            for n in nodes:
                cols_map.setdefault(col.get(n.id, 0), []).append(n)

            W, H = 240, 130
            for ci, col_nodes in sorted(cols_map.items()):
                for ri, n in enumerate(col_nodes):
                    positions[n.id] = (ci * W, ri * H)

        else:
            return {"ok": False,
                    "error": f"Unknown style: {style!r}. Use 'flow', 'grid', or 'tree'."}

        # ---- Apply positions ON THE MAIN THREAD (thread-safe) -----------
        done_event = _threading.Event()
        error_box  = [None]

        def _apply():
            try:
                id_map = {n.id: n for n in nodes}
                for nid, (x, y) in positions.items():
                    nd = id_map.get(nid)
                    if nd:
                        nd.setPos(QPointF(x, y))
                try:
                    le.save_state()
                except Exception:
                    pass
            except Exception as exc:
                error_box[0] = str(exc)
            finally:
                done_event.set()

        _QTimer.singleShot(0, _apply)

        if not done_event.wait(timeout=5.0):
            return {"ok": False,
                    "error": "arrange_nodes timed out — main thread may be busy."}
        if error_box[0]:
            return {"ok": False, "error": error_box[0]}

        return {"ok": True, "arranged": len(nodes), "style": style}

    # ------------------------------------------------------------------
    # Tool: clear_graph
    # ------------------------------------------------------------------

    def clear_graph(self, confirm: bool = False) -> dict:
        """Remove all nodes. Requires confirm=true."""
        if not confirm:
            le = self._le()
            count = len(getattr(le, 'nodes', []) or [])
            return {
                "ok": False,
                "error": "Confirmation required. Re-call with confirm=true to clear all nodes.",
                "node_count": count,
            }
        le = self._le()
        nodes = list(getattr(le, 'nodes', []) or [])
        count = len(nodes)
        try:
            le.remove_nodes(nodes)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        self._ref_map.clear()
        return {"ok": True, "cleared": True, "nodes_removed": count}

    # ------------------------------------------------------------------
    # Tool: create_template
    # ------------------------------------------------------------------

    def create_template(self, name: str, category: str = "Custom",
                        inputs: Optional[dict] = None, outputs: Optional[dict] = None,
                        code: Optional[str] = None, description: str = "") -> dict:
        """Create and register a new node template."""
        try:
            from py_editor.core.node_templates import save_template, load_templates, get_all_templates
        except Exception as e:
            return {"ok": False, "error": f"Could not import node_templates: {e}"}

        tmpl: Dict[str, Any] = {
            "type": "base",
            "name": name,
            "category": category,
            "description": description,
            "inputs":  inputs or {},
            "outputs": outputs or {},
        }
        if code:
            tmpl["code"] = code
        else:
            # Generate minimal boilerplate
            in_args = ", ".join(f"{k}=None" for k in (inputs or {}).keys())
            out_keys = list((outputs or {}).keys())
            ret = ("None" if not out_keys else
                   ("{" + ", ".join(f'"{k}": None' for k in out_keys) + "}"
                    if len(out_keys) > 1 else "None"))
            tmpl["code"] = (
                f"name = {name!r}\n"
                f"inputs = {json.dumps(inputs or {})}\n"
                f"outputs = {json.dumps(outputs or {})}\n\n"
                f"def process({in_args}):\n"
                f"    return {ret}\n"
            )

        try:
            save_template(tmpl)
            load_templates()
        except Exception as e:
            return {"ok": False, "error": f"save_template failed: {e}"}

        # Refresh logic editor template cache
        try:
            le = self._le()
            if hasattr(le, '_templates_cache'):
                le._templates_cache = get_all_templates()
        except Exception:
            pass

        return {"ok": True, "name": name, "category": category,
                "inputs": inputs or {}, "outputs": outputs or {}}

    # ------------------------------------------------------------------
    # Tool: add_variable
    # ------------------------------------------------------------------

    def add_variable(self, name: str, type: str = "float", value: Any = None) -> dict:
        """Add a graph variable."""
        le = self._le()
        if not hasattr(le, 'graph_variables') or le.graph_variables is None:
            le.graph_variables = {}
        default_values = {"float": 0.0, "int": 0, "bool": False, "string": "", "any": None}
        le.graph_variables[name] = {
            "type": type,
            "value": value if value is not None else default_values.get(type, None)
        }
        try:
            le.value_changed.emit()
        except Exception:
            pass
        return {"ok": True, "name": name, "type": type,
                "value": le.graph_variables[name]["value"]}

    # ------------------------------------------------------------------
    # Tool: set_variable
    # ------------------------------------------------------------------

    def set_variable(self, name: str, value: Any) -> dict:
        """Update the value of an existing graph variable."""
        le = self._le()
        if not hasattr(le, 'graph_variables') or name not in le.graph_variables:
            return {"ok": False, "error": f"Variable '{name}' not found. Use add_variable to create it."}
        
        le.graph_variables[name]["value"] = value
        try:
            le.value_changed.emit()
        except Exception:
            pass
        return {"ok": True, "name": name, "value": value}

    # ------------------------------------------------------------------
    # Tool: delete_variable
    # ------------------------------------------------------------------

    def delete_variable(self, name: str) -> dict:
        """Remove a graph variable."""
        le = self._le()
        if not hasattr(le, 'graph_variables') or name not in le.graph_variables:
            return {"ok": False, "error": f"Variable '{name}' not found."}
        
        del le.graph_variables[name]
        try:
            le.value_changed.emit()
            if hasattr(self.mw, 'variables'):
                self.mw.variables.refresh()
        except Exception:
            pass
        return {"ok": True, "deleted": name}

    # ------------------------------------------------------------------
    # Tool: get_variables
    # ------------------------------------------------------------------

    def get_variables(self) -> dict:
        """Return all graph variables (name, type, value)."""
        le = self._le()
        return {"ok": True, "variables": dict(getattr(le, 'graph_variables', {}) or {})}

    # ------------------------------------------------------------------
    # Tool: undo
    # ------------------------------------------------------------------

    def undo(self) -> dict:
        le = self._le()
        try:
            le.undo()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Tool: redo
    # ------------------------------------------------------------------

    def redo(self) -> dict:
        le = self._le()
        try:
            le.redo()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Tool: run_graph
    # ------------------------------------------------------------------

    def run_graph(self) -> dict:
        """Trigger graph simulation (like pressing Play)."""
        try:
            mw = self.mw
            if hasattr(mw, 'scene_editor') and hasattr(mw.scene_editor, 'toggle_simulation'):
                mw.scene_editor.toggle_simulation()
                return {"ok": True, "message": "Simulation started"}
            elif hasattr(mw, 'toggle_simulation'):
                mw.toggle_simulation()
                return {"ok": True, "message": "Simulation started"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "No simulation controller found"}

    # ------------------------------------------------------------------
    # Tool: select_nodes
    # ------------------------------------------------------------------

    def select_nodes(self, nodes: list) -> dict:
        """Select nodes by ref/id list. Pass [] to deselect all."""
        le = self._le()
        # Deselect all first
        for n in (getattr(le, 'nodes', []) or []):
            try:
                n.setSelected(False)
            except Exception:
                pass
        selected_ids = []
        for ref in nodes:
            n = self._resolve(ref)
            if n:
                try:
                    n.setSelected(True)
                    selected_ids.append(n.id)
                except Exception:
                    pass
        return {"ok": True, "selected": selected_ids}

    # ------------------------------------------------------------------
    # Tool: get_connections
    # ------------------------------------------------------------------

    def get_connections(self, node=None) -> dict:
        """Return connections, optionally filtered to a specific node."""
        le = self._le()
        all_c = getattr(le, 'connections', []) or []
        if node is not None:
            n = self._resolve(node)
            if n is None:
                return {"ok": False, "error": f"Node not found: {node!r}"}
            conns = [_conn_to_dict(c) for c in all_c
                     if getattr(c.from_node, 'id', None) == n.id
                     or getattr(c.to_node, 'id', None) == n.id]
        else:
            conns = [_conn_to_dict(c) for c in all_c]
        return {"ok": True, "connections": conns, "count": len(conns)}

    # ------------------------------------------------------------------
    # Tool: find_nodes
    # ------------------------------------------------------------------

    def find_nodes(self, query: str = "", template: str = "") -> dict:
        """Search the canvas for nodes whose template name or label matches a query.

        query    – substring match against template name OR display label (case-insensitive)
        template – exact template name match (case-insensitive)

        Pass query="" and template="" to return ALL nodes.
        """
        le    = self._le()
        nodes = getattr(le, 'nodes', []) or []
        q     = query.lower().strip()
        t     = template.lower().strip()

        results = []
        for n in nodes:
            tname = (getattr(n, 'template_name', '') or '').lower()
            try:
                lbl = (n.title.toPlainText() if hasattr(n.title, 'toPlainText') else str(n.title)).lower()
            except Exception:
                lbl = ''

            if t:
                if tname != t:
                    continue
            elif q:
                if q not in tname and q not in lbl:
                    continue
            # (no filter → include all)

            results.append(_node_to_dict(n))

        return {"ok": True, "count": len(results), "nodes": results}

    # ------------------------------------------------------------------
    # Tool: batch_connect
    # ------------------------------------------------------------------

    def batch_connect(self, connections: list) -> dict:
        """Connect multiple node pairs in one call.

        connections: list of {from_node, to_node, from_pin?, to_pin?}

        Returns per-pair results so the AI can see exactly which ones failed.
        """
        if not isinstance(connections, list):
            return {"ok": False, "error": "connections must be a list"}

        results    = []
        ok_count   = 0
        fail_count = 0
        for pair in connections:
            if not isinstance(pair, dict):
                fail_count += 1
                results.append({"ok": False, "error": "item is not a dict"})
                continue
            r = self.connect(
                from_node=pair.get('from_node'),
                to_node=pair.get('to_node'),
                from_pin=pair.get('from_pin'),
                to_pin=pair.get('to_pin'),
            )
            results.append(r)
            if r.get('ok'):
                ok_count += 1
            else:
                fail_count += 1

        return {
            "ok":      fail_count == 0,
            "success": ok_count,
            "failed":  fail_count,
            "results": results,
        }

    # ------------------------------------------------------------------
    # Dispatcher
    # ------------------------------------------------------------------

    TOOL_MAP = {
        "get_graph":        "get_graph",
        "get_node":         "get_node",
        "list_templates":   "list_templates",
        "search_templates": "search_templates",
        "add_node":         "add_node",
        "delete_node":      "delete_node",
        "connect":          "connect",
        "disconnect":       "disconnect",
        "set_value":        "set_value",
        "move_node":        "move_node",
        "rename_node":      "rename_node",
        "arrange_nodes":    "arrange_nodes",
        "clear_graph":      "clear_graph",
        "create_template":  "create_template",
        "add_variable":     "add_variable",
        "set_variable":     "set_variable",
        "delete_variable":  "delete_variable",
        "get_variables":    "get_variables",
        "run_graph":        "run_graph",
        "undo":             "undo",
        "redo":             "redo",
        "duplicate_node":   "duplicate_node",
        "select_nodes":     "select_nodes",
        "get_connections":  "get_connections",
        "find_nodes":       "find_nodes",
        "batch_connect":    "batch_connect",
    }

    def execute(self, tool_name: str, params: dict) -> dict:
        """Dispatch a tool call by name with params dict."""
        method_name = self.TOOL_MAP.get(tool_name)
        if not method_name:
            return {"ok": False, "error": f"Unknown tool: {tool_name!r}. Available: {sorted(self.TOOL_MAP.keys())}"}
        method = getattr(self, method_name, None)
        if not callable(method):
            return {"ok": False, "error": f"Internal error: method {method_name!r} not found"}
        try:
            return method(**params) if params else method()
        except TypeError as e:
            return {"ok": False, "error": f"Tool param error for {tool_name}: {e}"}
        except Exception as e:
            return {"ok": False, "error": f"Tool {tool_name} raised: {e}"}
