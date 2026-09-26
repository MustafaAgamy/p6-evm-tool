"""The 15 merged chat questions — each one comprehensive answer to what used to be several questions.

Each module ``q01.py`` … ``q15.py`` exports ``build(F, N, role) -> answer`` (see ``_kit2``), where F is the
grounded DB facts (``p6_chat.facts.build_facts``) and N is the network re-read from the P6 file
(``p6_chat.analysis.network``). The catalog (``p6_chat/data/questions_15.json``) holds each question's
wording, group, the topics it covers and the original library questions it answers.
"""
import json
import os
from importlib import import_module

from . import _kit2 as K2

IDS = [f'q{i:02d}' for i in range(1, 16)]
_BUILDERS, _ERRORS = {}, {}
for _qid in IDS:
    try:
        _BUILDERS[_qid] = getattr(import_module(f'{__name__}.{_qid}'), 'build')
    except Exception as exc:                    # a broken module must not sink the rest
        _ERRORS[_qid] = str(exc)

_CATALOG = None


def catalog():
    global _CATALOG
    if _CATALOG is None:
        try:
            from utils import resource_path
            path = resource_path(os.path.join('p6_chat', 'data', 'questions_15.json'))
        except Exception:
            path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'questions_15.json')
        with open(path, encoding='utf-8') as f:
            _CATALOG = json.load(f)
    return _CATALOG


def entry(qid):
    return next((q for q in catalog()['questions'] if q['id'] == qid), None)


def load_errors():
    return dict(_ERRORS)


def has(qid):
    return qid in _BUILDERS


def build(qid, F, N, role='planning'):
    """The merged answer for qid, or None when no builder is registered. Never raises."""
    fn = _BUILDERS.get(qid)
    if not fn:
        return None
    if not F.get('ok'):
        return K2.no_project()
    try:
        out = fn(F, N or {'ok': False}, role)
        return out if isinstance(out, dict) and out.get('verdict') else None
    except Exception as exc:
        return K2.A2("I hit a snag composing that answer.",
                     [K2.sec('What happened', "The numbers are in the project — try again, or open the matching "
                                              "feature directly. (" + str(exc)[:120] + ")")])
