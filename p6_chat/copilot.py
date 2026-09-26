"""Backend bridge — expose the ported AI-Copilot engines (``p6_copilot`` / ``p6_claims``
/ ``p6_evm.copilot``) to the Offline AI Chat.

This is a thin, fully-guarded adapter. It re-uses the *proven* assembly and validation
patterns from the standalone Copilot server (``_copilot_context`` and the
``_handle_copilot_*`` / ``_handle_claims_*`` handlers) so the in-chat Copilot answers with
exactly the same numbers. Nothing here computes a metric of its own:

  * ``project_brain`` reads the already-computed DB result (the DB read path — never
    re-parses) and normalises it into the answer engine's context;
  * ``ask`` / ``tia`` / ``manager_report`` reason over that context;
  * ``whatif`` / ``activities`` / ``scenario`` / ``impact`` re-parse the schedule (the
    sanctioned report/PDF exception) because they need the full ``ScheduleData``.

Every public function returns a JSON-ready dict; failures come back as
``{'ok': False, 'error': ...}`` rather than raising, and ``project_brain`` returns ``None``
when there is no loaded project.
"""
import os
import re
import sys


def _boot():
    """Make the project root importable (bundle-safe, mirrors the server handlers) and
    return the ``db`` module. Called at the top of every public function before the
    engine packages are imported — exactly as the server's handlers do."""
    from utils import resource_path
    sys.path.insert(0, resource_path('.'))
    import db
    return db


# ── the project 'brain' (DB read path — never re-parses) ──────────────────────

def project_brain(snapshot_id):
    """Assemble the Copilot's project context from the DB for the loaded snapshot's
    project: metrics + finish dates + audit findings + the previous update's delay (for
    the trend) + the planned/actual history (for the S-curve). Reads only. Mirrors the
    proven ``_copilot_context``. Returns the context dict (with ``_result`` and
    ``history`` attached) or ``None`` when there is no project/result."""
    if not snapshot_id:
        return None
    try:
        db = _boot()
        pid = db.get_project_id_for_snapshot(snapshot_id)
        if not pid:
            return None
        result = db.get_project_result(pid)          # most recent snapshot (= the loaded one)
        if not result:
            return None
        sid = result.get('_snapshot_id') or snapshot_id
        extras = db.get_evm_extras(sid) or {}
        result['baseline_finish'] = extras.get('baseline_finish')
        result['expected_finish'] = extras.get('expected_finish')
        audit = db.get_audit_modules_for_snapshot(sid)
        all_snaps = db.get_project_snapshots(pid)
        delayed = [s for s in all_snaps if s.get('delay_days') is not None]
        # Trend = this update vs the previous DISTINCT update period. Re-importing the same
        # file (documented, e.g. to change category weights) creates another snapshot with the
        # SAME data_date; comparing to delayed[-2] would then compare same-period re-imports (or
        # a snapshot to itself). So pick the latest delayed snapshot whose data_date is strictly
        # earlier than the loaded snapshot's (data_date is a sortable 'YYYY-MM-DD HH:MM:SS' string).
        cur_dd = result.get('data_date')
        prev_delay = None
        if cur_dd is not None:
            earlier = [s for s in delayed if s.get('data_date') and str(s['data_date']) < str(cur_dd)]
            if earlier:
                prev_delay = earlier[-1]['delay_days']
        if prev_delay is None and cur_dd is None and len(delayed) >= 2:
            prev_delay = delayed[-2]['delay_days']   # fallback only when the current date is unknown
        from p6_copilot.context import build_context
        ctx = weigh_driver(build_context(result, audit=audit, prev_delay=prev_delay))
        # Planned/actual history for the Manager Report S-curve (DB-only — never re-parses).
        # One point per UPDATE (data date): re-importing the same file adds snapshots, not history.
        by_date = {}
        for s in all_snaps:
            if s.get('data_date'):
                by_date[str(s['data_date'])] = {'date': s.get('data_date'),
                                                'planned': s.get('overall_planned_pct'),
                                                'actual': s.get('overall_actual_pct')}
        ctx['history'] = list(by_date.values())
        ctx['_result'] = result
        return ctx
    except Exception:
        return None


