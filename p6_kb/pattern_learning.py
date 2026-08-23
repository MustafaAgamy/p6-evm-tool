"""Planning Knowledge Engine — a continuously growing, project-aware learning layer
beside the curated Knowledge Base.

The model (Ibrahim, binding):
    Curated Industrial KB  = day-1 knowledge (always the baseline)
  + real project XER imports = continuous learning (large, detailed schedules)
  → cross-project patterns = growing intelligence, with provenance
  → current XER evidence   = the ONLY basis for a constructability finding

TWO LEVELS:
  1. Raw Project Knowledge — the original XER stays available/downloadable (handled by
     the schedule cache + the KB raw store); this module owns level 2.
  2. Learned / Generalized Knowledge — from every imported project this engine extracts
     RICH, MULTI-LEVEL generalized sequencing patterns and their occurrence frequency:
       • sysphase   — (system, phase) → (system, phase) with relationship type
       • system     — system → system  (cross-system interface order)
       • discipline — discipline → discipline (e.g. CIVIL→STRUCT→MECH→COMMISSIONING)
       • phase      — phase → phase (e.g. DESIGN→PROCUREMENT, ERECTION→TESTING; the EPC
                       and install→test→commission chains)
     Provenance is kept per pattern (which projects, hence how many — support strength),
     plus how often it occurs within a project (richness). Deduped by P6 project id so a
     re-import never inflates support/confidence.

Never stores activity names, WBS text, or project IDs as reusable rules — only the
generalized concept. A large 10,000-activity schedule is COMPRESSED into a bounded
pattern signature, not copied.

**Supporting intelligence only.** This layer NEVER raises, removes, reorders or re-grades
a finding — that is decided solely by the current XER's own logic. It only annotates a
finding with cross-project corroboration. The R1–R7 validation gate is untouched.

Storage: ``%APPDATA%/P6EVMTool/learned_patterns.json`` (per-user, private, offline).
"""
import json
import os
import re
from collections import Counter

from utils import app_data_dir

_STORE_VERSION = 2
_LEVELS = ('sysphase', 'system', 'discipline', 'phase')

# per-level key validators — enforce the generalized concept format (no spaces, bounded
# length) so raw activity/WBS text can never enter the reusable knowledge on import.
_KEY_RX = {
    'sysphase':   re.compile(r'^[a-z_*]{1,40}:[A-Z_*]{1,40}>[a-z_*]{1,40}:[A-Z_*]{1,40}:[A-Z]{2}$'),
    'system':     re.compile(r'^[a-z_]{1,40}>[a-z_]{1,40}:[A-Z]{2}$'),
    'discipline': re.compile(r'^[A-Z_]{1,40}>[A-Z_]{1,40}:[A-Z]{2}$'),
    'phase':      re.compile(r'^[A-Z_]{1,40}>[A-Z_]{1,40}:[A-Z]{2}$'),
}


def store_path(base=None):
    return os.path.join(base or app_data_dir(), 'learned_patterns.json')


# ── Level 1: Raw Project Knowledge — the original XERs kept, listable, downloadable ──

def raw_dir(base=None):
    return os.path.join(base or app_data_dir(), 'knowledge_raw')


def _safe_name(name):
    keep = ''.join(c if (c.isalnum() or c in ' _-.') else '_' for c in (name or 'project'))
    return keep.strip().replace(' ', '_')[:80] or 'project'


def store_raw(src_path, project_id='', label='', file_hash='', base=None):
    """Keep the original contributing XER/XML so the user can download it later (level 1
    backup). Deduped by file hash — the same project file is never stored twice."""
    import shutil
    d = raw_dir(base)
    os.makedirs(d, exist_ok=True)
    stamp = (file_hash or str(project_id) or _safe_name(label))[:12]
    ext = os.path.splitext(src_path)[1].lower() or '.xml'
    dst = os.path.join(d, f'{stamp}_{_safe_name(label or os.path.basename(src_path))}{ext}')
    for existing in os.listdir(d):                       # dedup by the hash/id stamp prefix
        if existing.startswith(f'{stamp}_'):
            return os.path.join(d, existing)
    try:
        shutil.copy2(src_path, dst)
    except OSError:
        return None
    return dst


