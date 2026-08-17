"""Load the Productivity Knowledge Base — bundled defaults + per-user overlay.

Mirrors ``p6_kb.kb`` exactly: glob the bundled ``productivity_kb/disciplines/**`` plus an
optional overlay under ``%APPDATA%/P6EVMTool/productivity_kb``; the overlay wins by
``template_id``. Malformed files are skipped, never fatal. Everything ships ``draft``.
"""
import glob
import json
import os

try:
    from utils import resource_path, app_data_dir
except Exception:  # pragma: no cover - keeps the engine importable in isolation
    def resource_path(rel):
        return rel

    def app_data_dir():
        return ""


def bundled_dir():
    return resource_path("productivity_kb")


def overlay_dir():
    base = app_data_dir()
    return os.path.join(base, "productivity_kb") if base else ""


def _load_dir(base):
    if not base or not isinstance(base, str) or not os.path.isdir(base):
        return []
    out = []
    for path in sorted(glob.glob(os.path.join(base, "disciplines", "**", "*.json"), recursive=True)):
        try:
            with open(path, encoding="utf-8") as f:
                entry = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(entry, dict) and entry.get("template_id"):
            out.append(entry)
    return out


def load_templates(bundled=None, overlay=None):
    """Return the merged list of activity templates (overlay overrides bundled by id)."""
    b = _load_dir(bundled if bundled is not None else bundled_dir())
    o = _load_dir(overlay if overlay is not None else overlay_dir())
    by_key, order = {}, []
    for entry in b + o:  # overlay last -> wins
        key = entry.get("template_id")
        if key not in by_key:
            order.append(key)
        by_key[key] = entry
    return [by_key[k] for k in order]


def by_id(templates=None):
    return {t["template_id"]: t for t in (templates if templates is not None else load_templates())}
