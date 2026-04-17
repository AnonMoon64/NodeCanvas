"""
ai_agent.py

Atom — the NodeCanvas Agentic AI.

Implements a ReAct (Reason + Act) loop:

  1. User message arrives.
  2. System prompt is built: includes full graph context + template catalogue.
  3. Message is sent to the LLM with the history.
  4. AI returns JSON: {thought, plan?, tools:[{tool,params}], done, message}
  5. Each tool in `tools` is executed via AgentToolExecutor.
  6. Tool results are appended to conversation history as a synthetic
     "tool_results" user message and the loop repeats (step 3).
  7. When done=true OR max_iterations reached, the final `message` is
     surfaced to the user and the agentic session ends.

The agent emits Qt signals for UI updates so all painting happens on the
main thread, while HTTP calls run on a background thread.
"""

import json
import threading
import time
from typing import Any, Callable, Dict, List, Optional
import sys

from PyQt6.QtCore import QObject, pyqtSignal, QTimer

from py_editor.ui.panels.ai_agent_tools import AgentToolExecutor

# Ensure stdout/stderr are UTF-8 capable to avoid UnicodeEncodeError
try:
  if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
  pass


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------

TOOL_SCHEMA = """
AVAILABLE TOOLS — call them in the `tools` array of your reply:

add_node        {template:str, x?:float, y?:float, ref?:str, label?:str}
  → Creates a node. Returns id + full pin list. Use ref to name it for later steps.

delete_node     {node:int|str}
  → Deletes by id, ref, template name, or "all:TemplateName".

connect         {from_node:int|str, to_node:int|str, from_pin?:str, to_pin?:str}
  → Connects two nodes. Auto-tries flow pins first (out→in, exec→exec).
  → On failure the error lists available pins — use them to retry explicitly.

batch_connect   {connections:[{from_node, to_node, from_pin?, to_pin?}]}
  → Connect multiple pairs in one call. Returns per-pair ok/error.

disconnect      {from_node:int|str, to_node:int|str, from_pin?:str, to_pin?:str}
  → Removes a connection.

set_value       {node:int|str, pin:str, value:any}
  → Sets a pin's value (for unconnected inputs). Accepts "75%" notation.

get_graph       {}
  → Returns full graph: nodes + connections. Use to inspect current state.

get_node        {node:int|str}
  → Returns detailed info about one node including its connections.

find_nodes      {query?:str, template?:str}
  → Search canvas for nodes by substring (query) or exact template name.
  → Omit both args to list ALL nodes.

get_connections {node?:int|str}
  → Returns all connections, optionally for one node.

list_templates  {}
  → Returns every available node template grouped by category, with pin types.

search_templates {query:str}
  → Fuzzy-searches templates by name, category, or description.

create_template {name:str, category?:str, inputs?:{pin:type}, outputs?:{pin:type}, code?:str, description?:str}
  → Creates a new reusable node template. code is Python with a process() function.

move_node       {node:int|str, x:float, y:float}
  → Repositions a node on the canvas.

rename_node     {node:int|str, name:str}
  → Changes a node's display label.

duplicate_node  {node:int|str, offset_x?:float, offset_y?:float, ref?:str}
  → Duplicates a node with optional ref alias.

arrange_nodes   {style?:"flow"|"grid"|"tree"}
  → Re-layouts all nodes. FOR MANUAL USER REQUESTS ONLY — do NOT call this
    automatically. add_node already places nodes intelligently.

clear_graph     {confirm:bool}
  → Removes ALL nodes. Requires confirm:true.

add_variable    {name:str, type?:str, value?:any}
  → Adds a graph variable (float|int|bool|string|vector2|vector3|array|map|struct|enum).

get_variables   {}
  → Lists all graph variables.

select_nodes    {nodes:[int|str]}
  → Selects nodes by ref/id. [] deselects all.

run_graph       {}
  → Starts simulation (like pressing Play).

undo            {}  redo {}
  → Undo/redo last graph action.

read_ai_docs    {query?:str}
  → List all logic guidelines (null query) or read a specific guide (e.g. "health_system").
  → CONSULT THESE GUIDES IF YOU ARE UNSURE HOW TO IMPLEMENT A COMPLEX REQUEST.

validate_graph  {}
  → Sanity-check the graph for execution orphans and wiring issues.
  → CALL THIS BEFORE FINISHING any logic construction task.

run_and_get_logs {}
  → Execute the graph exactly once (dry-run) and return captured Print outputs (logs).
  → Use this to verify that your logic actually triggers and produces expected values.

POSITIONING — AUTOMATIC:
  - add_node places every node automatically using layout rules. You do NOT need
    to specify x/y and you must NOT call arrange_nodes after building a graph.
  - If you want to place a node at a specific spot, pass x and y explicitly.
  - Layout rules (handled by ai_node_placer.py):
      Exec / flow nodes → placed to the RIGHT of the last exec node (~220px gap).
      Pure / data nodes (math, const, getvar…) → placed LEFT-OF their consumer.
      Event nodes (OnStart, OnTick…) → leftmost column, stacked vertically.
      Branches → each extra output fans downward (+110px per slot).

REFERENCING NODES:
  - Use the numeric `id` returned by add_node (most reliable).
  - Or use the `ref` alias you gave when adding the node.
  - Or use the template name (resolves to the most recently created of that type).
  - Use find_nodes to search when you don't know the id.

PIN CONNECTION STRATEGY:
  - connect auto-detects pins (flow-priority). Works for most cases.
  - If connect fails it returns the available pin names — use them in the retry.
  - batch_connect is more efficient when wiring ≥3 pairs at once.
"""


