"""Cross-sector synthetic schedules for the repeated-work-front engine.

Each fixture states, in its docstring, what a planning engineer would call the correct
answer, so a grouping strategy can be judged against a KNOWN truth rather than against
whichever number looks tidiest. None of these sectors was used to build the engine.

Deliberately varied along the axes real P6 files vary on: whether the instance marker
lives in the name, the WBS, the activity ID or an activity code; how deep the WBS goes;
whether code dimensions exist at all; and whether the file mixes several scope worlds
(engineering / procurement / construction) that each repeat differently.
"""
from p6_evm.parser import Calendar, ScheduleData


def _blank(day_hours=8.0):
    d = ScheduleData()
    d.calendars = {'C1': Calendar(object_id='C1', name='Cal', day_hours=day_hours)}
    d.project = {'data_date': None}
    d.wbs = {}
    d.activities = {}
    d.relationships = []
    d.activity_code_types = []
    d.bac_by_activity = {}
    d.ac_by_activity = {}
    return d


def _act(oid, name, wbs_id, dur_hours=40.0, act_id=None, codes=None, cost=None):
    act = {
        'object_id': oid, 'name': name, 'wbs_id': wbs_id, 'id': act_id or oid,
        'type': 'TaskDependent', 'calendar_id': 'C1',
        # ``intel.context`` reads ``planned_duration`` (hours) and divides by the
        # calendar's day hours; naming this ``planned_duration_hours`` silently produced
        # a zero-duration schedule and made the rhythm signal untestable on fixtures.
        'planned_duration': dur_hours,
    }
    if codes:
        act['activity_codes'] = dict(codes)
    return act


def _chain(d, oids):
    for a, b in zip(oids, oids[1:]):
        d.relationships.append({'pred_id': a, 'succ_id': b, 'type': 'FS', 'lag_days': 0.0})


# ── road ────────────────────────────────────────────────────────────────────
ROAD_STEPS = ('Clear and Grub', 'Earthworks Cut', 'Subgrade Preparation',
              'Subbase Layer', 'Base Course', 'Asphalt Binder', 'Asphalt Wearing')


def road(segments=12):
    """A road of ``segments`` chainage fronts, each running the same 7-step sequence.

    TRUTH: one repeated scope of ``segments`` fronts. The chainage marker lives in the
    activity ID and the WBS node name; names repeat verbatim across segments. Must NOT
    collapse to one front, and must NOT fragment into per-step trade buckets.
    """
    d = _blank()
    d.wbs['PRJ'] = {'name': 'Highway Upgrade', 'parent_object_id': None}
    d.wbs['RD'] = {'name': 'Roadworks', 'parent_object_id': 'PRJ'}
    for s in range(1, segments + 1):
        wid = 'CH%d' % s
        d.wbs[wid] = {'name': 'Chainage %d+000' % s, 'parent_object_id': 'RD'}
        oids = []
        for i, step in enumerate(ROAD_STEPS):
            oid = 'rd-%02d-%d' % (s, i)
            d.activities[oid] = _act(oid, step, wid,
                                     act_id='RD-CH%02d-%02d' % (s, i),
                                     dur_hours=40.0 + 8.0 * i)
            oids.append(oid)
        _chain(d, oids)
    return d


# ── tower ───────────────────────────────────────────────────────────────────
FLOOR_STEPS = ('Formwork', 'Rebar Fixing', 'Concrete Pour', 'Strip Formwork',
               'Blockwork', 'MEP First Fix')


def tower(floors=25, podium=True):
    """A tower of ``floors`` typical floors, each running the same 6-step cycle.

    TRUTH: one repeated scope of ``floors`` fronts, plus (when ``podium``) a structurally
    DIFFERENT podium scope that must stay separate. The floor marker lives in the WBS
    node name and the activity name suffix. WBS is four deep. Must NOT collapse the
    floors into a single front merely because they are highly repetitive, and must not
    merge the podium into the typical-floor group.
    """
    d = _blank()
    d.wbs['PRJ'] = {'name': 'Tower', 'parent_object_id': None}
    d.wbs['STR'] = {'name': 'Structure', 'parent_object_id': 'PRJ'}
    d.wbs['TYP'] = {'name': 'Typical Floors', 'parent_object_id': 'STR'}
    for f in range(1, floors + 1):
        wid = 'L%d' % f
        d.wbs[wid] = {'name': 'Level %02d' % f, 'parent_object_id': 'TYP'}
        oids = []
        for i, step in enumerate(FLOOR_STEPS):
            oid = 'tw-%02d-%d' % (f, i)
            d.activities[oid] = _act(oid, '%s Level %02d' % (step, f), wid,
                                     act_id='TW-L%02d-%s' % (f, step[:3].upper()),
                                     dur_hours=24.0 + 8.0 * i)
            oids.append(oid)
        _chain(d, oids)
    if podium:
        d.wbs['POD'] = {'name': 'Podium', 'parent_object_id': 'STR'}
        steps = ('Excavation', 'Piling', 'Pile Caps', 'Raft Slab', 'Retaining Walls',
                 'Waterproofing', 'Backfill')
        oids = []
        for i, step in enumerate(steps):
            oid = 'pod-%d' % i
            d.activities[oid] = _act(oid, step, 'POD', act_id='TW-POD-%02d' % i,
                                     dur_hours=80.0)
            oids.append(oid)
        _chain(d, oids)
    return d