# ── chat-side corrections to what the Copilot engine is given and says ────────
# p6_copilot itself is left unchanged; the chat corrects its inputs and its wording here.

def weigh_driver(ctx):
    """The Copilot context names the discipline with the widest RAW gap as the one causing the
    delay — so a 1%-weight design line 74 points behind outranks a 95%-weight construction front
    21 points behind, although the construction front moves the finish ~27x more. The chat names
    the WEIGHTED driver (weight x gap) everywhere, so hand the engine that one as
    ``worst_discipline`` and keep the raw leader as ``widest_gap``."""
    if not isinstance(ctx, dict):
        return ctx
    behind = [d for d in (ctx.get('disciplines') or []) if (d.get('gap') or 0) > 0]
    ctx['widest_gap'] = max(behind, key=lambda d: d['gap']) if behind else None
    ctx['worst_discipline'] = (max(behind, key=lambda d: d['gap'] * (d.get('weight') or 0))
                               if behind else None)
    return ctx


def engine_view(ctx):
    """A copy of the context for the engine's text, with the disciplines in weighted order, so its
    "after that, keep an eye on…" list follows what moves the finish, not the raw gap. The chat's own
    ctx (and the raw-gap order its facts use) is left as it is."""
    if not isinstance(ctx, dict):
        return ctx
    view = dict(ctx)
    view['disciplines'] = sorted(ctx.get('disciplines') or [],
                                 key=lambda d: -((d.get('gap') or 0) * (d.get('weight') or 0)))
    return view


# The engine's sentences call its driver "the biggest gap" / "the furthest behind" — true of the raw
# leader, not of the weighted driver the chat now hands it. Most specific phrase first. When the
# project is not behind there is no delay to drag, so the driver is described against its own plan.
_WORDING_ALWAYS = (
    ("— the biggest gap on the project.",
     "— the gap that moves the finish most, once each area's share of the job is weighed in."),
    ("— the biggest gap.", "— the gap that moves the finish most."),
    ("The largest schedule variance sits in ", "The largest weighted schedule variance sits in "),
    ("carries the largest variance (", "carries the largest weighted variance ("),
    ("holds the largest variance (", "holds the largest weighted variance ("),
)
_WORDING_BEHIND = (
    ("— it's already the furthest behind.", "— it's already the biggest drag on the finish."),
    ("— it's the furthest behind.", "— it's the biggest drag on the finish."),
    ("is the furthest behind.", "is the biggest drag on the finish."),
)
_WORDING_NOT_BEHIND = (
    ("— it's already the furthest behind.", "— it already has the largest weighted shortfall against its own plan."),
    ("— it's the furthest behind.", "— it has the largest weighted shortfall against its own plan."),
    ("is the furthest behind.", "has the largest weighted shortfall against its own plan."),
)
_BARE_GAP = re.compile(r'\((\d+) behind\)')          # "Design (74 behind)" reads as 74 days beside a wd delay
_WORKS_WORK = re.compile(r'(\*\*[^*]*\bWorks?\*\*) work\b')   # "**Construction Works** work" → "**Construction Works**"


def _inputs_text(late, k=3):
    """'Layout Approval (+122 wd), Design Road Level (+114 wd) and 5 more' from late client-input rows."""
    names = [' '.join(str(x['name']).split()) + (f" ({x['slip_wd']:+d} wd)" if x.get('slip_wd') is not None else '')
             for x in late[:k]]
    more = len(late) - len(names)
    return ', '.join(names) + (f" and {more} more" if more > 0 else '')


