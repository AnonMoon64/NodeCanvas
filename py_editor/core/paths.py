"""
paths.py — project-root aware asset path handling.

Assets (meshes, textures, shaders, PBR maps, spawner prefabs, logic scripts)
are stored on disk as paths relative to the project root when possible, and
resolved to absolute paths in-memory so the rest of the runtime can keep
treating them as absolute.
"""
from pathlib import Path
from typing import Any, Optional

_PROJECT_ROOT: Path = Path.cwd()

# Keys whose string values are asset paths that should be normalised.
ASSET_PATH_KEYS = {
    "mesh_path", "texture_path", "shader_name", "file_path",
    "logic_path", "albedo", "normal", "roughness", "metallic",
    "ao", "displacement", "controller_type", "spawner_source_path",
}

# Keys whose value is a list of asset paths.
ASSET_PATH_LIST_KEYS = {"prefabs", "logic_list", "spawner_prefabs"}

# Listeners invoked when the project root changes.
_LISTENERS = []


def get_project_root() -> Path:
    return _PROJECT_ROOT


def set_project_root(path) -> None:
    global _PROJECT_ROOT
    _PROJECT_ROOT = Path(path).resolve()
    for cb in list(_LISTENERS):
        try:
            cb(_PROJECT_ROOT)
        except Exception as e:
            print(f"[PATHS] listener error: {e}")


def on_project_root_changed(callback) -> None:
    _LISTENERS.append(callback)


def to_relative(path: str, root: Optional[Path] = None) -> str:
    """Return path relative to project root (POSIX), or unchanged if outside."""
    if not path or not isinstance(path, str) or path in ("None", "Standard", "PulseEngine_Legacy"):
        return path
    root = Path(root) if root else _PROJECT_ROOT
    try:
        p = Path(path)
        if not p.is_absolute():
            return path.replace("\\", "/")
        rel = p.resolve().relative_to(root.resolve())
        return rel.as_posix()
    except (ValueError, OSError):
        return path.replace("\\", "/")


def resolve(path: str, root: Optional[Path] = None) -> str:
    """If path is relative, resolve against project root. Else return as-is."""
    if not path or not isinstance(path, str) or path in ("None", "Standard", "PulseEngine_Legacy"):
        return path
    p = Path(path)
    if p.is_absolute():
        return str(p)
    root = Path(root) if root else _PROJECT_ROOT
    return str((root / p).resolve())


def _walk(value: Any, fn) -> Any:
    """Recursively walk dicts/lists applying fn(key, str_value) to asset-path strings."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k in ASSET_PATH_KEYS and isinstance(v, str) and v:
                out[k] = fn(v)
            elif k in ASSET_PATH_LIST_KEYS and isinstance(v, list):
                out[k] = [fn(x) if isinstance(x, str) and x else x for x in v]
            else:
                out[k] = _walk(v, fn)
        return out
    if isinstance(value, list):
        return [_walk(v, fn) for v in value]
    return value


def normalize_for_save(data: Any, root: Optional[Path] = None) -> Any:
    r = Path(root) if root else _PROJECT_ROOT
    return _walk(data, lambda s: to_relative(s, r))


def resolve_on_load(data: Any, root: Optional[Path] = None) -> Any:
    r = Path(root) if root else _PROJECT_ROOT
    return _walk(data, lambda s: resolve(s, r))