# ── opaque ids, no codes, flat wbs ──────────────────────────────────────────
def opaque(units=8, steps=5):
    """Meaningless activity names ("Activity 1010"), NO code dimensions, ONE WBS node.

    TRUTH: ``units`` repeated fronts discoverable only from the relationship structure.
    An honest "cannot tell" is acceptable; inventing groups from numbering is not.
    """
    d = _blank()
    d.wbs['PRJ'] = {'name': 'Plant', 'parent_object_id': None}
    seq = 1000
    for u in range(units):
        oids = []
        for s in range(steps):
            seq += 10
            oid = 'op-%d-%d' % (u, s)
            d.activities[oid] = _act(oid, 'Activity %d' % seq, 'PRJ',
                                     act_id='%d' % seq, dur_hours=40.0)
            oids.append(oid)
        _chain(d, oids)
    return d


# ── phase vs trade coding (the general failure mode) ────────────────────────
def phase_vs_trade(buildings=14, trades=('Structure', 'Finishing', 'Electrical',
                                         'HVAC', 'Plumbing')):
    """A coarse phase code covering 100% of the file, plus a trade code inside one phase.

    Engineering + Procurement carry only the phase code. Construction carries phase AND
    trade, giving a genuine buildings x trades grid.

    TRUTH: the construction scope repeats across ``buildings`` fronts, each running the
    same trade sequence; engineering and procurement repeat on their own package
    structure. The coarse phase code covers everything and explains nothing — a selector
    that follows raw coverage picks it and finds no fronts at all.
    """
    d = _blank()
    d.activity_code_types = ['Phase', 'Trade']
    d.wbs['PRJ'] = {'name': 'Factory', 'parent_object_id': None}
    d.wbs['ENG'] = {'name': 'Engineering', 'parent_object_id': 'PRJ'}
    d.wbs['PRC'] = {'name': 'Procurement', 'parent_object_id': 'PRJ'}
    d.wbs['CON'] = {'name': 'Construction', 'parent_object_id': 'PRJ'}

    # The three worlds share NO vocabulary and no duration rhythm. Real phase worlds sit
    # at 0.085-0.16 name-token overlap; an earlier version of this fixture reused words
    # like "Works" and "Package" across all three and landed at 0.30-0.45, which would
    # have certified a world-detection rule that fails on a real file.
    for b in range(1, buildings + 1):
        wid = 'B%d' % b
        d.wbs[wid] = {'name': 'Building %02d' % b, 'parent_object_id': 'CON'}
        oids = []
        for t, trade in enumerate(trades):
            oid = 'con-%02d-%d' % (b, t)
            d.activities[oid] = _act(
                oid, '%s Erection Building %02d' % (trade, b), wid,
                act_id='CO-B%02d-%s-%02d' % (b, trade[:2].upper(), t),
                dur_hours=40.0 + 16.0 * t,
                codes={'Phase': 'Construction', 'Trade': trade})
            oids.append(oid)
        _chain(d, oids)

    for p in range(1, 9):                      # engineering: drawings and approvals
        oids = []
        for i, step in enumerate(('Draft', 'Issue', 'Comment', 'Endorse')):
            oid = 'eng-%02d-%d' % (p, i)
            d.activities[oid] = _act(oid, '%s Drawing Set %02d' % (step, p), 'ENG',
                                     act_id='EN-P%02d-%02d' % (p, i),
                                     dur_hours=16.0)      # short rhythm
            oids.append(oid)
        _chain(d, oids)

    for p in range(1, 11):                     # procurement: orders and shipping
        oids = []
        for i, step in enumerate(('Enquiry', 'Purchase', 'Fabricate', 'Ship')):
            oid = 'prc-%02d-%d' % (p, i)
            d.activities[oid] = _act(oid, '%s Order %02d' % (step, p), 'PRC',
                                     act_id='PR-P%02d-%02d' % (p, i),
                                     dur_hours=160.0)     # long rhythm
            oids.append(oid)
        _chain(d, oids)
    return d


# ── hostile ─────────────────────────────────────────────────────────────────
def no_repetition(n=40):
    """Every activity unique, one long chain. TRUTH: ZERO groups, 100% singletons."""
    d = _blank()
    d.wbs['PRJ'] = {'name': 'One Off', 'parent_object_id': None}
    words = ('Mobilise', 'Survey', 'Demolish', 'Excavate', 'Shore', 'Dewater')
    oids = []
    for i in range(n):
        oid = 'nr-%d' % i
        d.activities[oid] = _act(oid, '%s Area %d Task %d' % (words[i % len(words)], i, i),
                                 'PRJ', act_id='NR-%03d' % i, dur_hours=8.0 * (i + 1))
        oids.append(oid)
    _chain(d, oids)
    return d