EXAMPLES = """
EXAMPLES (study these patterns carefully):

--- Example 1: "Create a health system" ---
// Turn 1: initialize variables and create core nodes
{
  "thought": "I will build a robust health system. Rules: 1. Use variables for state. 2. Initialize Health=MaxHealth on Start. 3. Ensure no orphaned nodes. I'll create variables and nodes for initialization + print.",
  "tools": [
    {"tool":"add_variable","params":{"name":"Health","type":"float","value":100.0}},
    {"tool":"add_variable","params":{"name":"MaxHealth","type":"float","value":100.0}},
    {"tool":"add_node","params":{"template":"OnStart","ref":"trigger"}},
    {"tool":"add_node","params":{"template":"SetVariable","ref":"init_val"}},
    {"tool":"add_node","params":{"template":"GetVariable","ref":"get_max"}},
    {"tool":"add_node","params":{"template":"Print","ref":"log"}},
    {"tool":"add_node","params":{"template":"GetVariable","ref":"get_cur"}}
  ],
  "done": false,
  "message": "Initializing robust health system with auto-initialization logic..."
}
// Turn 2: configure and wire the complete initialization flow
{
  "thought": "Nodes spawned. Now I'll wire: OnStart -> SetVariable(Health = MaxHealth) -> Print(Health). This ensures the system is robust and uses all created nodes.",
  "tools": [
    {"tool":"set_value","params":{"node":"init_val","pin":"name","value":"Health"}},
    {"tool":"set_value","params":{"node":"get_max","pin":"name","value":"MaxHealth"}},
    {"tool":"set_value","params":{"node":"get_cur","pin":"name","value":"Health"}},
    {"tool":"batch_connect","params":{"connections":[
      {"from_node":"trigger","to_node":"init_val","from_pin":"exec_out","to_pin":"exec_in"},
      {"from_node":"get_max","to_node":"init_val","from_pin":"value","to_pin":"value"},
      {"from_node":"init_val","to_node":"log","from_pin":"exec_out","to_pin":"exec_in"},
      {"from_node":"get_cur","to_node":"log","from_pin":"value","to_pin":"value"}
    ]}}
  ],
  "done": true,
  "message": "Health system complete with Health=MaxHealth initialization on startup!"
}

--- Example 2: "What templates are available for timers?" ---
{
  "thought": "I'll search for timer templates.",
  "tools": [{"tool":"search_templates","params":{"query":"timer delay wait"}}],
  "done": false,
  "message": "Searching for timer templates…"
}
// After results, if found:
{
  "thought": "Found Timer and Delay nodes.",
  "tools": [],
  "done": true,
  "message": "Found: Timer (Logic), Delay (Flow). Timer has 'interval' and 'out' pins. Want me to add one?"
}

--- Example 3: "Delete all Print nodes" ---
{
  "thought": "Delete all Print nodes using the all: prefix.",
  "tools": [{"tool":"delete_node","params":{"node":"all:Print"}}],
  "done": true,
  "message": "Deleted all Print nodes."
}

--- Example 4: "Set the Chance node probability to 75%" ---
{
  "thought": "Find Chance node and set prob to 0.75.",
  "tools": [{"tool":"set_value","params":{"node":"Chance","pin":"prob","value":0.75}}],
  "done": true,
  "message": "Chance probability set to 75%."
}

--- Example 5: connect fails → read error → retry with explicit pins ---
// Turn 1:
{"thought":"Wire Timer to Counter.","tools":[{"tool":"connect","params":{"from_node":"Timer","to_node":"Counter"}}],"done":false,"message":"Connecting…"}
// Tool result: {"ok":false,"error":"Could not connect. Tried ['out']×['in']. Available outputs: ['tick','reset']. Available inputs: ['count','reset']."}
// Turn 2 — fix using info from the error:
{"thought":"connect told me outputs=['tick','reset'], inputs=['count','reset']. Use tick→count.","tools":[{"tool":"connect","params":{"from_node":"Timer","to_node":"Counter","from_pin":"tick","to_pin":"count"}}],"done":true,"message":"Timer.tick → Counter.count connected."}

--- Example 6: find existing nodes by query ---
{
  "thought": "User wants to delete all math nodes. I'll search first to see what's there.",
  "tools": [{"tool":"find_nodes","params":{"query":"math"}}],
  "done": false,
  "message": "Searching for math nodes…"
}
// After result with ids [3, 7, 12]:
{
  "thought": "Found 3 math nodes. Delete each by id.",
  "tools": [
    {"tool":"delete_node","params":{"node":3}},
    {"tool":"delete_node","params":{"node":7}},
    {"tool":"delete_node","params":{"node":12}}
  ],
  "done": true,
  "message": "Deleted 3 math nodes (ids 3, 7, 12)."
}
"""


