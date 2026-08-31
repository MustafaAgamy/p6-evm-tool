import argparse
import csv
import json
import os
import sys

from p6_evm.metrics import compute
from p6_evm.parser import parse_file

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')


def load_config(path):
    with open(path) as f:
        return json.load(f)


def fmt_money(x):
    return f'{x:,.2f}'


def fmt_pct(x):
    return f'{x * 100:.2f}%' if x is not None else 'n/a'


def print_report(result):
    print(f"Data Date: {result['data_date']}")
    print(f"Delay (finish-milestone Total Float): {result['delay_days']} working days")
    print()
    print('Cost-based EVM (categories carrying budget only):')
    print(f"  Planned Value (PV): {fmt_money(result['pv'])}")
    print(f"  Earned Value  (EV): {fmt_money(result['ev'])}")
    print(f"  Actual Cost   (AC): {fmt_money(result['ac'])}")
    print(f"  SPI: {result['spi']:.4f}" if result['spi'] is not None else '  SPI: n/a')
    cpi_note = '  (structurally ~1: cost is derived from % complete, not measured independently)'
    print((f"  CPI: {result['cpi']:.4f}" if result['cpi'] is not None else '  CPI: n/a') + cpi_note)
    print(f"  Variance (EV-PV): {fmt_money(result['variance'])}"
          f" ({'behind/delayed' if result['variance'] < 0 else 'ahead/on-schedule'})")
    print()
    print(f"Overall Project Planned%: {fmt_pct(result['overall_planned_pct'])}"
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
    parser = argparse.ArgumentParser(prog='controlyx',
                                     description='Controlyx — Primavera P6 EVM & delay report (CLI)')
    parser.add_argument('xml_file')
    parser.add_argument('--config', default=DEFAULT_CONFIG_PATH)
    parser.add_argument('--overrides', help=(
        'JSON file of {"Category Name": {"planned_pct": 0.81, "actual_pct": 0.09}} '
        'for categories whose progress is not derivable from the XML (e.g. '
        'drawing-count-based design progress), supplied by the user alongside the XML'
    ))
    parser.add_argument('--out', help='write per-activity breakdown to this CSV path')
    args = parser.parse_args()

    config = load_config(args.config)
    overrides = load_config(args.overrides) if args.overrides else None
    data = parse_file(args.xml_file)
    result = compute(data, config, overrides=overrides)
    print_report(result)

    if args.out:
        write_activity_csv(result, args.out)
        print(f"\nPer-activity breakdown written to {args.out}")


if __name__ == '__main__':
    sys.exit(main())
