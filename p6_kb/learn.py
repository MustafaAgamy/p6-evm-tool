"""Local learning — the tool quietly learns from every schedule you import.

Per project type, it accumulates which activities and WBS branches recur across
*your own* imports, and their typical durations. Fully local and private: stored
under the per-user app folder, nothing leaves the PC. Kept separate from the
curated Knowledge Base standards and always marked "learned".

Storage: one JSON profile per project type under ``%APPDATA%/Controlyx/learned/``.
Deduped by file hash, so re-importing the same schedule never inflates the counts.
"""
import json
import os
import re

from p6_kb.detect import detect_subtype, score_entries
from p6_kb.kb import load_kb
from p6_kb.model import schedule_view
from utils import app_data_dir

DAY_HOURS = 8.0
MIN_CONFIDENCE = 3          # don't learn a type we only weakly detected
MIN_FRACTION = 0.5          # "recurring" = seen in ≥ half your imports…
MIN_SEEN = 2                # …and in at least two of them


def learned_dir(base=None):
    return os.path.join(base or app_data_dir(), 'learned')


def _slug(type_name):
    return re.sub(r'[^a-z0-9]+', '_', (type_name or '').lower()).strip('_') or 'unknown'


def _norm(name):
    return re.sub(r'\s+', ' ', (name or '').strip().lower())


def _profile_path(type_name, base=None):
    return os.path.join(learned_dir(base), _slug(type_name) + '.json')


