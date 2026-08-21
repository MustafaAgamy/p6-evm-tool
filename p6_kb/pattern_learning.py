"""Cross-project constructability intelligence — a continuously growing, project-aware
learning layer that sits BESIDE the curated Knowledge Base.

The model (Ibrahim, binding):
    Curated Industrial KB  = day-1 knowledge (always the baseline)
  + User XER imports       = continuous real-project learning
  → Cross-project patterns = growing intelligence, with provenance
  → Current XER evidence   = the ONLY basis for a constructability finding

What it learns is the *concept*, never the wording: a generalized sequencing
transition between two (system, phase) states with a relationship type — e.g.
``piping:ERECTION_INSTALL → piping:TESTING (FS)`` or
``electrical_power:POWER_AVAILABLE → chilled_water:COMMISSIONING (FS)``. Activity
names, WBS text and project IDs are deliberately NOT stored: the tool learns the
relationship pattern, so ``Material Submittal → Approval → PO → Delivery`` is the same
concept whatever a given project called its activities.

Provenance is preserved per pattern: which projects it was observed in, and therefore
in how many (1 vs 5 vs 10). Support strength = distinct projects, deduped by P6 project
id so re-importing the same project never inflates it.

**Supporting intelligence only.** This layer NEVER raises, removes or changes whether an
R1–R7 finding fires — that is decided solely by the current XER's own logic. It only
annotates a finding with cross-project corroboration (curated baseline + N projects), so
a planner can see how well-established the expected sequence is. The R1–R7 validation
gate is untouched.

Storage: ``%APPDATA%/P6EVMTool/learned_patterns.json`` (per-user, private, offline).
"""
import json
import os


from utils import app_data_dir

_STORE_VERSION = 1


def store_path(base=None):
    return os.path.join(base or app_data_dir(), 'learned_patterns.json')


def _sys(a):
    return (a.get('identity') or {}).get('system') or '*'


def _phase(a):
    return (a.get('identity') or {}).get('phase') or '*'


def transition_key(psys, pphase, ssys, sphase, rtype):
    """A project-agnostic sequencing pattern: (system, phase) → (system, phase) [type].
    No names, no WBS, no IDs — the concept only."""
    return f"{psys}:{pphase}>{ssys}:{sphase}:{rtype or 'FS'}"


def generalized(view):
    """(systems, transitions) a schedule exhibits, in generalized concept space.
    systems: set of tagged system ids present. transitions: set of transition keys."""
    by_oid = view.get('by_oid', {})
    systems = {(a.get('identity') or {}).get('system')
               for a in view.get('activities_oid', [])} - {None}
    transitions = set()
    for r in view.get('relationships_oid', []):
        pa, sa = by_oid.get(r['pred_oid'], {}), by_oid.get(r['succ_oid'], {})
        if not pa or not sa:
            continue
        transitions.add(transition_key(_sys(pa), _phase(pa), _sys(sa), _phase(sa),
                                        r.get('type') or 'FS'))
    return systems, transitions


# ── store ────────────────────────────────────────────────────────────────────

def load_store(base=None):
    try:
        with open(store_path(base), encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get('projects'), dict):
            return data
    except (OSError, ValueError):
        pass
    return {'version': _STORE_VERSION, 'projects': {}}


def _save_store(store, base=None):
    path = store_path(base)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(store, f, ensure_ascii=False, indent=0)


def learn_from_view(view, project_id, project_type='', base=None, store=None):
    """Fold one imported schedule's generalized patterns into the store under its P6
    project id (deduped — a re-import of the same project replaces, never inflates).
    Returns the updated store. Learns the concept only; stores no activity/WBS text."""
    owns = store is None                      # if we loaded it, we persist it
    store = store if store is not None else load_store(base)
    systems, transitions = generalized(view)
    key = str(project_id or '').strip() or f'anon:{len(store["projects"])}'
    store['projects'][key] = {'type': project_type or '',
                              'systems': sorted(systems),
                              'transitions': sorted(transitions)}
    if owns:
        _save_store(store, base)
    return store


def save(store, base=None):
    _save_store(store, base)


def _index(store):
    """Derived indexes: transition_key → set(project_ids), system → set(project_ids)."""
    tx, sy = {}, {}
    for pid, rec in (store.get('projects') or {}).items():
        for t in rec.get('transitions', []):
            tx.setdefault(t, set()).add(pid)
        for s in rec.get('systems', []):
            sy.setdefault(s, set()).add(pid)
    return tx, sy


def project_count(store):
    return len(store.get('projects') or {})


# ── annotation (supporting only — never changes whether a finding fires) ──────

def _expected_transition(finding):
    """The CORRECT ordering the finding says is violated, as a generalized key with a
    wildcard relationship type. An out-of-sequence finding carries its P6 activities as
    [wrong-predecessor, wrong-successor] (the reversed link the rule found), so the
    correct order is simply the reverse — successor drives predecessor. Deliberately not
    phase-rank based: the pipe insulation-vs-hydrotest pair is ranked the wrong way round
    globally, which is exactly why R6 exists. Returns None for missing-interface /
    sequence-gap findings that carry no ordered pair (they fall back to system support)."""
    if finding.get('kind') != 'out_of_sequence':
        return None
    p6 = finding.get('p6') or []
    if len(p6) < 2:
        return None
    wrong_pred, wrong_succ = p6[0], p6[1]
    if not wrong_pred.get('phase') or not wrong_succ.get('phase'):
        return None
    return transition_key(wrong_succ.get('system') or '*', wrong_succ.get('phase'),
                          wrong_pred.get('system') or '*', wrong_pred.get('phase'), '*')


def _match_support(key_wild, tx_index):
    """Projects supporting a transition key whose relationship type is a wildcard '*'."""
    if not key_wild:
        return set()
    stem = key_wild.rsplit(':', 1)[0] + ':'      # drop the '*' type, match any type
    out = set()
    for k, pids in tx_index.items():
        if k.startswith(stem):
            out |= pids
    return out


def annotate_findings(findings, base=None, store=None):
    """Attach cross-project support to each finding — SUPPORTING context only. Never
    adds, drops or reorders findings. Each finding gains ``support``:
        {curated, learned_projects, total_projects, label}
    'curated' is always True (the expected sequence is KB-standard); 'learned_projects'
    is how many of the user's imported projects corroborate it; the current XER remains
    the sole evidence for the finding itself."""
    store = store if store is not None else load_store(base)
    tx_index, sy_index = _index(store)
    total = project_count(store)
    for f in findings:
        key = _expected_transition(f)
        pids = _match_support(key, tx_index) if key else sy_index.get(f.get('system'), set())
        n = len(pids)
        if n and total:
            label = (f"KB standard, corroborated by {n} of your imported "
                     f"project{'s' if n != 1 else ''}")
        else:
            label = "KB standard (no corroborating imports yet)"
        f['support'] = {'curated': True, 'learned_projects': n, 'total_projects': total,
                        'basis': 'transition' if key else 'system', 'label': label}
    return findings
