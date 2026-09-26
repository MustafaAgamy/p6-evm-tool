"""q12 — Constructability: does the logic make sense, what's missing, and is the WBS right?

Covers, for ANY project: the logic's bones (open ends, loops, leads, dangling, out-of-sequence, lags,
relationship types, float deeper than the finish), a construction-order read of the chain that sets the
finish, candidate missing construction/execution steps (commissioning, energisation, per-layer tests,
Knowledge-Base type items), safety hold-points and permits (an honest partial gap), whether the WBS is
sound for the project type, the KB reference sequence mapped to the file, a suggested WBS and the KB
starter baseline. Every name and number comes from F (stored audit + EVM) or N (the P6 file re-read);
the project type is read from the file's own WBS and activity names against the Knowledge Base.

The small chain helpers (``chain_steps``, ``chain_front``, ``short_name``, ``ids_text``) are reused by q13.
"""
import re
from collections import Counter, OrderedDict
from datetime import datetime

from . import _kit2 as K

# ── vocabulary (generic construction words, never project nouns) ─────────────────────────────────
COMM_WORDS = ('commission', 'pre-comm', 'precomm', 'no-load', 'no load', 'trial run', 'fill trial', 'performance test',
              'loop check', 'energis', 'energiz', 'taking over', 'taking-over', 'take over', 'handover', 'hand over',
              'punch', 'snag', 'sat ', 'site acceptance')
ENERGISE_WORDS = ('energis', 'energiz', 'power on', 'permanent power', 'power available', 'back-feed', 'backfeed')
ELEC_WORDS = ('cable', 'terminat', 'conduct', 'conduit', 'panel', 'mcc', 'switchgear', 'wiring', 'lighting', 'earthing')
ELEC_BRANCH = ('mcc', 'electric', 'substation', 'switchgear', 'power')
GATE_WORDS = ('test', 'inspection', 'survey', 'hold point', 'hold-point', 'sign-off', 'witness')
PERMIT_WORDS = ('permit', 'ptw', 'hot work', 'work at height', 'work-at-height', 'lifting plan', 'scaffold insp',
                'confined space', 'method statement')
HEIGHT_WORDS = OrderedDict([('roof', 'roof'), ('sheet', 'sheets'), ('cladding', 'cladding'), ('catwalk', 'catwalks'),
                            ('scaffold', 'scaffolding'), ('section', 'steel sections'), ('erection', 'steel erection'),
                            ('tower', 'towers'), ('lift', 'lifts')])
INSTALL_WBS = ('mechanical', 'installation', 'erection', 'steel structure', 'equipment', 'cable')
SEA_WORDS = ('quay', 'port', 'harbour', 'harbor', 'coast', 'sea', 'offshore', 'wharf', 'dock', 'marina')  # used by q13
MILESTONE_BRANCH = ('milestone', 'key date')

# civil build order: (rank, keywords) — checked in THIS order (fill layers before slabs, so "soil replacement
# under the SOG" reads as fill, and "insulation between PC & RC SOG" as slab)
_CIVIL_RANK = [(4, ('soil replac', 'backfill', 'compaction', 'sub-base', 'subbase', 'sub base')),
               (5, ('sog', 'slab', 'raft', 'ring beam', 'fiber concrete', 'fibre concrete', 'deck', 'shuttering',
                    'embedded', 'screed', 'topping')),
               (3, ('column', 'footing', 'pile cap', 'foundation', 'grade beam', 'plinth', 'pedestal', 'tie beam')),
               (2, ('excavat', 'pile head', 'pile test', 'loading test', 'load test', 'blinding', 'lean concrete')),
               (1, ('drilling for pile', 'piling', 'bored pile', 'driven pile', 'drilling'))]

# phase-name token → extra words that find that phase in a real file (KB keywords are thin)
_PHASE_SYN = {'civil': ('excavat', 'pile', 'raft', 'footing', 'column', 'soil', 'backfill', 'slab', 'sog', 'concrete'),
              'foundation': ('excavat', 'pile', 'raft', 'footing', 'pile cap'),
              'structure': ('erection', 'roof', 'sheet', 'frame'),
              'convey': ('conveyor', 'roller', 'elevator', 'sections assembly', 'handling'),
              'handling': ('conveyor', 'roller', 'elevator'),
              'electric': ELEC_WORDS + ('sensor', 'motor'),
              'automation': ('sensor', 'plc', 'scada', 'instrument'),
              'ventilat': ('fan', 'hvac', 'ductwork'),
              'mechanical': ('install', 'erection', 'equipment'),
              'steel': ('steel', 'erection', 'catwalk', 'bolting')}
# phase-name token → the gate a construction reviewer expects at that step
_GATES = [(('client', 'input', 'release'), 'Approvals, area release, free-issue items'),
          (('pil',), 'Pile load test — hold point'),
          (('civil', 'foundation', 'substructure'), 'Pile / formation tests; concrete strength before load'),
          (('excavat', 'earth'), 'Formation and compaction test per layer'),
          (('roof', 'envelope', 'cladding', 'facade'), 'Water-tightness test'),
          (('structure', 'frame', 'slipform'), 'Structural sign-off / strength before loading'),
          (('convey', 'handling', 'mechanical', 'equipment'), 'Alignment, then no-load run'),
          (('aeration', 'ventilat', 'hvac'), 'Air-flow / balancing test'),
          (('electric', 'automation', 'cable', 'instrument'), 'Terminations, IR and loop checks complete'),
          (('test', 'commission'), 'No-load, then load runs / trials'),
          (('handover', 'taking'), 'Taking-Over')]


# ── small helpers ─────────────────────────────────────────────────────────────────────────────────
def _dt(s):
    try:
        return datetime.strptime(s, '%d-%b-%Y')
    except Exception:
        return None


def _has(text, words):
    t = (text or '').lower()
    return any(w in t for w in words)


def _kp(F, mod):
    return (((F.get('audit') or {}).get(mod) or {}).get('kpis')) or {}


def _n(v):
    return '—' if v is None else f"{v:,}"


_WORDS = ('zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten')


def num_word(n, cap=False):
    """Small counts in running prose read as words, the way a person writes them: 7 -> 'seven', 12 -> '12'.
    Tables, pills and evidence keep digits; this is for sentences only."""
    s = _WORDS[n] if isinstance(n, int) and 1 <= n <= 10 else (f"{n:,}" if isinstance(n, int) else str(n))
    return _cap(s) if cap else s