def _client_wording(late):
    """The engine says client-caused delays 'aren't in the schedule'. When the P6 file carries late client
    inputs, that is false — name them instead."""
    n = len(late)
    what = f"{n} client input{'s are' if n != 1 else ' is'} late and still open — {_inputs_text(late)}"
    return (
        ("What the schedule itself shows leans execution-side (progress and out-of-order work). Any client-caused "
         "delays — late access, late drawings, variations — aren't in the schedule and must be added to judge who "
         "owns the delay.",
         f"The schedule shows evidence on both sides. On the employer side, {what}. On the contractor side, the work "
         "that sets the finish hasn't progressed as planned. Who owns each part of the delay needs a time-impact "
         "analysis — one update can't split it."),
        ("Any client-side causes (e.g. late access, late information) aren't in the schedule — note them in the "
         "Claims tool to complete the ownership picture.",
         f"The schedule also shows {what}. Log each as a potential delay event and make sure a notice is on record."),
    )


def chat_wording(obj, behind=True, late=None):
    """Apply the chat's corrections to every string in an engine answer / report dict.
    ``behind`` = the finish is actually late (delay_days > 0); ``late`` = the file's late, still-open
    client inputs (so client-side delays are named, not called absent)."""
    if isinstance(obj, str):
        for old, new in (_WORDING_ALWAYS + (_WORDING_BEHIND if behind else _WORDING_NOT_BEHIND)
                         + (_client_wording(late) if late else ())):
            obj = obj.replace(old, new)
        return _WORKS_WORK.sub(r'\1', _BARE_GAP.sub(r'(\1 pts behind)', obj))
    if isinstance(obj, list):
        return [chat_wording(x, behind, late) for x in obj]
    if isinstance(obj, dict):
        return {k: chat_wording(v, behind, late) for k, v in obj.items()}
    return obj


def _state(days):
    """Signed plain position: 'about 3 months late' / 'about 2 weeks ahead' / 'on the planned date'."""
    if days is None:
        return None
    if days == 0:
        return "on the planned date"
    d = abs(days)
    months, weeks = round(d / 21), max(1, round(d / 5))
    size = (f"about {months} months" if months >= 2 else f"about {weeks} weeks" if weeks >= 2 else
            f"about {d} working day{'s' if d != 1 else ''}")
    return f"{size} {'late' if days > 0 else 'ahead'}"


def fix_report(report, ctx):
    """The engine's briefing drops the delay's sign in its trend line and finish tile (a project 20 wd
    ahead read as '4 weeks late'). Rebuild those from the signed delay; tidy the forecast note."""
    delay = ctx.get('delay_days')
    t = ctx.get('trend')
    if report.get('trend') and t and delay is not None:
        head = {'worse': 'Getting worse', 'better': 'Improving'}.get(t.get('direction'), 'About the same')
        report['trend'] = dict(report['trend'],
                               text=f"{head} — {_state(t.get('prev_delay'))} last update, {_state(delay)} now.")
    if report.get('finish') and delay is not None:
        report['finish'] = dict(report['finish'], later=_state(delay))
    det = report.get('detail') or {}
    if det.get('forecast_note') and delay and delay > 0:
        drv = (ctx.get('worst_discipline') or {}).get('name') or 'the works in progress'
        report['detail'] = dict(det, forecast_note=(
            f"The forecast — {_state(delay)} — assumes {drv} finishes on its current dates. To see the finish date "
            "if it slips further, the what-if gives the exact number."))
    return report


