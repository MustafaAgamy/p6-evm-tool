"""The question library — the catalogue of PM questions the chat offers, grouped by
theme and tagged by job role, plus the honest 'future' gaps.

The data ships as ``p6_chat/data/questions.json`` (built once from the question-
library workflow). This module loads it (cached) and shapes it for the UI. Every
question carries: ``q`` (the wording), ``grounds`` (which feature answers it),
``status`` (today / in-progress / gap), ``role_keys`` (which job titles ask it) and
a bundled sample answer (``answer_full``) used only as a fallback before the local
brain is set up. The live per-project answer always comes from the model.
"""
import json
import os

try:
    from utils import resource_path
except Exception:                                    # pragma: no cover - dev fallback
    def resource_path(rel):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', rel)

_CACHE = None


def _data_path():
    # Bundled as p6_chat/data/questions.json (see controlyx.spec datas).
    return resource_path(os.path.join('p6_chat', 'data', 'questions.json'))


def load():
    """The raw catalogue dict {catalog, roles, gaps}, cached after first read."""
    global _CACHE
    if _CACHE is None:
        with open(_data_path(), encoding='utf-8') as f:
            _CACHE = json.load(f)
    return _CACHE


def roles():
    """The job titles, in display order: [{key, title}, ...]."""
    return list(load().get('roles', []))


def gaps():
    """The honest 'future' list — things PMs want that the tool can't ground yet."""
    return list(load().get('gaps', []))


def _counts():
    per_role, today = {}, 0
    total = prog = gap = 0
    for t in load().get('catalog', []):
        for q in t.get('questions', []):
            total += 1
            st = q.get('status')
            if st == 'today':
                today += 1
            elif st == 'in-progress':
                prog += 1
            else:
                gap += 1
            for rk in q.get('role_keys', []):
                per_role[rk] = per_role.get(rk, 0) + 1
    return {'total': total, 'today': today, 'in_progress': prog, 'gap': gap,
            'per_role': per_role}


def library():
    """The full payload the UI needs to render the visible, role-filtered library:
    themes with their questions, the role list (with per-role counts), the gaps,
    and headline counts. Bundled sample answers are NOT sent to the browser (the
    live answer comes from the model); only q/grounds/status/role_keys go out."""
    c = _counts()
    role_list = []
    for r in roles():
        rr = dict(r)
        rr['count'] = c['per_role'].get(r['key'], 0)
        role_list.append(rr)
    themes = []
    for t in load().get('catalog', []):
        qs = [{
            'q': q.get('q'),
            'grounds': q.get('grounds'),
            'status': q.get('status'),
            'role_keys': q.get('role_keys', []),
        } for q in t.get('questions', [])]
        themes.append({'theme': t.get('theme'), 'blurb': t.get('blurb', ''), 'questions': qs})
    return {
        'themes': themes,
        'roles': role_list,
        'gaps': gaps(),
        'counts': {k: c[k] for k in ('total', 'today', 'in_progress', 'gap')},
    }


def find(question_text):
    """Return the full catalogue entry (incl. bundled sample answer) for an exact
    question, or None. Used for the pre-brain fallback answer."""
    if not question_text:
        return None
    qn = ' '.join(question_text.split()).strip().lower()
    for t in load().get('catalog', []):
        for q in t.get('questions', []):
            if ' '.join((q.get('q') or '').split()).strip().lower() == qn:
                return q
    return None
