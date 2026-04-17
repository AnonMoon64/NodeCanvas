"""
ai_chat_panel.py

AI assistant panel: chat UI, mode selector and settings.
Provider dropdown (OpenAI, Mistral) with API key and per-provider model fields.
"""
from pathlib import Path
import threading
import json
import urllib.request
import urllib.error

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTextBrowser, QPlainTextEdit, QDialog, QFormLayout, QLineEdit, QTextEdit,
    QDialogButtonBox, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QSettings, QTimer, QPointF
import re
from py_editor.ui.panels.ai_memory import short_term, memory_update, session_summary_manager

# Shared default system prompt used when no user-saved prompt exists.
DEFAULT_SYSTEM_PROMPT = (
    "You are Atom, the expert AI assistant for NodeCanvas (Pulse Engine). "
    "NodeCanvas is a node-based game engine supporting 2D, 3D, UI-only, and code-only modes. "
    "In Agentic mode you have DIRECT tool access to the logic editor — you can create, connect, "
    "move and configure nodes without asking. "
    "In Assistant mode respond with valid JSON only using this schema: "
    "{\"thought\":\"<reasoning>\","
    "\"action\":\"edit_file|ask_user|none\","
    "\"message\":\"<reply to user>\","
    "\"files_to_edit\":[],"
    "\"remember\":<optional>} "
    "Be concise, accurate, and prefer doing over explaining. "
    "When asked who you are: {\"message\":\"I am Atom, the NodeCanvas AI agent — I can build node graphs for you directly.\"}. "
    "You know NodeCanvas deeply: nodes have typed pins (float, int, bool, string, any), "
    "connections flow data between output pins and input pins, "
    "and graphs run when simulation starts."
)


class ChatInputField(QPlainTextEdit):
    enter_pressed = pyqtSignal()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.enter_pressed.emit()
            return
        super().keyPressEvent(event)


class AISettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI Settings")
        self.setModal(True)
        layout = QFormLayout(self)

        # Provider dropdown replaces raw endpoint input for a simpler UX.
        self.provider = QComboBox()
        self.provider.addItems(["OpenAI", "Mistral"])

        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)

        settings = QSettings("NodeCanvas", "AI")
        # Backwards compatibility: if old "endpoint" exists try to infer provider
        endpoint_legacy = settings.value("endpoint", "") or ""
        prov = settings.value("provider", "") or ""
        if not prov and endpoint_legacy:
            le = endpoint_legacy.lower()
            if "openai" in le:
                prov = "OpenAI"
            elif "mistral" in le:
                prov = "Mistral"
            else:
                prov = "OpenAI"

        self.provider.setCurrentText(prov or "OpenAI")
        self.api_key.setText(settings.value("api_key", ""))

        layout.addRow("Provider:", self.provider)
        layout.addRow("API Key:", self.api_key)

        # Model selection dropdown that updates based on provider selection
        self.model_combo = QComboBox()

        # Predefined model options per provider
        self._model_options = {
            "OpenAI": ["gpt-3.5-turbo", "gpt-4", "gpt-4o", "gpt-4o-mini"],
            "Mistral": ["devstral-2512", "mistral-medium-latest", "mistral-medium-2508", "open-mistral-nemo", "mistral-tiny-latest", "codestral-latest"]
        }

        # Populate model choices based on the currently selected provider
        def initial_model_for_provider(p):
            if p == "OpenAI":
                return settings.value("openai_model", "gpt-3.5-turbo")
            return settings.value("mistral_model", "devstral-2512")

        self._populate_models = lambda p: None

        def _populate_models_impl(p):
            self.model_combo.clear()
            opts = self._model_options.get(p, [])
            for o in opts:
                self.model_combo.addItem(o)
            # Allow custom entry
            self.model_combo.addItem("<custom>")
            # Select saved model if present, otherwise default to first
            saved = initial_model_for_provider(p) or (opts[0] if opts else "")
            if saved and saved in opts:
                self.model_combo.setCurrentText(saved)
            else:
                # If saved is custom, insert it and select
                if saved and saved != "":
                    self.model_combo.insertItem(0, saved)
                    self.model_combo.setCurrentIndex(0)
                else:
                    if opts:
                        self.model_combo.setCurrentIndex(0)

        self._populate_models = _populate_models_impl

        # Initialize models for current provider
        self._populate_models(self.provider.currentText())
        # Update models when provider changes
        self.provider.currentTextChanged.connect(self._populate_models)

        layout.addRow("Model:", self.model_combo)

        # Assistant persona / system prompt. Editable so you can refine Atom's behavior.
        default_prompt = (
            "You are Atom, the concise AI assistant for NodeCanvas (Pulse Engine). "
            "NodeCanvas is a node-based game engine supporting 2D, 3D, UI-only, and code-only modes. "
            "You MUST respond with valid JSON only. Do not include any text before or after the JSON. "
            "Do not add explanations or commentary. Do not use markdown. Your entire response must be a single valid JSON object. "
            "Use this exact JSON schema for every reply (top-level object): "
            "{\"thought\":\"<short internal reasoning>\"," \
            "\"action\":\"edit_file|ask_user|none\"," \
            "\"message\":\"<text to show the user or clarification question>\"," \
            "\"files_to_edit\":[], " \
            "\"remember\":<optional string|object|array> } "
            "If you are unsure or need more data, set \"action\":\"ask_user\" and place the concise question in \"message\". "
            "If there is nothing to do, set \"action\":\"none\" and provide a short \"message\". "
            "When asked who you are, reply exactly with {\"who\":\"I am Atom, the NodeCanvas assistant.\"}. "
            "When asked who the user is, reply exactly with {\"who\":\"I do not know personal details unless you share them.\"}."
        )
        self.system_prompt = QTextEdit()
        self.system_prompt.setPlaceholderText("Assistant persona / system prompt")
        self.system_prompt.setPlainText(settings.value("system_prompt", DEFAULT_SYSTEM_PROMPT))
        layout.addRow("Assistant Persona:", self.system_prompt)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save(self):
        settings = QSettings("NodeCanvas", "AI")
        settings.setValue("provider", self.provider.currentText())
        settings.setValue("api_key", self.api_key.text())
        # Save the selected model for the active provider
        sel_provider = self.provider.currentText()
        sel_model = self.model_combo.currentText()
        if sel_provider == "OpenAI":
            settings.setValue("openai_model", sel_model)
        else:
            settings.setValue("mistral_model", sel_model)
        settings.setValue("system_prompt", self.system_prompt.toPlainText())


