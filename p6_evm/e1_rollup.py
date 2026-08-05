"""Roll up E1 Log summary rows so uploading the E1 Log updates the whole report.

From the per-(trade, type) E1 summary we derive:
  * two overall rows — Design drawings (Schematic/Detailed/IFC/anything non-Shop)
    and Engineering drawings (Shop) — each with the same columns as the E1 table;
  * category Actual% overrides — the Design overall Approved% drives categories whose
    name contains 'design'; the Engineering (Shop) Approved% drives 'engineering';
  * two gap sets (Design, Engineering) grouped by trade, using the SAME logic as the
    PV-EV gap: gap = Planned - Approved, pct_of_gap = each trade's share of the total.

Ibrahim's rule (2026-08-04): a Shop drawing is an engineering drawing; every other
drawing type is a design drawing. Kept here as the single source of truth so the
on-screen view and the PDF never diverge.
"""


from p6_evm.classify import is_design_drawing


def is_shop(submittal_type):
    # Kept for compatibility; "engineering" now means "not a design drawing"
    # (Shop + Other + unknown), per Ibrahim's decision to count Other into Engineering.
    return not is_design_drawing(submittal_type)


def _agg(rows):
    req = sum(r.get('req') or 0 for r in rows)
    planned = sum(r.get('planned') or 0 for r in rows)
    submitted = sum(r.get('submitted_rows') or 0 for r in rows)
    approved = sum(r.get('approved_rows') or 0 for r in rows)
    not_appr = sum(r.get('not_approved_rows') or 0 for r in rows)
    under = sum(r.get('under_review_rows') or 0 for r in rows)

    def pct(n):
        return round(100.0 * n / req, 1) if req else 0.0

    return {
        'req': req, 'planned': planned, 'submitted_rows': submitted,
        'approved_rows': approved, 'not_approved_rows': not_appr, 'under_review_rows': under,
        'planned_pct': pct(planned), 'submitted_pct': pct(submitted - not_appr),
        'approved_pct': pct(approved),
    }


def _split(rows):
    """Design vs Engineering. A row's explicit 'bucket' (set when the whole file is a
    Design Log or a Shop Drawing Log) wins; otherwise classify by drawing type."""
    design, eng = [], []
    for r in rows:
        b = r.get('bucket')
        if b == 'design':
            design.append(r)
        elif b == 'engineering':
            eng.append(r)
        elif is_design_drawing(r.get('submittal_type')):
            design.append(r)
        else:
            eng.append(r)
    return design, eng


def overall_split(rows):
    """{'design': {..agg..}, 'engineering': {..agg..}} — the two overall rows."""
    design, shop = _split(rows)
    return {'design': _agg(design), 'engineering': _agg(shop)}


def category_actuals(rows, category_names):
    """{category_name: actual_fraction 0-1}. Design Approved% -> categories whose name
    contains 'design'; Engineering(Shop) Approved% -> names containing 'engineering'.

    Only override a category when its bucket actually has drawings — so uploading ONLY a
    Shop log doesn't wipe the Design categories to 0 (they keep their schedule value), and
    vice-versa."""
    split = overall_split(rows)
    d = (split['design']['approved_pct'] or 0) / 100.0
    e = (split['engineering']['approved_pct'] or 0) / 100.0
    has_design = split['design']['req'] > 0
    has_eng = split['engineering']['req'] > 0
    out = {}
    for name in category_names or []:
        low = (name or '').lower()
        if 'engineering' in low and has_eng:
            out[name] = e
        elif 'design' in low and has_design:
            out[name] = d
    return out


def _gap_groups(rows):
    by_trade = {}
    for r in rows:
        t = r.get('trade') or ''
        g = by_trade.setdefault(t, {'trade': t, 'planned': 0, 'approved': 0})
        g['planned'] += r.get('planned') or 0
        g['approved'] += r.get('approved_rows') or 0
    groups = []
    for g in by_trade.values():
        g['gap'] = g['planned'] - g['approved']
        groups.append(g)
    total = sum(g['gap'] for g in groups)
    for g in groups:
        g['pct_of_gap'] = (100.0 * g['gap'] / total) if total else 0.0
    groups.sort(key=lambda g: g['gap'], reverse=True)
    return groups


def engineering_gaps(rows):
    """{'design': [gap groups by trade], 'engineering': [gap groups by trade]}.
    Same shape/logic as PV-EV gap: gap = Planned - Approved, pct_of_gap = share of total."""
    design, shop = _split(rows)
    return {'design': _gap_groups(design), 'engineering': _gap_groups(shop)}


def trade_totals(rows):
    """Total per trade — Total Civil = every Civil drawing (Concrete Dimension + RFT + …),
    using the same agreed counting as the per-type rows."""
    by = {}
    for r in rows:
        by.setdefault(r.get('trade') or '', []).append(r)
    out = []
    for trade, rs in sorted(by.items()):
        agg = _agg(rs)
        agg['trade'] = trade
        out.append(agg)
    return out


def e1_extras(rows, category_names):
    """Everything the UI/PDF need from an E1 upload, in one call."""
    return {
        'overall': overall_split(rows),
        'by_trade': trade_totals(rows),
        'category_actuals': category_actuals(rows, category_names),
        'gaps': engineering_gaps(rows),
    }
