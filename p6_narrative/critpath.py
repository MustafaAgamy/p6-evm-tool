"""Appendix — Critical Path : the "critical-path sweep".

Instead of dumping the (often hundreds of) total-float = 0 activities as a table, this
distils them into the project's own ZONES (read generically from the WBS) and shows, for
every month of the project, which zone is driving the schedule and by which trade — so the
critical path reads as a coloured staircase from contract start to completion.

DATA ONLY (like :mod:`p6_narrative.volwork` / :mod:`p6_narrative.prodrate`): both the HTML/PDF
renderer (:func:`p6_narrative.html._critpath`) and the native Word renderer
(:func:`p6_narrative.docx_writer._render_critpath`) draw straight from this payload, so
screen == PDF == Word (same zones, months, colours, KPIs, narrative).

Everything is derived from the loaded file:

* **Critical set** — activities whose P6-exported total float ≤ 0 (``crit_basis='tf<=0'``).
  When none qualify but the schedule carries float, the minimum-float band is used
  (``crit_basis='min-float'``, within 0.5 day of the least float). When no activity carries
  float at all → ``{'available': False}`` with an honest note. The critical path is P6's OWN
  total float — nothing is re-scheduled / re-run.
* **Zones (rows)** — generic, from the WBS path (``activity['wbs_path']``, root-first
  "A > B > C"). A single depth is chosen so the zone count is readable (6–24), never
  hard-coded to any project's naming.
* **Trade (colour)** — a coarse construction phase inferred from the activity NAME by broad
  keyword buckets; colour only, degrades to a neutral grey bucket when unmatched.

Nothing is specific to any one schedule.
"""
import re
from collections import defaultdict
from datetime import date

_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
           'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

# ── trade → colour (≤9 broad construction-phase buckets, colour only) ──────────
# (display name, [name-keywords], hex6). The FIRST bucket whose any keyword is a substring
# of the lower-cased activity name wins; anything unmatched falls to the last, neutral
# "Pre-construction / other" grey bucket, so the mapping always degrades gracefully. Order
# matters (more specific stages first). Colours mirror the approved concept mockup.
_TRADES = [
    ('Piling / excavation',      ['dril', 'piling', 'bored pile', 'pile cap', 'pile head',
                                   'excav', 'earthwork', 'dewater', 'shoring'],        '8C6D3F'),
    ('Reinforcement',            ['reinforc', 'rebar', 'rft', 'steel fix', 'steelfix'], 'D98A2B'),
    ('Columns',                  ['column', 'pedestal', 'pier'],                        '2F8F83'),
    ('Slabs / foundations',      ['slab', 'raft', ' sog', 'footing', 'foundation',
                                  'grade beam', 'blinding', 'screed'],                  '4A9D5B'),
    ('Concrete / formwork',      ['concret', 'pour', 'cast', 'formwork', 'shutter',
                                  'wall'],                                              '3B6EA5'),
    ('Steel structure',          ['steel', 'structur', 'frame', 'girder', 'truss',
                                  'beam', 'roof', 'cladding', 'purlin'],                '5B6472'),
    ('Equipment / installation', ['equip', 'silo', 'handling', 'mechanic', 'electric',
                                  'install', 'erect', 'machine', 'conveyor', 'roller',
                                  'pipe', 'duct', 'hvac', 'pump', 'crane', 'gate'],     '7D5BA6'),
    ('Testing / commissioning',  ['test', 'commission', 'snag', 'inspect', 'handover',
                                  'punch', 't&c', 'pre-comm', 'precomm'],              'C0392B'),
    ('Pre-construction / other', ['contract', 'addend', 'mobil', 'permit', 'approv',
                                  'procure', 'material', 'submittal', 'design',
                                  'engineer', 'ifc', 'drawing', 'award', 'noti',
                                  'survey', 'setting out', 'set out', 'milestone'],     '9AA4B0'),
]
_OTHER = _TRADES[-1]            # the neutral catch-all bucket (grey)
_TRADE_ORDER = {name: i for i, (name, _kw, _c) in enumerate(_TRADES)}
_TRADE_HEX = {name: hexv for (name, _kw, hexv) in _TRADES}