class AIClient:
    """HTTP client that supports provider selection (OpenAI, Mistral) or a legacy raw endpoint.

    Usage:
      AIClient("OpenAI", api_key)
      AIClient("Mistral", api_key)
      AIClient("https://custom.endpoint/ai", api_key)  # legacy
    """
    def __init__(self, provider_or_endpoint: str, api_key: str = "", model: str = None):
        self.provider = (provider_or_endpoint or "").strip()
        self.api_key = api_key or ""
        self.model = model

    def send_message(self, text: str, mode: str = "Assistant", timeout: int = 30, system_prompt: str = None) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        provider_lower = (self.provider or "").lower()

        def _extract_text_from_response(resp):
            body = resp.read()
            ct = resp.getheader("Content-Type", "") or ""
            if "application/json" in ct:
                obj = json.loads(body.decode("utf-8"))
                for key in ("output", "result", "text", "response"):
                    if key in obj:
                        return obj[key] if isinstance(obj[key], str) else json.dumps(obj[key])
                if "choices" in obj and isinstance(obj["choices"], list) and obj["choices"]:
                    ch = obj["choices"][0]
                    if isinstance(ch, dict):
                        if "message" in ch and isinstance(ch["message"], dict):
                            return ch["message"].get("content") or json.dumps(ch)
                        return ch.get("text") or json.dumps(ch)
                return json.dumps(obj)
            else:
                try:
                    return body.decode("utf-8")
                except Exception:
                    return str(body)

        if provider_lower == "openai":
            model = self.model or QSettings("NodeCanvas", "AI").value("openai_model", "gpt-3.5-turbo")
            url = "https://api.openai.com/v1/chat/completions"
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": text})
            payload = {"model": model, "messages": messages}
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return _extract_text_from_response(resp)
            except urllib.error.HTTPError as e:
                try:
                    body = e.read().decode("utf-8", errors="replace")
                except Exception:
                    body = "<unreadable>"
                raise RuntimeError(f"HTTP Error {getattr(e,'code',None)}: {getattr(e,'reason',None)} - {body} (url={url})")
            except urllib.error.URLError as e:
                raise RuntimeError(f"URL Error: {getattr(e,'reason',e)} (url={url})")

        elif provider_lower == "mistral":
            model = self.model or QSettings("NodeCanvas", "AI").value("mistral_model", "devstral-2512")
            if not model or model == "mistral-large":
                model = "devstral-2512"

            # Prefer the chat completions endpoint for Mistral (modern API)
            url_chat = "https://api.mistral.ai/v1/chat/completions"
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": text})
            payload_chat = {"model": model, "messages": messages}
            req_chat = urllib.request.Request(url_chat, data=json.dumps(payload_chat).encode("utf-8"), headers=headers)
            try:
                with urllib.request.urlopen(req_chat, timeout=timeout) as resp:
                    return _extract_text_from_response(resp)
            except urllib.error.HTTPError as e_chat:
                try:
                    body_chat = e_chat.read().decode("utf-8", errors="replace")
                except Exception:
                    body_chat = "<unreadable>"
                # Try the model-specific generate endpoint as a fallback
                url_model = f"https://api.mistral.ai/v1/models/{model}/generate"
                model_payload = {"input": (system_prompt + "\n\n" + text) if system_prompt else text}
                req_model = urllib.request.Request(url_model, data=json.dumps(model_payload).encode("utf-8"), headers=headers)
                try:
                    with urllib.request.urlopen(req_model, timeout=timeout) as resp2:
                        return _extract_text_from_response(resp2)
                except urllib.error.HTTPError as e_model:
                    try:
                        body_model = e_model.read().decode("utf-8", errors="replace")
                    except Exception:
                        body_model = "<unreadable>"
                    # Also try the generic /v1/generate endpoint
                    url_gen = "https://api.mistral.ai/v1/generate"
                    gen_payload = {"model": model, "input": (system_prompt + "\n\n" + text) if system_prompt else text}
                    req_gen = urllib.request.Request(url_gen, data=json.dumps(gen_payload).encode("utf-8"), headers=headers)
                    try:
                        with urllib.request.urlopen(req_gen, timeout=timeout) as resp3:
                            return _extract_text_from_response(resp3)
                    except Exception as e_final:
                        try:
                            body_final = e_final.read().decode("utf-8", errors="replace") if isinstance(e_final, urllib.error.HTTPError) else str(e_final)
                        except Exception:
                            body_final = "<unreadable>"
                        raise RuntimeError(f"Mistral endpoints failed: {url_chat} -> {body_chat}; {url_model} -> {body_model}; {url_gen} -> {body_final}")
            except urllib.error.URLError as e:
                raise RuntimeError(f"URL Error: {getattr(e,'reason',e)} (url={url_chat})")

        else:
            # Fallback: treat provider string as a raw endpoint (backwards compatibility)
            url = self.provider
            if not url:
                raise ValueError("No AI provider or endpoint configured")
            payload = {"input": (system_prompt + "\n\n" + text) if system_prompt else text, "mode": mode}
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return _extract_text_from_response(resp)
            except urllib.error.HTTPError as e:
                try:
                    body = e.read().decode("utf-8", errors="replace")
                except Exception:
                    body = "<unreadable>"
                raise RuntimeError(f"HTTP Error {getattr(e,'code',None)}: {getattr(e,'reason',None)} - {body} (url={url})")
            except urllib.error.URLError as e:
                raise RuntimeError(f"URL Error: {getattr(e,'reason',e)} (url={url})")


