"""The Construction Database — a local library of P6 schedules, grouped by project
type. Every Knowledge Base type offers generated example baselines (a clean one and a
"with typical gaps" one); on top of that the user can *contribute* their own imported
schedules, which are copied into the per-user database folder and also feed the
learning engine. Private and local — nothing leaves the PC.
"""
import json
import os
import re
import shutil
from datetime import datetime

from p6_kb.detect import detect_subtype, score_entries
from p6_kb.kb import load_kb
from p6_kb.learn import MIN_CONFIDENCE
from p6_kb.model import schedule_view
from utils import app_data_dir


def database_dir(base=None):
    return os.path.join(base or app_data_dir(), 'database')


def _index_path(base=None):
    return os.path.join(database_dir(base), 'index.json')


def _slug(name):
    return re.sub(r'[^a-z0-9]+', '_', (name or '').lower()).strip('_') or 'unknown'


def load_index(base=None):
    try:
        with open(_index_path(base), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_index(idx, base=None):
    os.makedirs(database_dir(base), exist_ok=True)
    with open(_index_path(base), 'w', encoding='utf-8') as f:
        json.dump(idx, f, ensure_ascii=False, indent=1)


def _detect(data, entries, forced_type=None):
    view = schedule_view(data)
    if forced_type:
        entry = next((e for e in entries if e.get('type') == forced_type), None)
        if entry:
            return entry
    entry, _ = detect_subtype(view, entries)
    if entry is None:
        return None
    hits = next((h for e, h in score_entries(view, entries) if e is entry), 0)
    return entry if hits >= MIN_CONFIDENCE else None


def add_import(src_path, data, base=None, entries=None, forced_type=None, when=None):
    """Copy an imported schedule into the database under its detected type, index it,
    and return the record — or None if the type can't be identified (never mis-filed)."""
    if not src_path or not os.path.isfile(src_path):
        return None
    entries = entries if entries is not None else load_kb()
    entry = _detect(data, entries, forced_type)
    if entry is None:
        return None

    slug = _slug(entry['type'])
    dest_dir = os.path.join(database_dir(base), slug)
    os.makedirs(dest_dir, exist_ok=True)
    fname = os.path.basename(src_path)
    dest = os.path.join(dest_dir, fname)
    stem, ext = os.path.splitext(fname)
    n = 1
    while os.path.exists(dest) and os.path.getsize(dest) != os.path.getsize(src_path):
        dest = os.path.join(dest_dir, f"{stem}_{n}{ext}")
        n += 1
    shutil.copy2(src_path, dest)

    idx = load_index(base)
    rec = idx.setdefault(slug, {'type': entry['type'], 'category': entry.get('category', ''), 'files': []})
    rec['type'] = entry['type']
    rec['category'] = entry.get('category', '')
    filename = os.path.basename(dest)
    record = {'filename': filename, 'kind': 'contributed',
              'activities': len(data.activities), 'wbs': len(data.wbs),
              'added': when or datetime.now().strftime('%Y-%m-%d')}
    existing = next((f for f in rec['files'] if f['filename'] == filename), None)
    if existing:
        existing.update(record)
    else:
        rec['files'].append(record)
    _save_index(idx, base)
    # Adding a schedule also grows the tool's learned knowledge for this exact type
    # (deduped by project id — safe alongside import-time learning).
    try:
        from p6_kb.learn import fold_under
        fold_under(data, entry, base=base)
    except Exception:
        pass
    return {'type': entry['type'], 'category': entry.get('category', ''), **record}


def list_database(base=None, entries=None):
    """The full type tree (every KB type) with each type's contributed files.
    Generated examples (clean + gappy) are always available per type."""
    kb = entries if entries is not None else load_kb()
    idx = load_index(base)
    cats, order = {}, []
    for e in kb:
        c = e.get('category', 'Other')
        t = e.get('type', '')
        rec = idx.get(_slug(t), {})
        contributed = rec.get('files', [])
        if c not in cats:
            cats[c] = []
            order.append(c)
        cats[c].append({'type': t, 'category': c, 'contributed': contributed,
                        'contributed_count': len(contributed)})
    categories = [{'category': c, 'count': len(cats[c]), 'types': cats[c]} for c in order]
    total = sum(len(r.get('files', [])) for r in idx.values())
    return {'categories': categories, 'contributed_total': total, 'types_total': len(kb)}


def contributed_path(type_name, filename, base=None):
    """Absolute path of a stored contributed file, or None. Guards against traversal."""
    safe = os.path.basename(filename or '')
    p = os.path.join(database_dir(base), _slug(type_name), safe)
    return p if os.path.isfile(p) else None
