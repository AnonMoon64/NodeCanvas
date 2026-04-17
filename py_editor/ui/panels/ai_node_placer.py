"""
ai_node_placer.py
=================
Intelligent node placement for the Atom AI agent.

ALL layout constants and classification rules live here.
To tune placement behaviour — spacing, which templates count as data/event/flow,
collision margins, branch fan angle — edit ONLY this file.

Layout model
------------
Flow direction   : left → right along the main execution chain.
Pure / data nodes: placed LEFT-OF and above/below the node they feed into,
                   creating the characteristic "vein" look.
Exec / flow nodes: placed to the RIGHT of the previous exec node.
Event nodes      : placed at the leftmost available position, stacked vertically.
Branches         : each extra output fans downward with V_BRANCH spacing.
Collision guard  : only the new node moves; existing nodes are NEVER rearranged.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Layout constants — tune here
# ---------------------------------------------------------------------------

NODE_W       = 180    # assumed node width         (px)
NODE_H       = 90     # assumed node height        (px)
H_EXEC       = 220    # left-edge-to-left-edge gap for exec-chain nodes   (px)
H_DATA_BACK  = 60     # how far LEFT of the consumer's left edge a data node sits
V_DATA_STEP  = 140    # vertical slot step for stacked data nodes         (px)
V_BRANCH     = 110    # vertical fan per extra branch output              (px)
COLLISION_PAD = 16    # extra margin used in overlap detection            (px)

# Vertical nudge sequence when the chosen position is occupied.
# Tried in order; first collision-free candidate wins.
_NUDGES = (
    V_DATA_STEP,   -V_DATA_STEP,
    V_DATA_STEP*2, -V_DATA_STEP*2,
    V_DATA_STEP*3, -V_DATA_STEP*3,
)


# ---------------------------------------------------------------------------
# Template classification
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Word-level sets  (matched against CamelCase-split words, not raw substrings)
# ---------------------------------------------------------------------------

# Words that mark a node as "pure data" (produces values, no exec flow).
# These nodes are placed to the LEFT of the node they feed.
#
# IMPORTANT: use WHOLE words only (matched against CamelCase-split words),
# so 'int' does NOT match 'Print', 'abs' does NOT match 'Abstract', etc.
_DATA_WORDS: frozenset = frozenset({
    # Types / literals — standalone type names
    'const', 'constant', 'float', 'integer', 'bool', 'boolean',
    'string', 'vec', 'vec2', 'vec3', 'vec4', 'vector', 'vector2',
    'vector3', 'vector4', 'literal',
    # Variable READS only  (set/write are exec — they run in the flow chain)
    'get', 'getvar', 'getvariable', 'getlocal', 'read', 'load', 'fetch',
    # Math — full words
    'add', 'subtract', 'sub', 'multiply', 'mul', 'divide', 'div',
    'modulo', 'mod', 'power', 'pow', 'abs', 'negate', 'neg',
    'sin', 'cos', 'tan', 'atan', 'asin', 'acos', 'sqrt', 'exp', 'ln',
    'logarithm',   # 'log' alone = console print in game engines → exec
    'clamp', 'lerp', 'min', 'max', 'ceil', 'floor', 'round', 'sign',
    'frac', 'fraction', 'random', 'noise',
    # Vector / spatial
    'length', 'normalize', 'dot', 'cross', 'distance', 'magnitude',
    'reflect', 'project',
    # Colour
    'rgb', 'rgba', 'hsv', 'hsl', 'color', 'colour',
    # Time / frame reads
    'delta', 'deltatime', 'frametime',
})

# Write-first prefixes: nodes whose FIRST word is one of these are EXEC
# even if later words appear in _DATA_WORDS.  (Set, Write, Assign, etc.)
_WRITE_FIRST_WORDS: frozenset = frozenset({
    'set', 'write', 'assign', 'store', 'push', 'put', 'emit', 'send',
    'fire', 'dispatch', 'post', 'apply', 'update', 'save',
})

# Template categories (from template data) that are always pure data.
# NOTE: 'variables' is intentionally excluded — SetVariable has that category
# but is exec (side-effecting).  Rely on word-level matching for variables.
_DATA_CATEGORIES: frozenset = frozenset({
    'math', 'constants', 'math & logic',
})

# Words that mark a graph-entry "event" node (no exec input).
_EVENT_WORDS: frozenset = frozenset({
    'onstart', 'ontick', 'onplay', 'onstop', 'onkey', 'oncollision',
    'onevent', 'onbegin', 'oninit', 'onawake', 'onenabled', 'onenable',
    'onupdate', 'onlateupdate',
    # Also the plain word 'event' / 'trigger' when it IS the whole name
    'event', 'trigger',
})

# Words for branching / flow-control nodes (fan downward on multiple outputs).
_BRANCH_WORDS: frozenset = frozenset({
    'branch', 'sequence', 'forloop', 'foreach', 'whileloop', 'dowhile',
    'switch', 'select', 'gate', 'flipflop',
})


def _name_words(template_name: str) -> List[str]:
    """Split a CamelCase or snake_case name into lowercase words.

    Examples
    --------
    'ConstFloat'  → ['const', 'float']
    'GetVariable' → ['get', 'variable']
    'ForLoop'     → ['for', 'loop']
    'Print'       → ['print']
    'OnStart'     → ['on', 'start']
    'exec_out'    → ['exec', 'out']
    """
    # Insert _ between a lowercase letter (or digit) and an uppercase letter
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', template_name)
    # Insert _ between a run of uppercase letters and an uppercase+lowercase pair
    s = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', s)
    # Split on non-alphanumeric separators
    return [w.lower() for w in re.split(r'[^a-zA-Z0-9]+', s) if w]


def classify_from_pins(template_name: str,
                       inputs:  Optional[dict] = None,
                       outputs: Optional[dict] = None,
                       category: str = '') -> str:
    """Like classify() but also inspects actual pin type dicts.

    A node with NO 'exec' pins whatsoever (neither in its inputs nor its
    outputs) is definitively a pure data/function node — even if its name
    or category doesn't say so.  This fixes nodes like 'Chance' whose name
    gives no clue but which only have data pins (prob→result).

    Falls back to classify() when pin info is absent.
    """
    # Helper: does a pin dict contain any exec-typed pin?
    def _has_exec(pins: Optional[dict]) -> bool:
        if not pins:
            return False
        for val in pins.values():
            if isinstance(val, str) and val == 'exec':
                return True
            if isinstance(val, dict) and val.get('type') == 'exec':
                return True
        return False

    if inputs is not None or outputs is not None:
        has_exec_out = _has_exec(outputs)
        has_exec_in  = _has_exec(inputs)
        if not has_exec_out and not has_exec_in:
            # No exec pins at all → pure data/function node
            return 'data'
        if not has_exec_in and has_exec_out:
            # Only exec output → entry/event node
            return 'event'

    # Fall back to name/category heuristics
    return classify(template_name, category)


def classify(template_name: str, category: str = '') -> str:
    """Return the layout class: 'event' | 'data' | 'branch' | 'exec'.

    Priority: event > data-category > data-word > branch > exec
    Matching is done at the WORD level (CamelCase split) to avoid false
    positives like 'int' matching 'Print'.
    """
    words = _name_words(template_name)
    full  = template_name.lower()
    cat   = category.lower()

    # --- Event: full-name OR significant word match ---
    if full in _EVENT_WORDS or any(w in _EVENT_WORDS for w in words if len(w) > 3):
        return 'event'

    # --- Write-first: SetVar, SetValue, WriteFile … are always exec ---
    if words and words[0] in _WRITE_FIRST_WORDS:
        return 'exec'

    # --- Data: category takes priority over keywords ---
    if any(dc in cat for dc in _DATA_CATEGORIES):
        return 'data'

    # --- Data: word-level keyword match ---
    if any(w in _DATA_WORDS for w in words):
        return 'data'

    # --- Branch / flow-control ---
    if full in _BRANCH_WORDS or any(w in _BRANCH_WORDS for w in words):
        return 'branch'

    return 'exec'


# ---------------------------------------------------------------------------
# Occupancy / collision helpers
# ---------------------------------------------------------------------------

def _rects(nodes: list) -> List[Tuple[float, float, float, float]]:
    """Return (x, y, NODE_W, NODE_H) bounding boxes for all existing nodes."""
    result = []
    for n in nodes:
        try:
            p = n.pos()
            result.append((p.x(), p.y(), NODE_W, NODE_H))
        except Exception:
            pass
    return result


def _collides(x: float, y: float, rects: list) -> bool:
    """True if a node placed at (x, y) overlaps any existing bounding box."""
    pad = COLLISION_PAD
    for rx, ry, rw, rh in rects:
        if (x < rx + rw + pad and x + NODE_W + pad > rx and
                y < ry + rh + pad and y + NODE_H + pad > ry):
            return True
    return False


def _free(x: float, y: float, rects: list) -> Tuple[float, float]:
    """Return the nearest collision-free position, nudging vertically first."""
    if not _collides(x, y, rects):
        return x, y
    for dy in _NUDGES:
        if not _collides(x, y + dy, rects):
            return x, y + dy
    # Last resort: nudge right until free
    for extra in range(1, 7):
        nx = x + extra * (NODE_W + H_EXEC)
        if not _collides(nx, y, rects):
            return nx, y
    return x, y   # accept the overlap rather than infinite loop


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def suggest_position(
    le,
    template_name: str,
    category: str = '',
    hint_x: Optional[float] = None,
    hint_y: Optional[float] = None,
    connect_from_id: Optional[int] = None,
    inputs:  Optional[dict] = None,
    outputs: Optional[dict] = None,
) -> Tuple[float, float]:
    """Return the best (x, y) canvas position for a new node.

    Parameters
    ----------
    le               Logic editor with ``.nodes`` and ``.connections`` attrs.
    template_name    Template name of the node being placed.
    category         Template category string (aids classification).
    hint_x / hint_y  Explicit position from the caller.  If both are provided
                     and at least one is non-zero they are used as the starting
                     candidate (collision-checked only; full algorithm skipped).
    connect_from_id  ID of the node this new node connects FROM.  When given,
                     the new node is anchored relative to that source node.
    inputs / outputs Template pin dicts.  When provided, classify_from_pins()
                     is used instead of classify() so that pure-function nodes
                     (e.g. Chance, whose name gives no clue) are reliably placed
                     to the left of their consumer rather than in the exec chain.
    """
    nodes: list = list(getattr(le, 'nodes', []) or [])
    conns: list = list(getattr(le, 'connections', []) or [])
    rects = _rects(nodes)
    kind  = classify_from_pins(template_name, inputs, outputs, category)

    # -- Explicit hint: respect it, only check collision -------------------
    if hint_x is not None and hint_y is not None and (hint_x != 0.0 or hint_y != 0.0):
        return _free(float(hint_x), float(hint_y), rects)

    # -- Empty canvas: start at origin ------------------------------------
    if not nodes:
        return 0.0, 0.0

    # -- Locate context node (the node this one connects FROM) ------------
    ctx = None
    if connect_from_id is not None:
        for n in nodes:
            if getattr(n, 'id', None) == connect_from_id:
                ctx = n
                break
    if ctx is None:
        # Default: rightmost node in the graph (end of current exec chain)
        ctx = max(nodes, key=lambda n: n.pos().x())

    cx, cy = ctx.pos().x(), ctx.pos().y()

    # =====================================================================
    # Event nodes — place at the far left, stacked UPWARDS
    # =====================================================================
    if kind == 'event':
        lx = min(n.pos().x() for n in nodes)
        # Find y positions of existing nodes at that column
        col_ys = [n.pos().y() for n in nodes if n.pos().x() <= lx + NODE_W * 0.75]
        # Stack upwards to avoid crossing data nodes which stack downwards
        ty = (min(col_ys) - NODE_H - V_DATA_STEP) if col_ys else -V_DATA_STEP
        return _free(lx, ty, rects)

    # =====================================================================
    # Pure / data nodes — place to the LEFT and above/below the consumer
    # =====================================================================
    if kind == 'data':
        tx = cx - H_DATA_BACK - NODE_W
        # Count data nodes already parked near that column / row
        data_near = [
            n for n in nodes
            if abs(n.pos().x() - tx) < NODE_W * 0.8
            and abs(n.pos().y() - cy) < NODE_H * 5
        ]
        slot = len(data_near)
        # Start by placing data nodes BELOW (sign=1) the exec line
        sign = 1 if slot % 2 == 0 else -1
        bias = 40 if sign > 0 else -40  # Ensure nodes are never "even" with the consumer
        ty   = cy + sign * (V_DATA_STEP * (slot // 2 + 1)) + bias
        return _free(tx, ty, rects)

    # =====================================================================
    # Exec / flow / branch nodes — place to the RIGHT of context
    # =====================================================================
    # Count existing outgoing connections from context to set branch index
    out_conns = [
        c for c in conns
        if getattr(c.from_node, 'id', None) == getattr(ctx, 'id', None)
    ]
    branch_i = len(out_conns)

    tx = cx + NODE_W + H_EXEC
    ty = cy + branch_i * V_BRANCH   # fan downward for each extra branch

    return _free(tx, ty, rects)