def _p1(v):
    """1-dp percent without trailing .0 noise: 1.4 -> '1.4%', 0.0 -> '0%'."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return '—'
    return f"{v:.1f}".rstrip('0').rstrip('.') + '%'


def _clean(name):
    n = re.sub(r'\s*@\s*L\s*=\s*[+\-]?[\d.]+', '', name or '')
    return re.sub(r'\s+', ' ', n).strip(' -')


def _cap(s):
    return s[:1].upper() + s[1:] if s else s


def short_name(name, words=None):
    """A readable short form of an activity name for running text (full names stay in tables)."""
    s = re.sub(r'\s+', ' ', name or '').strip()
    s = re.sub(r'^(get the|delivery for|delivery of)\s+', '', s, flags=re.I)
    s = re.sub(r'\s+from (the )?(client|employer|owner)\b', '', s, flags=re.I)
    m = re.search(r'\s+to start\s+', s, re.I)
    if m:
        pre, post = s[:m.start()], s[m.end():]
        if len(pre.split()) >= 2 and not pre.lower().startswith('approval'):
            s = pre
        else:
            s = pre + ' to start ' + ' '.join(post.split()[:2])
    s = re.sub(r'\s+before the\b.*$', '', s, flags=re.I)
    if words and len(s.split()) > words:
        s = ' '.join(s.split()[:words]) + '…'
    return _cap(s)


def ids_text(ids):
    """'A.B.1060 / 1090 / 1100' when ids share a prefix up to the last dot, else joined with ' / '."""
    ids = [i for i in ids if i]
    if len(ids) < 2:
        return ids[0] if ids else ''
    pre = ids[0].rsplit('.', 1)[0] + '.' if '.' in ids[0] else None
    if pre and all(i.startswith(pre) for i in ids):
        return ids[0] + ' / ' + ' / '.join(i[len(pre):] for i in ids[1:])
    return ' / '.join(ids)


def chain_front(rows):
    """The work front a chain runs through: its most common WBS segment below level 1, plus the areas under it.
    Returns (label, dominant_segment) — e.g. ('Zone 2 (Block A, Block B)', 'Zone 2') — or ('', '')."""
    rows = [x for x in rows if 'Milestone' not in (x.get('type') or '') and x.get('wbs')]
    if not rows:
        return '', ''
    seg = Counter()
    for x in rows:
        for p in dict.fromkeys((x['wbs'].split(' / '))[1:]):
            seg[p] += 1
    best, n = max(seg.items(), key=lambda kv: (kv[1], -len(kv[0])))
    if n < 0.5 * len(rows):
        best = Counter(x['wbs'].split(' / ')[1] for x in rows if len(x['wbs'].split(' / ')) > 1).most_common(1)
        best = best[0][0] if best else ''
    leaves = []
    for x in rows:
        parts = x['wbs'].split(' / ')
        if best in parts:
            i = parts.index(best)
            if i + 1 < len(parts) and parts[i + 1] not in leaves:
                leaves.append(parts[i + 1])
    leaves = [lf for lf in leaves if len(lf) <= 24][:3]
    return (f"{best} ({', '.join(leaves)})" if leaves else best), best


def chain_steps(rows, limit=12):
    """The chain's work in date order as readable steps: consecutive operations on one element merged
    ('Columns (RFT, FW, Concrete Pouring)'), ordinal layers collapsed ('Soil Replacement (4 layers)').
    Returns (steps, remaining_rows)."""
    steps, used = [], 0
    for x in rows:
        if 'Milestone' in (x.get('type') or ''):
            continue
        n = _clean(x.get('name'))
        unit = None
        m = re.match(r'(\d+)(?:st|nd|rd|th)\s+(\w+)\s+(.+)$', n, re.I)
        if m:
            unit, n = m.group(2).lower(), m.group(3)
        op, key = None, n
        m = re.match(r'(.{2,40}?)\s+(?:for|of)\s+(.+)$', n, re.I)
        if m and len(m.group(1).split()) <= 4:
            op, key = m.group(1).strip(), m.group(2).strip()
        k = key.lower().rstrip('s')
        if steps and steps[-1]['k'] == k:
            s = steps[-1]
            if op and op not in s['ops']:
                s['ops'].append(op)
            if unit:
                s['n'] += 1
        else:
            if len(steps) >= limit:
                break
            steps.append({'k': k, 'key': key, 'full': n, 'ops': [op] if op else [], 'n': 1 if unit else 0, 'unit': unit})
        used += 1
    out = []
    for s in steps:
        if len(s['ops']) >= 2:
            out.append(f"{s['key']} ({', '.join(s['ops'])})")
        elif s['unit'] and s['n'] >= 2:
            out.append(f"{s['full']} ({s['n']} {s['unit']}s)")
        else:
            out.append(s['full'])
    rest = [x for x in rows if 'Milestone' not in (x.get('type') or '')][used:]
    return out, rest


_AREA = re.compile(r'^(phase|area|zone|block|sector|level|building|plot|stage)\b', re.I)
NON_CONSTRUCTION = ('design', 'engineering', 'procurement', 'submittal', 'submital', 'shop drawing', 'input',
                    'client', 'employer', 'milestone', 'key date', 'as-built', 'as built')


def _trade(x):
    parts = (x.get('wbs') or '').split(' / ')
    return ' / '.join(parts[1:3]) if len(parts) > 1 else (x.get('wbs') or '')


def trade_name(x):
    """The trade a row belongs to: its level-2/3 WBS segment that isn't an area ('Civil Works', not 'Phase C')."""
    parts = [p for p in (x.get('wbs') or '').split(' / ')[1:3] if p]
    named = [p for p in parts if not _AREA.match(p)]
    return (named[-1] if named else (parts[0] if parts else ''))


def _is_area(seg):
    return bool(_AREA.match(seg or '') or re.search(r'\d', seg or ''))


def _civil_rank(name):
    t = (name or '').lower()
    for r, words in _CIVIL_RANK:
        if any(w in t for w in words):
            return r
    return None


def sequence_flags(rows):
    """Civil build-order check on each front of the chain: a step finishing AFTER a step that physically
    follows it (e.g. pile tests after the columns on them). Returns (checked_count, flags[(late, early)])."""
    groups = {}
    for x in rows:
        if 'Milestone' in (x.get('type') or '') or not _dt(x.get('finish')):
            continue
        if not _has(x.get('wbs'), ('civil', 'foundation', 'substructure')):
            continue
        r = _civil_rank(x.get('name'))
        if r is not None:
            groups.setdefault(x.get('wbs'), []).append((x, r))
    flags, checked = [], 0
    for items in groups.values():
        items.sort(key=lambda t: _dt(t[0]['finish']))
        checked += len(items)
        for j in range(len(items)):
            for i in range(j):
                a, ra = items[i]
                b, rb = items[j]
                if rb < ra and _dt(b['finish']) > _dt(a['finish']):
                    flags.append((b, a))
                    break
    return checked, flags


def _oos_concentration(text):
    m = re.search(r'concentrated in the (.+?) package \((\d+) of (\d+)', text or '', re.I)
    return (m.group(1), int(m.group(2)), int(m.group(3))) if m else None


def detect_type(N):
    """Best-fit Knowledge Base project type from the file's own activity + WBS names — weighted by how many
    activities each type's signatures cover (the WBS says what is being built; a project name can mislead)."""
    acts = ((N or {}).get('kb_view') or {}).get('activities') or []
    if not acts:
        return None
    try:
        from p6_kb.kb import load_kb
        entries = load_kb() or []
    except Exception:
        return None
    # A WBS node carried by (nearly) every activity is the project / facility name, not what is being built —
    # one word in it ('terminal', 'bulk') would otherwise match every row and outvote the real scope.
    paths = [(a.get('wbs_path') or '').split(' / ') for a in acts]
    seg_n = Counter(s for p in paths for s in set(p) if s)
    common = {s for s, c in seg_n.items() if c >= 0.9 * len(acts)} if len(acts) >= 20 else set()
    texts = [((a.get('name') or '') + ' | ' + ' / '.join(s for s in p if s not in common)).lower()
             for a, p in zip(acts, paths)]
    blob = '\n'.join(texts)
    cover = {}
    scored = []
    for e in entries:
        sigs = [s.lower() for s in (e.get('signatures') or []) if s and s.lower() in blob]
        if not sigs:
            continue
        rows, hit = set(), set()
        for s in sigs:
            if s not in cover:
                p = re.compile(r'\b' + re.escape(s))
                cover[s] = {i for i, t in enumerate(texts) if p.search(t)}
            if cover[s]:
                rows |= cover[s]
                hit.add(s)
        if rows:
            scored.append((len(rows) * (1 + 0.1 * len(hit)), len(rows), sorted(hit), e))
    if not scored:
        return None
    scored.sort(key=lambda t: -t[0])
    top = scored[0]
    run = scored[1] if len(scored) > 1 else None
    return {'entry': top[3], 'type': top[3].get('type'), 'category': top[3].get('category'), 'cover': top[1],
            'hits': top[2], 'n_types': len(entries), 'runner': run[3].get('type') if run else None,
            'confident': (not run) or top[0] >= 1.15 * run[0], 'draft': (top[3].get('status') == 'draft')}


def _phase_words(ph):
    words = [k.lower() for k in (ph.get('keywords') or [])]
    nm = (ph.get('name') or '').lower()
    for tok, syn in _PHASE_SYN.items():
        if tok in nm:
            words += list(syn)
    return tuple(dict.fromkeys(words))


def _gate(phase_name):
    nm = (phase_name or '').lower()
    for toks, g in _GATES:
        if any(t in nm for t in toks):
            return g
    return '—'


def _assign(name, phases, wbs=''):
    """Which KB phase an activity belongs to. A civil / foundation WBS decides it outright; otherwise the
    longest keyword evidence in the name wins (ties → the earlier phase)."""
    t = (name or '').lower()
    if _has(wbs, ('civil', 'foundation', 'substructure')):
        for i, (ph, _) in enumerate(phases):
            if _has(ph.get('name'), ('civil', 'foundation', 'substructure')):
                return i
    best, score = None, 0
    for i, (ph, words) in enumerate(phases):
        s = sum(len(w) for w in words if w in t)
        if s > score:
            best, score = i, s
    return best


def file_activities(N):
    """The file's activities (whitespace-normalised) and the construction / execution ones among them — design,
    procurement, client inputs and milestones don't prove a construction step is in the programme."""
    acts = [{'name': re.sub(r'\s+', ' ', a.get('name') or '').strip(),
             'wbs_path': re.sub(r'[ \t]{2,}', ' ', a.get('wbs_path') or '')}
            for a in (((N or {}).get('kb_view') or {}).get('activities') or [])]
    cacts = [a for a in acts if not _has(a['wbs_path'].split(' / ')[0] + ' / ' + a['name'], NON_CONSTRUCTION)]
    return acts, cacts