def build_system_prompt(graph_snapshot: str, template_catalogue: str,
                        base_persona: str = "", iteration: int = 1) -> str:
    persona = base_persona.strip() if base_persona.strip() else \
        "You are Atom, an expert agentic AI for NodeCanvas (Pulse Engine)."

    # Include full examples only on the first iteration — saves ~2 KB of tokens per subsequent turn.
    examples_block = f"\n═══ EXAMPLES ═══\n{EXAMPLES}\n" if iteration <= 1 else ""

    return f"""{persona}

NodeCanvas is a visual node-based game engine. You have DIRECT access to the logic editor
via tools — you can add, delete, move, connect and configure nodes WITHOUT asking the user.
Execute first, explain after.

═══ RESPONSE FORMAT ═══
ALWAYS respond with a SINGLE valid JSON object. NO markdown. NO plain text. NO extra keys.

{{
  "thought":  "<COMPULSORY: detailed step-by-step reasoning. If the request is complex, call read_ai_docs first to find the correct architectural pattern. Explain which variables you will create and how the flow will connect.>",
  "tools":    [                        // list of tool calls to execute THIS turn (can be [])
    {{"tool": "TOOL_NAME", "params": {{...}} }}
  ],
  "done":     true | false,           // true = task complete; false = waiting for tool results
  "message":  "<friendly status update describing EXACTLY what you are doing in this step>"
}}

═══ CORE RULES ═══
1.  Batch ALL independent tool calls in ONE turn — don't spread add_node across turns.
2.  When done=false the system executes your tools and sends back results automatically.
3.  When done=true the session ends. Be specific: mention node ids, pin names, values set.
4.  If a tool fails (ok:false), read the error carefully — it often contains the fix.
5.  NEVER invent node ids — use the id returned by add_node or call find_nodes/get_graph.
6.  NEVER call arrange_nodes — add_node places nodes automatically using smart layout.
    Only call arrange_nodes if the user explicitly asks to "tidy" or "re-layout" the graph.
7.  When asked what you can do or what templates exist, call list_templates.
8.  Create missing templates with create_template — don't tell the user to do it manually.
9.  connect auto-detects pins (flow-first). On failure, use the pin list in the error to retry.
10. Use batch_connect when wiring 3+ connections at once — one tool call beats many.
11. Do NOT specify x/y in add_node unless you have a specific reason — let auto-placement work.
12. Use Variables for state (Health, Score, Speed, Inventories, Transforms) instead of Constants whenever the value needs to be modified at runtime. Supports primitives and complex types like array, map, and struct.
13. If you didn't finish the task in one turn, set done=false and continue in the next iteration.
14. **USE OR DELETE**: Connect all variables and nodes you create to a valid logic flow. Never leave orphaned variables like MaxHealth without reading them.
15. **COMPLEXITY BIAS**: Aim for robust, production-ready systems. A health system MUST initialize Health=MaxHealth on OnStart. 
16. **STRICT STATE SYNC**: For any system with a 'Current' and 'Max' value (Health, Stamina, etc.), you MUST wire a logic branch starting at `OnStart` that performs `SetVariable(Current) = GetVariable(Max)` to ensure correct initial state.
17. **VERIFY YOUR WORK**: Before concluding a task (done=true), you MUST call `validate_graph`. If it finds orphans or missing entry points, you MUST fix them. If you implemented a Print node, use `run_and_get_logs` to ensure the value is being logged correctly.
{examples_block}
{TOOL_SCHEMA}

═══ CURRENT GRAPH (refreshed every step) ═══
{graph_snapshot}

═══ TEMPLATE CATALOGUE (sample — call list_templates for full detail) ═══
{template_catalogue}
"""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

