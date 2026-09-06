"""Load the System-Pattern Knowledge Base — deep, reusable construction
intelligence per building/industrial system, composed into project archetypes.

This is the Phase 2 knowledge layer of the MEP-first constructability redesign,
kept separate from the legacy curated ``knowledge_base/<category>/<type>.json``
standards so the v1 review is unaffected until the v2 engine consumes it.

Files (bundled defaults + optional per-user overlay, exactly like ``kb.py``):
  * ``knowledge_base/system_patterns/<system>.json`` — one System Pattern each
    (work packages · sequence · typical predecessor/successor relationships ·
    interfaces · zones · testing · commissioning dependencies · exceptions ·
    evidence).
  * ``knowledge_base/archetypes.json`` — the archetype → systems composition
    (which systems are the review focus for each project type).

Generalized, project-agnostic knowledge — never project-specific templates.
"""
import glob
import json
import os

from utils import app_data_dir, resource_path

_PATTERNS_SUBDIR = os.path.join('knowledge_base', 'system_patterns')
_ARCHETYPES_FILE = os.path.join('knowledge_base', 'archetypes.json')


def patterns_bundled_dir():
    return resource_path(_PATTERNS_SUBDIR)


def patterns_overlay_dir():
    return os.path.join(app_data_dir(), _PATTERNS_SUBDIR)


def archetypes_bundled_path():
    return resource_path(_ARCHETYPES_FILE)


def archetypes_overlay_path():
    return os.path.join(app_data_dir(), _ARCHETYPES_FILE)


def _iter_pattern_objects(obj):
    """A file may hold a single pattern dict or a list of them."""
    if isinstance(obj, dict) and obj.get('system'):
        yield obj
    elif isinstance(obj, dict) and isinstance(obj.get('patterns'), list):
        yield from (p for p in obj['patterns'] if isinstance(p, dict) and p.get('system'))
    elif isinstance(obj, list):
        yield from (p for p in obj if isinstance(p, dict) and p.get('system'))


def load_system_patterns(bundled=None, overlay=None):
    """Return {system_id: pattern}. Overlay entries override bundled by system id."""
    out = {}
    for base in (bundled if bundled is not None else patterns_bundled_dir(),
                 overlay if overlay is not None else patterns_overlay_dir()):
        if not base or not os.path.isdir(base):
            continue
        for path in sorted(glob.glob(os.path.join(base, '*.json'))):
            try:
                with open(path, encoding='utf-8') as f:
                    data = json.load(f)
            except (OSError, ValueError):
                continue
            for pat in _iter_pattern_objects(data):
                out[pat['system']] = pat
    return out


def load_archetypes(bundled=None, overlay=None):
    """Return {archetype_id: archetype}. Overlay overrides bundled by id."""
    out = {}
    for path in (bundled if bundled is not None else archetypes_bundled_path(),
                 overlay if overlay is not None else archetypes_overlay_path()):
        if not path or not os.path.isfile(path):
            continue
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        items = data.get('archetypes', []) if isinstance(data, dict) else (data or [])
        for arc in items:
            if isinstance(arc, dict) and arc.get('archetype'):
                out[arc['archetype']] = arc
    return out
