"""
ai_memory.py

Simple memory subsystem used by the AI chat panel.

- ShortTermMemory: keeps the last N messages and auto-creates a short session summary every M messages.
- SessionSummaryManager: appends short summaries to a session JSON file.
- VectorDB: lightweight on-disk JSON "vector" store using sha256-based embeddings.
- memory_update(facts): normalize and persist facts to user memory and vector DB.

This is intentionally lightweight and dependency-free so it runs in-editor.
"""
from pathlib import Path
import time
import json
import hashlib
import uuid
import math
import threading
from typing import Any

# Directory for persistent memory files (project-root /memories)
BASE = Path.cwd() / "memories"
BASE.mkdir(exist_ok=True)

SESSION_SUMMARY_PATH = BASE / "session_summaries.json"
LONG_TERM_FACTS_PATH = BASE / "long_term_facts.json"
USER_MEMORY_PATH = BASE / "user_memory.json"


def _read_json(path: Path, default: Any):
    try:
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return default


def _write_json(path: Path, data: Any):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


class SessionSummaryManager:
    def __init__(self, path: Path = SESSION_SUMMARY_PATH):
        self.path = path
        self._lock = threading.Lock()
        self.data = _read_json(self.path, {"summaries": []})

    def add_summary(self, summary: str):
        with self._lock:
            entry = {"ts": int(time.time()), "summary": summary}
            self.data.setdefault("summaries", []).append(entry)
            _write_json(self.path, self.data)

    def get_combined_summary(self, n: int = 5) -> str:
        with self._lock:
            s = [e["summary"] for e in self.data.get("summaries", [])[-n:]]
            return " ".join(s)


class ShortTermMemory:
    def __init__(self, max_messages: int = 8, auto_summary_every: int = 5, session_mgr: SessionSummaryManager | None = None):
        self.max_messages = max_messages
        self.auto_summary_every = auto_summary_every
        self.messages: list[dict] = []
        self.count_since_summary = 0
        self._lock = threading.Lock()
        self.session_mgr = session_mgr

    def add_message(self, role: str, content: str):
        with self._lock:
            entry = {"role": role, "content": content, "ts": int(time.time())}
            self.messages.append(entry)
            if len(self.messages) > self.max_messages:
                self.messages = self.messages[-self.max_messages:]
            self.count_since_summary += 1
            if self.count_since_summary >= self.auto_summary_every:
                summary = self._summarize()
                try:
                    if self.session_mgr:
                        self.session_mgr.add_summary(summary)
                except Exception:
                    pass
                self.count_since_summary = 0

    def _summarize(self) -> str:
        # Very small heuristic summarizer: join recent messages and truncate.
        recent = [m['content'] for m in self.messages[-(self.auto_summary_every * 2):]]
        joined = ' '.join(recent).strip()
        if not joined:
            return ""
        if len(joined) <= 240:
            return joined
        # Prefer ending on a sentence boundary
        cut = joined[:240]
        if '.' in cut:
            return cut.rsplit('.', 1)[0] + '.'
        return cut + '...'

    def get_context(self) -> str:
        with self._lock:
            return json.dumps(self.messages, separators=(',', ':'), ensure_ascii=False)


class VectorDB:
    def __init__(self, path: Path = LONG_TERM_FACTS_PATH):
        self.path = path
        self._lock = threading.Lock()
        self.data = _read_json(self.path, {"entries": []})

    def _embed(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode('utf-8')).digest()
        return [b / 255.0 for b in h]

    def add_entry(self, text: str, meta: dict | None = None) -> dict:
        with self._lock:
            eid = uuid.uuid4().hex
            vec = self._embed(text)
            entry = {"id": eid, "text": text, "meta": meta or {}, "vec": vec, "ts": int(time.time())}
            self.data.setdefault("entries", []).append(entry)
            _write_json(self.path, self.data)
            return entry

    def query(self, text: str, top_n: int = 5) -> list:
        q = self._embed(text)

        def dot(a, b):
            return sum(x * y for x, y in zip(a, b))

        def norm(a):
            return math.sqrt(sum(x * x for x in a)) or 1.0

        qn = norm(q)
        scored = []
        with self._lock:
            for e in self.data.get("entries", []):
                v = e.get("vec", [])
                try:
                    score = dot(q, v) / (qn * norm(v))
                except Exception:
                    score = 0.0
                scored.append((score, e))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for s, e in scored[:top_n]]


# Instantiate singletons used by the UI
session_summary_manager = SessionSummaryManager()
short_term = ShortTermMemory(max_messages=8, auto_summary_every=5, session_mgr=session_summary_manager)
vector_db = VectorDB()


def memory_update(facts: Any) -> list[dict]:
    """
    Persist facts into user memory and vector DB.

    facts may be a string, dict, or list. The function normalizes items into short strings
    and appends them to `user_memory.json` and the vector DB.
    Returns the list of added entries.
    """
    if facts is None:
        return []

    items: list[str] = []
    if isinstance(facts, str):
        items = [facts]
    elif isinstance(facts, dict):
        # flatten dict to lines
        for k, v in facts.items():
            items.append(f"{k}: {v}")
    elif isinstance(facts, list):
        for it in facts:
            if isinstance(it, (str, int, float)):
                items.append(str(it))
            elif isinstance(it, dict):
                for k, v in it.items():
                    items.append(f"{k}: {v}")
            else:
                items.append(str(it))
    else:
        items = [str(facts)]

    user_data = _read_json(USER_MEMORY_PATH, {"facts": []})
    added = []
    for text in items:
        entry = {"id": uuid.uuid4().hex, "text": text, "ts": int(time.time())}
        user_data.setdefault("facts", []).append(entry)
        added.append(entry)
        try:
            vector_db.add_entry(text, meta={"source": "assistant", "id": entry["id"]})
        except Exception:
            pass

    _write_json(USER_MEMORY_PATH, user_data)
    return added