MAX_ITERATIONS = 8   # hard limit on tool-call rounds per user message
AGENT_TIMEOUT  = 90  # seconds per LLM call


class AtomAgent(QObject):
    """
    ReAct agentic loop.

    Signals
    -------
    status_update(str)   – progress text shown in chat while the loop runs
    turn_complete(str)   – final user-visible message (shown once done=true)
    error_occurred(str)  – error message (network, JSON parse, etc.)
    tool_executed(str, dict)  – (tool_name, result) for UI feedback
    """

    status_update  = pyqtSignal(str)
    turn_complete  = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    tool_executed  = pyqtSignal(str, dict)
    
    # Internal signal to bridge tool calls to the main thread
    _tool_call_sig = pyqtSignal(str, dict)

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.mw = main_window
        self.executor = AgentToolExecutor(main_window)
        # Conversation history maintained across one agentic session
        self._history: List[Dict[str, str]] = []

        # Setup main-thread bridging for tool execution
        self._tool_call_sig.connect(self._on_tool_call_requested)
        self._current_tool_res = None
        self._tool_wait_evt = threading.Event()

    def _on_tool_call_requested(self, tool_name, params):
        """Internal slot executed on the main thread to perform UI actions."""
        try:
            self._current_tool_res = self.executor.execute(tool_name, params)
        except Exception as e:
            self._current_tool_res = {"ok": False, "error": str(e)}
        finally:
            self._tool_wait_evt.set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, user_message: str, ai_client, base_persona: str = ""):
        """
        Launch the agentic loop in a background thread.

        Parameters
        ----------
        user_message  The raw text from the chat input.
        ai_client     An AIClient instance (already configured with provider/key/model).
        base_persona  The user-edited system prompt from settings (optional).
        """
        t = threading.Thread(
            target=self._loop,
            args=(user_message, ai_client, base_persona),
            daemon=True,
        )
        t.start()

    def reset_session(self):
        """Clear conversation history (start fresh)."""
        self._history.clear()
        self.executor._ref_map.clear()

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    def _loop(self, user_message: str, ai_client, base_persona: str):
        try:
            self._run_loop(user_message, ai_client, base_persona)
        except Exception as e:
            import traceback
            print(f"[Atom] EXCEPTION in agent loop:", flush=True)
            traceback.print_exc()
            self._log(f"Agent error: {e}", self.error_occurred)

    # ------------------------------------------------------------------ #
    # Logging helper — prints to stdout immediately (visible even when  #
    # the Qt UI is frozen) and also emits the Qt signal for the chat UI #
    # ------------------------------------------------------------------ #
    def _log(self, msg: str, signal=None):
      text = f"[Atom] {msg}"
      try:
        print(text, flush=True)
      except Exception:
        try:
          enc = getattr(sys.stdout, 'encoding', None) or 'utf-8'
          safe = text.encode(enc, errors='backslashreplace').decode(enc)
          print(safe, flush=True)
        except Exception:
          try:
            sys.stdout.buffer.write(text.encode('utf-8', errors='backslashreplace') + b"\n")
            sys.stdout.buffer.flush()
          except Exception:
            pass
      if signal is not None:
        try:
          signal.emit(msg)
        except Exception:
          pass

    def _run_loop(self, user_message: str, ai_client, base_persona: str):
        print(f"\n{'='*60}", flush=True)
        print(f"[Atom] User: {user_message}", flush=True)
        print(f"{'='*60}", flush=True)

        # 1. Append user message to history
        self._history.append({"role": "user", "content": user_message})

        iteration = 0
        stalled_count = 0  # consecutive turns with no tool execution

        while iteration < MAX_ITERATIONS:
            iteration += 1

            # 2. Rebuild context EVERY iteration so the AI always sees the latest graph.
            graph_snap   = self._snapshot_graph()
            template_cat = self._template_catalogue()
            sys_prompt   = build_system_prompt(graph_snap, template_cat, base_persona,
                                               iteration=iteration)

            self._log(f"Atom is formulating architectural plan (Iteration {iteration})...",
                      self.status_update)

            # 3. Trim history to avoid context overflow (keep system + last N exchanges)
            self._trim_history(max_messages=12)

            # 4. LLM call
            try:
                raw = ai_client.send_message(
                    text=self._build_user_payload(),
                    system_prompt=sys_prompt,
                    timeout=AGENT_TIMEOUT,
                )
            except Exception as e:
                self._log(f"LLM call failed: {e}", self.error_occurred)
                return

            # 5. Parse response — be lenient
            parsed = self._parse_response(raw)
            if parsed is None:
                print(f"[Atom] WARNING: non-JSON response, wrapping as message. Raw: {str(raw)[:300]}",
                      flush=True)
                parsed = {"thought": "", "tools": [], "done": True, "message": str(raw)[:500]}

            # Print thought + planned tools to console immediately
            thought = parsed.get("thought", "")
            if thought:
                print(f"[Atom] Thought: {thought[:400]}", flush=True)

            # Store assistant response in history (compact form)
            self._history.append({
                "role":    "assistant",
                "content": json.dumps(parsed, ensure_ascii=False)
            })

            tools   = parsed.get("tools") or parsed.get("actions") or []
            done    = bool(parsed.get("done", not bool(tools)))  # no tools → assume done
            message = (parsed.get("message") or parsed.get("clarify") or
                       parsed.get("thought") or "Done.")

            # Update status with AI's own message if it's descriptive
            if message and not done:
                self._log(message, self.status_update)

            if tools:
                tool_names = [t.get('tool', '?') for t in tools if isinstance(t, dict)]
                print(f"[Atom] Tools planned ({len(tool_names)}): {tool_names}", flush=True)

            # 6. Execute tools
            tool_results  = []
            failed_tools  = []

            for tc in (tools if isinstance(tools, list) else []):
                if not isinstance(tc, dict):
                    continue
                tool_name = (tc.get("tool") or tc.get("name") or tc.get("action") or "").strip()
                params    = tc.get("params") or tc.get("args") or tc.get("arguments") or {}
                if not tool_name:
                    continue

                print(f"[Atom]   → {tool_name}({json.dumps(params, separators=(',',':'))[:120]})",
                      flush=True)
                self._log(f"Atom is executing {tool_name}...", self.status_update)
                
                # BRIDGE: Execute tool on Main Thread (PyQt6 requirement)
                # We emit a signal which is connected to a slot on this same 
                # object. Since AtomAgent lives on the main thread, the signal 
                # across threads will be queued and executed on the main thread.
                self._current_tool_res = {"ok": False, "error": "timeout"}
                self._tool_wait_evt.clear()
                self._tool_call_sig.emit(tool_name, params if isinstance(params, dict) else {})

                if not self._tool_wait_evt.wait(timeout=15.0):
                    result = {"ok": False, "error": f"Tool {tool_name} timed out"}
                else:
                    result = self._current_tool_res

                ok_flag = result.get("ok", True)
                if ok_flag:
                    # Print a compact success summary
                    brief = {k: v for k, v in result.items()
                             if k not in ('ok',) and not isinstance(v, (list, dict))}
                    print(f"[Atom]      OK  {json.dumps(brief, separators=(',',':'))[:120]}",
                          flush=True)
                else:
                    print(f"[Atom]      FAIL  {result.get('error','?')[:200]}", flush=True)

                tool_results.append({
                    "tool":   tool_name,
                    "params": params,
                    "result": result,
                })
                self.tool_executed.emit(tool_name, result)

                if not ok_flag:
                    failed_tools.append({"tool": tool_name, "error": result.get("error", "unknown")})

            any_failed = bool(failed_tools)

            # 7. Determine loop continuation
            if done and not any_failed:
                # Clean finish
                print(f"[Atom] DONE. Message: {message[:300]}", flush=True)
                self._log(message, self.turn_complete)
                return

            if done and any_failed:
                # Finished but with errors — give AI one more chance to fix up
                print(f"[Atom] done=true but {len(failed_tools)} tool(s) failed — retrying…",
                      flush=True)
                done = False

            if not tool_results:
                stalled_count += 1
                if stalled_count >= 2:
                    # AI is generating replies but not calling tools — bail out
                    print(f"[Atom] STALL — no tools called for {stalled_count} turns. Bailing.",
                          flush=True)
                    self._log(
                        message or "I'm not sure how to proceed. Please clarify what you'd like.",
                        self.turn_complete,
                    )
                    return
            else:
                stalled_count = 0

            # 8. Feed tool results back for next iteration
            # Include only essential info (avoid graph dumps every turn which waste tokens)
            compact_results = []
            for tr in tool_results:
                r = tr["result"]
                # For get_graph / list_templates — they return large objects; include only summary
                if tr["tool"] in ("get_graph", "list_templates"):
                    if tr["tool"] == "get_graph":
                        compact_results.append({
                            "tool": tr["tool"],
                            "result": {
                                "ok":               r.get("ok"),
                                "node_count":       r.get("node_count"),
                                "connection_count": r.get("connection_count"),
                                "nodes": [{"id": n["id"], "template": n["template"], "pos": n["pos"]}
                                          for n in r.get("nodes", [])],
                                "connections": r.get("connections", []),
                            }
                        })
                    else:
                        # list_templates — just return category names + counts
                        cats = r.get("categories", {})
                        compact_results.append({
                            "tool": tr["tool"],
                            "result": {
                                "ok": r.get("ok"),
                                "categories": {c: len(items) for c, items in cats.items()}
                            }
                        })
                else:
                    compact_results.append({"tool": tr["tool"], "result": r})

            feedback = json.dumps({
                "tool_results":  compact_results,
                "failed_tools":  failed_tools,   # [{tool, error}] — empty if all ok
                "all_ok":        not any_failed,
                "note":          ("FAILURES detected — each failed tool has an 'error' key. "
                                  "Read the error, then fix and retry in the next turn."
                                  if any_failed else
                                  "All tools executed successfully. Continue if more steps needed."),
            }, ensure_ascii=False)
            self._history.append({"role": "user", "content": feedback})

        # Max iterations hit
        final_msg = ("I've completed the maximum number of steps. "
                     "The graph has been modified — let me know if you need further changes.")
        print(f"[Atom] MAX ITERATIONS ({MAX_ITERATIONS}) reached.", flush=True)
        self._log(final_msg, self.turn_complete)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _trim_history(self, max_messages: int = 12):
        """Keep only the last max_messages to avoid context overflow.
        Always preserves the original user message (index 0) so Atom
        never forgets what the task is.
        """
        if len(self._history) <= max_messages:
            return
        # Keep first (task) message + last (max_messages - 1) messages
        first = self._history[0]
        tail  = self._history[-(max_messages - 1):]
        self._history = [first] + tail

    def _build_user_payload(self) -> str:
        """Flatten history into a single user content string for providers
        that don't support multi-turn (fallback). For OpenAI/Mistral the
        history is sent as `messages` directly by the client.
        """
        # We rely on ai_client using the `messages` kwarg format.
        # Pass the whole history as the 'text' arg; the AIClient will
        # detect the list form.  Encode as JSON so the server can parse.
        return json.dumps(self._history, ensure_ascii=False)

    def _parse_response(self, raw: str) -> Optional[dict]:
        """Extract a JSON dict from the raw LLM response.

        Handles:
          • Pure JSON response (ideal).
          • JSON wrapped in markdown fences (```json ... ``` or ``` ... ```).
          • JSON object embedded somewhere in plain text (extracts the first
            top-level { … } block found, so preamble/postamble are tolerated).
        """
        if not raw or not isinstance(raw, str):
            return None

        # Try sanitize_assistant_text first (strips known artifacts)
        try:
            from py_editor.ui.panels.ai_chat_panel import sanitize_assistant_text
            cleaned = sanitize_assistant_text(raw).strip()
        except Exception:
            cleaned = raw.strip()

        # --- Pass 1: direct parse ---
        try:
            obj = json.loads(cleaned)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

        # --- Pass 2: strip markdown code fences ---
        for fence in ('```json', '```JSON', '```'):
            if cleaned.startswith(fence):
                end = cleaned.rfind('```', len(fence))
                if end > len(fence):
                    candidate = cleaned[len(fence):end].strip()
                    try:
                        obj = json.loads(candidate)
                        if isinstance(obj, dict):
                            return obj
                    except Exception:
                        pass
                break

        # --- Pass 3: find first { … } object in the text ---
        depth = 0
        start = -1
        for i, ch in enumerate(cleaned):
            if ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start >= 0:
                    candidate = cleaned[start:i + 1]
                    try:
                        obj = json.loads(candidate)
                        if isinstance(obj, dict):
                            return obj
                    except Exception:
                        pass
                    start = -1

        return None

    def _snapshot_graph(self) -> str:
        """Return a compact JSON summary of the current graph."""
        try:
            result = self.executor.get_graph()
            # Limit to essential fields for prompt size
            nodes = result.get("nodes", [])
            compact = {
                "node_count": result.get("node_count", 0),
                "connection_count": result.get("connection_count", 0),
                "nodes": [
                    {
                        "id": n["id"],
                        "template": n["template"],
                        "pos": n["pos"],
                        "inputs": n.get("inputs", {}),
                        "outputs": n.get("outputs", {}),
                        "values": n.get("values", {}),
                    }
                    for n in nodes
                ],
                "connections": result.get("connections", []),
            }
            return json.dumps(compact, separators=(",", ":"), ensure_ascii=False)
        except Exception as e:
            return f'{{"error": "Could not snapshot graph: {e}"}}'

    def _template_catalogue(self, max_per_category: int = 5) -> str:
        """Return a compact listing of template categories + sample names."""
        try:
            result = self.executor.list_templates()
            cats = result.get("categories", {})
            lines = []
            for cat, items in sorted(cats.items()):
                names = [t["name"] for t in items[:max_per_category]]
                more = len(items) - max_per_category
                suffix = f" (+{more} more)" if more > 0 else ""
                lines.append(f"  {cat}: {', '.join(names)}{suffix}")
            return "\n".join(lines) or "(no templates found)"
        except Exception:
            return "(could not load templates)"