def kb_presence(entry, cacts):
    """The type's construction phases (testing / handover are read separately) and how many of your
    construction activities fall in each: ([(phase, words)], Counter{phase index: activities})."""
    kb_phases = [(ph, _phase_words(ph)) for ph in ((entry or {}).get('wbs') or [])
                 if not _has(ph.get('name'), ('test', 'commission', 'handover'))]
    kb_counts = Counter(_assign(a['name'], kb_phases, a['wbs_path']) for a in cacts) if kb_phases else Counter()
    return kb_phases, kb_counts


def commissioning_hits(cnames, N):
    """Construction activity and milestone names that carry a testing / commissioning / handover step."""
    return [n for n in list(cnames) + [x['name'] for x in ((N or {}).get('milestones') or [])] if _has(n + ' ', COMM_WORDS)]


# ── the answer ────────────────────────────────────────────────────────────────────────────────────
def build(F, N, role):
    nok = bool(N and N.get('ok'))
    d = F.get('delay_days')
    behind = (d or 0) > 0
    drv = K.main_driver(F)
    fin = (N.get('finish_milestone') or {}) if nok else {}
    fin_tf = N.get('finish_tf') if nok else None
    chain = list(N.get('chain') or []) if nok else []
    deep = list(N.get('deepest') or []) if nok else []
    tasks = [x for x in chain if 'Milestone' not in (x.get('type') or '')]
    acts, cacts = file_activities(N) if nok else ([], [])
    names = [a['name'] for a in acts]
    cnames = [a['name'] for a in cacts]
    n_acts = (N.get('activity_count') if nok else None) or F.get('activity_count')
    cal_n = F.get('calendar_count')
    thinking = []

    # ── the stored logic checks (only when this update actually has them) ───────────────────────────
    audited = bool(F.get('has_audit') or F.get('audit'))
    g = (lambda k: F.get(k)) if audited else (lambda k: None)
    oe, ci, le, dg = _kp(F, 'open_ends'), _kp(F, 'circular'), _kp(F, 'leads'), _kp(F, 'dangling')
    oo, lg, rt = _kp(F, 'out_of_sequence'), _kp(F, 'lag_lead'), _kp(F, 'relationship_types')
    open_ends = g('open_ends') if g('open_ends') is not None else oe.get('open_ends')
    loops = ci.get('loops')
    leads = le.get('leads') if le.get('leads') is not None else lg.get('leads_count')
    n_logic = dg.get('total_activities') or oo.get('total_activities') or oe.get('total_activities')
    n_rel = lg.get('total_relationships') or rt.get('total_relationships')
    dang, d_start, d_fin, d_both = (g('dangling_count'), dg.get('start_dangling'), dg.get('finish_dangling'),
                                    dg.get('both_dangling'))
    oos, crit_oos, oos_pct = g('oos_count'), g('critical_oos'), g('oos_pct')
    conc = _oos_concentration(oo.get('executive_conclusion'))
    lagged, lag_pct, lag_line = lg.get('lagged_count'), lg.get('lagged_pct'), lg.get('dcma_lag_line')
    long_lags, thr, lag_crit = lg.get('long_count'), lg.get('long_threshold_days'), lg.get('critical_count')
    by_type = [t for t in (lg.get('by_type') or []) if t.get('count')]
    nf_n, nf_pct = g('neg_float_count'), g('neg_float_pct')
    has_logic = any(v is not None for v in (open_ends, loops, leads, dang, oos, lagged))
    closed = (open_ends == 0 and not loops and not leads) if (open_ends is not None and loops is not None) else None
    if has_logic:
        thinking.append(f"Read the stored logic checks: {_n(n_rel)} relationships, {_n(lagged)} lags, "
                        f"{_n(dang)} dangling, {_n(oos)} out-of-sequence")
    else:
        thinking.append("Looked for a stored logic check (open ends, loops, leads, lags, out-of-sequence) — none is "
                        "stored for this update")

    # ── what the file holds ─────────────────────────────────────────────────────────────────────────
    front, front_seg = chain_front(chain) if chain else ('', '')
    steps, rest = chain_steps(chain) if chain else ([], [])
    checked, flags = sequence_flags(chain + deep) if chain else (0, [])
    install = sorted([x for x in tasks if _has(x.get('wbs'), INSTALL_WBS) and not _has(x.get('wbs'), ('civil',))],
                     key=lambda x: _dt(x['finish']) or datetime.max)
    survey = next((x for x in install if 'survey' in x['name'].lower()), None)
    first_inst = next((x for x in install if 'survey' not in x['name'].lower()), None)
    survey_gate = bool(survey and first_inst and _dt(survey['finish']) <= _dt(first_inst['finish']))
    comm_hits = commissioning_hits(cnames, N) if nok else []
    no_comm = nok and not comm_hits
    last_task = max(tasks, key=lambda x: _dt(x['finish']) or datetime.min) if tasks else None
    if chain:
        thinking.append(f"Read the {N.get('chain_count') or len(chain)}-activity chain that sets the finish in date order "
                        f"and checked {checked} civil steps against a standard build order")

    ktype = detect_type(N) if nok else None
    entry = (ktype or {}).get('entry') or {}
    tname = (ktype or {}).get('type')
    if ktype:
        thinking.append(f"Matched your WBS and activity names against {ktype['n_types']} Knowledge Base project types — "
                        f"best fit: {tname} ({ktype['cover']:,} activities covered)")
    # the type's construction phases (testing / handover are read separately) and how many of your
    # construction activities fall in each
    kb_phases, kb_counts = kb_presence(entry, cacts)

    # WBS tree from the file (level 1 → 2 → 3, activity counts)
    t1, t2, t3 = Counter(), Counter(), Counter()
    for a in acts:
        p = (a.get('wbs_path') or '').split(' / ')
        if p and p[0]:
            t1[p[0]] += 1
            if len(p) > 1:
                t2[(p[0], p[1])] += 1
            if len(p) > 2:
                t3[(p[0], p[1], p[2])] += 1
    discs = F.get('disciplines') or []
    dnames = {x['name'].lower(): x for x in discs}
    cbranch = None
    if nok and N.get('client_inputs'):
        cb = Counter((x.get('wbs') or '').split(' / ')[0] for x in N['client_inputs'] if x.get('wbs'))
        cbranch = next((b for b, _ in cb.most_common() if _has(b, ('client', 'employer', 'owner', 'input'))), None)
    main_l1 = None
    if drv and drv['name'] in t1:
        main_l1 = drv['name']
    elif t1:
        main_l1 = max((b for b in t1 if b.lower() in dnames), key=lambda b: t1[b], default=None)
    kids = sorted([(k[1], v) for k, v in t2.items() if k[0] == main_l1], key=lambda kv: -kv[1]) if main_l1 else []
    weights_l1 = bool(main_l1 and main_l1.lower() in dnames and len(kids) >= 2)
    main_w = round(((dnames.get((main_l1 or '').lower()) or {}).get('weight') or 0) * 100)
    if t1:
        thinking.append(f"Mapped the WBS: {len(t1)} level-1 branches, {len(t2)} level-2 branches"
                        + (f"; {main_l1} splits into {len(kids)}" if kids else ''))
    if not nok:
        thinking.append("Tried to re-read the P6 file for the sequence, missing-step and WBS checks — "
                        + ((N or {}).get('error') or 'file not found'))
        if discs:
            _top = max(discs, key=lambda x: x.get('weight') or 0)
            thinking.append(f"Read the stored EVM weights instead: {len(discs)} level-1 lines, led by {_top['name']} "
                            f"at {round((_top.get('weight') or 0) * 100)}%")

    # ── verdict ─────────────────────────────────────────────────────────────────────────────────────
    concerns = []
    if long_lags:
        concerns.append(f"{long_lags} long lags standing in for unmodelled work")
    if crit_oos:
        concerns.append(f"{crit_oos} critical out-of-sequence link{'s' if crit_oos != 1 else ''}")
    if no_comm and chain:
        concerns.append('a finish with no commissioning in it')
    if not concerns and dang:
        concerns.append(f"{dang} dangling activities")
    if closed:
        lead = 'The network is closed'
    elif closed is False:
        lead = (f"The network has {open_ends or 0} open end{'s' if open_ends != 1 else ''}, {loops or 0} loop"
                f"{'s' if loops != 1 else ''} and {leads or 0} lead{'s' if leads != 1 else ''} to close first")
    else:
        lead = "I have no stored logic check for this update"
    if chain and not flags:
        lead += f" and the {front_seg or 'finish-chain'} sequence makes construction sense"
    elif flags:
        lead += f", and {len(flags)} step{'s' if len(flags) != 1 else ''} on the finish chain read out of construction order"
    wbs_bit = ''
    if kids:
        wbs_bit = ("the WBS is sound, it just isn't weighted below level 1" if weights_l1 else "the WBS is sound")
    if not has_logic and not nok:
        top = max(F.get('disciplines') or [{}], key=lambda x: x.get('weight') or 0)
        head = ("I can't give you a constructability read on this update yet: there's no stored logic check and the "
                "schedule file couldn't be re-read"
                + (f". All I hold is the weighting — {top['name']} carries {round((top.get('weight') or 0) * 100)}% of the job"
                   if top.get('name') else '')
                + ". Re-import the file (and run the Schedule Audit) and I'll check the logic, the build sequence, the "
                  "missing steps and the WBS against your project type.")
    elif concerns:
        head = lead + ' — what needs a construction eye is ' + K2_join(concerns) + (f"; {wbs_bit}." if wbs_bit else '.')
    else:
        head = lead + (f"; {wbs_bit}." if wbs_bit else '.')
    if not nok and has_logic:
        head += " Re-import the file for the activity-level read (sequence, missing steps, WBS tree)."

    pills = [
        K.pill(f"{_n(open_ends)} open ends · {_n(loops)} loops · {_n(leads)} leads", 'success' if closed else 'warning')
        if closed is not None else None,
        (K.pill(f"{front_seg or 'Finish-chain'} sequence: construction-sound", 'success') if chain and not flags else
         K.pill(f"{len(flags)} sequence flag{'s' if len(flags) != 1 else ''} on the finish chain", 'warning') if flags else None),
        K.pill(f"{_n(dang)} dangling · {_n(oos)} out-of-sequence ({_n(crit_oos)} critical)",
               'warning' if (crit_oos or (dang or 0) > 0) else 'success') if (dang is not None or oos is not None) else None,
        K.pill(f"{_n(lagged)} lags · {_n(long_lags)} over {thr or 14} wd · {_n(lag_crit)} critical",
               'warning' if (lag_pct or 0) > (lag_line or 5) else 'neutral') if lagged is not None else None,
        K.pill(f"No commissioning before {fin.get('name') or 'the finish'}", 'warning') if no_comm and fin else None,
        K.pill('WBS sound · weighted only at level 1' if weights_l1 else 'WBS sound', 'neutral') if kids else None,
        K.pill(f"KB: {tname} sequence + starter XML", 'accent') if tname else None,
        K.pill('No logic check stored for this update', 'neutral') if not has_logic else None,
        K.pill('Schedule file not re-read', 'neutral') if not nok else None]

    # ── 1. the network's bones ──────────────────────────────────────────────────────────────────────
    s1 = []
    if not nok:
        s1.append(K.network_note(N))
    if has_logic:
        bold = (('The network is closed and loop-free — ' if closed else 'The network is not yet closed — ')
                + f"{_n(open_ends)} open ends, {_n(loops)} circular loops, {_n(leads)} leads"
                + (f" — and the {front_seg or 'finish-chain'} sequence reads in the right construction order." if chain and not flags
                   else (f" — but {len(flags)} step(s) on the finish chain read out of construction order." if flags else '.')))
        eye = []
        if lagged:
            eye.append(f"the lag load ({lagged:,} lags, {_n(long_lags)} over {thr or 14} working days, {_n(lag_crit)} on the critical path)")
        if oos:
            eye.append(f"{oos} out-of-sequence links ({_n(crit_oos)} critical" + (f", most of them in {conc[0]})" if conc else ')'))
        if dang:
            eye.append(f"{dang} dangling activities")
        if no_comm and chain:
            eye.append('a finish chain with no commissioning in it')
        if eye:
            bold += ' What needs a construction eye is ' + K2_join(eye) + '.'
        s1.append('**' + bold + '**')
        plain = [f"In plain terms: across the {_n(n_logic)} activities and {_n(n_rel)} relationships in the logic check"]
        if closed:
            plain[0] += (", every activity has a predecessor and a successor, nothing loops back on itself, and no link "
                         "carries a lead (a negative lag).")
        else:
            plain[0] += (f", {_n(open_ends)} activities lack a predecessor or successor, {_n(loops)} loops exist and "
                         f"{_n(leads)} links carry a lead — close those before anything else, they break the float read.")
        if dang is not None:
            size = 'small' if (g('dangling_pct') or 0) < 5 else 'material'
            plain.append(f"Dangling is {size} — {dang} activities ({_p1(g('dangling_pct'))}) where one end isn't properly tied"
                         + (f": {d_start} with a start nothing drives, {d_fin} with a finish that drives nothing, {d_both} both."
                            if d_start is not None else '.'))
        if oos is not None:
            txt = f"Out-of-sequence is {oos} ({_p1(oos_pct)}) — progress recorded before a predecessor finished."
            if conc:
                txt += f" {conc[1]} of the {conc[2]} sit in the {conc[0]} package"
                txt += (f", but {crit_oos} {'are' if crit_oos != 1 else 'is'} on the critical path, and "
                        f"{'those' if crit_oos != 1 else 'that'} touch{'es' if crit_oos == 1 else ''} the completion date directly."
                        if crit_oos else '.')
            elif crit_oos:
                txt += f" {crit_oos} of them sit on the critical path and touch the completion date directly."
            plain.append(txt)
        s1.append(' '.join(plain))
        if nf_n:
            s1.append(f"The slip itself is out in the open: {nf_n:,} activities ({_p1(nf_pct)}) carry negative float — the "
                      "logic is showing the lateness, not hiding it. That's a lateness signal, not a logic defect — but it's "
                      "why the few loose links matter"
                      + (f". On a path already at {fin_tf:+d} wd, a loose link is where more delay can hide." if fin_tf is not None and fin_tf < 0
                         else '.'))
    else:
        s1.append("There's no stored logic check for this update, so I can't give you open ends, loops, leads, lags or "
                  "out-of-sequence counts — and I won't guess them. Run the Schedule Audit on this file (it stores those "
                  "checks) and ask again; the constructability read builds on them.")
    sec1 = K.sec("The network's bones", *s1)

    # ── 2. relationships that don't make construction sense ─────────────────────────────────────────
    rows2 = []
    if long_lags:
        ex = []
        if any('shuttering' in x['name'].lower() or 'strik' in x['name'].lower() for x in chain + deep):
            el = next((re.split(r'\s+for\s+', _clean(x['name']), flags=re.I)[-1] for x in chain + deep
                       if 'shuttering' in x['name'].lower()), 'the formwork')
            ex.append(f"curing before striking the {el.lower()} props")
        elif not chain:
            ex.append('curing before striking formwork')
        if any(re.match(r'\d+(st|nd|rd|th)\s+layer', x['name'], re.I) for x in chain + deep) or not chain:
            ex.append('a test per fill layer')
        ex.append('an approval wait')
        rows2.append([f"Long lags (over {thr or 14} wd)",
                      f"{long_lags} of {_n(lagged)} lags; {_n(lag_crit)} lags sit on the critical path"
                      + ('; lags by type ' + ' · '.join(f"{t['type']} {t['count']}" for t in by_type) if by_type else ''),
                      f"A long lag is usually real work with no activity — {K2_join(ex)}. As dead time it can't be "
                      f"progressed, tracked or recovered. Each of the {long_lags} needs a written reason, or conversion to an activity."])
    if lag_pct is not None and lag_line:
        r = (lag_pct or 0) / lag_line
        times = (f"About {num_word(round(r))} times the guide." if r >= 1.5 else ('Over the guide.' if r > 1 else 'Within the guide.'))
        rows2.append(['Lag density', f"{_p1(lag_pct)} of relationships carry a lag (DCMA 14-point guide: {_p1(lag_line)})",
                      times + " On a repetitive job lags are often used to stagger crews front to front — legitimate, but it "
                      "should be movement logic you can explain, not a date fudge."])
    if leads:
        rows2.append(['Leads (negative lags)', f"{leads} links", "A lead lets a successor start before its driver finishes — "
                      "physically that's an overlap nobody can progress. Convert to SS with a positive lag."])
    if loops:
        rows2.append(['Circular logic', f"{loops} loop(s)", "A loop has no buildable order at all — it must be broken before any float is trusted."])
    if (rt.get('sf_pct') or 0) > 0:
        rows2.append(['Start-to-finish links', f"{_p1(rt.get('sf_pct'))} of relationships",
                      "SF almost never describes how work is built — check each one."])
    if crit_oos:
        rows2.append(['Out-of-sequence on the critical path',
                      f"{crit_oos} of {oos}" + (f" ({conc[1]} of the {conc[2]} are in {conc[0]})" if conc else ''),
                      "Work progressed ahead of its logic on the path to "
                      + (f"{fin.get('finish')}" if fin.get('finish') else 'completion')
                      + ". Either the logic is wrong (fix the link) or the site built it out of order (retained logic will "
                      "push the rest). Either way it changes the finish."])
    elif oos:
        rows2.append(['Out-of-sequence (none critical)', f"{oos}" + (f" ({conc[1]} in {conc[0]})" if conc else ''),
                      "Not on the path to the finish today — fix the links before the path moves onto them."])
    deeper = [x for x in deep if fin_tf is not None and x.get('tf') is not None and x['tf'] < fin_tf][:2]
    if deeper:
        def _lbl(x):
            leaf = (x.get('wbs') or '').split(' / ')[-1]
            nm = x['name'] + (f", {leaf}" if _is_area(leaf) and leaf.lower() not in x['name'].lower() else '')
            return f"{nm} ({x['id']}) {x['tf']:+d} wd"
        rows2.append(['Float deeper than the finish', '; '.join(_lbl(x) for x in deeper) + f" — against {fin_tf:+d} at the finish",
                      "Something downstream holds them tighter than the finish: an intermediate constraint, a sectional key "
                      "date or a calendar difference" + (f" (the file has {cal_n} calendars)" if cal_n else '')
                      + ". If it's a constraint, it's a date someone has promised — find it."])
    if d_both:
        rows2.append(['Dangling at both ends', f"{d_both} of the {dang}",
                      "Start not driven and finish drives nothing — it can move without consequence, so as it stands it "
                      "isn't really in the logic."])
    if open_ends:
        rows2.append(['Open ends', f"{open_ends} activities", "No predecessor or no successor — float on them is meaningless until tied in."])
    p2 = []
    if rows2 or chain:
        p2.append("I can't name a physically reversed link from the summary I hold, and I won't invent one — the Dangling, "
                  "Out-of-Sequence and Lag reports list your real links by name, with the reason and a suggested fix each."
                  + ((f" What {'the file does' if nok else 'the stored checks do'} show "
                      + (f"are {num_word(len(rows2))} patterns" if len(rows2) != 1 else 'is one pattern')
                      + " worth a construction read. None is an automatic fault; each is a place to ask 'is this how "
                        "we'll actually build it?'") if rows2 else ''))
    if steps:
        seq = ' → '.join(steps)
        if rest:
            trades = list(dict.fromkeys(trade_name(x) for x in rest if trade_name(x)))[:4]
            seq += (f" → then {len(rest)} more through {K2_join(trades)}, ending with "
                    f"{rest[-1]['name']} ({rest[-1]['id']})")
        if flags:
            fl = '; '.join(f"{b['name']} ({b['id']}) finishes {b['finish']}, after {a['name']} ({a['id']}, {a['finish']}), "
                           "which normally follows it" for b, a in flags[:3])
            p2.append(f"In date order, the finish chain runs: {seq}. Checked against a standard civil build order, "
                      f"{len(flags)} step(s) read out of order on the same front: {fl}. That's a question for the site "
                      "team, not a verdict — the link may be right and the dates wrong.")
        else:
            p2.append(f"The sequence itself holds up. In date order, the {front or 'finish-chain'} works on the finish chain "
                      f"run: {seq}. I checked the {checked} civil steps on each front against a standard build order (piling "
                      "→ excavation and pile tests → columns and foundations → fill layers → raft and slabs) and nothing "
                      "sits before a step it physically needs"
                      + (f"; installation starts after {survey['name']} ({survey['id']}), which is the right gate" if survey_gate else '')
                      + ". A construction reviewer would accept that order.")
    sec2 = K.sec("Relationships that don't make construction sense", *p2,
                 table=K.tbl(['What the file shows', 'Count / where', 'The construction question'], rows2,
                             note="Real — counts from the logic, lag and float checks on your file. The individual links "
                                  "are listed by name in the Dangling, Out-of-Sequence and Lag reports."))

    # ── 3. missing construction activities ──────────────────────────────────────────────────────────
    rows3, miss_bits = [], []
    fin_name, fin_id, fin_date = fin.get('name'), fin.get('id'), fin.get('finish')
    if nok and no_comm and last_task:
        same = bool(fin_date) and last_task.get('finish') == fin_date
        gap_days = ((_dt(fin_date) - _dt(last_task['finish'])).days if _dt(fin_date) and _dt(last_task.get('finish')) else None)
        lt = f"The last activity on the finish chain ({last_task['name']}, {last_task['id']})"
        if same:
            why = f"{lt} and {fin_name} both finish {fin_date} — no testing duration is in the forecast at all"
        elif gap_days is not None:
            why = (f"{lt} finishes {last_task['finish']}, {gap_days} days before {fin_name} ({fin_date}) — and nothing in "
                   "the file is named as testing")
        else:
            why = f"{lt} finishes {last_task['finish']} — and nothing in the file is named as testing or commissioning"
        fin_ref = fin_id or fin_name or 'completion'
        rows3.append(['Pre-commissioning — no-load runs, rotation and loop checks', why,
                      f"FS from {last_task['name']}, before {fin_ref} — if in your scope"])
        kb_comm = next((a for a in (entry.get('activities') or []) if _has(a.get('wbs', '') + ' ' + a.get('name', ''), ('commission', 'trial'))), None)
        eqp_late = [x for x in (N.get('client_inputs_late_done') or []) if _has(x['name'], ('equipment', 'accessor', 'material'))]
        rows3.append([(kb_comm.get('name') if kb_comm else 'Commissioning / performance trials'),
                      ((kb_comm.get('why') if kb_comm else 'Installed systems need a load run before handover').rstrip('. ')
                       + ('; with client-furnished equipment in the scope, who does what must be written down' if eqp_late else '')),
                      f"FS from pre-commissioning, before {fin_name or 'completion'}"])
        miss_bits.append('the commissioning tail')
    if nok and not any(_has(n, ENERGISE_WORDS) for n in names) and any(_has(n, ELEC_WORDS) for n in cnames):
        # the electrical branch of the construction works (e.g. an MCC room / substation), else any such branch
        cand = [(k, v) for k, v in t2.items() if _has(k[1], ELEC_BRANCH) and not _has(k[0], MILESTONE_BRANCH)]
        cand.sort(key=lambda kv: (kv[0][0] != main_l1, -kv[1]))
        eb = (cand[0][0][1], cand[0][1]) if cand else None
        ed = next((x for x in discs if _has(x['name'], ELEC_BRANCH) and (x.get('gap') or 0) > 0), None)
        util = next((a for a in acts if _has(a['name'] + ' ' + a['wbs_path'], ('electricity company', 'utility',
                                                                             'power company', 'grid connection'))), None)
        why = "Terminations can't be tested dead"
        if eb:
            why += f"; the {eb[0]} branch has only {eb[1]} activit{'ies' if eb[1] != 1 else 'y'}"
        if ed:
            why += f"{' and' if eb else ';'} {ed['name']} is {ed['actual']}% vs {ed['planned']}% planned"
        if util:
            uw = ('electricity company', 'utility', 'power company', 'grid connection')
            ut = util['name'] if _has(util['name'], uw) else util['wbs_path'].split(' / ')[-1]
            why += f". The file carries a utility approval ('{ut}') but no energisation activity after it"
        rows3.append([f"{eb[0] + ' energisation' if eb else 'Permanent power / energisation'} (power available for testing)",
                      why, 'Before pre-commissioning' + (f", tied into the {eb[0]} branch" if eb else '')])
    layer_rows = [x for x in chain + deep if re.match(r'\d+(st|nd|rd|th)\s+layer\s', _clean(x['name']) + ' ', re.I)]
    if layer_rows:
        by_leaf = {}
        for x in layer_rows:
            by_leaf.setdefault(x.get('wbs'), {})[x['id']] = x
        leaf, lr = max(by_leaf.items(), key=lambda kv: len(kv[1]))
        lr = sorted(lr.values(), key=lambda x: _dt(x['finish']) or datetime.max)
        tested = [x for x in chain + deep if x.get('wbs') == leaf and _has(x['name'], ('compaction', 'density', 'plate load', 'layer test'))]
        if len(lr) >= 2 and not tested:
            what = re.sub(r'^\d+(st|nd|rd|th)\s+layer\s+', '', _clean(lr[0]['name']), flags=re.I)
            gaps = [(_dt(b['finish']) - _dt(a['finish'])).days for a, b in zip(lr, lr[1:]) if _dt(a['finish']) and _dt(b['finish'])]
            area = (leaf or '').split(' / ')[-1]
            gtxt = (f", {min(gaps)}–{max(gaps)} days apart" if gaps and min(gaps) != max(gaps) else (f", {gaps[0]} days apart" if gaps else ''))
            rows3.append([f"Compaction test per layer — {what} ({area} layers 1–{len(lr)}: {ids_text([x['id'] for x in lr])})",
                          f"{num_word(len(lr), cap=True)} layers finish {lr[0]['finish']} → {lr[-1]['finish']}{gtxt}; if each layer's test and "
                          "approval is hidden in a duration or lag, a failed test has nowhere to show",
                          'Between layers, as a short hold-point activity'])
            miss_bits.append('the per-layer tests')
    if entry and nok:
        for i, (ph, words) in enumerate(kb_phases):
            if _has(ph.get('name'), ('design', 'engineering', 'procure')):
                continue
            if words and not kb_counts.get(i):
                ka = next((a for a in (entry.get('activities') or []) if a.get('wbs') == ph.get('name')), {})
                rows3.append([ka.get('name') or ph.get('name'),
                              (ka.get('why') or f"The {tname} reference carries it; nothing in your file is named for it").rstrip('. '),
                              (f"After {ka.get('typical_pred')}, before {ka.get('typical_succ')} — if in your scope"
                               if ka.get('typical_pred') else 'If in your scope')])
    rows3 = rows3[:6]
    p3 = []
    if rows3:
        p3.append(f"These are construction/execution steps a {(tname or 'job of this type').lower()} job needs that I can't see "
                  f"{'on the finish chain' if chain else 'in the file'}. They're candidates to confirm by a name search in P6, "
                  "not findings — but any one discovered late will quietly eat "
                  + (f"the days you're trying to recover on {front_seg or 'the finish chain'}:" if behind else 'the float you have:'))
    elif nok:
        p3.append("I found no obvious gap by name: commissioning, energisation and the tests I look for all appear in the "
                  f"file ({len(comm_hits)} commissioning/handover activities). Check they're tied into {fin_name or 'the finish'} "
                  "by logic, not just present.")
    else:
        p3.append("Without the file I can't search activity names for the steps a job like this needs (commissioning, "
                  "energisation, per-layer tests). The Constructability / Knowledge Base review does it against your project type.")
    if rows3:
        thinking.append(f"Searched {len(names):,} activity names for commissioning, energisation and hold-point steps — "
                        f"{len(rows3)} candidate gaps")
    sec3 = K.sec('Missing construction activities that break continuity — or would eat the recovery', *p3,
                 table=K.tbl(['Missing activity', 'Why it matters', 'Where it fits'], rows3,
                             note="Candidates from the real finish chain" + (f" and the {tname} reference" if tname else '')
                                  + " — confirm each by name in P6 before adding. The missing-activities check suggests "
                                    "construction/execution steps only."))

    # ── 4. safety hold-points and permits ───────────────────────────────────────────────────────────
    p4 = []
    if nok:
        pool, seen = [], set()
        for x in chain + deep:
            if _has(x['name'], GATE_WORDS) and _clean(x['name']).lower() not in seen:
                seen.add(_clean(x['name']).lower())
                pool.append(f"{_clean(x['name'])} ({x['id']})")
        appr = [x for x in (N.get('client_inputs') or []) if _has(x['name'], ('approval',)) and _has(x['name'], ('start', 'commence'))]
        gates = pool[:6] + [f"an approval-to-start gate on the client side, {short_name(x['name'])} ({x['id']})" for x in appr[:1]]
        permits = [n for n in names if _has(n, PERMIT_WORDS)]
        txt = ("The tool doesn't ingest a permit register or an inspection-and-test plan (ITP), so it can't confirm that "
               "permits and hold-points are gates in your logic.")
        if gates:
            txt += f" What your file does carry are named inspection gates: {K2_join(gates)}. Those are the right kind of gates."
        if permits:
            txt += (f" It also names {len(permits)} permit / safety activities (e.g. {permits[0]}) — keep them tied in as "
                    "predecessors, not floating.")
        p4.append(txt)
        high = [x for x in install if _has(x['name'], tuple(HEIGHT_WORDS)) and not _has(x['name'], ('polyeth', 'under'))]
        if high:
            kinds = list(dict.fromkeys(v for k, v in HEIGHT_WORDS.items() for x in high if k in x['name'].lower()))[:4]
            t0, t1_ = min(_dt(x['finish']) for x in high), max(_dt(x['finish']) for x in high)
            window = t0.strftime('%B') + ('' if t0.year == t1_.year else t0.strftime(' %Y')) + (
                '–' + t1_.strftime('%B %Y') if (t0.month, t0.year) != (t1_.month, t1_.year) else t1_.strftime(' %Y'))
            overlap = {_trade(x) for x in tasks if _dt(x['finish']) and t0 <= _dt(x['finish']) <= t1_}
            p4.append(f"What I'd expect to see and can't: work-at-height and lifting permits for the {K2_join(kinds)}, and "
                      "hot-work permits for the steel. On the finish chain all of that falls in "
                      f"{window}, when {num_word(len(overlap))} work front{'s' if len(overlap) != 1 else ''} "
                      f"{'overlap' if len(overlap) != 1 else 'is active'}. Build that permit / hold-point line manually for "
                      "now, and don't report the schedule as 'safety-sequenced' on the tool's word alone.")
        else:
            p4.append("What I'd expect to see and can't: permit-to-work, work-at-height, lifting and confined-space gates tied "
                      "into the logic. Build that line manually for now, and don't report the schedule as "
                      "'safety-sequenced' on the tool's word alone.")
    else:
        p4.append("The tool doesn't ingest a permit register or an inspection-and-test plan (ITP), so it can't confirm that "
                  "scaffold erect-then-inspect, permits-to-work, heavy-lift exclusions or confined-space entries are gates in "
                  "your logic. Walk the chain that sets the finish by hand for those, and don't report the schedule as "
                  "'safety-sequenced' on the tool's word alone.")
    sec4 = K.sec('Safety hold-points and permits — a partial gap, told straight', *p4)

    # ── 5. is the WBS sound ─────────────────────────────────────────────────────────────────────────
    p5 = []
    others = [b for b in t1 if b != main_l1 and not _has(b, MILESTONE_BRANCH)]
    if kids:
        def _kid(k, n, first):
            gg = sorted([(kk[2], v) for kk, v in t3.items() if kk[0] == main_l1 and kk[1] == k], key=lambda kv: -kv[1])
            gg = [x[0] for x in gg][:4]
            area = sorted(x for x in gg if _AREA.match(x))
            inner = (f", by {K2_join(area)}" if area and len(area) == len(gg) else (f", including {K2_join(gg)}" if gg else ''))
            return f"{k} ({n:,}{' activities' if first else ''}{inner})"
        kid_txt = K2_join([_kid(k, n, i == 0) for i, (k, n) in enumerate(kids[:4])])
        bold = (f"Yes — your WBS is sound, and more granular than the rollup makes it look. Under {main_l1} it already "
                f"splits into {kid_txt}" + (f", with separate branches for {K2_join(others[:7])}" if others else '') + '.')
        if weights_l1:
            bold += (f" The one weakness is that the EVM weights stop at level 1, so your report shows a single "
                     f"{main_w}% {main_l1} line and can't say which part is late.")
        p5.append('**' + bold + '**')
        by_area = any(re.match(r'(phase|area|zone|block|sector|level|building|plot)\b', kk[2], re.I) for kk in t3 if kk[0] == main_l1)
        good = f"It's organised the right way for a {'phased ' if by_area else ''}job — {'by area/phase and ' if by_area else ''}by trade"
        if cbranch:
            open_ci = [x for x in N.get('client_inputs') or [] if not x['done'] and (x.get('wbs') or '').startswith(cbranch)]
            good += (f" — with a dedicated '{cbranch}' branch ({t1.get(cbranch, 0)} activities, {len(open_ci)} still open), "
                     "which is good practice and valuable for the delay record")
        vg = F.get('value_gap') or {}
        if vg.get('dimension'):
            good += f". The activity codes add the cross-cuts a WBS can't — your '{vg['dimension']}' code already splits the value gap"
        p5.append(good + '.')
        ch = []
        if weights_l1:
            first = (f"First, push the EVM weighting down to level 2 ({K2_join([k for k, _ in kids[:4]])})"
                     + (f", or report by the '{vg['dimension']}' code" if vg.get('dimension') else ''))
            top = next((x for x in (vg.get('groups') or []) if (x.get('gap') or 0) > 0), None)
            first += (f" — that one step shows immediately that {top['code']} carries {round(top.get('pct_of_gap') or 0, 2)}% of "
                      "the value gap." if top else " — then the report can say which of them is late, instead of one "
                      f"{main_w}% line.")
            ch.append(first)
        if no_comm:
            ch.append(f"{'Second' if ch else 'First'}, add a Testing, Commissioning & Handover branch — or write down that it's "
                      "outside your scope.")
        heavy = [(b, t1[b], dnames[b.lower()]) for b in t1 if b.lower() in dnames and n_acts and t1[b] >= 0.15 * n_acts
                 and (dnames[b.lower()].get('weight') or 0) <= 0.02]
        if heavy:
            b, cnt, dd_ = heavy[0]
            txt = (f"{b} is {cnt:,} activities at {round((dd_.get('weight') or 0) * 100)}% weight; that's fine (weight should "
                   "follow value, not count)")
            if conc and conc[0].lower() in b.lower():
                txt += f", but it sits in the {conc[0]} package, where {conc[1]} of the {conc[2]} out-of-sequence findings are, so keep its logic reviewed"
            ch.append(txt + '.')
        if ch:
            p5.append(('Two changes I\'d make. ' if len([c for c in ch if c.startswith(('First', 'Second'))]) >= 2 else
                       "What I'd change: ") + ' '.join(ch))
    elif discs:
        top = max(discs, key=lambda x: x.get('weight') or 0)
        p5.append(f"From the stored weights, the WBS rolls up into {len(discs)} level-1 lines, led by {top['name']} "
                  f"({round((top.get('weight') or 0) * 100)}% of the weight). I can't see the tree under them without the "
                  "file, so I can't say whether the big line is split by area and trade — the test of a sound WBS is that "
                  "each work front can be read on its own. The Constructability / Knowledge Base review checks it against "
                  "your project type.")
    sec5 = K.sec('Is your WBS sound for this project type', *p5)

    # ── 6. reference sequence ───────────────────────────────────────────────────────────────────────
    rows6, p6 = [], []
    if ktype and nok:
        phases, counts = kb_phases, kb_counts
        pool = [x for x in chain + deep + list(N.get('milestones') or []) if 'Milestone' not in (x.get('type') or '')]
        seen_ids, by_phase = set(), {}
        for x in pool:
            if x['id'] in seen_ids:
                continue
            seen_ids.add(x['id'])
            if _has((x.get('wbs') or '').split(' / ')[0] + ' / ' + x['name'], NON_CONSTRUCTION):
                continue
            i = _assign(x['name'], phases, x.get('wbs'))
            if i is not None:
                by_phase.setdefault(i, []).append(x)
        k = 1
        late_ci = N.get('client_inputs_late_open') or []
        if N.get('client_inputs'):
            slips = ' / '.join('%+d' % x['slip_wd'] for x in late_ci[:3])
            rows6.append([str(k), 'Client inputs & area release', _gate('client input'),
                          (f"Present — {ids_text([x['id'] for x in late_ci[:3]])}, all late ({slips} wd)") if late_ci else
                          f"Present — {len(N['client_inputs'])} items, none late"])
            k += 1
        for i, (ph, words) in enumerate(phases):
            ex = by_phase.get(i) or []
            c = counts.get(i, 0)
            if ex:
                uniq = list({_clean(x['name']).lower(): x for x in reversed(ex)}.values())[::-1]
                cell = f"Present — {c:,} activities, e.g. " + '; '.join(f"{_clean(x['name'])} ({x['id']})" for x in uniq[:2])
            elif c:
                eg = next((a['name'] for a in cacts if _assign(a['name'], phases, a['wbs_path']) == i), '')
                cell = f"Present — {c:,} activities, e.g. {eg}"
            else:
                cell = 'Not visible — confirm scope'
            rows6.append([str(k), ph.get('name'), _gate(ph.get('name')), cell])
            k += 1
        rows6.append([str(k), 'Pre-commissioning & trials', _gate('test commission'),
                      'Not visible — confirm scope' if no_comm else f"Present — {len(comm_hits)} activities, e.g. {comm_hits[0]}"])
        k += 1
        takeover = [n for n in names if _has(n, ('taking over', 'taking-over', 'take over', 'handover', 'hand over'))]
        rows6.append([str(k), 'Commissioning & handover', _gate('handover'),
                      (f"Present — e.g. {takeover[0]}" if takeover else
                       f"Finish is {fin_name} ({fin_id}); no Taking-Over milestone visible" if fin_name else 'Not visible')])
        p6.append(f"For this file, the relevant reference is **{tname}** — the best fit of {ktype['n_types']} Knowledge Base "
                  f"types, read from your WBS and activity names ({ktype['cover']:,} activities match its signatures: "
                  f"{', '.join(ktype['hits'][:5])})"
                  + (f"; {ktype['runner']} is the runner-up" if ktype.get('runner') else '') + '. '
                  + ("" if ktype.get('confident') else "The margin is narrow, so pick the type yourself in the Knowledge Base if it's wrong. ")
                  + "Here's the reference order, mapped to where your file already has each step:")
    else:
        p6.append("I need the file to read the project type from its WBS and activity names" if not nok else
                  "None of the Knowledge Base types matches your WBS and activity names strongly enough to name one")
        p6[0] += (" — open the Constructability / Knowledge Base, pick the type, and it lays out the reference build order "
                  "with the gates a construction reviewer expects (pile / formation tests, strength before load, "
                  "water-tightness, alignment, loop checks, load runs, Taking-Over).")
    label6 = f"Reference construction sequence for a {tname.lower()} project" if tname else 'Reference construction sequence for this project type'
    sec6 = K.sec(label6, *p6, table=K.tbl(['#', 'Phase', 'Key gate', 'In your file'], rows6,
                                         note=(f"Reference order for {tname} from the Knowledge Base"
                                               + (" (a starter draft — confirm with a planning engineer)" if (ktype or {}).get('draft') else '')
                                               + ". The 'In your file' column is real — from your finish chain, milestones, "
                                                 "client inputs and activity names.") if tname else None))

    # ── 7. suggested WBS ────────────────────────────────────────────────────────────────────────────
    p7 = []
    if t1:
        phase_tok = lambda s: (re.search(r'\bphase\s+([ivx]+|\d+)\b', s or '', re.I) or [None, None])[1]
        mtok = phase_tok(main_l1)

        def rank(b):
            if b == cbranch:
                return 0
            if b == main_l1:
                return 2
            if _has(b, ('as-built', 'as built', 'close', 'handover')):
                return 4
            if _has(b, ('design', 'engineering', 'procurement')) and (phase_tok(b) or mtok) == mtok:
                return 1
            return 5
        l1s = sorted([b for b in t1 if not _has(b, MILESTONE_BRANCH)], key=lambda b: (rank(b), -t1[b]))
        lines, num, main_ref, tc_num = [], 0, None, None
        kind = lambda b: next((i for i, w in enumerate(('design', 'engineering', 'procurement')) if w in b.lower()), 3)
        grp1 = sorted([b for b in l1s if rank(b) == 1], key=lambda b: (kind(b), -t1[b]))
        for r in (0, 1, 2, 3, 4, 5):
            if r == 1 and grp1:
                num += 1
                lines.append(f"{num}  {' · '.join(grp1)}  (as now)")
                continue
            if r == 3:
                if no_comm:
                    num += 1
                    tc_num = num
                    lines.append(f"{num}  NEW  Testing, Commissioning & Handover  →  {num}.1 Pre-commissioning · {num}.2 "
                                 f"Commissioning / trials · {num}.3 Punch list · {num}.4 Taking-Over  —  only if in your scope")
                continue
            for b in [x for x in l1s if rank(x) == r]:
                num += 1
                if b == cbranch or b == main_l1:
                    ch = sorted([(kk[1], v) for kk, v in t2.items() if kk[0] == b], key=lambda kv: -kv[1])
                    ch = ch[:10] if b == cbranch else ch[:6]
                    sub = ' · '.join(f"{num}.{i} {c}" for i, (c, _) in enumerate(ch, 1))
                    tail = '  —  NEW: weight EVM at this level' if (b == main_l1 and weights_l1) else ''
                    lines.append(f"{num}  {b}" + (f"  →  {sub}" if sub else '') + tail)
                    if b == main_l1 and len(ch) >= 2:
                        main_ref = f"{num}.1–{num}.{len(ch)}"
                else:
                    lines.append(f"{num}  {b}  (as now)")
        adds = (1 if weights_l1 else 0) + (1 if no_comm else 0)
        p7.append("Keep your tree — it already mirrors the sequence. The suggestion is your current WBS"
                  + (f" with {num_word(adds)} addition{'s' if adds != 1 else ''} (marked NEW), not a replacement:" if adds else ", unchanged:"))
        p7 += lines
        ms = [b for b in t1 if _has(b, MILESTONE_BRANCH)]
        if ms:
            p7.append(f"Milestone branches ({', '.join(ms)}) stay as they are.")
        fix = []
        if weights_l1:
            fix.append(f"weighting {main_ref or 'the level-2 branches'} separately is the visibility fix from the WBS section")
        if tc_num:
            fix.append(f"adding {tc_num} is the fix from the commissioning gap")
        if fix:
            p7.append(_cap('; '.join(fix)) + '.')
    else:
        p7.append("I need the file to lay out your current tree with the suggested additions. The Knowledge Base gives the "
                  "reference WBS for the project type; keep your own tree and add only what's missing (typically a "
                  "Testing, Commissioning & Handover branch), weighting EVM one level below the main construction line.")
    sec7 = K.sec('Suggested WBS to copy into P6', *p7)

    # ── 8. starter baseline ─────────────────────────────────────────────────────────────────────────
    p8 = []
    kb_ms = [m for m in (entry.get('milestones') or [])][:4]
    p8.append(f"You don't need a starter to plan this job — you have a {_n(n_acts)}-activity live schedule. Where the KB "
              "starter baseline earns its place is as a logic reference: "
              + (f"download the {tname} starter (P6 XML: the reference WBS pre-built, a phase activity per branch, the KB's "
                 f"often-missed activities in their home branch, milestones such as {K2_join(kb_ms)}, all linked "
                 "Finish-to-Start in physical order, with placeholder durations)" if tname else
                 "download the playbook starter for your type (P6 XML: reference WBS, phases in physical order with FS logic, "
                 "placeholder durations)")
              + " and import it as a separate P6 project. Don't merge it into the live schedule.")
    p8.append("Then compare the two side by side. It shows at a glance the steps your network doesn't carry"
              + (f" — {K2_join(miss_bits)} above —" if miss_bits else '')
              + (f" and helps sort which of your {dang} dangling and {oos} out-of-sequence findings are genuine logic errors "
                 "and which are naming differences." if dang is not None and oos is not None else ' and helps sort genuine '
                 'logic errors from naming differences.')
              + " Its durations and resources are placeholders; never quote them in a report or forecast.")
    sec8 = K.sec('Starter baseline (XER / XML) to import into P6', *p8)

    # ── measured / actions / evidence ────────────────────────────────────────────────────────────────
    rel_mix = ' · '.join(f"{t} {_p1(rt.get(t.lower() + '_pct'))}" for t in ('FS', 'SS', 'FF', 'SF') if rt.get(t.lower() + '_pct') is not None)
    measured = ((f"From your P6 file: open ends ({_n(open_ends)}), circular loops ({_n(loops)}), leads ({_n(leads)}), dangling "
                 f"({_n(dang)}" + (f" = {d_start} start / {d_fin} finish / {d_both} both" if d_start is not None else '')
                 + f", of {_n(n_logic)} activities in the logic check), out-of-sequence ({_n(oos)}, {_n(crit_oos)} critical"
                 + (f", {conc[1]} in {conc[0]}" if conc else '') + f"), lags ({_n(lagged)} of {_n(n_rel)} relationships; "
                 f"{_n(long_lags)} over {thr or 14} wd; {_n(lag_crit)} on the critical path)"
                 + (f" and relationship types ({rel_mix})" if rel_mix else '')
                 + " are deterministic reads of the relationship table. ") if has_logic else
                "No stored logic check was available for this update. ")
    if deeper:
        measured += ("'Float deeper than the finish' comes from the float check ("
                     + ' / '.join('%+d' % x['tf'] for x in deeper) + f" against {fin_tf:+d}). ")
    if chain:
        measured += ("The sequence read uses the incomplete activities sharing the finish's negative float, in finish order, "
                     "checked against a standard civil build order. ")
    if tname:
        measured += (f"The project type ({tname}) is read from your WBS and activity names against the Knowledge Base — "
                     "construction sense is a reference read, candidates with reasons, not a score, and nothing is changed "
                     "automatically. ")
    if t1:
        measured += "WBS branches and activity counts come from the file's WBS; weights from the category breakdown. "
    measured += ("The reference sequence, the suggested WBS additions and the starter XML are a curated KB template with "
                 "placeholder durations and resources; the 'In your file' column is real. Permits and ITP hold-points are "
                 "not ingested — only named gates are visible.")
    if not nok:
        measured += " The P6 file couldn't be re-read, so the activity-level parts are limited."

    actions = [
        (f"Open the lag report and write a reason against each of the {long_lags} lags over {thr or 14} wd; convert any that "
         "hide real work (curing before striking, per-layer tests, approval waits) into activities"
         + (f" — start with the {lag_crit} lags on the critical path." if lag_crit else '.')) if long_lags else '',
        (f"Fix the {crit_oos} critical out-of-sequence link{'s' if crit_oos != 1 else ''} first (Out-of-Sequence Resolve & Correct)"
         + (f", then review the {conc[1]} {conc[0]} findings with the {conc[0].lower()} team." if conc else '.')) if crit_oos else '',
        ("Find what holds " + ' and '.join(f"{x['name']} ({x['id']}, {x['tf']:+d})" for x in deeper)
         + f" tighter than the finish ({fin_tf:+d}) — constraint, sectional key date or calendar — and record it.") if deeper else '',
        (f"Run Dangling Resolve & Correct on the {dang}" + (f", the {d_both} loose at both ends first." if d_both else '.')) if dang else '',
        (f"Confirm commissioning scope; if it's yours, add energisation, pre-commissioning and commissioning FS from "
         f"{last_task['name']} ({last_task['id']}) into {fin_name}.") if (no_comm and last_task and fin_name) else '',
        ("Search P6 for per-layer tests on the layered fill works; add short hold-point activities if they're missing.")
        if 'the per-layer tests' in miss_bits else '',
        (f"Push EVM weighting down to level 2 ({' / '.join(k for k, _ in kids[:4])})"
         + (f", or report by the '{(F.get('value_gap') or {}).get('dimension')}' code." if (F.get('value_gap') or {}).get('dimension') else '.'))
        if weights_l1 else '',
        "Add work-at-height, lifting and hot-work permit gates manually on the installation works of the finish chain."
        if nok and install else 'Walk the finish chain by hand for permits and hold-points (scaffold inspect, lifts, hot work).',
        (f"Import the KB {tname} starter XML as a separate reference project and compare it with the live network — never merge it."
         if tname else "Pick the project type in the Knowledge Base and compare its reference sequence with your network."),
        '' if has_logic else 'Run the Schedule Audit on this update so the logic checks are stored, then ask again.',
    ]
    evidence = [
        K.ev('Open ends / loops / leads', f"{_n(open_ends)} / {_n(loops)} / {_n(leads)}") if has_logic else None,
        K.ev('Dangling', f"{dang} ({_p1(g('dangling_pct'))})" + (f" — {d_start} start, {d_fin} finish, {d_both} both" if d_start is not None else ''))
        if dang is not None else None,
        K.ev('Out-of-sequence', f"{oos} ({_p1(oos_pct)}) — {_n(crit_oos)} critical" + (f", {conc[1]} in {conc[0]}" if conc else ''))
        if oos is not None else None,
        K.ev('Lags', f"{lagged} ({_p1(lag_pct)}) — {_n(long_lags)} over {thr or 14} wd, {_n(lag_crit)} critical") if lagged is not None else None,
        K.ev('Relationship types', rel_mix) if rel_mix else None,
        K.ev('Deepest float', f"{deeper[0]['tf']:+d} wd ({deeper[0]['id']}) vs {fin_tf:+d} at the finish") if deeper else None,
        K.ev('Negative float', f"{nf_n:,} activities ({_p1(nf_pct)})") if nf_n else None,
        K.ev(f"Commissioning before {fin_id or 'the finish'}", 'none visible' if no_comm else (f"{len(comm_hits)} activities" if nok else None)),
        K.ev(f"WBS level 2 ({main_l1})", ' · '.join(f"{k} {v:,}" for k, v in kids[:4])) if kids else None,
        K.ev('Main line weight', f"{main_w}% ({'one EVM line' if weights_l1 else main_l1})") if main_l1 and main_w else None,
        K.ev('Project type', f"{tname} (KB best fit)") if tname else None,
    ]
    drills = [K.drill('q06', 'Which logic problems do I fix first?'),
              K.drill('q11', 'Is commissioning covered, and who\'s behind?'),
              K.drill('q04', "What's driving the date?"),
              K.drill('q05', f"How do I recover the ~{round(d)} days?") if behind else K.drill('q02', 'When will we finish?')]
    a = K.A2(head, [sec1, sec2, sec3, sec4, sec5, sec6, sec7, sec8], pills=pills, measured=measured,
             actions=actions, evidence=evidence, drilldowns=drills)
    a['thinking'] = thinking[:4] or ['Read the stored EVM weights for this update']
    return a


def K2_join(items):
    """'a', 'a and b', 'a, b and c'."""
    items = [str(i) for i in items if i]
    if len(items) <= 1:
        return items[0] if items else ''
    return ', '.join(items[:-1]) + ' and ' + items[-1]