def engine_answer(qid, ctx, mode):
    """One Copilot-engine answer as the chat shows it: weighted driver, weighted wording, the file's late
    client inputs named, and no "causing the delay" when the finish isn't late."""
    from p6_copilot.answers import answer
    delay = (ctx or {}).get('delay_days')
    behind = delay is not None and delay > 0
    worst = (ctx or {}).get('worst_discipline')
    if qid == 'which_wbs' and not behind:
        pos = ("the finish is on its planned date" if delay == 0 else
               f"the finish is about {abs(delay)} working days ahead" if delay is not None else
               "this update has no finish-milestone delay to attribute")
        body = [f"There's no delay to completion to put on any area — {pos}."]
        if worst:
            body.append(f"The area with the largest weighted shortfall against its own plan is **{worst['name']}**: about "
                        f"**{worst['actual']}%** done against **{worst['planned']}%** planned. It isn't moving the "
                        "finish today, but it's the one to watch.")
        return {'headline': "No part of the project is delaying the finish right now.", 'body': body,
                'advice': ([f"Keep **{worst['name']}** on the watch list so it doesn't start eating the float."]
                           if worst else []), 'evidence': []}
    return chat_wording(answer(qid, engine_view(ctx), mode), behind, (ctx or {}).get('net_late_inputs'))


_NOT_CONSTRUCTION = re.compile(r'\b(design|engineering|shop drawings?|drawings? (issue|approval|submission)|'
                               r'submittals?|procure\w*|purchas\w*|tender\w*|approvals?|permits?|FAT|'
                               r'factory acceptance|right of way|wayleave|land acquisition)\b', re.I)


def _a(word):
    """'a' or 'an' before a type name — by sound: an Airports, an HVDC, a Silos."""
    w = (word or '').strip()
    first = w.split(' ')[0] if w else ''
    if first.isupper() and len(first) > 1:                        # an acronym is read letter by letter
        return 'an' if first[0] in 'AEFHILMNORSX' else 'a'
    return 'an' if first[:1].lower() in 'aeiou' else 'a'


def _acts(n):
    return f"{n:,} activit{'y' if n == 1 else 'ies'}"


def project_needs(N):
    """'What does this project type usually need?' — answered by the chat itself. The Copilot engine
    guesses the type from the project NAME, which can mislead; the chat reads the file's WBS and
    activity names against the Knowledge Base (the same read as merged q12) and checks each item the
    type needs against the file. Construction / execution items only."""
    nok = bool((N or {}).get('ok'))
    if not nok:
        return {'headline': "I need your P6 file to name the project type.",
                'body': ["I read the project type from the WBS and activity names in the file, not from the project "
                         "name — a name can mislead. The file couldn't be read for this snapshot."],
                'advice': ["Send the P6 file (📎) and ask again."], 'evidence': []}
    try:
        from p6_chat.merged import q12
        t = q12.detect_type(N)
    except Exception:
        t = None
    if not t:
        return {'headline': "None of the Knowledge Base types matches this file strongly enough to name one.",
                'body': ["I matched the WBS and activity names against every Knowledge Base project type and no type's "
                         "signatures cover enough of the file to call it."],
                'advice': ["Open the Knowledge Base, pick the closest type yourself, and compare its reference build "
                           "order with your WBS."], 'evidence': []}
    label = (t.get('type') or 'this') + (f" ({t['category']})" if t.get('category') else '')
    entry = t.get('entry') or {}
    # The same presence read as the q12 reference-sequence table: your construction activities assigned to the
    # type's WBS phases; testing / commissioning / handover read from the commissioning words.
    acts, cacts = q12.file_activities(N)
    phases, counts = q12.kb_presence(entry, cacts)
    comm = q12.commissioning_hits([a['name'] for a in cacts], N)
    idx = {(ph.get('name') or '').strip().lower(): i for i, (ph, _) in enumerate(phases)}
    by_phase = {}
    for x in cacts:
        by_phase.setdefault(q12._assign(x['name'], phases, x['wbs_path']), []).append(x['name'])
    body = [f"From your file's activities and WBS — not the project name — this "
            f"{'looks like' if t.get('confident') else 'may be'} {_a(label)} **{label}** project: the best fit of "
            f"{t.get('n_types')} Knowledge Base types, with {t.get('cover', 0):,} of your {_acts(len(acts))} matching its "
            f"signatures ({', '.join((t.get('hits') or [])[:4])})"
            + (f"; {t['runner']} is the runner-up" if t.get('runner') else '') + '.'
            + ('' if t.get('confident') else " The margin is narrow, so confirm the type in the Knowledge Base.")]
    needs = [a for a in (entry.get('activities') or []) if a.get('name') and not _NOT_CONSTRUCTION.search(a['name'])]
    missing = []
    if needs:
        body.append("What this type usually needs on site, checked against your construction activities:")
        for a in needs:
            phase = (a.get('wbs') or '').strip().lower()
            if q12._has(phase, ('test', 'commission', 'handover')):
                found = comm
            else:
                found = by_phase.get(idx[phase], []) if phase in idx else []
            if found:
                body.append(f"• **{a['name']}** — present: {_acts(len(found))} in your file, e.g. {found[0]}.")
            else:
                missing.append(a['name'])
                body.append(f"• **{a['name']}** — not visible in your file. Confirm it's in scope, or add it and tie it "
                            "into the logic.")
    issues = [str(i) for i in (entry.get('common_issues') or [])][:4]
    if issues:
        body.append("Common pitfalls for this type: " + '; '.join(issues) + '.')
    n_miss = len(missing)
    advice = [(f"Check {'the item' if n_miss == 1 else f'the {n_miss} items'} not visible first — "
               f"{'it is' if n_miss == 1 else 'each is'} either under another name in P6 or missing scope." if missing else
               "Every item this type usually needs appears in your file — confirm each is logic-linked into the chain."),
              f"Open the Knowledge Base, pick **{t.get('type')}**, and compare its reference build order with your WBS."]
    return {'headline': f"What {_a(label)} {label} programme usually needs — checked against your file:",
            'body': body, 'advice': advice,
            'evidence': [{'module': 'Knowledge Base', 'plain': 'Best-fit type (from WBS + activity names)',
                          'value': label}]}


