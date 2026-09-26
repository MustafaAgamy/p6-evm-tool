"""Grounded FACTS for the Offline AI Chat answer engine.

`build_facts(snapshot_id)` assembles ONE flat, plain, None-safe dict of everything the
182 library questions can be answered from — read-only, from the DB snapshot (never
re-parses). It reuses the proven ``p6_chat.copilot.project_brain`` context (EVM + delay +
progress-by-discipline + trend + the previous update) and enriches it with every stored
audit module's grade + KPIs (float, out-of-sequence, negative float, CPLI, dangling,
open ends, constraints, leads/lags, …).

The answer functions in ``p6_chat.qa`` read ONLY from this dict, so grounding lives in one
place and every answer cites the same numbers the EVM tab and the audit screens show.
Nothing here computes a metric of its own; a fact that isn't stored comes back ``None`` and
the answer degrades honestly (judgement + a pointer to the feature that computes it).

Sign convention (matches the whole tool after the delay-sign fix): ``delay_days`` is
working days LATE to completion — POSITIVE = behind, negative = ahead, 0 = on the date.
"""


def _num(v):
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _weeks(days):
    d = _num(days)
    return None if d is None else max(1, round(abs(d) / 5))


def _mod(audit, name):
    """One stored audit module dict ({grade, score, pct, kpis, findings, …}) or {}."""
    if not isinstance(audit, dict):
        return {}
    mods = audit.get('modules') or {}
    return mods.get(name) or {}


def add_network(F, N):
    """Add what the re-read P6 file shows (``p6_chat.analysis.network``) to the FACTS, so the library
    answers speak from the same finish chain, client inputs and commissioning read as the 15 merged
    answers instead of guessing. Keys are prefixed ``net_``; ``net_ok`` is False when the file couldn't
    be read (answers then fall back to the stored analysis). Also fills a missing baseline / forecast
    finish from the finish milestone. Stored values always win. Never raises."""
    F['net_ok'] = bool((N or {}).get('ok'))
    if not F['net_ok']:
        return F
    try:
        fin = N.get('finish_milestone') or {}
        if not F.get('baseline_finish') and fin.get('baseline_finish'):
            F['baseline_finish'] = fin['baseline_finish']
        if not F.get('forecast_finish') and fin.get('finish'):
            F['forecast_finish'] = fin['finish']
        chain = list(N.get('chain') or [])
        tfs = [x['tf'] for x in chain if x.get('tf') is not None]
        F.update({
            'net_finish_name': fin.get('name'),
            'net_finish_tf': N.get('finish_tf'),
            'net_chain_count': N.get('chain_count') or len(chain),
            'net_chain_started': sum(1 for x in chain if (x.get('pct') or 0) > 0),
            'net_chain_tf_min': min(tfs) if tfs else None,
            'net_chain_tf_max': max(tfs) if tfs else None,
            'net_chain_head': chain[0] if chain else None,
            'net_late_inputs': list(N.get('client_inputs_late_open') or []),
            'net_late_inputs_done': list(N.get('client_inputs_late_done') or []),
            'net_client_inputs': len(N.get('client_inputs') or []),
        })
        from p6_chat.merged import q12
        _, cacts = q12.file_activities(N)
        F['net_commissioning'] = bool(q12.commissioning_hits([a['name'] for a in cacts], N))
    except Exception:
        pass
    try:
        # the same DCMA scorecard the schedule-health answer shows, so both quote one pass / fail count
        if F.get('audit'):
            from p6_chat.merged import q06
            rows, _ = q06._scorecard(F, N, True, N.get('finish_milestone') or {}, F.get('net_chain_count') or 0)
            fails = [r for r in rows if r['state'] == 'fail']
            scored = len(fails) + sum(1 for r in rows if r['state'] == 'pass')
            plain = {1: 'logic links', 2: 'leads', 3: 'lags', 4: 'relationship mix (FS share)', 5: 'hard constraints',
                     6: 'high float', 7: 'negative float', 8: 'long durations', 12: 'critical path test', 13: 'CPLI'}
            F['net_dcma'] = {'scored': scored, 'fails': [r['label'] for r in fails],
                             'names': [plain.get(r['no'], r['label']) for r in fails]}
    except Exception:
        pass
    return F


