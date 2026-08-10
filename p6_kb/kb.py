"""Load the Construction Knowledge Base.

Two sources merge: the **bundled defaults** shipped in the app
(``knowledge_base/<category>/<type>.json``) and an optional **user overlay** in the
per-user app folder (``%APPDATA%/P6EVMTool/knowledge_base/...``). An overlay entry
overrides a bundled one with the same (category, type) — so Ibrahim, and later a
company, can add or refine standards without touching the application.
"""
import glob
import json
import os

from utils import resource_path, app_data_dir


def bundled_dir():
    return resource_path('knowledge_base')


def overlay_dir():
    return os.path.join(app_data_dir(), 'knowledge_base')


def _load_dir(base):
    entries = []
    if not base or not os.path.isdir(base):
        return entries
    for path in sorted(glob.glob(os.path.join(base, '*', '*.json'))):
        try:
            with open(path, encoding='utf-8') as f:
                entry = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(entry, dict) and entry.get('type'):
            entries.append(entry)
    return entries


def load_kb(bundled=None, overlay=None):
    """Return the list of KB sub-type entries (overlay overrides bundled by key)."""
    b = _load_dir(bundled if bundled is not None else bundled_dir())
    o = _load_dir(overlay if overlay is not None else overlay_dir())
    by_key = {}
    order = []
    for entry in b + o:  # overlay processed last → wins
        key = (entry.get('category', ''), entry.get('type', ''))
        if key not in by_key:
            order.append(key)
        by_key[key] = entry
    return [by_key[k] for k in order]