def list_raw(base=None):
    """The raw project files the KB has kept: {filename, label, size}."""
    d = raw_dir(base)
    out = []
    if os.path.isdir(d):
        for fn in sorted(os.listdir(d)):
            p = os.path.join(d, fn)
            if os.path.isfile(p):
                label = fn.split('_', 1)[1] if '_' in fn else fn
                out.append({'filename': fn, 'label': label, 'size': os.path.getsize(p)})
    return out


def raw_file_path(filename, base=None):
    """Resolve a raw file for download, guarding against path traversal."""
    d = raw_dir(base)
    p = os.path.abspath(os.path.join(d, os.path.basename(filename or '')))
    return p if p.startswith(os.path.abspath(d)) and os.path.isfile(p) else None


def _sys(a):
    return (a.get('identity') or {}).get('system')


def _phase(a):
    return (a.get('identity') or {}).get('phase')


def _disc(a):
    return (a.get('identity') or {}).get('discipline')


def _valid_key(level, key):
    rx = _KEY_RX.get(level)
    return isinstance(key, str) and bool(rx and rx.match(key))


def extract(view):
    """Multi-level generalized patterns (with per-project occurrence counts) from a tagged
    schedule. Returns {systems, disciplines, levels:{level:{key:count}}}. Concept only —
    no names/WBS/ids."""
    by_oid = view.get('by_oid', {})
    acts = view.get('activities_oid', [])
    systems = sorted({s for s in (_sys(a) for a in acts) if s})
    disciplines = sorted({d for d in (_disc(a) for a in acts) if d})
    levels = {lv: Counter() for lv in _LEVELS}
    for r in view.get('relationships_oid', []):
        pa, sa = by_oid.get(r['pred_oid'], {}), by_oid.get(r['succ_oid'], {})
        if not pa or not sa:
            continue
        rt = (r.get('type') or 'FS')
        psys, pph, pd = _sys(pa), _phase(pa), _disc(pa)
        ssys, sph, sd = _sys(sa), _phase(sa), _disc(sa)
        if (psys or pph) and (ssys or sph):
            levels['sysphase'][f"{psys or '*'}:{pph or '*'}>{ssys or '*'}:{sph or '*'}:{rt}"] += 1
        if psys and ssys and psys != ssys:
            levels['system'][f"{psys}>{ssys}:{rt}"] += 1
        if pd and sd and pd != sd:
            levels['discipline'][f"{pd}>{sd}:{rt}"] += 1
        if pph and sph and pph != sph:
            levels['phase'][f"{pph}>{sph}:{rt}"] += 1
    return {'systems': systems, 'disciplines': disciplines,
            'levels': {lv: dict(c) for lv, c in levels.items()}}


# ── store ────────────────────────────────────────────────────────────────────

def load_store(base=None):
    try:
        with open(store_path(base), encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get('projects'), dict):
            return _migrate(data)
    except (OSError, ValueError):
        pass
    return {'version': _STORE_VERSION, 'projects': {}}


def _migrate(store):
    """Bring a v1 store (flat 'transitions' list) up to the v2 multi-level shape so an
    existing knowledge base is never lost."""
    for _pid, rec in (store.get('projects') or {}).items():
        if 'levels' not in rec and isinstance(rec.get('transitions'), list):
            rec['levels'] = {'sysphase': {t: 1 for t in rec.pop('transitions')},
                             'system': {}, 'discipline': {}, 'phase': {}}
            rec.setdefault('disciplines', [])
    store['version'] = _STORE_VERSION
    return store


def _save_store(store, base=None):
    path = store_path(base)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(store, f, ensure_ascii=False, indent=0)