INACTIVE_HEX = 'F2F4F7'        # empty month cell (light track), screen + Word


def trade_of(name):
    """Coarse construction phase for one activity name → a bucket display name (colour only)."""
    n = (name or '').lower()
    for disp, kws, _hexv in _TRADES:
        for kw in kws:
            if kw in n:
                return disp
    return _OTHER[0]


# ── zone (row) derivation — generic, from the WBS path ─────────────────────────
def _segments(act):
    """The root-first WBS path segments for an activity, e.g. ['Project', 'Zone A', 'Raft']."""
    return [s.strip() for s in str(act.get('wbs_path') or '').split(' > ')]


def _id_token(act):
    """Leading token of the activity Id (fallback zone label), e.g. 'S3-DRILL' → 'S3'."""
    aid = str(act.get('id') or '').strip()
    if not aid:
        return ''
    tok = re.split(r'[.\-_ /]', aid)[0].strip()
    return tok


def _zone_label(segs, depth, act):
    """The zone label an activity maps to at ``depth`` (index into its WBS path):
    the segment at ``depth`` when the path is that deep, else the deepest available
    non-empty segment, else the Id's leading token, else 'Project'. Fully generic."""
    if segs and len(segs) > depth and segs[depth]:
        return segs[depth]
    for s in reversed(segs or []):
        if s:
            return s
    tok = _id_token(act)
    return tok or 'Project'


def _choose_depth(pairs):
    """Pick a single WBS depth (index after the root at 0) giving the most informative zones:
    the DEEPEST depth whose distinct-zone count stays readable (6–28) — deeper levels expose the
    real work areas (e.g. individual silos/towers) that a shallow level collapses into one giant
    branch — and if none qualifies, the depth whose count is closest to ~14. A long tail of tiny
    zones is later merged into one "Other areas" row by :func:`critical_path`, so a slightly-high
    count here is fine. ``pairs`` = [(segments, act), …]. Returns (depth, zone_count)."""
    maxdepth = max((len(s) for s, _a in pairs), default=1)
    counts = []                                   # [(depth, distinct_count)]
    for d in range(1, max(maxdepth, 2)):
        counts.append((d, len({_zone_label(s, d, a) for s, a in pairs})))
    if not counts:
        return 1, len({_zone_label(s, 1, a) for s, a in pairs})
    best = None
    for d, c in counts:                           # keep overwriting → ends on the DEEPEST in-band
        if 6 <= c <= 28:
            best = (d, c)
    if best:
        return best
    return min(counts, key=lambda dc: abs(dc[1] - 14))   # else closest to ~14


# ── month timeline ─────────────────────────────────────────────────────────────
def _as_date(v):
    try:
        return v.date()
    except AttributeError:
        return v


def _month_list(start, fin):
    """Inclusive list of (year, month) from ``start`` to ``fin``."""
    out = []
    y, m = start.year, start.month
    while (y, m) <= (fin.year, fin.month):
        out.append((y, m))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def _month_bounds(y, m):
    first = date(y, m, 1)
    if m == 12:
        nxt = date(y + 1, 1, 1)
    else:
        nxt = date(y, m + 1, 1)
    return first, nxt        # [first, nxt)  half-open