# ── ask one repertoire / free-typed question ──────────────────────────────────

def ask(snapshot_id, question_id=None, question_text=None, mode='management'):
    """Answer one question from the offline engine. A repertoire ``question_id`` (button)
    is answered directly; a freely-typed ``question_text`` is resolved to the nearest
    repertoire question by keyword intent-matching, falling back to a graceful offline
    deferral when nothing matches. Never touches the cloud."""
    ctx = project_brain(snapshot_id)
    if ctx is None:
        return {'ok': False, 'error': 'Open a schedule first, then ask the Copilot.'}
    try:
        _boot()
        from p6_copilot.answers import answer
        from p6_copilot.questions import label_for
        mode = mode or 'management'
        qid = (question_id or '').strip()
        text = (question_text or '').strip()
        interpreted = None
        if not qid and text:
            from p6_copilot.intent import match_intent
            qid, matched = match_intent(text, mode)
            if not matched or not qid:
                a = answer('__unknown__', ctx, mode)      # graceful offline deferral
                return {'ok': True, 'answer': a, 'matched': False,
                        'question_id': None, 'question_label': text}
            interpreted = label_for(qid, mode)
        from p6_chat import analysis
        N = analysis.network(snapshot_id)
        if qid == 'project_needs':
            a = project_needs(N)
        else:
            ctx['net_late_inputs'] = N.get('client_inputs_late_open') or [] if N.get('ok') else []
            a = engine_answer(qid, ctx, mode)
        return {'ok': True, 'answer': a, 'matched': True, 'question_id': qid,
                'question_label': interpreted or label_for(qid, mode)}
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}


# ── TIA decomposition + insights (DB result, no re-parse) ─────────────────────

def tia(snapshot_id):
    """Finish-slip decomposition (to-date / performance / weather) + the ranked insights
    for the loaded project, from the same ``build_copilot`` the EVM tab uses."""
    ctx = project_brain(snapshot_id)
    if ctx is None:
        return {'ok': False, 'error': 'Open a schedule first, then ask the Copilot.'}
    try:
        _boot()
        from p6_evm.copilot import build_copilot
        out = build_copilot(ctx['_result']) or {}
        return {'ok': True, 'tia': out.get('tia'), 'insights': out.get('insights'),
                'has_forecast': out.get('has_forecast')}
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}