def learn_from_view(view, project_id, project_type='', label='', file_hash='', base=None, store=None):
    """Fold one imported schedule's multi-level patterns into the store under its P6
    project id (deduped — a re-import of the same project REPLACES its entry, never
    inflates support/confidence). Concept only; no activity/WBS text stored."""
    owns = store is None
    store = store if store is not None else load_store(base)
    ex = extract(view)
    key = str(project_id or '').strip() or f'anon:{len(store["projects"])}'
    store['projects'][key] = {'label': str(label or '')[:120], 'type': str(project_type or '')[:80],
                              'hash': str(file_hash or ''), 'systems': ex['systems'],
                              'disciplines': ex['disciplines'], 'levels': ex['levels']}
    if owns:
        _save_store(store, base)
    return store


def save(store, base=None):
    _save_store(store, base)


def project_count(store):
    return len(store.get('projects') or {})


def _index(store):
    """Derived indexes per level: {level: {key: set(project_ids)}}, plus occurrence totals
    and a system-presence index."""
    idx = {lv: {} for lv in _LEVELS}
    occ = {lv: Counter() for lv in _LEVELS}
    sysp = {}
    for pid, rec in (store.get('projects') or {}).items():
        for lv in _LEVELS:
            for k, n in (rec.get('levels', {}).get(lv, {}) or {}).items():
                idx[lv].setdefault(k, set()).add(pid)
                occ[lv][k] += n
        for s in rec.get('systems', []):
            sysp.setdefault(s, set()).add(pid)
    return {'idx': idx, 'occ': occ, 'systems': sysp}


# ── annotation (supporting only — never changes whether a finding fires) ──────

def _wild(idx_level, stem):
    """Distinct projects supporting a key whose relationship type is wildcarded."""
    out = set()
    for k, pids in idx_level.items():
        if k.startswith(stem):
            out |= pids
    return out


def _finding_support(finding, index):
    """Graded cross-project corroboration for the finding's EXPECTED (correct) sequence,
    drawn from the richest level that matches: sysphase → system → phase → system-
    presence. Returns (distinct_projects, level)."""
    idx = index['idx']
    if finding.get('kind') == 'out_of_sequence':
        p6 = finding.get('p6') or []
        if len(p6) >= 2:
            wp, ws = p6[0], p6[1]            # wrong pred, wrong succ → correct is succ→pred
            ssys, sph = ws.get('system'), ws.get('phase')
            psys, pph = wp.get('system'), wp.get('phase')
            if ssys and sph and psys and pph:
                pids = _wild(idx['sysphase'], f"{ssys}:{sph}>{psys}:{pph}:")
                if pids:
                    return len(pids), 'system + phase sequence'
            if ssys and psys and ssys != psys:
                pids = _wild(idx['system'], f"{ssys}>{psys}:")
                if pids:
                    return len(pids), 'system interface'
            if sph and pph and sph != pph:
                pids = _wild(idx['phase'], f"{sph}>{pph}:")
                if pids:
                    return len(pids), 'construction-phase sequence'
    return len(index['systems'].get(finding.get('system'), set())), 'system presence'


def annotate_findings(findings, base=None, store=None):
    """Attach cross-project support to each finding — SUPPORTING context only. Never adds,
    drops, reorders or re-grades a finding. Each finding gains ``support``:
        {curated: True, learned_projects: N, level, total_projects, label}."""
    store = store if store is not None else load_store(base)
    index = _index(store)
    total = project_count(store)
    for f in findings:
        n, level = _finding_support(f, index)
        if n and total:
            label = (f"KB standard, corroborated by {n} of your imported "
                     f"project{'s' if n != 1 else ''} ({level})")
        else:
            label = "KB standard (no corroborating imports yet)"
        f['support'] = {'curated': True, 'learned_projects': n, 'level': level,
                        'total_projects': total, 'label': label}
    return findings


# ── export / import (user-extensible knowledge) ──────────────────────────────

_KNOWLEDGE_FORMAT = 'constructability-knowledge'


def _clean_levels(levels):
    """Keep only validly-generalized keys per level (drops anything raw-looking)."""
    out, dropped = {}, 0
    for lv in _LEVELS:
        kept = {}
        for k, n in (levels.get(lv, {}) or {}).items():
            if _valid_key(lv, k):
                kept[k] = int(n) if isinstance(n, (int, float)) else 1
            else:
                dropped += 1
        out[lv] = kept
    return out, dropped