# ---------------------------------------------------------------------------
# Multi-turn AI client wrapper
# ---------------------------------------------------------------------------

def patch_client_for_history(client, history: List[Dict[str, str]], system_prompt: str):
    """
    Monkey-patch one request so the client sends the full conversation history
    instead of just the last message.

    The AIClient.send_message always formats a fresh messages list internally.
    We intercept by wrapping send_message to inject our history.
    """
    original_send = client.send_message

    def _patched_send(text: str, mode: str = "Assistant",
                      timeout: int = AGENT_TIMEOUT, system_prompt: str = system_prompt):
        import json as _json
        import urllib.request
        import urllib.error

        # Deserialise history from JSON (it was stringified in _build_user_payload)
        try:
            history_list = _json.loads(text)
            if not isinstance(history_list, list):
                raise ValueError
        except Exception:
            # Fallback: treat text as a plain user message
            history_list = [{"role": "user", "content": text}]

        provider = (client.provider or "").lower()
        api_key  = client.api_key
        model    = client.model

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        from PyQt6.QtCore import QSettings
        if provider == "openai":
            from PyQt6.QtCore import QSettings as _QS
            model = model or _QS("NodeCanvas", "AI").value("openai_model", "gpt-3.5-turbo")
            url   = "https://api.openai.com/v1/chat/completions"
            messages = [{"role": "system", "content": system_prompt}] + history_list
            payload  = {"model": model, "messages": messages}
        elif provider == "mistral":
            from PyQt6.QtCore import QSettings as _QS
            model   = model or _QS("NodeCanvas", "AI").value("mistral_model", "devstral-2512") or "devstral-2512"
            url     = "https://api.mistral.ai/v1/chat/completions"
            messages = [{"role": "system", "content": system_prompt}] + history_list
            payload  = {"model": model, "messages": messages}
        else:
            # Fallback: original behaviour
            return original_send(text, mode=mode, timeout=timeout,
                                  system_prompt=system_prompt)

        data = _json.dumps(payload).encode("utf-8")
        req  = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
                obj  = _json.loads(body.decode("utf-8"))
                choices = obj.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", _json.dumps(obj))
                return _json.dumps(obj)
        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode("utf-8", errors="replace")
            except Exception:
                err_body = "<unreadable>"
            raise RuntimeError(f"HTTP {e.code}: {e.reason} — {err_body}")

    client.send_message = _patched_send
    return client