# ── public entry point ──────────────────────────────────────────────────────────
def critical_path(data, path=None):
    """Build the Appendix — Critical Path payload (data only). ``path`` is accepted for
    signature parity with the other section builders and is unused (the critical path comes
    from P6's own exported total float; nothing is re-parsed or re-scheduled)."""
    acts_all = [a for a in (data.activities or {}).values()
                if a.get('planned_start') and a.get('planned_finish')]

    # ── critical set: P6 total float ≤ 0, else the minimum-float band ──
    crit = [a for a in acts_all
            if a.get('total_float_days') is not None and a['total_float_days'] <= 0.0001]
    crit_basis, min_float = 'tf<=0', None
    if not crit:
        floated = [a for a in acts_all if a.get('total_float_days') is not None]
        if not floated:
            return {'available': False,
                    'note': 'The schedule carries no total-float values, so a critical '
                            'path cannot be distilled from it.'}
        min_float = min(a['total_float_days'] for a in floated)
        crit = [a for a in floated if a['total_float_days'] <= min_float + 0.5]
        crit_basis = 'min-float'
    if not crit:
        return {'available': False,
                'note': 'No critical activities could be identified in the schedule.'}

    # ── zones (rows) — generic depth choice on the WBS path ──
    pairs = [(_segments(a), a) for a in crit]
    depth, _zone_count = _choose_depth(pairs)
    zone_acts = defaultdict(list)
    for segs, a in pairs:
        zone_acts[_zone_label(segs, depth, a)].append(a)

    # Keep the sweep readable: show the substantive zones (>= MIN_ACTS critical activities) and
    # merge the long tail of tiny, often single-milestone zones into one honest "Other areas" row,
    # rather than cluttering the staircase with dozens of one-cell rows. If there are more
    # substantive zones than fit, the busiest are kept and the rest fold into "Other areas" too.
    MAX_ZONES, MIN_ACTS = 18, 3
    subst = [(k, v) for k, v in zone_acts.items() if len(v) >= MIN_ACTS]
    tiny = [(k, v) for k, v in zone_acts.items() if len(v) < MIN_ACTS]
    if subst:
        subst.sort(key=lambda kv: (-len(kv[1]), str(kv[0])))
        keep = dict(subst[:MAX_ZONES])
        tail = subst[MAX_ZONES:] + tiny
        other = []
        for _lab, alist in tail:
            other.extend(alist)
        if other:
            keep['Other areas (%d)' % len(tail)] = other
        zone_acts = keep
    elif len(zone_acts) > MAX_ZONES:                    # no substantive zones — just cap, no merge
        ranked = sorted(zone_acts.items(), key=lambda kv: (-len(kv[1]), str(kv[0])))
        zone_acts = dict(ranked[:MAX_ZONES])

    # ── month timeline across the critical span ──
    starts = [_as_date(a['planned_start']) for a in crit]
    fins = [_as_date(a['planned_finish']) for a in crit]
    proj_start, proj_finish = min(starts), max(fins)
    yms = _month_list(proj_start, proj_finish)
    months = [{'y': y, 'm': m, 'label': _MONTHS[m - 1]} for (y, m) in yms]
    bounds = [_month_bounds(y, m) for (y, m) in yms]

    # ── per-zone × per-month cell: active? + dominant trade colour ──
    zones = []
    seen_trades = set()
    for label, acts in zone_acts.items():
        # pre-compute each activity's window + trade once
        items = []
        for a in acts:
            items.append((_as_date(a['planned_start']), _as_date(a['planned_finish']),
                          trade_of(a.get('name'))))
        cells, start_mi, fin_mi = [], None, None
        for i, (first, nxt) in enumerate(bounds):
            tally = defaultdict(int)
            for a_start, a_fin, tr in items:
                if a_start < nxt and a_fin >= first:      # overlaps this month
                    tally[tr] += 1
            if tally:
                # dominant trade = highest count, ties broken by canonical bucket order
                tr = max(tally.items(),
                         key=lambda kv: (kv[1], -_TRADE_ORDER.get(kv[0], 99)))[0]
                seen_trades.add(tr)
                cells.append({'active': True, 'trade': tr,
                              'color': _TRADE_HEX.get(tr, _OTHER[2])})
                start_mi = i if start_mi is None else start_mi
                fin_mi = i
            else:
                cells.append(None)
        if start_mi is None:                       # no active month (defensive) — skip
            continue
        zones.append({'label': label, 'cells': cells,
                      'start_mi': start_mi, 'fin_mi': fin_mi})

    # staircase order: earliest critical start, then earliest finish, then label; the catch-all
    # "Other areas" row (if any) always sits last so the driving staircase reads cleanly.
    zones.sort(key=lambda z: (z['start_mi'], z['fin_mi'], str(z['label'])))
    zones.sort(key=lambda z: str(z['label']).startswith('Other areas'))

    legend = [[disp, hexv] for (disp, _kw, hexv) in _TRADES if disp in seen_trades]

    # ── KPIs ──
    n_crit = len(crit)
    n_zones = len(zones)
    dur_months = len(months)

    def _fd(d):
        return '%d %s %d' % (d.day, _MONTHS[d.month - 1], d.year)

    kpis = [
        ['%d months' % dur_months, 'Contract duration'],
        [_fd(proj_start), 'Contract start'],
        [_fd(proj_finish), 'Contract completion'],
        ['{:,}'.format(n_crit), 'Critical activities'],
        ['%d' % n_zones, 'Driving zones'],
    ]

    # ── auto-narrative (generic — names the first/last zone dynamically, never hardcoded) ──
    if crit_basis == 'min-float':
        basis_txt = ('the %s lowest-float activities (minimum total float = %s days, read '
                     'directly from P6 — no float value is exactly zero in this file)'
                     % ('{:,}'.format(n_crit), _fmt_float(min_float)))
    else:
        basis_txt = ('%s critical activities (total float = 0, read directly from P6)'
                     % '{:,}'.format(n_crit))
    # name the first/last DRIVING zone (skip the "Other areas" catch-all): earliest start, latest finish
    real = [z for z in zones if not str(z['label']).startswith('Other areas')]
    if real:
        first_zone = min(real, key=lambda z: (z['start_mi'], z['fin_mi']))['label']
        last_zone = max(real, key=lambda z: (z['fin_mi'], z['start_mi']))['label']
    else:
        first_zone = zones[0]['label'] if zones else 'the first zone'
        last_zone = zones[-1]['label'] if zones else 'the last zone'
    ending = '' if first_zone == last_zone else ' and ending in %s' % last_zone
    narrative = (
        'The baseline is driven by %s running from contract start on %s to completion on %s '
        '— about %d months. The critical path sweeps through the project’s %d '
        'driving zones in turn, beginning in %s%s, so the staircase below reads the sequence '
        'in which each area controls the finish date.'
        % (basis_txt, _fd(proj_start), _fd(proj_finish), dur_months, n_zones,
           first_zone, ending))

    if crit_basis == 'min-float':
        note = ('Every cell marks a month in which that zone has its lowest-float activities '
                'active, coloured by the dominant trade. No activity in this file carries '
                'exactly zero total float, so the minimum-float band (within 0.5 day of %s '
                'days) stands in for the critical path. Derived from the schedule’s own '
                'logic and P6’s exported total float; nothing is re-scheduled or assumed.'
                % _fmt_float(min_float))
    else:
        note = ('Every cell marks a month in which that zone has critical (total-float = 0) '
                'activities active, coloured by the dominant trade — read the staircase '
                'top-to-bottom to follow the driving sequence. Derived automatically from the '
                'schedule’s own logic and P6’s exported total float; nothing is '
                're-scheduled or assumed.')

    return {
        'available': True,
        'crit_basis': crit_basis,
        'min_float': min_float,
        'wbs_depth': depth,
        'months': months,
        'zones': zones,
        'legend': legend,
        'kpis': kpis,
        'narrative': narrative,
        'subhead': 'Critical-path sweep — when each zone drives the schedule',
        'note': note,
    }


def _fmt_float(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return ('%d' % f) if f == int(f) else ('%.1f' % f)