def export_knowledge(base=None, store=None):
    """The full learned knowledge as a portable, project-agnostic package: multi-level
    generalized patterns + provenance only (never activity/WBS text). Downloaded for
    backup / transfer and re-importable to rebuild the KB anywhere."""
    store = store if store is not None else load_store(base)
    projects = {}
    for pid, rec in (store.get('projects') or {}).items():
        levels, _drop = _clean_levels(rec.get('levels', {}))
        projects[pid] = {'label': rec.get('label', ''), 'type': rec.get('type', ''),
                         'hash': rec.get('hash', ''), 'systems': list(rec.get('systems', [])),
                         'disciplines': list(rec.get('disciplines', [])), 'levels': levels}
    return {'format': _KNOWLEDGE_FORMAT, 'version': _STORE_VERSION,
            'projects_count': len(projects), 'projects': projects}


def import_knowledge(data, base=None, store=None):
    """Merge a knowledge package into the store. Deduped by project id (a project already
    present is refreshed, never double-counted → confidence never inflated). Every pattern
    is validated as a generalized concept; raw / malformed keys are dropped, never stored.
    Returns {imported, refreshed, skipped, total, dropped_patterns}."""
    if not isinstance(data, dict) or data.get('format') != _KNOWLEDGE_FORMAT:
        raise ValueError('not a constructability-knowledge file')
    owns = store is None
    store = store if store is not None else load_store(base)
    existing = store.setdefault('projects', {})
    imported = refreshed = skipped = dropped = 0
    for pid, rec in (data.get('projects') or {}).items():
        if not isinstance(rec, dict):
            skipped += 1
            continue
        levels, d = _clean_levels(rec.get('levels', {}))
        dropped += d
        if not any(levels.values()) and not rec.get('systems'):
            skipped += 1
            continue
        refreshed += 1 if pid in existing else 0
        imported += 0 if pid in existing else 1
        existing[pid] = {'label': str(rec.get('label', ''))[:120], 'type': str(rec.get('type', ''))[:80],
                         'hash': str(rec.get('hash', '')),
                         'systems': [str(s)[:40] for s in rec.get('systems', []) if isinstance(s, str)],
                         'disciplines': [str(s)[:40] for s in rec.get('disciplines', []) if isinstance(s, str)],
                         'levels': levels}
    if owns:
        _save_store(store, base)
    return {'imported': imported, 'refreshed': refreshed, 'skipped': skipped,
            'total': len(existing), 'dropped_patterns': dropped}


_LEVEL_LABEL = {'sysphase': 'system+phase sequence', 'system': 'system interface',
                'discipline': 'discipline sequence', 'phase': 'construction-phase sequence'}


def provenance(store=None, base=None, limit=250):
    """Which imported projects support each learned pattern, how strongly (distinct
    projects) and how richly (total occurrences) — the view that lets a user SEE the
    corroboration behind the knowledge. Patterns from all levels, most-supported first."""
    store = store if store is not None else load_store(base)
    index = _index(store)
    # provenance identity is the project label (its name) or, failing that, its id —
    # never the archetype 'type', which is shared across many projects.
    labels = {pid: (rec.get('label') or pid)
              for pid, rec in (store.get('projects') or {}).items()}
    rows = []
    for lv in _LEVELS:
        for key, pids in index['idx'][lv].items():
            rows.append({'level': _LEVEL_LABEL[lv], 'pattern': key, 'support': len(pids),
                         'occurrences': index['occ'][lv][key],
                         'projects': sorted({labels.get(p, p) for p in pids})})
    rows.sort(key=lambda r: (-r['support'], -r['occurrences'], r['pattern']))
    by_level = {_LEVEL_LABEL[lv]: len(index['idx'][lv]) for lv in _LEVELS}
    return {'projects_learned': project_count(store), 'patterns': rows[:limit],
            'pattern_count': sum(len(index['idx'][lv]) for lv in _LEVELS),
            'patterns_by_level': by_level}