def build_facts(snapshot_id):
    """Return the grounded FACTS dict for the loaded snapshot's project, or a dict with
    ``ok=False`` when there is no project/result. Never raises."""
    try:
        from p6_chat import copilot as _cp
    except Exception:
        return {'ok': False}
    try:
        ctx = _cp.project_brain(snapshot_id)
    except Exception:
        ctx = None
    if not ctx:
        return {'ok': False}

    result = ctx.get('_result') or {}
    # Audit modules are read straight from the DB (same read path project_brain used).
    audit = None
    extras = {}
    try:
        from p6_chat.copilot import _boot
        db = _boot()
        sid = result.get('_snapshot_id') or snapshot_id
        audit = db.get_audit_modules_for_snapshot(sid)
        extras = db.get_evm_extras(sid) or {}
    except Exception:
        audit = audit or None

    delay = ctx.get('delay_days')
    F = {
        'ok': True,
        'snapshot_id': result.get('_snapshot_id') or snapshot_id,
        # ── identity / cutoff ─────────────────────────────────────────────
        'project_name': ctx.get('project_name') or 'the project',
        'data_date': ctx.get('data_date'),
        'activity_count': result.get('activity_count'),
        'calendar_count': result.get('calendar_count'),
        # ── time / finish ─────────────────────────────────────────────────
        'baseline_finish': ctx.get('baseline_finish'),
        'forecast_finish': ctx.get('forecast_finish'),
        'delay_days': delay,
        'delay_weeks': _weeks(delay),
        'behind': ctx.get('behind'),
        'ahead': ctx.get('ahead'),
        'on_track': (delay == 0) if delay is not None else None,
        # ── EVM / cost ────────────────────────────────────────────────────
        'spi': _num(result.get('spi')),
        'cpi': _num(result.get('cpi')),
        'pv': _num(result.get('pv')),
        'ev': _num(result.get('ev')),
        'ac': _num(result.get('ac')),
        'variance': _num(result.get('variance')),
        'pace_pct': ctx.get('pace_pct'),                    # SPI as whole %
        # Actual cost that equals earned value is cost DERIVED from progress: CPI is then 1.00 by
        # construction and must never be read as "on budget".
        'cost_derived': bool(_num(result.get('ac')) and _num(result.get('ev')) and
                             abs(_num(result.get('ac')) - _num(result.get('ev'))) <= max(1.0, 1e-6 * _num(result.get('ev')))),
        'planned_pct': ctx.get('planned_pct'),              # overall planned %, whole
        'actual_pct': ctx.get('actual_pct'),                # overall actual %, whole
        # ── progress by discipline ────────────────────────────────────────
        'disciplines': ctx.get('disciplines') or [],
        'worst_discipline': ctx.get('worst_discipline'),      # weighted driver (weight x gap) — see copilot.weigh_driver
        'widest_gap': ctx.get('widest_gap'),                  # largest raw gap
        'top_gaps': [d for d in (ctx.get('disciplines') or []) if (d.get('gap') or 0) > 0][:3],
        # ── trend / history (for S-curve, period comparisons) ─────────────
        'trend': ctx.get('trend'),
        'history': ctx.get('history') or [],
        'has_history': len(ctx.get('history') or []) >= 2,
    }

    # ── audit modules: grade + KPIs, plus flat convenience scalars ─────────
    fl = _mod(audit, 'float')
    oos = _mod(audit, 'out_of_sequence')
    nf = _mod(audit, 'negative_float')
    cpli = _mod(audit, 'cpli')
    de = _mod(audit, 'dangling')
    oe = _mod(audit, 'open_ends')
    hc = _mod(audit, 'hard_constraints')
    # Stored at import: the PV-EV gap split by an activity code (e.g. Type of Works) and engineering
    # submittal status by trade. Plain dicts/lists or None.
    F['value_gap'] = extras.get('gap') if isinstance(extras, dict) else None
    F['submittals'] = extras.get('engineering_p6') if isinstance(extras, dict) else None
    F['has_audit'] = bool(audit and (audit.get('modules')))
    F['audit'] = {
        name: {'grade': m.get('grade'), 'score': m.get('score'),
               'pct': m.get('pct'), 'kpis': m.get('kpis') or {}}
        for name, m in ((audit.get('modules') or {}).items() if isinstance(audit, dict) else [])
    }
    fk = fl.get('kpis') or {}
    ok = oos.get('kpis') or {}
    nk = nf.get('kpis') or {}
    ck = cpli.get('kpis') or {}
    dk = de.get('kpis') or {}
    ek = oe.get('kpis') or {}
    F.update({
        'float_grade': fl.get('grade') or ctx.get('float_grade'),
        'float_above': fk.get('above_threshold'),
        'float_pct': fk.get('float_pct'),
        'float_threshold': fk.get('threshold'),
        'max_float': fk.get('max_float'),
        'avg_float': fk.get('avg_float'),
        'neg_float_count': nk.get('negative_count'),
        'neg_float_pct': nk.get('neg_pct'),
        'neg_float_grade': nf.get('grade'),
        'oos_count': ok.get('oos_count') if ok.get('oos_count') is not None else ctx.get('oos_count'),
        'oos_pct': ok.get('oos_pct'),
        'critical_oos': ok.get('critical_oos'),
        'oos_grade': oos.get('grade'),
        'cpli_critical_count': ck.get('critical_count'),
        'cpli_critical_pct': ck.get('critical_pct'),
        'driving_path_count': ck.get('driving_path_count'),
        'cpli_grade': cpli.get('grade'),
        'cpli_density_grade': ck.get('critical_density_grade'),
        'dangling_count': dk.get('total_dangling'),
        'dangling_pct': dk.get('dangling_pct'),
        'dangling_grade': de.get('grade'),
        'open_ends': ek.get('open_ends'),
        'open_ends_grade': oe.get('grade'),
        'hard_constraints_computable': (hc.get('kpis') or {}).get('computable'),
    })
    return F