# ── instant offline what-if ESTIMATE (needs the parsed schedule) ──────────────

def whatif(xml_path, kind, activity_id=None, days=None):
    """Instant, offline what-if ESTIMATE from the parsed update (float + critical path).
    ``kind``: delay / shorten / add_crew / overtime / remove_relationship / six_day. The
    exact figure stays the planner's F9 path — this is a clearly-labelled estimate."""
    try:
        _boot()
        from p6_evm.parser import parse_file
        from p6_copilot.whatif import estimate
        activity_id = (activity_id or '').strip() or None
        try:
            days = float(days) if days is not None else None
        except (TypeError, ValueError):
            days = None
        data = parse_file(xml_path)
        return {'ok': True, 'result': estimate(data, kind, activity_id=activity_id, days=days)}
    except (KeyError, ValueError) as exc:
        return {'ok': False, 'error': str(exc)}
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}


# ── activity picker (needs the parsed schedule) ───────────────────────────────

def activities(xml_path):
    """Activity list (id, name, WBS path, milestone flag) for the Copilot's activity
    picker — from the parsed schedule, sorted by id."""
    try:
        _boot()
        from p6_evm.parser import parse_file
        data = parse_file(xml_path)
        acts = sorted(
            ({'id': a['id'], 'name': a.get('name') or '', 'wbs_path': a.get('wbs_path') or '',
              'is_milestone': a.get('task_type') in ('StartMilestone', 'FinishMilestone')}
             for a in data.activities.values() if a.get('id')),
            key=lambda x: x['id'])
        return {'ok': True, 'activities': acts}
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}


# ── build a what-if scenario programme to F9 in P6 ────────────────────────────

def scenario(xml_path, kind, activity_id=None, days=None, output_path=None, label=None):
    """Write a what-if scenario programme (delay / shorten / six_day) for the planner to
    open in P6 and F9. The exact impact is then read back via ``impact`` — P6's own
    number, never computed here."""
    activity_id = (activity_id or '').strip() or None
    try:
        days = float(days) if days is not None else None
    except (TypeError, ValueError):
        days = None
    if not output_path:
        return {'ok': False, 'error': 'No output path provided.'}
    if kind in ('delay', 'shorten'):
        if not activity_id:
            return {'ok': False, 'error': 'Pick the activity first.'}
        if not days or days <= 0:
            return {'ok': False, 'error': 'Enter a number of working days (at least 1).'}
    try:
        _boot()
        from p6_evm.parser import parse_file
        from p6_claims.scenarios import build_scenario
        data = parse_file(xml_path)
        day_hours = 8.0
        act_name = None
        if activity_id:
            act = next((a for a in data.activities.values() if a.get('id') == activity_id), None)
            if act is None:
                return {'ok': False, 'error': f'Activity {activity_id} not found in the schedule.'}
            cal = data.calendars.get(act.get('calendar_id'))
            day_hours = cal.day_hours if cal else 8.0
            act_name = act.get('name') or activity_id
        with open(xml_path, encoding='utf-8') as f:
            xml_text = f.read()
        out = build_scenario(xml_text, kind, activity_id=activity_id, days=days,
                             day_hours=day_hours, label=(label or None))
        abs_out = os.path.abspath(output_path)
        with open(abs_out, 'w', encoding='utf-8') as f:
            f.write(out['xml'])
        return {'ok': True, 'output_path': abs_out, 'label': out.get('label'),
                'activity_name': out.get('activity_name') or act_name}
    except (KeyError, ValueError) as exc:
        return {'ok': False, 'error': str(exc)}
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}


# ── read P6's exact TIA impact (base vs the F9-rescheduled file) ──────────────