def load_profile(type_name, base=None):
    try:
        with open(_profile_path(type_name, base), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def load_all_profiles(base=None):
    out = []
    d = learned_dir(base)
    if not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        if not fn.endswith('.json'):
            continue
        try:
            with open(os.path.join(d, fn), encoding='utf-8') as f:
                out.append(json.load(f))
        except (OSError, ValueError):
            continue
    return out


def _save(profile, base=None):
    d = learned_dir(base)
    os.makedirs(d, exist_ok=True)
    with open(_profile_path(profile['type'], base), 'w', encoding='utf-8') as f:
        json.dump(profile, f, ensure_ascii=False, indent=1)


def _fold(data, entry, key, base):
    """Fold one schedule into the profile. `key` identifies the source so it is
    only counted once — the P6 project id (so weekly updates of the same project
    don't inflate the counts), falling back to the file hash."""
    profile = load_profile(entry['type'], base) or {
        'type': entry['type'], 'category': entry.get('category', ''),
        'imports': 0, 'keys': [], 'activities': {}, 'wbs': {},
    }
    if key and key in profile.get('keys', []):
        return profile  # this project already contributed
    profile['imports'] = profile.get('imports', 0) + 1
    if key:
        profile.setdefault('keys', []).append(key)

    seen = set()
    for a in data.activities.values():
        key = _norm(a.get('name'))
        if not key or key in seen:
            continue
        seen.add(key)
        rec = profile['activities'].setdefault(
            key, {'name': a.get('name') or '', 'seen': 0, 'dur_sum': 0.0, 'dur_count': 0})
        rec['seen'] += 1
        dur_h = a.get('planned_duration')
        if dur_h and dur_h > 0:
            rec['dur_sum'] += float(dur_h) / DAY_HOURS
            rec['dur_count'] += 1

    wseen = set()
    for w in data.wbs.values():
        key = _norm(w.get('name'))
        if not key or key in wseen:
            continue
        wseen.add(key)
        rec = profile['wbs'].setdefault(key, {'name': w.get('name') or '', 'seen': 0})
        rec['seen'] += 1

    _save(profile, base)
    return profile


def learn_from_schedule(data, file_hash=None, base=None, entries=None):
    """Detect the type of an imported schedule and fold it into the learned
    profile for that type. Returns the profile, or None (unknown/low-confidence
    type, or any error). Safe to call on every import — never raises."""
    try:
        view = schedule_view(data)
        entries = entries if entries is not None else load_kb()
        entry, _ = detect_subtype(view, entries)
        if entry is None:
            return None
        hits = next((h for e, h in score_entries(view, entries) if e is entry), 0)
        if hits < MIN_CONFIDENCE:
            return None
        proj = ''
        try:
            proj = (getattr(data, 'project', None) or {}).get('id') or ''
        except Exception:
            proj = ''
        return _fold(data, entry, proj or file_hash, base)
    except Exception:
        return None


def fold_under(data, entry, base=None):
    """Fold a schedule into the learned profile under a KNOWN type (the one the
    user chose when adding it to the Construction Database) — so adding a schedule
    grows the tool's knowledge for that exact type. Deduped by P6 project id, so
    it composes safely with import-time learning."""
    try:
        proj = ''
        try:
            proj = (getattr(data, 'project', None) or {}).get('id') or ''
        except Exception:
            proj = ''
        return _fold(data, entry, proj or None, base)
    except Exception:
        return None


# ── deriving usable knowledge from a profile ────────────────────────────────

def _threshold(imports):
    return max(MIN_SEEN, round(MIN_FRACTION * imports))


def recurring_activities(profile, base=None):
    imports = max(profile.get('imports', 1), 1)
    need = _threshold(imports)
    out = []
    for rec in profile.get('activities', {}).values():
        if rec['seen'] < need:
            continue
        avg = (rec['dur_sum'] / rec['dur_count']) if rec.get('dur_count') else None
        out.append({'name': rec['name'], 'seen': rec['seen'], 'imports': imports,
                    'avg_duration': int(round(avg)) if avg else None})
    out.sort(key=lambda x: (-x['seen'], x['name'].lower()))
    return out


def recurring_wbs(profile):
    imports = max(profile.get('imports', 1), 1)
    need = _threshold(imports)
    out = [{'name': r['name'], 'seen': r['seen'], 'imports': imports}
           for r in profile.get('wbs', {}).values() if r['seen'] >= need]
    out.sort(key=lambda x: (-x['seen'], x['name'].lower()))
    return out


def has_learning(profile):
    return bool(profile) and profile.get('imports', 0) >= MIN_SEEN and bool(recurring_activities(profile))


def learned_panel(profile, view):
    """For the Constructability review: the recurring activities for this type,
    each flagged for whether it's present in the current schedule."""
    if not has_learning(profile):
        return None
    present = [_norm(a['name']) for a in view['activities']]

    def in_schedule(name):
        n = _norm(name)
        return any(n and (n in p or p in n) for p in present)

    acts = [{**a, 'in_schedule': in_schedule(a['name'])} for a in recurring_activities(profile)]
    return {
        'type': profile['type'], 'category': profile.get('category', ''),
        'imports': profile.get('imports', 0),
        'activities': acts,
        'missing_count': sum(1 for a in acts if not a['in_schedule']),
        'wbs': recurring_wbs(profile),
    }


def learned_entry(profile):
    """A KB-shaped entry built from a learned profile — feeds the library detail
    view and the starter-baseline export, exactly like a curated standard."""
    acts = recurring_activities(profile)
    wbs = recurring_wbs(profile)
    imports = profile.get('imports', 0)
    return {
        'category': 'Learned from your projects',
        'type': profile['type'],
        'status': 'learned',
        'source': 'learned',
        'imports': imports,
        'note': f"Learned from {imports} of your imported {profile['type']} schedules — local & private.",
        'signatures': [],
        'wbs': [{'name': w['name'], 'keywords': []} for w in wbs],
        'activities': [{
            'name': a['name'], 'keywords': [], 'wbs': '',
            'typical_pred': '', 'typical_succ': '',
            'duration_days': a['avg_duration'] or 10,
            'why': f"Recurs in {a['seen']} of your {imports} {profile['type']} schedules.",
        } for a in acts],
        'logic_rules': [], 'milestones': [], 'common_issues': [],
    }
