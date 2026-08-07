"""End-to-end: /api/baseline/upload attaches a baseline XER to an imported update XER and
recomputes EVM off the baseline's DATES and BUDGET. Before attaching, PV weights by the update's
own cost (200); after attaching the baseline (where activity A240's budget is higher), PV weights
by the baseline cost (250). This is the fix that makes a XER update match its XML.
"""
import json
import urllib.request

# Update: A230 complete, A240 not started; both baselined 01-Jan→01-Feb (planned 100% by the
# 01-Mar data date). Update budget: A230=100, A240=100.
UPDATE_XER = (
    "ERMHDR\t19.12\n"
    "%T\tPROJECT\n%F\tproj_id\tproj_short_name\tlast_recalc_date\n%R\t1\tJOB\t2026-03-01 00:00\n"
    "%T\tCALENDAR\n%F\tclndr_id\tclndr_name\tday_hr_cnt\n%R\t10\t5-Day\t8\n"
    "%T\tPROJWBS\n%F\twbs_id\twbs_name\tparent_wbs_id\tproj_node_flag\n"
    "%R\t100\tJOB\t\tY\n%R\t101\tConstruction Works\t100\tN\n"
    "%T\tTASK\n%F\ttask_id\tproj_id\twbs_id\tclndr_id\ttask_type\ttask_code\ttask_name\tstatus_code\tcomplete_pct_type\tphys_complete_pct\ttarget_drtn_hr_cnt\tremain_drtn_hr_cnt\ttarget_start_date\ttarget_end_date\ttotal_float_hr_cnt\n"
    "%R\t1001\t1\t101\t10\tTT_Task\tA230\tRoof Steel\tTK_Complete\tCP_Drtn\t100\t80\t0\t2026-01-01 00:00\t2026-02-01 00:00\t0\n"
    "%R\t1002\t1\t101\t10\tTT_Task\tA240\tRoof Cladding\tTK_NotStart\tCP_Drtn\t0\t80\t80\t2026-01-01 00:00\t2026-02-01 00:00\t0\n"
    "%T\tTASKRSRC\n%F\ttask_id\ttarget_cost\tact_reg_cost\tact_ot_cost\n%R\t1001\t100\t0\t0\n%R\t1002\t100\t0\t0\n"
    "%E\n"
)

# Baseline: same activities/dates, but A240's baseline budget is 150 (vs the update's 100).
BASELINE_XER = UPDATE_XER.replace("%R\t1002\t100\t0\t0\n", "%R\t1002\t150\t0\t0\n")


def _post(port, route, body):
    req = urllib.request.Request(
        f'http://127.0.0.1:{port}/{route}',
        data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def test_baseline_upload_reweights_pv_to_baseline_budget(test_server, tmp_path):
    up = tmp_path / 'update.xer'; up.write_text(UPDATE_XER, encoding='cp1252')
    bl = tmp_path / 'baseline.xer'; bl.write_text(BASELINE_XER, encoding='cp1252')

    parsed = _post(test_server, 'api/parse', {'path': str(up), 'overrides_path': None})
    assert parsed['ok']
    # Before attaching, PV weights by the update's own cost: 100 + 100 = 200
    assert round(parsed['result']['pv'], 2) == 200.0

    attached = _post(test_server, 'api/baseline/upload', {
        'path': str(bl), 'xml_path': str(up),
        'cached_path': parsed.get('cached_path'), 'snapshot_id': parsed.get('snapshot_id'),
    })
    assert attached['ok'], attached.get('error')
    assert attached['matched'] == 2 and attached['total'] == 2
    # After attaching, PV weights by the BASELINE budget: 100 + 150 = 250 (both planned 100%)
    assert round(attached['pv'], 2) == 250.0
    # EV = baseline-weighted actual: A230 100%*100 + A240 0%*150 = 100
    assert round(attached['ev'], 2) == 100.0