def impact(xml_path, rescheduled_path):
    """Read the exact TIA impact — how far completion moved between the base update and the
    F9-rescheduled file the planner re-exported from P6. The day-count is P6's; nothing is
    computed here."""
    if not rescheduled_path or not os.path.isfile(rescheduled_path):
        return {'ok': False, 'error': 'Load the rescheduled P6 file you exported after F9.'}
    try:
        _boot()
        from p6_evm.parser import parse_file
        from p6_claims.tia import compute_impact
        base_data = parse_file(xml_path)
        impacted_data = parse_file(rescheduled_path)
        imp = compute_impact(base_data, impacted_data)
        if imp.get('impact_days') is None:
            return {'ok': False, 'error': (
                'Could not read a completion date from the files — check the rescheduled export.')}
        return {'ok': True, 'impact': imp}
    except (KeyError, ValueError) as exc:
        return {'ok': False, 'error': str(exc)}
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}


# ── the plain-English Manager Report (preview HTML or a written PDF) ──────────

def manager_report(snapshot_id, xml_path=None, preview=True, output_path=None, meta=None):
    """Build the plain-English Manager Report. ``preview`` returns the report dict + HTML;
    otherwise a PDF is written to ``output_path`` via headless Chrome. When behind and the
    XML is available, the drivers/recovery are enriched by a best-effort re-parse (the
    sanctioned report exception) — the report still renders if the XML is unavailable."""
    ctx = project_brain(snapshot_id)
    if ctx is None:
        return {'ok': False, 'error': 'Open a schedule first, then generate the report.'}
    if not preview and not output_path:
        return {'ok': False, 'error': 'No output path provided'}
    try:
        _boot()
        # Drivers + recovery explain and fix a *delay* — only compute them when behind, and
        # only when the XML is available (they need the full ScheduleData). Best-effort.
        try:
            if xml_path and (ctx.get('delay_days') or 0) > 0:
                from p6_evm.parser import parse_file
                from p6_copilot.briefing import critical_drivers, recovery_estimate
                data = parse_file(xml_path)
                ctx['drivers'] = critical_drivers(data)
                ctx['recovery'] = recovery_estimate(data)
        except Exception:
            pass
        from p6_copilot.report import build_manager_report, render_manager_report_html
        try:
            from p6_chat import analysis
            N = analysis.network(snapshot_id)
            ctx['net_late_inputs'] = N.get('client_inputs_late_open') or []
            fin = N.get('finish_milestone') or {}
            if not ctx.get('baseline_finish') and fin.get('baseline_finish'):
                ctx['baseline_finish'] = fin['baseline_finish']       # stored extras missing → P6's own dates
            if not ctx.get('forecast_finish') and fin.get('finish'):
                ctx['forecast_finish'] = fin['finish']
        except Exception:
            ctx['net_late_inputs'] = []
        report = fix_report(chat_wording(build_manager_report(engine_view(ctx)), (ctx.get('delay_days') or 0) > 0,
                                         ctx['net_late_inputs']), ctx)
        html_content = render_manager_report_html(report, meta or {})
        if (report.get('finish') or {}).get('later'):
            import html as _h
            later = _h.escape(report['finish']['later'])
            html_content = html_content.replace(f"· {later} later</div>", f"· {later}</div>")
        if preview:
            return {'ok': True, 'report': report, 'html': html_content}
        import subprocess
        import tempfile
        from server import _find_chrome
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w', encoding='utf-8') as tmp:
            tmp.write(html_content)
            html_path = tmp.name
        try:
            chrome = _find_chrome()
            subprocess.run([
                chrome, '--headless', '--disable-gpu', '--no-sandbox',
                f'--print-to-pdf={os.path.abspath(output_path)}', '--no-pdf-header-footer',
                f'file:///{html_path.replace(os.sep, "/")}',
            ], check=True, capture_output=True)
        finally:
            try:
                os.unlink(html_path)
            except OSError:
                pass
        return {'ok': True}
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}
