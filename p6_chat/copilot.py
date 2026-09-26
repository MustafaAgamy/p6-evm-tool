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
        ctx = build_context(result, audit=audit, prev_delay=prev_delay)
        # Planned/actual history for the Manager Report S-curve (DB-only — never re-parses).
        ctx['history'] = [{'date': s.get('data_date'),
                           'planned': s.get('overall_planned_pct'),
                           'actual': s.get('overall_actual_pct')}
                          for s in all_snaps if s.get('data_date')]
        ctx['_result'] = result
        return ctx
    except Exception:
        return None


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
        a = answer(qid, ctx, mode)
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
        report = build_manager_report(ctx)
        html_content = render_manager_report_html(report, meta or {})
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