def scale(fronts=650, steps=20):
    """~13,000 activities with realistic repetition, for timing and memory only."""
    d = _blank()
    d.wbs['PRJ'] = {'name': 'Mega', 'parent_object_id': None}
    for f in range(fronts):
        wid = 'U%d' % f
        d.wbs[wid] = {'name': 'Unit %04d' % f, 'parent_object_id': 'PRJ'}
        oids = []
        for s in range(steps):
            oid = 'sc-%04d-%02d' % (f, s)
            d.activities[oid] = _act(oid, 'Operation %02d' % s, wid,
                                     act_id='SC-U%04d-%02d' % (f, s), dur_hours=40.0)
            oids.append(oid)
        _chain(d, oids)
    return d


# ── matrix-WBS EPC (gates the instance-primary path) ─────────────────────────
def matrix_epc(buildings=4):
    """A minimal matrix-WBS EPC schedule: World (Type of Work) × Building × Trade, plus an
    Engineering document-control PHASE (Shop Drawing Submittal → Approval) that mirrors the
    construction. The Submittal and Approval of one building's drawings are cross-linked and
    live under two sibling WBS branches — the mirror the instance-primary engine must merge.

    TRUTH: this has the matrix signature (``has_matrix_structure`` True); the engine must
    merge Submittal + Approval into ONE document-control front per drawing package (both
    phases kept inside), keep the Construction world as its own fronts, and never split the
    two phases into two independent repeated fronts.
    """
    d = _blank()
    d.activity_code_types = ['Type of Work', 'Building', 'Trade', 'Engineering', 'Work Type']
    d.wbs['PRJ'] = {'name': 'Factory', 'parent_object_id': None}
    d.wbs['ENG'] = {'name': 'Engineering', 'parent_object_id': 'PRJ'}
    d.wbs['SUB'] = {'name': 'Shop Drawing Submittal', 'parent_object_id': 'ENG'}
    d.wbs['APP'] = {'name': 'Shop Drawing Approval', 'parent_object_id': 'ENG'}
    d.wbs['CON'] = {'name': 'Construction', 'parent_object_id': 'PRJ'}
    con_steps = ('Excavation', 'Foundation', 'Columns', 'Slab')
    for b in range(1, buildings + 1):
        bname = 'Building %02d' % b
        last_app = None
        for disc in ('Structural', 'Steel'):        # ≥2 disciplines → a real mirror matrix
            sub_wid, app_wid = 'SUB-%s-B%d' % (disc, b), 'APP-%s-B%d' % (disc, b)
            d.wbs[sub_wid] = {'name': '%s %s Drawings' % (bname, disc), 'parent_object_id': 'SUB'}
            d.wbs[app_wid] = {'name': '%s %s Drawings' % (bname, disc), 'parent_object_id': 'APP'}
            sub_oid, app_oid = 'eng-sub-%s-%d' % (disc, b), 'eng-app-%s-%d' % (disc, b)
            d.activities[sub_oid] = _act(
                sub_oid, 'SDS %s %s' % (disc, bname), sub_wid, act_id='EN-SUB-%s-%02d' % (disc[:2], b),
                codes={'Type of Work': 'Engineering', 'Building': bname,
                       'Trade': 'Civil Works', 'Engineering': '%s S.D Submittal' % disc})
            d.activities[app_oid] = _act(
                app_oid, 'SDA %s %s' % (disc, bname), app_wid, act_id='EN-APP-%s-%02d' % (disc[:2], b),
                codes={'Type of Work': 'Engineering', 'Building': bname,
                       'Trade': 'Civil Works', 'Engineering': '%s S.D Approval' % disc})
            d.relationships.append({'pred_id': sub_oid, 'succ_id': app_oid, 'type': 'FS', 'lag_days': 0.0})
            last_app = app_oid
        con_wid = 'CON-B%d' % b
        d.wbs[con_wid] = {'name': bname, 'parent_object_id': 'CON'}
        oids = []
        for i, step in enumerate(con_steps):
            oid = 'con-%d-%d' % (b, i)
            d.activities[oid] = _act(
                oid, '%s %s' % (step, bname), con_wid, act_id='CO-B%02d-%d' % (b, i),
                dur_hours=40.0 + 8.0 * i,
                codes={'Type of Work': 'Construction', 'Building': bname,
                       'Trade': 'Civil Works', 'Work Type': step})
            oids.append(oid)
        _chain(d, oids)
        d.relationships.append({'pred_id': last_app, 'succ_id': oids[0], 'type': 'FS', 'lag_days': 0.0})
    return d
