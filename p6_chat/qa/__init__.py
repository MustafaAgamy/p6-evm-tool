"""The offline question-answer engine: maps a library question id to a grounded,
senior-planning-engineer answer, with NO AI model needed.

Each theme module ``t00.py`` … ``t16.py`` exports ``ANSWERS = {question_id: fn(F, role)}``
where ``F`` is the grounded FACTS dict (``p6_chat.facts.build_facts``) and ``role`` is
'management' or 'planning'. This package discovers those modules, builds one registry, and
exposes ``answer(qid, F, role)``. A question with no registered function returns None so
the caller can fall back (to the Copilot capability engines or an honest message).
"""
from importlib import import_module

from . import _kit

_THEME_MODULES = [f't{i:02d}' for i in range(17)]

_REGISTRY = {}
_LOAD_ERRORS = {}


def _load():
    for name in _THEME_MODULES:
        if name in _LOAD_ERRORS or any(k.startswith(name[1:3]) for k in _REGISTRY):
            pass
        try:
            mod = import_module(f'{__name__}.{name}')
            got = getattr(mod, 'ANSWERS', {}) or {}
            if isinstance(got, dict):
                _REGISTRY.update(got)
        except Exception as exc:                     # a broken theme module must not sink the rest
            _LOAD_ERRORS[name] = str(exc)


_load()


def has(qid):
    return qid in _REGISTRY


def registered_ids():
    return set(_REGISTRY.keys())


def load_errors():
    return dict(_LOAD_ERRORS)


def answer(qid, F, role='management'):
    """The grounded answer dict for ``qid``, or None if no function is registered.
    Never raises — a failing answer function degrades to an honest note."""
    fn = _REGISTRY.get(qid)
    if not fn:
        return None
    try:
        out = fn(F, role)
        return out if isinstance(out, dict) and out.get('headline') else None
    except Exception as exc:
        return _kit.A(
            "I hit a snag composing that answer.",
            body=["The underlying numbers are in the project — please try another question, "
                  "or open the matching feature directly."],
            evidence=[_kit.ev('Engine', 'Detail', str(exc)[:80])])
