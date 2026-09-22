"""Schedule Audit / Schedule Health Review provider.

Exposes the FULL result set of the feature to Special Report, parse-free from
``ctx.audit`` (``db.get_audit_modules_for_snapshot`` → ``{'modules','module_order',
'health'}``):

  * the executive **Schedule Health** roll-up — a headline score KPI plus the whole
    Summary dashboard (reused verbatim from ``p6_audit.report.render_summary_report``);
  * **every module the review ran** (``module_order``) — each one's own full module
    report (reused from ``render_module_report`` via ``FR.audit_module``), so a new
    module added to the engine appears here automatically;
  * a headline **score** KPI for every module that actually shows a score/grade —
    which is every module EXCEPT the two that deliberately show none: Circular Logic
    (a GATE, not weighted) and Lag & Lead (scoring deferred; its screen/PDF show no
    score). Float uses its DCMA-anchored Float Health, exactly like the Float tab.

Parity: the section items reuse the feature's OWN renderers; the score/health KPIs
mirror the on-screen score cards (85/60 colour bands). Availability complements
produce() exactly — an item is 'ready' only when it will render real content.
"""
from p6_special import payloads as P
from p6_special import fmt
from p6_special import feature_reports as FR
from p6_special import reuse
from p6_special.registry import Item

FEATURE = 'audit'
FEATURE_TITLE = 'Schedule Audit'


def _audit(ctx):
    return ctx.audit or {}


def _mod(ctx, key):
    return (_audit(ctx).get('modules') or {}).get(key)


def _health(ctx):
    return _audit(ctx).get('health') or {}


def _avail(key):
    return lambda ctx: 'ready' if _mod(ctx, key) else 'no_data'


def _score_tone(s):
    # Match the feature's on-screen gauge bands (audit.js scoreColor): green >=85,
    # amber >=60, else red — not 80/50.
    if s is None:
        return 'neutral'
    return 'good' if s >= 85 else ('warn' if s >= 60 else 'bad')


def _headline_score(m):
    """The headline figure a module shows on its own tab: Float shows its DCMA-anchored
    Float Health (never the raw defect score), every other module its module score."""
    if m.get('module') == 'float':
        return (m.get('mgmt') or {}).get('float_health')
    return m.get('score')


def _score(key):
    def produce(ctx):
        m = _mod(ctx, key)
        if not m:
            return P.NO_DATA
        if key == 'float':
            # The Float feature's headline is float_health (a linear 100−defect% over the
            # construction population), labelled 'Float Health' with NO word-grade — the
            # feature deliberately shows no grade. Mirror it exactly.
            fh = _headline_score(m)
            if fh is None:
                return P.NO_DATA
            return P.kpi_group([P.kpi('Float Health', f'{fmt.num(fh)}/100',
                                      tone=_score_tone(fh))])
        s, g = m.get('score'), m.get('grade')
        if s is None:
            return P.NO_DATA
        return P.kpi_group([P.kpi(m.get('name') or key, f'{fmt.num(s)}/100',
                                  sub=(f'Grade {g}' if g else None), tone=_score_tone(s))])
    return produce


def _score_avail(key):
    """Ready only when the module carries a real headline score — so a module that
    could not be scored on this file (e.g. CPLI on a schedule with no dated finish)
    shows the score item as no_data instead of a 'ready' tile rendering '—'."""
    def avail(ctx):
        m = _mod(ctx, key)
        if not m:
            return 'no_data'
        return 'ready' if _headline_score(m) is not None else 'no_data'
    return avail


def _full(key):
    return lambda ctx, k=key: FR.audit_module(ctx, k) or P.NO_DATA


# ── Schedule Health roll-up (the executive Summary) ──────────────────────────
def _health_kpi(ctx):
    h = _health(ctx)
    score = h.get('score')
    if score is None:
        return P.NO_DATA
    grade, verdict = h.get('grade'), h.get('verdict')
    sub = ' · '.join(x for x in (grade, verdict) if x) or None
    return P.kpi_group([P.kpi('Schedule Health', f'{fmt.num(score)}/100',
                              sub=sub, tone=_score_tone(score))])


def _health_avail(ctx):
    return 'ready' if _health(ctx).get('score') is not None else 'no_data'


def _summary_report(ctx):
    """The whole Schedule Health Review Summary dashboard, reused verbatim from the
    feature's own renderer (weighted health score + grade, submission verdict, checks
    donut, sub-feature composition, problem areas, fix-these-first). Self-contained:
    imports the feature renderer directly and wraps it with the shared scoping helpers,
    so it composes into the document exactly like every other reused audit section."""
    def b():
        h = _health(ctx)
        if not h:
            return None
        from p6_audit.report import render_summary_report
        return render_summary_report(
            h, {'project_name': ctx.project_name, 'data_date': ctx.data_date},
            modules=_audit(ctx).get('modules') or {}, theme=ctx.mode)
    html = ctx.memo(f'fr:audit_summary:{ctx.mode}', b)
    if not html:
        return P.NO_DATA
    return FR._payload('audit', reuse.extract_styles(html), FR._body_after_head(html)) or P.NO_DATA


def _summary_avail(ctx):
    return 'ready' if _health(ctx) else 'no_data'


# Circular Logic is a GATE in the Schedule Health model (it never scores into the
# roll-up — while a loop exists P6 cannot F9), and Lag & Lead scoring was deliberately
# deferred (its screen and PDF show no score/grade). Neither exposes a headline score,
# so the Studio must not fabricate one. Every OTHER module DOES show a score card, so
# it gets a score Item. This complements produce() and matches the feature 1:1.
_NO_SCORE = {'circular', 'lag_lead'}


def provide(ctx):
    audit = _audit(ctx)
    modules = audit.get('modules') or {}
    order = audit.get('module_order') or list(modules.keys())

    items = [
        # Executive Schedule Health roll-up first — the weighted overview.
        Item('audit:health_score', FEATURE, FEATURE_TITLE, 'Schedule Health — score',
             'kpi', _health_kpi, _health_avail),
        Item('audit:summary_report', FEATURE, FEATURE_TITLE,
             'Schedule Health Review — Summary (full dashboard)', 'section',
             _summary_report, _summary_avail),
    ]
    # Every module the review ran (module_order) — future modules auto-appear.
    for key in order:
        m = modules.get(key) or {}
        label = m.get('name') or key
        if key not in _NO_SCORE:
            items.append(Item(f'audit:{key}_score', FEATURE, FEATURE_TITLE,
                              f'{label} — score', 'score', _score(key), _score_avail(key)))
        items.append(Item(f'audit:{key}_report', FEATURE, FEATURE_TITLE,
                          f'{label} — full report', 'section', _full(key), _avail(key)))
    return items