class AIChatWidget(QWidget):
    """AI chat panel — legacy assistant + full agentic (ReAct) mode."""
    response_received = pyqtSignal(str)
    # Signals wired to the AtomAgent for thread-safe UI updates
    _agent_status  = pyqtSignal(str)
    _agent_done    = pyqtSignal(str)
    _agent_error   = pyqtSignal(str)
    _agent_tool    = pyqtSignal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header bar ─────────────────────────────────────────────────
        header = QWidget()
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(4, 4, 4, 4)
        h_layout.setSpacing(6)

        atom_label = QLabel("⚛ ATOM")
        atom_label.setStyleSheet("color:#4fc3f7; font-weight:bold; font-size:12px;")
        h_layout.addWidget(atom_label)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Agentic", "Assistant", "Code"])
        self.mode_combo.setFixedWidth(110)
        self.mode_combo.setToolTip(
            "Agentic: full multi-step agent with tool execution\n"
            "Assistant: single-turn JSON response\n"
            "Code: code generation helper"
        )
        h_layout.addWidget(self.mode_combo)

        self.new_session_btn = QPushButton("↺")
        self.new_session_btn.setFixedWidth(26)
        self.new_session_btn.setToolTip("Reset agent session (clears conversation history)")
        self.new_session_btn.clicked.connect(self._reset_session)
        h_layout.addWidget(self.new_session_btn)

        h_layout.addStretch()
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setFixedWidth(26)
        self.settings_btn.setToolTip("AI Settings")
        self.settings_btn.clicked.connect(self._open_settings)
        h_layout.addWidget(self.settings_btn)

        layout.addWidget(header)

        # ── Chat display ───────────────────────────────────────────────
        self.chat_display = QTextBrowser()
        self.chat_display.setOpenExternalLinks(False)
        self.chat_display.setStyleSheet(
            "background-color:#1e1e1e; color:#cccccc; border:none; "
            "font-size:12px; padding:4px;"
        )
        layout.addWidget(self.chat_display)

        # ── Input row ──────────────────────────────────────────────────
        self.input_field = ChatInputField()
        self.input_field.setPlaceholderText(
            "Describe what to build… (Enter sends, Shift+Enter = newline)"
        )
        self.input_field.setMaximumHeight(80)
        self.input_field.enter_pressed.connect(self._send_message)
        layout.addWidget(self.input_field)

        self.send_btn = QPushButton("▶ Send")
        self.send_btn.clicked.connect(self._send_message)
        self.send_btn.setStyleSheet(
            "background:#0e7a9e; color:#fff; border:none; padding:5px; font-weight:bold;"
        )
        layout.addWidget(self.send_btn)

        # ── Legacy internals ───────────────────────────────────────────
        self.response_received.connect(self._append_response)
        self._ai_ref_map = {}
        self._last_created_nodes = []

        # ── Agent wiring ───────────────────────────────────────────────
        self._atom_agent = None   # lazy-init on first agentic send
        self._agent_busy  = False

        # Thread-safe signal routing
        self._agent_status.connect(self._on_agent_status)
        self._agent_done.connect(self._on_agent_done)
        self._agent_error.connect(self._on_agent_error)
        self._agent_tool.connect(self._on_agent_tool)

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def _reset_session(self):
        if self._atom_agent:
            self._atom_agent.reset_session()
        self.chat_display.append(
            "<i style='color:#888'>— Session reset. Atom's memory of this conversation cleared. —</i>"
        )

    # ------------------------------------------------------------------
    # Agent lazy init + signal connections
    # ------------------------------------------------------------------

    def _get_agent(self):
        if self._atom_agent is None:
            from py_editor.ui.panels.ai_agent import AtomAgent
            self._atom_agent = AtomAgent(self.main_window, parent=self)
            self._atom_agent.status_update.connect(self._agent_status)
            self._atom_agent.turn_complete.connect(self._agent_done)
            self._atom_agent.error_occurred.connect(self._agent_error)
            self._atom_agent.tool_executed.connect(self._agent_tool)
        return self._atom_agent

    # ------------------------------------------------------------------
    # Agent signal handlers (always on main thread via Qt)
    # ------------------------------------------------------------------

    def _on_agent_status(self, text: str):
        # Replace the last "..." line with status
        cursor = self.chat_display.textCursor()
        self.chat_display.append(f"<span style='color:#888;font-size:11px;'>  {text}</span>")

    def _on_agent_tool(self, tool_name: str, result: dict):
        ok = result.get("ok", True)
        if not ok:
            # Hide failed attempts from chat, but keep them in logs
            return
            
        icon = "✓"
        color = "#4caf50"
        # Show a compact one-liner per tool
        summary = self._summarize_tool_result(tool_name, result)
        self.chat_display.append(
            f"<span style='color:{color};font-size:11px;'>  {icon} {tool_name}: {summary}</span>"
        )

    def _on_agent_done(self, message: str):
        self._agent_busy = False
        self.send_btn.setEnabled(True)
        self.input_field.setEnabled(True)
        self.chat_display.append(f"<b style='color:#4fc3f7'>⚛ Atom:</b> {message}")
        try:
            from py_editor.ui.panels.ai_memory import short_term
            short_term.add_message('assistant', message)
        except Exception:
            pass

    def _on_agent_error(self, error: str):
        self._agent_busy = False
        self.send_btn.setEnabled(True)
        self.input_field.setEnabled(True)
        self.chat_display.append(f"<span style='color:#f44336'>⚠ Error: {error}</span>")

    def _summarize_tool_result(self, tool_name: str, result: dict) -> str:
        if not result.get("ok"):
            return f"failed — {result.get('error', '?')}"
        # Per-tool friendly summaries
        if tool_name == "add_node":
            return f"added {result.get('template')} (id {result.get('id')})"
        if tool_name == "delete_node":
            return f"deleted id {result.get('id', result.get('all_of_template', '?'))}"
        if tool_name == "connect":
            return f"{result.get('from_id')}.{result.get('from_pin')} → {result.get('to_id')}.{result.get('to_pin')}"
        if tool_name == "disconnect":
            return f"{result.get('removed', 0)} connection(s) removed"
        if tool_name == "set_value":
            return f"node {result.get('id')} {result.get('pin')}={result.get('value')}"
        if tool_name == "get_graph":
            return f"{result.get('node_count')} nodes, {result.get('connection_count')} connections"
        if tool_name == "arrange_nodes":
            return f"{result.get('arranged')} nodes arranged ({result.get('style')})"
        if tool_name == "create_template":
            return f"template '{result.get('name')}' created in {result.get('category')}"
        if tool_name == "clear_graph":
            return f"{result.get('nodes_removed', 0)} nodes cleared"
        if tool_name == "list_templates":
            cats = result.get("categories", {})
            return f"{sum(len(v) for v in cats.values())} templates in {len(cats)} categories"
        if tool_name == "search_templates":
            return f"{len(result.get('results', []))} results for '{result.get('query')}'"
        if tool_name == "find_nodes":
            return f"{result.get('count', 0)} node(s) found"
        if tool_name == "batch_connect":
            return f"{result.get('success', 0)} ok, {result.get('failed', 0)} failed"
        if tool_name == "move_node":
            return f"node {result.get('id')} → {result.get('pos')}"
        if tool_name == "rename_node":
            return f"node {result.get('id')} → '{result.get('name')}'"
        if tool_name == "add_variable":
            return f"var '{result.get('name')}' = {result.get('value')}"
        if tool_name == "get_variables":
            return f"{len(result.get('variables', {}))} variable(s)"
        if tool_name == "run_graph":
            return result.get("message", "started")
        if tool_name in ("undo", "redo"):
            return "ok"
        return "ok"

    def _open_settings(self):
        dlg = AISettingsDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            dlg.save()
            QMessageBox.information(self, "AI Settings", "Saved AI settings.")

    def _append_response(self, text: str):
        # Display the assistant's response. If the assistant returned a JSON object
        # we parse it and present a concise, human-friendly summary instead
        display = text
        try:
            obj = json.loads(text)
            display = self._format_assistant_json(obj)
        except Exception:
            # Not JSON — show raw text
            display = text
        self.chat_display.append(f"<b>AI:</b> {display}")

    def _format_assistant_json(self, obj) -> str:
        """Create a short, human-readable summary from the assistant's JSON reply.

        - Prefer explicit keys like `clarify`, `who`, `answer`, `message`, `content`.
        - Hide `remember` payloads from direct display (they're stored internally).
        - Fall back to a compact key/value preview for a few keys.
        """
        try:
            if isinstance(obj, dict):
                # Prefer top-level schema fields
                # Show only the human-facing message and a small action summary.
                msg = None
                if 'message' in obj and obj['message']:
                    msg = str(obj['message'])
                elif 'clarify' in obj and obj['clarify']:
                    msg = str(obj['clarify'])
                elif 'who' in obj and len(obj) == 1:
                    return str(obj['who'])
                else:
                    for k in ('answer', 'result', 'content', 'explain'):
                        if k in obj and obj[k]:
                            msg = str(obj[k])
                            break

                action = obj.get('action')
                files = obj.get('files_to_edit') if isinstance(obj.get('files_to_edit'), list) else None

                suffix_parts = []
                if action:
                    suffix_parts.append(f"action:{action}")
                if files:
                    suffix_parts.append(f"edits:{len(files)}")

                suffix = ''
                if suffix_parts:
                    suffix = ' (' + ','.join(suffix_parts) + ')'

                if msg:
                    return (msg + suffix).strip()

                # If remember present, acknowledge without showing payload
                if 'remember' in obj:
                    rem = obj.get('remember')
                    if isinstance(rem, (str, int, float)):
                        return f"(Saved memory) {str(rem)[:200]}"
                    if isinstance(rem, list):
                        return f"(Saved {len(rem)} memory items)"
                    return "(Saved memory)"

                # Fallback: show brief key preview
                parts = []
                for k, v in list(obj.items())[:4]:
                    if k == 'remember':
                        continue
                    if isinstance(v, (dict, list)):
                        parts.append(f"{k}:(...)")
                    else:
                        parts.append(f"{k}:{str(v)[:120]}")
                if parts:
                    return ' | '.join(parts)
                return str(obj)

            if isinstance(obj, list):
                if not obj:
                    return '[]'
                sample = obj[0]
                if isinstance(sample, dict) and sample:
                    k = next(iter(sample.keys()))
                    return f"List[{len(obj)}] sample: {k}={sample.get(k)}"
                return f"List[{len(obj)}]"

            return str(obj)
        except Exception:
            return str(obj)

    # ------------------------------------------------------------------
    # Agentic dispatch
    # ------------------------------------------------------------------

    def _send_agentic(self, user_message: str):
        """Route the user message through the full ReAct agent loop."""
        settings = QSettings("NodeCanvas", "AI")
        provider     = settings.value("provider", "") or ""
        endpoint_leg = settings.value("endpoint", "") or ""
        api_key      = settings.value("api_key", "") or ""
        model        = None
        if provider.lower() == "openai":
            model = settings.value("openai_model", "") or None
        elif provider.lower() == "mistral":
            model = settings.value("mistral_model", "") or None
        provider_or_ep = provider or endpoint_leg or "OpenAI"
        base_persona   = settings.value("system_prompt", DEFAULT_SYSTEM_PROMPT) or DEFAULT_SYSTEM_PROMPT

        if not api_key:
            self.chat_display.append(
                "<span style='color:#f44336'>⚠ No API key configured. Go to ⚙ Settings.</span>"
            )
            return

        # Disable input while agent is running
        self._agent_busy = True
        self.send_btn.setEnabled(False)
        self.input_field.setEnabled(False)
        self.chat_display.append(
            "<span style='color:#888;font-size:11px;'>⚛ Atom is thinking…</span>"
        )

        agent = self._get_agent()
        client = AIClient(provider_or_ep, api_key, model=model)

        # Patch client for multi-turn history support
        from py_editor.ui.panels.ai_agent import patch_client_for_history, build_system_prompt
        tools_executor = agent.executor
        graph_snap = agent._snapshot_graph()
        tmpl_cat   = agent._template_catalogue()
        sys_prompt = build_system_prompt(graph_snap, tmpl_cat, base_persona)
        patch_client_for_history(client, agent._history, sys_prompt)

        # Add user message to short-term memory
        try:
            from py_editor.ui.panels.ai_memory import short_term
            short_term.add_message('user', user_message)
        except Exception:
            pass

        agent.run(user_message, client, base_persona)

    def _build_selected_object_context(self) -> str | None:
        try:
            if not self.main_window or not hasattr(self.main_window, 'properties'):
                return None
            props = getattr(self.main_window, 'properties')
            objs = getattr(props, '_current_objects', None)
            if not objs:
                return None

            def _summarize(obj):
                keys = [
                    'id', 'name', 'obj_type', 'position', 'rotation', 'scale',
                    'physics_enabled', 'mass', 'collision_properties',
                    'shader_name', 'mesh_path', 'texture_path', 'file_path',
                    'controller_type', 'logic_list', 'pbr_maps', 'pbr_tiling',
                    'voxel_block_size', 'voxel_type', 'voxel_seed'
                ]
                s = {}
                for k in keys:
                    if not hasattr(obj, k):
                        continue
                    try:
                        v = getattr(obj, k)
                    except Exception:
                        continue
                    if k == 'collision_properties' and isinstance(v, list):
                        simplified = []
                        for c in v:
                            try:
                                simplified.append({
                                    'tag': c.get('tag'), 'shape': c.get('shape'),
                                    'radius': c.get('radius'), 'enabled': c.get('enabled', True)
                                })
                            except Exception:
                                pass
                        s[k] = simplified
                    elif k == 'pbr_maps' and isinstance(v, dict):
                        s[k] = {kk: vv for kk, vv in v.items() if vv}
                    else:
                        s[k] = v
                return s

            if len(objs) == 1:
                ctx = {'selected_count': 1, 'primary': _summarize(objs[0])}
            else:
                ctx = {'selected_count': len(objs), 'primary': _summarize(objs[0])}

            return json.dumps(ctx, separators=(',', ':'), ensure_ascii=True)
        except Exception:
            return None

    def _send_message(self):
        txt = self.input_field.toPlainText().strip()
        if not txt:
            return
        if self._agent_busy:
            self.chat_display.append(
                "<i style='color:#888'>Atom is still working… please wait.</i>"
            )
            return

        self.chat_display.append(f"<b style='color:#aaa'>You:</b> {txt}")
        self.input_field.clear()

        mode = self.mode_combo.currentText()

        # ── Agentic mode ───────────────────────────────────────────────
        if mode == "Agentic":
            self._send_agentic(txt)
            return

        # ── Legacy single-turn modes ───────────────────────────────────
        self.chat_display.append("<b>AI:</b> ...")

        # Read settings (provider + api key). Keep legacy "endpoint" as fallback.
        settings = QSettings("NodeCanvas", "AI")
        provider = settings.value("provider", "") or ""
        endpoint_legacy = settings.value("endpoint", "") or ""
        api_key = settings.value("api_key", "") or ""
        mode = self.mode_combo.currentText()

        # If provider is empty but legacy endpoint exists, use the legacy endpoint URL as a fallback
        provider_or_endpoint = provider or endpoint_legacy or "OpenAI"

        # Determine model selection from settings for the chosen provider
        model = None
        if provider:
            if provider.lower() == "openai":
                model = settings.value("openai_model", "") or None
            elif provider.lower() == "mistral":
                model = settings.value("mistral_model", "") or None
        else:
            # Try to infer provider from legacy endpoint
            le = endpoint_legacy.lower()
            if "openai" in le:
                model = settings.value("openai_model", "") or None
            elif "mistral" in le:
                model = settings.value("mistral_model", "") or None

        # Load system prompt and pass it into the LLM request so Atom's persona is respected
        system_prompt = settings.value("system_prompt", DEFAULT_SYSTEM_PROMPT) or DEFAULT_SYSTEM_PROMPT

        # Add the user's message to short-term memory
        try:
            short_term.add_message('user', txt)
        except Exception:
            pass

        # Shortcut: if the user replied with a simple confirmation (yes) and
        # the last assistant message was an "ask_user" clarification, assume
        # defaults and apply a sensible action (create a Chance node).
        try:
            txt_l = txt.strip().lower()
            yes_tokens = {"yes", "y", "sure", "ok", "do it", "please", "yeah"}
            if txt_l in yes_tokens:
                # find last assistant message in short_term
                last_assistant = None
                try:
                    for m in reversed(short_term.messages):
                        if m.get('role') == 'assistant':
                            last_assistant = m.get('content')
                            break
                except Exception:
                    last_assistant = None

                if last_assistant and (('"action":"ask_user"' in last_assistant) or ('action:ask_user' in last_assistant) or ('"action": "ask_user"' in last_assistant)):
                    # Auto-create a default Chance node and short-circuit AI call.
                    try:
                        self._create_default_chance_node()
                        # Record assistant action in short-term memory
                        short_term.add_message('assistant', json.dumps({"thought":"auto","action":"edit_file","message":"Created Chance node (assumed defaults)."}))
                        self.chat_display.append("<i>AI:</i> Created Chance node (assumed default: outputs random boolean with `prob` input).")
                        return
                    except Exception as e:
                        # Fall through to normal LLM call if auto-action failed
                        print(f"Auto-action failed: {e}")
                        pass
        except Exception:
            pass

        # Build selected object context and append to system prompt if present
        selected_ctx = self._build_selected_object_context()
        short_ctx = short_term.get_context() if short_term else None
        session_sum = session_summary_manager.get_combined_summary() if session_summary_manager else None

        # Include the active graph identifier if available
        active_graph = None
        try:
            if self.main_window and hasattr(self.main_window, 'get_active_graph_identifier'):
                active_graph = self.main_window.get_active_graph_identifier()
        except Exception:
            active_graph = None

        parts = []
        if system_prompt:
            parts.append(system_prompt)
        if selected_ctx:
            parts.append("Selected Scene Object: " + selected_ctx)
        if active_graph:
            parts.append("ActiveGraph: " + active_graph)
        if short_ctx:
            parts.append("ShortTermMemory: " + short_ctx)
        if session_sum:
            parts.append("SessionSummaries: " + session_sum)

        final_system_prompt = "\n\n".join(parts) if parts else system_prompt

        def task():
            try:
                client = AIClient(provider_or_endpoint, api_key, model=model)
                resp = client.send_message(txt, mode=mode, system_prompt=final_system_prompt)
                # Save raw provider reply for debugging
                try:
                    from pathlib import Path
                    log_dir = Path.cwd() / "memories"
                    log_dir.mkdir(exist_ok=True)
                    with open(log_dir / "last_raw_assistant_reply.txt", 'w', encoding='utf-8') as lf:
                        lf.write(str(resp))
                except Exception:
                    pass
                resp = sanitize_assistant_text(resp)
                # Try to parse JSON and update memories if assistant asked to remember facts
                try:
                    obj = json.loads(resp)
                except Exception:
                    obj = None

                if obj is not None:
                    # Add assistant message to short-term memory
                    try:
                        short_term.add_message('assistant', json.dumps(obj, ensure_ascii=False))
                    except Exception:
                        pass

                    # If assistant provided facts to remember, update persistent memory
                    for key in ('remember', 'facts', 'remember_this', 'store'):
                        if isinstance(obj, dict) and key in obj:
                            try:
                                memory_update(obj[key])
                                # Briefly annotate the chat display with saved memory (non-blocking)
                                self.chat_display.append(f"<i>Memory saved ({key}).</i>")
                            except Exception as e:
                                self.chat_display.append(f"<i>Memory save error: {e}</i>")
                            break

                    # If assistant requested edits, try to apply them (files_to_edit schema)
                    try:
                        action = obj.get('action') if isinstance(obj, dict) else None
                        if action and str(action).startswith('edit') and isinstance(obj.get('files_to_edit'), list):
                            ops = obj.get('files_to_edit')
                            # schedule UI-thread application
                            try:
                                QTimer.singleShot(0, lambda ops=ops: self._apply_files_to_edit(ops))
                                # notify chat that edits are being applied
                                self.chat_display.append(f"<i>AI:</i> Applying {len(ops)} edit(s)...")
                            except Exception as e:
                                print(f"Failed to schedule edits: {e}")
                    except Exception:
                        pass

            except Exception as e:
                resp = json.dumps({"error": str(e)})
            self.response_received.emit(resp)

        t = threading.Thread(target=task, daemon=True)
        t.start()

    def _create_default_chance_node(self):
        """Create a small 'Chance' node template if missing and add a node to the logic editor."""
        try:
            from py_editor.core.node_templates import get_template, save_template, load_templates, get_all_templates
        except Exception:
            # Import fallback
            try:
                from ..core.node_templates import get_template, save_template, load_templates, get_all_templates
            except Exception:
                get_template = save_template = load_templates = get_all_templates = None

        try:
            tmpl = None
            if callable(get_template):
                try:
                    tmpl = get_template("Chance")
                except Exception:
                    tmpl = None

            if not tmpl and callable(save_template):
                chance = {
                    "type": "base",
                    "name": "Chance",
                    "category": "Random",
                    "inputs": {"prob": "float"},
                    "outputs": {"result": "bool"},
                    "code": "name = 'Chance'\ninputs = {'prob':'float'}\noutputs = {'result':'bool'}\nimport random\ndef process(prob=0.5):\n    try:\n        return random.random() < float(prob)\n    except Exception:\n        return False\n"
                }
                try:
                    save_template(chance)
                except Exception:
                    pass
                try:
                    load_templates()
                except Exception:
                    pass
                # refresh local cache on logic editor
                try:
                    if self.main_window and hasattr(self.main_window, 'logic_editor'):
                        self.main_window.logic_editor._templates_cache = get_all_templates()
                except Exception:
                    pass

        except Exception:
            pass

        # Add the node to the logic editor (UI thread)
        try:
            le = getattr(self.main_window, 'logic_editor', None)
            if not le:
                return
            pos = QPointF(0, 0)
            try:
                node = le.add_node_from_template('Chance', pos=pos)
            except Exception:
                # Fallback: add a simple titled node
                node = le.add_node('Chance')
                try:
                    node.setPos(pos)
                except Exception:
                    pass
            # Select and center on the new node if possible
            try:
                for n in le.nodes:
                    try:
                        n.setSelected(False)
                    except Exception:
                        pass
                node.setSelected(True)
                try:
                    le.centerOn(node)
                except Exception:
                    pass
            except Exception:
                pass
            # Record reference mapping so subsequent ops can target this node
            try:
                nid = getattr(node, 'id', None)
                if nid is not None:
                    # Map generic keys for convenience
                    self._ai_ref_map.setdefault('last_created', nid)
                    # Also map by template/name for easy lookup
                    try:
                        tname = getattr(node, 'template_name', None) or getattr(node, 'title', None)
                        if hasattr(tname, 'toPlainText'):
                            tname = tname.toPlainText()
                        if tname:
                            self._ai_ref_map[str(tname)] = nid
                    except Exception:
                        pass
                    self._last_created_nodes.append(node)
                    # Ensure default probability is set on newly created Chance nodes
                    try:
                        if not getattr(node, 'pin_values', None):
                            node.pin_values = {}
                        # prefer float 0.5 default
                        node.pin_values.setdefault('prob', 0.5)
                        # Update UI widget if present
                        try:
                            proxy = getattr(node, 'value_widgets', {}).get('prob')
                            if proxy:
                                w = proxy.widget()
                                try:
                                    from PyQt6.QtWidgets import QLineEdit, QComboBox
                                    if hasattr(w, 'setValue'):
                                        try:
                                            w.setValue(0.5)
                                        except Exception:
                                            try:
                                                w.setText(str(0.5))
                                            except Exception:
                                                pass
                                    elif isinstance(w, QLineEdit):
                                        w.setText(str(0.5))
                                    elif isinstance(w, QComboBox):
                                        # try to set by text
                                        idx = w.findText('0.5')
                                        if idx >= 0:
                                            w.setCurrentIndex(idx)
                                except Exception:
                                    pass
                        except Exception:
                            pass
                    except Exception:
                        pass
            except Exception as e:
                print(f"_create_default_chance_node failed: {e}")
        except Exception as e:
            print(f"_create_default_chance_node failed: {e}")

    def _apply_files_to_edit(self, ops: list):
        """Apply a list of edit operations returned by the assistant.

        Supported ops (best-effort):
        - {op: 'add_node', node_type: 'Name', pos: [x,y]}
        - {op: 'connect', from: id, from_pin: 'out', to: id, to_pin: 'in'}
        """
        try:
            le = getattr(self.main_window, 'logic_editor', None)
            if not le:
                self.chat_display.append("<i>AI:</i> Could not apply edits: Logic editor not available.")
                return

            try:
                from py_editor.core.node_templates import get_template
            except Exception:
                get_template = None
        except Exception:
            self.chat_display.append("<i>AI:</i> Could not access logic editor.")
            return

        def _normalize_ops(input_ops):
            out = []
            if not input_ops:
                return out
            if isinstance(input_ops, dict):
                # single dict containing nested edits
                # prefer keys 'edits' or 'actions'
                for k in ('edits', 'actions', 'ops', 'operations', 'files_to_edit'):
                    if k in input_ops and isinstance(input_ops[k], list):
                        out.extend(_normalize_ops(input_ops[k]))
                        return out
                return [input_ops]
            if isinstance(input_ops, list):
                for it in input_ops:
                    if isinstance(it, (list, tuple)):
                        out.extend(_normalize_ops(list(it)))
                    elif isinstance(it, dict):
                        # flatten nested action lists
                        if any(k in it for k in ('edits', 'actions', 'ops', 'operations')):
                            for k in ('edits', 'actions', 'ops', 'operations'):
                                if k in it and isinstance(it[k], list):
                                    out.extend(_normalize_ops(it[k]))
                                    break
                            else:
                                out.append(it)
                        else:
                            out.append(it)
                    else:
                        # ignore unknown non-dict items
                        continue
            return out

        def _find_node_by_ref(ref):
            # Resolve ref to a NodeItem in the logic editor
            try:
                if ref is None:
                    return None
                # If int-like
                if isinstance(ref, int):
                    for n in le.nodes:
                        if getattr(n, 'id', None) == ref:
                            return n
                    return None
                # If ref is string, check mapping
                if isinstance(ref, str):
                    if ref in self._ai_ref_map:
                        nid = self._ai_ref_map.get(ref)
                        for n in le.nodes:
                            if getattr(n, 'id', None) == nid:
                                return n
                    # numeric string
                    try:
                        nid = int(ref)
                        for n in le.nodes:
                            if getattr(n, 'id', None) == nid:
                                return n
                    except Exception:
                        pass

                    rr = ref.lower().strip()
                    # exact match on template_name or title
                    for n in reversed(le.nodes):
                        t = getattr(n, 'template_name', None)
                        if isinstance(t, str) and t.lower() == rr:
                            return n
                        title = getattr(n, 'title', None)
                        try:
                            ttxt = title.toPlainText() if hasattr(title, 'toPlainText') else str(title)
                        except Exception:
                            ttxt = str(title)
                        if isinstance(ttxt, str) and ttxt.lower() == rr:
                            return n

                    # contains match
                    for n in reversed(le.nodes):
                        t = getattr(n, 'template_name', '') or ''
                        title = getattr(n, 'title', None)
                        try:
                            ttxt = title.toPlainText() if hasattr(title, 'toPlainText') else str(title)
                        except Exception:
                            ttxt = str(title)
                        if rr in str(t).lower() or rr in str(ttxt).lower():
                            return n

                    # fallback to last created
                    if self._last_created_nodes:
                        return self._last_created_nodes[-1]
                    if le.nodes:
                        return le.nodes[-1]
            except Exception:
                return None
            return None

        def _set_node_pin_value(node, pin_name, value):
            if node is None:
                return False
            # Normalize numeric percentage values
            val = value
            try:
                if isinstance(value, str) and value.strip().endswith('%'):
                    val = float(value.strip().rstrip('%')) / 100.0
                else:
                    if isinstance(value, str):
                        try:
                            val = float(value) if ('.' in value or 'e' in value.lower()) else int(value)
                        except Exception:
                            val = value
            except Exception:
                val = value

            try:
                if isinstance(val, (int, float)) and val > 1 and pin_name and pin_name.lower() in ('prob', 'probability', 'chance', 'percent'):
                    # user likely provided '50' meaning 50%
                    try:
                        val = float(val) / 100.0
                    except Exception:
                        pass
            except Exception:
                pass

            try:
                pv = getattr(node, 'pin_values', None)
                if pv is None:
                    node.pin_values = {pin_name: val}
                else:
                    pv[pin_name] = val
            except Exception:
                try:
                    setattr(node, 'pin_values', {pin_name: val})
                except Exception:
                    pass

            # Update UI widget if present
            try:
                proxy = getattr(node, 'value_widgets', {}).get(pin_name)
                widget = None
                if proxy:
                    widget = proxy.widget()
                if widget is not None:
                    try:
                        # If widget is a container, dig for inner widgets
                        if hasattr(widget, 'layout') and widget.layout():
                            layout = widget.layout()
                            for i in range(layout.count()):
                                item = layout.itemAt(i)
                                if item and item.widget():
                                    widget = item.widget()
                                    break
                    except Exception:
                        pass
                    try:
                        from PyQt6.QtWidgets import QComboBox, QLineEdit
                        if isinstance(widget, QComboBox):
                            txt = str(val)
                            idx = widget.findText(txt)
                            if idx >= 0:
                                widget.setCurrentIndex(idx)
                            else:
                                # booleans
                                if txt.lower() in ('true', 'false'):
                                    widget.setCurrentIndex(1 if txt.lower() == 'true' else 0)
                                else:
                                    try:
                                        widget.setCurrentText(txt)
                                    except Exception:
                                        pass
                        elif hasattr(widget, 'setValue'):
                            try:
                                widget.setValue(float(val))
                            except Exception:
                                try:
                                    widget.setText(str(val))
                                except Exception:
                                    pass
                        elif isinstance(widget, QLineEdit):
                            widget.setText(str(val))
                    except Exception:
                        pass
            except Exception:
                pass

            # Emit value changed if available
            try:
                if hasattr(le, 'value_changed'):
                    try:
                        le.value_changed.emit()
                    except Exception:
                        pass
            except Exception:
                pass

            return True

        normalized = _normalize_ops(ops)
        # Debug: write normalized ops to disk for inspection
        try:
            from pathlib import Path
            debug_dir = Path.cwd() / 'memories'
            debug_dir.mkdir(exist_ok=True)
            with open(debug_dir / 'last_ai_ops.json', 'w', encoding='utf-8') as df:
                import json as _json
                _json.dump({'raw': ops, 'normalized': normalized}, df, indent=2, ensure_ascii=False)
        except Exception:
            pass

        # Heuristic: if an op is a single human-readable message describing multiple edits,
        # try to parse it into structured ops (simple cases like "change Chance to 50, add On Play, add Print, connect them").
        parsed = []
        import re
        for op in normalized:
            if isinstance(op, dict) and not any(k in op for k in ('op', 'action', 'type', 'edits', 'actions', 'files_to_edit')):
                text = None
                for k in ('message', 'text', 'content', 'description'):
                    if k in op and isinstance(op[k], str):
                        text = op[k]
                        break
                if not text:
                    parsed.append(op)
                    continue

                # split into clauses
                clauses = re.split(r'[;,] | and ', text)
                ops_from_text = []
                for c in clauses:
                    cc = c.lower()
                    # set/change chance value
                    m = re.search(r'(?:change|set|modified|modify) .*chance.* to (\d+\.?\d*)', cc)
                    if m:
                        val = m.group(1)
                        try:
                            if '.' in val:
                                v = float(val)
                            else:
                                v = int(val)
                        except Exception:
                            v = val
                        ops_from_text.append({'op': 'set_node_value', 'node': 'Chance', 'pin': 'prob', 'value': v})
                        continue

                    # add On Play node
                    if 'on play' in cc or "onplay" in cc:
                        ops_from_text.append({'op': 'add_node', 'node_type': 'On Play'})
                        continue

                    # add Print node
                    if 'print' in cc or 'print node' in cc:
                        ops_from_text.append({'op': 'add_node', 'node_type': 'Print'})
                        continue

                    # connect them / connect
                    if 'connect' in cc or 'connected' in cc:
                        # naive: connect last created On Play -> Chance -> Print if present
                        ops_from_text.append({'op': 'connect', 'from': 'On Play', 'to': 'Chance'})
                        ops_from_text.append({'op': 'connect', 'from': 'Chance', 'to': 'Print'})
                        continue

                    # fallback: keep original op
                    ops_from_text.append(op)

                if ops_from_text:
                    parsed.extend(ops_from_text)
                else:
                    parsed.append(op)
            else:
                parsed.append(op)

        normalized = parsed
        applied = 0

        def _apply_single(op_item) -> bool:
            nonlocal applied
            try:
                if not isinstance(op_item, dict):
                    return False

                # flatten single-key shorthand
                kind = op_item.get('op') or op_item.get('action') or op_item.get('type') or None
                if not kind:
                    if 'node_type' in op_item or 'template' in op_item or 'name' in op_item:
                        kind = 'add_node'

                kind = str(kind).lower() if kind else None

                if kind in ('add_node', 'create_node', 'add'):
                    node_type = op_item.get('node_type') or op_item.get('template') or op_item.get('name') or 'Chance'
                    pos = op_item.get('pos')
                    qpos = QPointF(0, 0)
                    try:
                        if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                            qpos = QPointF(float(pos[0]), float(pos[1]))
                    except Exception:
                        qpos = QPointF(0, 0)

                    try:
                        created = None
                        if callable(get_template) and get_template(node_type):
                            created = le.add_node_from_template(node_type, pos=qpos)
                        else:
                            created = le.add_node(node_type)
                            try:
                                created.setPos(qpos)
                            except Exception:
                                pass

                        # record mapping if assistant supplied a ref
                        ref = op_item.get('ref') or op_item.get('id') or op_item.get('assign')
                        nid = getattr(created, 'id', None)
                        if nid is not None:
                            if ref:
                                try:
                                    self._ai_ref_map[str(ref)] = nid
                                except Exception:
                                    pass
                            # generic mapping
                            self._ai_ref_map.setdefault('last_created', nid)
                            try:
                                tname = getattr(created, 'template_name', None) or getattr(created, 'title', None)
                                if hasattr(tname, 'toPlainText'):
                                    tname = tname.toPlainText()
                                if tname:
                                    self._ai_ref_map[str(tname)] = nid
                            except Exception:
                                pass
                            self._last_created_nodes.append(created)

                        applied += 1
                        self.chat_display.append(f"<i>AI:</i> Added node: {node_type}")
                        return True
                    except Exception as e:
                        print(f"Failed to add node {node_type}: {e}")
                        return False

                elif kind in ('set_value', 'set_node_value', 'modify_node', 'change_value', 'update_value'):
                    # Determine target node
                    target = op_item.get('node') or op_item.get('node_id') or op_item.get('ref') or op_item.get('target') or op_item.get('which')
                    pin = op_item.get('pin') or op_item.get('field') or op_item.get('key') or op_item.get('property') or op_item.get('name') or 'prob'
                    val = op_item.get('value') if 'value' in op_item else op_item.get('val') if 'val' in op_item else op_item.get('set') if 'set' in op_item else None
                    node = _find_node_by_ref(target)
                    if node is None:
                        # try by template_name
                        node = _find_node_by_ref(op_item.get('node_type') or op_item.get('template') or 'Chance')
                    if node is not None:
                        ok = _set_node_pin_value(node, pin, val)
                        if ok:
                            applied += 1
                            self.chat_display.append(f"<i>AI:</i> Modified node {getattr(node,'id', '?')} {pin}={val}")
                            return True
                        else:
                            self.chat_display.append(f"<i>AI:</i> Failed to modify node {pin}")
                            return False
                    else:
                        self.chat_display.append(f"<i>AI:</i> Could not find target node to modify ({target})")
                        return False

                elif kind in ('connect', 'add_connection', 'link', 'connect_nodes'):
                    fr = op_item.get('from') or op_item.get('from_id') or op_item.get('source')
                    to = op_item.get('to') or op_item.get('to_id') or op_item.get('target') or op_item.get('dest')
                    from_pin = op_item.get('from_pin') or op_item.get('out_pin')
                    to_pin = op_item.get('to_pin') or op_item.get('in_pin')

                    from_node = _find_node_by_ref(fr)
                    to_node = _find_node_by_ref(to)
                    if from_node and to_node:
                        # determine default pins if not provided
                        try:
                            if not from_pin:
                                out_pins = getattr(from_node, 'output_pins', {}) or {}
                                from_pin = next(iter(out_pins.keys()), None)
                            if not to_pin:
                                in_pins = getattr(to_node, 'input_pins', {}) or {}
                                to_pin = next(iter(in_pins.keys()), None)
                        except Exception:
                            pass
                        try:
                            res = le.add_connection_by_id(getattr(from_node, 'id', None), from_pin, getattr(to_node, 'id', None), to_pin)
                            if res:
                                applied += 1
                                self.chat_display.append(f"<i>AI:</i> Connected {getattr(from_node,'id',None)}.{from_pin} -> {getattr(to_node,'id',None)}.{to_pin}")
                                return True
                        except Exception as e:
                            print(f"Failed to connect: {e}")
                            return False
                    else:
                        self.chat_display.append(f"<i>AI:</i> Could not resolve nodes to connect: {fr} -> {to}")
                        return False

                else:
                    # Unknown op - try to handle nested action lists
                    self.chat_display.append(f"<i>AI:</i> Unhandled op: {op_item}")
                    return False
            except Exception as e:
                print(f"Error applying op: {e}")
                return False

        # Try applying in multiple passes to allow forward references
        pending = list(normalized)
        max_rounds = 3
        round_no = 0
        while pending and round_no < max_rounds:
            round_no += 1
            new_pending = []
            for op in pending:
                try:
                    ok = _apply_single(op)
                    if not ok:
                        new_pending.append(op)
                except Exception as e:
                    print(f"_apply_single raised: {e}")
                    new_pending.append(op)
            if len(new_pending) == len(pending):
                # no progress
                break
            pending = new_pending

        if applied:
            self.chat_display.append(f"<i>AI:</i> Applied {applied} edit(s).")

