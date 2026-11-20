"""P6 Project Expenses count in the Budgeted / Actual Total Cost (BAC / AC), in both formats.

P6's Budgeted Total Cost = labour + non-labour + material + EXPENSES. The parsers used to read
only the resource assignments, so a schedule costed partly as expenses lost that money from the
BAC, PV and EV (Giza Zoo 14-Nov-2026: its baseline carries 8,287,033.49 of expenses on 63
activities, BAC came out 1,319.8 M instead of P6's 1,328.1 M).

Built on the XML/XER parity fixture: the same expenses are injected into both formats as P6
writes them (<ActivityExpense> in <Project> / <BaselineProject>; the PROJCOST table).
"""
import pytest
from pathlib import Path

from p6_evm.parser import parse_file
from tests import test_parser_parity as fx

# (expense ObjectId, activity ObjectId, PlannedCost, ActualCost)
CURRENT_EXPENSES = [('81001', '70004', 1000.5, 400.25),
                    ('81002', '70004', 250.0, 0.0)]
# 69004 already has baseline resources (7000 + 2400); 69001 (A1000) has NONE - an expense-only
# baseline budget must still reach the activity.
BASELINE_EXPENSES = [('82001', '69004', 900.0, 0.0),
                     ('82002', '69001', 500.0, 0.0)]


def _xml_expense(oid, act, planned, actual, proj):
    return ('<ActivityExpense>'
            f'<ActivityObjectId>{act}</ActivityObjectId><ActualCost>{actual}</ActualCost>'
            f'<ExpenseItem>Restoration Cost</ExpenseItem><ObjectId>{oid}</ObjectId>'
            f'<PlannedCost>{planned}</PlannedCost><ProjectObjectId>{proj}</ProjectObjectId>'
            f'<RemainingCost>{planned - actual}</RemainingCost>'
            '</ActivityExpense>')


def _with_expenses_xml():
    xml = fx.build_xml()
    cur = ''.join(_xml_expense(*e, fx.PROJECT['object_id']) for e in CURRENT_EXPENSES)
    bl = ''.join(_xml_expense(*e, fx.BASELINE['object_id']) for e in BASELINE_EXPENSES)
    xml = xml.replace('</Project>', cur + '</Project>', 1)
    return xml.replace('</BaselineProject>', bl + '</BaselineProject>', 1)


def _with_expenses_xer():
    xer = fx.build_xer()
    rows = [{'cost_item_id': oid, 'task_id': act, 'proj_id': fx.PROJECT['object_id'],
             'target_cost': planned, 'act_cost': actual, 'remain_cost': planned - actual,
             'cost_name': 'Restoration Cost'} for oid, act, planned, actual in CURRENT_EXPENSES]
    rows += [{'cost_item_id': oid, 'task_id': act, 'proj_id': fx.BASELINE['object_id'],
              'target_cost': planned, 'act_cost': actual, 'remain_cost': planned - actual,
              'cost_name': 'Restoration Cost'} for oid, act, planned, actual in BASELINE_EXPENSES]
    table = fx._xer_table('PROJCOST', ['cost_item_id', 'task_id', 'proj_id', 'target_cost',
                                       'act_cost', 'remain_cost', 'cost_name'], rows)
    head, tail = xer.rsplit('%E', 1)
    return head + '\r\n'.join(table) + '\r\n%E' + tail


@pytest.fixture
def parsed(tmp_path):
    return {
        'xml_plain': parse_file(fx._write(tmp_path, 'plain.xml', fx.build_xml())),
        'xer_plain': parse_file(fx._write(tmp_path, 'plain.xer', fx.build_xer())),
        'xml': parse_file(fx._write(tmp_path, 'exp.xml', _with_expenses_xml())),
        'xer': parse_file(fx._write(tmp_path, 'exp.xer', _with_expenses_xer())),
    }


@pytest.mark.parametrize('fmt', ['xml', 'xer'])
def test_current_expenses_add_to_budget_and_actual_cost(parsed, fmt):
    plain, exp = parsed[fmt + '_plain'], parsed[fmt]
    assert exp.bac_by_activity['70004'] == pytest.approx(plain.bac_by_activity['70004'] + 1250.5)
    assert exp.ac_by_activity['70004'] == pytest.approx(plain.ac_by_activity['70004'] + 400.25)
    # nothing else moves, and expenses are not resources
    for oid in plain.bac_by_activity:
        if oid != '70004':
            assert exp.bac_by_activity[oid] == plain.bac_by_activity[oid]
    assert exp.assignments_by_activity == plain.assignments_by_activity


@pytest.mark.parametrize('fmt', ['xml', 'xer'])
def test_baseline_budget_includes_baseline_expenses(parsed, fmt):
    plain, exp = parsed[fmt + '_plain'], parsed[fmt]
    assert exp.baseline_bac_by_activity['70004'] == pytest.approx(
        plain.baseline_bac_by_activity['70004'] + 900.0)
    # an activity whose baseline budget is ONLY an expense still gets it
    assert '70001' not in plain.baseline_bac_by_activity
    assert exp.baseline_bac_by_activity['70001'] == pytest.approx(500.0)
    assert exp.baseline_bac_by_code['A1000'] == pytest.approx(500.0)


def test_expenses_read_the_same_in_xml_and_xer(parsed):
    for field in ('bac_by_activity', 'ac_by_activity', 'baseline_bac_by_activity', 'baseline_bac_by_code'):
        x, r = getattr(parsed['xml'], field), getattr(parsed['xer'], field)
        assert set(x) == set(r), field
        assert all(abs(x[k] - r[k]) <= fx.XER_MONEY_HALF_UNIT * 10 + 1e-9 for k in x), field


def test_expenses_flow_into_bac_pv_ev(parsed):
    """EVM's BAC grows by the baseline expenses; EV = budget x % complete picks them up."""
    import json
    from p6_evm.metrics import compute
    from p6_evm.classify import auto_categories, build_wbs_classifier

    def run(d):
        cfg = json.loads((Path(__file__).resolve().parents[1] / 'config.json').read_text())
        cfg['categories'] = auto_categories(d)
        return compute(d, cfg, classifier=build_wbs_classifier(d))

    before, after = run(parsed['xml_plain']), run(parsed['xml'])
    bac = lambda r: sum(c['bac'] for c in r['categories'].values() if c['bac'] > 0)  # noqa: E731
    assert bac(after) == pytest.approx(bac(before) + 900.0 + 500.0)
    assert after['ac'] == pytest.approx(before['ac'] + 400.25)
    assert after['ev'] >= before['ev'] and after['pv'] >= before['pv']


# ── The real file the planner reported (skipped when the sample folder is absent) ───────────
GIZA = Path.home() / 'Desktop' / 'XER File Test' / 'Updates' / 'Updates XML' / 'Giza Zoo-Z-UP-14-Nov.2026.xml'


@pytest.mark.skipif(not GIZA.exists(), reason='Giza Zoo sample not on this machine')
def test_giza_zoo_bac_matches_p6_budgeted_total_cost():
    """P6 Budgeted Total Cost 1,328,099,999.99: baseline resources 1,319,812,966.50 + 63
    baseline expenses 8,287,033.49 (the update itself has the money on resources)."""
    from p6_evm.baseline import load_schedule
    d = load_schedule(str(GIZA), None)
    assert sum(d.baseline_bac_by_code.values()) == pytest.approx(1328099999.99, abs=0.01)
    assert sum(d.bac_by_activity.values()) == pytest.approx(1328099999.99, abs=0.01)
