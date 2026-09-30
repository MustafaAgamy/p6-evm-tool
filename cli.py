import argparse
import csv
import json
import os
import sys

from p6_evm.baseline import load_schedule, schedule_baseline
from p6_evm.metrics import compute
from utils import APP_NAME

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')


def load_config(path):
    with open(path) as f:
        return json.load(f)


def fmt_money(x):
    return f'{x:,.2f}'


def fmt_pct(x):
    return f'{x * 100:.2f}%' if x is not None else 'n/a'


def print_report(result, baseline=None):
    # The baseline the numbers are measured against — named first, never silent (R4 / R2 F5):
    # inside the schedule file, the --baseline file, or the update's own Planned dates standing
    # in (then every baseline-derived figure is marked approx, as on screen and in the PDF).
    bl = baseline or {}
    ax = '  (approx)' if bl.get('baseline_approx') else ''
    if bl.get('baseline_label'):
        print(f"Baseline: {bl['baseline_label']}")
    print(f"Data Date: {result['data_date']}")
    print(f"Delay (finish-milestone Total Float): {result['delay_days']} working days{ax}")
    print()
    print('Cost-based EVM (categories carrying budget only):')
    print(f"  Planned Value (PV): {fmt_money(result['pv'])}{ax}")
    print(f"  Earned Value  (EV): {fmt_money(result['ev'])}")
    print(f"  Actual Cost   (AC): {fmt_money(result['ac'])}")
    print((f"  SPI: {result['spi']:.4f}" if result['spi'] is not None else '  SPI: n/a') + ax)
    cpi_note = '  (structurally ~1: cost is derived from % complete, not measured independently)'
    print((f"  CPI: {result['cpi']:.4f}" if result['cpi'] is not None else '  CPI: n/a') + cpi_note)
    print(f"  Variance (EV-PV): {fmt_money(result['variance'])}"
          f" ({'behind/delayed' if result['variance'] < 0 else 'ahead/on-schedule'}){ax}")
    print()
    print(f"Overall Project Planned%: {fmt_pct(result['overall_planned_pct'])}{ax}"
          f"   Actual%: {fmt_pct(result['overall_actual_pct'])}")
    print()
    print('By category:')
    header = (f"  {'Category':<24}{'Weight':>8}{'Planned%':>12}{'Actual%':>12}"
              f"{'BAC':>18}{'AC':>18}{'#Act':>6}  Source")
    print(header)
    for name, c in result['categories'].items():
        source = 'manual override' if c.get('overridden') else 'from XML'
        print(
            f"  {name:<24}{c['weight'] * 100:>7.1f}%{fmt_pct(c['planned_pct']):>12}"
            f"{fmt_pct(c['actual_pct']):>12}{fmt_money(c['bac']):>18}{fmt_money(c['ac']):>18}"
            f"{c['activity_count']:>6}  {source}"
        )


def write_activity_csv(result, path):
    with open(path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'activity_id', 'name', 'category', 'status', 'bac', 'ac',
            'planned_pct', 'actual_pct', 'total_float',
        ])
        for r in result['records']:
            a = r['activity']
            writer.writerow([
                a['id'], a['name'], r['category'] or '', a['status'],
                r['bac'], r['ac'], r['planned_pct'], r['actual_pct'], r['total_float'],
            ])


def main():
    parser = argparse.ArgumentParser(prog=APP_NAME.lower(),
                                     description=f'{APP_NAME} — Primavera P6 EVM & delay report (CLI)')
    parser.add_argument('xml_file')
    parser.add_argument('--config', default=DEFAULT_CONFIG_PATH)
    parser.add_argument('--overrides', help=(
        'JSON file of {"Category Name": {"planned_pct": 0.81, "actual_pct": 0.09}} '
        'for categories whose progress is not derivable from the XML (e.g. '
        'drawing-count-based design progress), supplied by the user alongside the XML'
    ))
    parser.add_argument('--out', help='write per-activity breakdown to this CSV path')
    parser.add_argument('--baseline', metavar='PATH', help=(
        'the baseline schedule (XER or XML) for an update that does not carry it — a P6 XER '
        'update, or an XML exported without its baseline project; matched by Activity ID, the '
        'same way Earned Value / Update Analysis "Attach baseline" works. Ignored when the '
        'schedule file already contains its baseline'
    ))
    args = parser.parse_args()
    try:                                # a console / pipe that cannot show '—' must not crash
        sys.stdout.reconfigure(errors='replace')
        sys.stderr.reconfigure(errors='replace')
    except (AttributeError, ValueError):
        pass
    if args.baseline and not os.path.isfile(args.baseline):
        parser.error(f'--baseline: file not found: {args.baseline}')

    config = load_config(args.config)
    overrides = load_config(args.overrides) if args.overrides else None
    # ONE baseline resolution, as every feature of the app: inside the file, else --baseline,
    # else the file's own Planned dates (labelled approx) — so XER + baseline == XML with it.
    data = load_schedule(args.xml_file, args.baseline)
    info = getattr(data, 'baseline_info', None) or {}
    if args.baseline and info.get('source') == 'embedded':
        print('Note: the schedule file contains its own baseline — --baseline was not used.',
              file=sys.stderr)
    elif args.baseline and info.get('matched') == 0:
        print(f"Warning: {args.baseline} matches none of the schedule's Activity IDs "
              f'(another project?) — not applied.', file=sys.stderr)
    result = compute(data, config, overrides=overrides)
    print_report(result, schedule_baseline(data))

    if args.out:
        write_activity_csv(result, args.out)
        print(f"\nPer-activity breakdown written to {args.out}")


if __name__ == '__main__':
    sys.exit(main())