def sanitize_assistant_text(text: str) -> str:
    """Robustly extract/validate JSON from assistant text and return a compact JSON string.

    Behavior:
    - Strip common wrappers (assistant labels, triple-backtick fences).
    - Accept JSON, double-encoded JSON strings, or JSON embedded inside text.
    - Attempt to extract balanced JSON substrings (objects or arrays) while ignoring
      braces that appear inside quoted strings.
    - As a last resort, try `ast.literal_eval` to parse Python-style dicts/lists.
    - If parsing fails, return a `clarify` JSON asking for additional info.
    """
    if not text or not text.strip():
        return json.dumps({"clarify": "I did not receive a response. Please provide more details."})

    s = str(text).strip()

    # Remove common assistant label prefixes like "AI:" or "Assistant:"
    s = re.sub(r'^[A-Za-z ]{1,20}:\s*', '', s)

    # Unwrap triple-backtick code fences if present
    m = re.search(r'```(?:json)?\n?([\s\S]*?)```', s, flags=re.IGNORECASE)
    if m:
        s = m.group(1).strip()

    # Try direct JSON parse
    try:
        obj = json.loads(s)
        return json.dumps(obj, separators=(',', ':'), ensure_ascii=False)
    except Exception:
        pass

    # If it's a JSON-encoded string (double-encoded), try loading twice
    try:
        first = json.loads(s)
        if isinstance(first, str):
            try:
                obj = json.loads(first)
                return json.dumps(obj, separators=(',', ':'), ensure_ascii=False)
            except Exception:
                pass
    except Exception:
        pass

    # Helper: find a balanced JSON substring starting at any { or [ while ignoring
    # braces inside strings. Returns the substring or None.
    def _find_json_substring(t: str) -> str | None:
        n = len(t)
        for i, ch in enumerate(t):
            if ch not in '{[':
                continue
            start = i
            stack = []
            in_str = False
            str_char = ''
            esc = False
            for j in range(i, n):
                c = t[j]
                if in_str:
                    if esc:
                        esc = False
                        continue
                    if c == '\\':
                        esc = True
                        continue
                    if c == str_char:
                        in_str = False
                        str_char = ''
                        continue
                    continue
                else:
                    if c == '"' or c == "'":
                        in_str = True
                        str_char = c
                        continue
                    if c in '{[':
                        stack.append(c)
                        continue
                    if c in '}]':
                        if not stack:
                            break
                        top = stack[-1]
                        if (top == '{' and c == '}') or (top == '[' and c == ']'):
                            stack.pop()
                            if not stack:
                                return t[start:j+1]
                        else:
                            break
        return None

    # Try to extract a JSON substring using the bracket matcher
    candidate = _find_json_substring(s)
    if candidate:
        try:
            obj = json.loads(candidate)
            return json.dumps(obj, separators=(',', ':'), ensure_ascii=False)
        except Exception:
            # Try a best-effort single-quote -> double-quote replacement
            candidate2 = candidate.replace("'", '"')
            try:
                obj = json.loads(candidate2)
                return json.dumps(obj, separators=(',', ':'), ensure_ascii=False)
            except Exception:
                pass

    # Final fallback: try to evaluate Python literal (handles single-quoted dicts)
    try:
        import ast
        pyobj = ast.literal_eval(s)
        if isinstance(pyobj, (dict, list)):
            return json.dumps(pyobj, separators=(',', ':'), ensure_ascii=False)
    except Exception:
        pass

    clarify = json.dumps({"clarify": "I could not produce valid JSON. What additional information should I use?"})
    # Log the raw reply to assist debugging
    try:
        from pathlib import Path
        log_dir = Path.cwd() / "memories"
        log_dir.mkdir(exist_ok=True)
        with open(log_dir / "last_failed_assistant_reply.txt", 'w', encoding='utf-8') as lf:
            lf.write(s)
    except Exception:
        pass
    return clarify
