"""
controller_manager.py

Manages .controller files from the controllers/ directory.
Mirrors the shader_manager pattern: discovers files, loads JSON definitions,
and maps controller type strings to the correct Python controller class.
"""
import json
import os
from pathlib import Path

from py_editor.core.controller import (
    BaseController, AIController, PlayerController,
    AIGPUFishController, AIGPUBirdController
)

# ── Discovery ────────────────────────────────────────────────────────────────

_CONTROLLER_DIR = Path(__file__).parent.parent.parent / "controllers"

def get_controller_list():
    """Return list of available controller display names from .controller files."""
    names = ["None"]  # Always include "None" as first option
    try:
        if _CONTROLLER_DIR.exists():
            for f in sorted(_CONTROLLER_DIR.glob("*.controller")):
                if f.stem == "base":
                    continue  # Don't list abstract base
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    names.append(data.get("name", f.stem))
                except Exception:
                    names.append(f.stem)
    except Exception:
        pass
    return names


def get_controller_path(display_name):
    """Given a display name like 'GPU Fish', return the .controller file path."""
    if display_name == "None":
        return None
    try:
        if _CONTROLLER_DIR.exists():
            for f in _CONTROLLER_DIR.glob("*.controller"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    if data.get("name") == display_name:
                        return str(f)
                except Exception:
                    pass
            # Fallback: match stem
            for f in _CONTROLLER_DIR.glob("*.controller"):
                if f.stem == display_name:
                    return str(f)
    except Exception:
        pass
    return None


def load_controller_def(name_or_path):
    """Load and return the JSON definition dict for a controller."""
    if not name_or_path or name_or_path == "None":
        return None

    # Direct path
    if os.path.isabs(name_or_path) and os.path.exists(name_or_path):
        try:
            return json.loads(Path(name_or_path).read_text(encoding="utf-8"))
        except Exception:
            return None

    # Search by display name or stem
    if _CONTROLLER_DIR.exists():
        for f in _CONTROLLER_DIR.glob("*.controller"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if data.get("name") == name_or_path or f.stem == name_or_path:
                    return data
            except Exception:
                continue
    return None


# ── Type → Class mapping ─────────────────────────────────────────────────────

_TYPE_MAP = {
    "player":       PlayerController,
    "ai_cpu":       AIController,
    "ai_gpu_fish":  AIGPUFishController,
    "ai_gpu_bird":  AIGPUBirdController,
}

# Legacy display-name map (backwards compat with old scenes)
_LEGACY_MAP = {
    "Player":          "player",
    "AI (CPU)":        "ai_cpu",
    "AI (GPU Fish)":   "ai_gpu_fish",
    "AI (GPU Bird)":   "ai_gpu_bird",
}


def create_controller(name_or_path, owner):
    """Instantiate the correct controller class for the given name/path."""
    if not name_or_path or name_or_path == "None":
        return None

    # 1. Legacy string → type
    ctrl_type = _LEGACY_MAP.get(name_or_path)

    # 2. Load from file definition
    defn = None
    if not ctrl_type:
        defn = load_controller_def(name_or_path)
        if defn:
            ctrl_type = defn.get("type")

    if not ctrl_type:
        print(f"[CTRL MGR] Error: Could not resolve type for '{name_or_path}'")
        return None

    cls = _TYPE_MAP.get(ctrl_type)
    if not cls:
        print(f"[CTRL MGR] Warning: No implementation class for type '{ctrl_type}'")
        return None

    print(f"[CTRL MGR] Creating '{cls.__name__}' for '{owner.name}' using '{name_or_path}'")
    ctrl = cls(owner)

    # Apply params from definition
    if not defn:
        defn = load_controller_def(name_or_path)
    if defn and "params" in defn:
        for k, v in defn["params"].items():
            if hasattr(ctrl, k):
                setattr(ctrl, k, v)

    return ctrl
