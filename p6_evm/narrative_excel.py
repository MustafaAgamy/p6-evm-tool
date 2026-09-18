"""Baseline Narrative — Excel exporter.

Turns the Baseline Narrative the CLIENT is showing — the deterministic, section-keyed
narrative produced by `p6_evm.narrative.build_narrative` — together with the EVM result the
narrative is written from, into the `sheets` structure consumed by
`p6_evm.xlsx_writer.write_sections_xlsx`, so the workbook MIRRORS the on-screen / PDF
narrative rather than dumping a flat blob:

  Sheet 'Baseline Narrative'
    • 'Baseline Narrative'  — the header block: project, data date, overall verdict, and the
                              figures the narrative is built from (SPI, CPI, overall progress,
                              delay) — the same chips + note the screen shows. Numbers numeric.
    • one titled table per narrative section (Executive summary, Schedule performance, Cost
      performance, Progress by area, Outlook & recommendation), each section's paragraphs
      stacked as rows — the same section titles + prose the screen and PDF show.

report = {
    'narrative': build_narrative() output = {'headline', 'tone',
                 'sections': [{'key','title','tone','paragraphs':[str,...]}]},
    'result':    the compute() result the screen holds (project_name, data_date, spi, cpi,
                 delay_days, overall_planned_pct, overall_actual_pct, ...),
}

Nothing is computed here — it only presents what `build_narrative` already wrote and the
figures already in the result. Never raises on empty/missing data: a 'No data' sheet is
returned instead.
"""
from datetime import datetime, date

# Overall-verdict word beside the narrative — mirrors TONE_WORD in ui/modules/narrative.js.
_TONE_WORD = {'good': 'On track', 'warn': 'Watch', 'bad': 'Action needed', 'neutral': '—'}


def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _round2(v):
    """SPI/CPI as a numeric cell (2 dp); None → '—' string."""
    n = _num(v)
    return round(n, 2) if n is not None else '—'


def _pct_whole(frac):
    """Stored fraction (0–1) → whole-percent numeric cell (0.5825 → 58); None → '—'."""
    n = _num(frac)
    return round(n * 100) if n is not None else '—'


def _fmt_date(v):
    """ISO / datetime → '09 Feb 2026' (mirrors narrative.py _date); None → '—'."""
    if v is None:
        return '—'
    if isinstance(v, (datetime, date)):
        return v.strftime('%d %b %Y')
    s = str(v)[:10]
    try:
        return datetime.strptime(s, '%Y-%m-%d').strftime('%d %b %Y')
    except ValueError:
        return s or '—'


def _header_block(result, narr):
    """The screen's title chips (project, data date, verdict) + the figures the note names
    (SPI, CPI, overall progress, delay) as a small Field/Value table — numbers kept numeric."""
    result = result or {}
    delay = result.get('delay_days')
    try:
        delay = None if delay is None else int(delay)
    except (TypeError, ValueError):
        delay = None
    rows = [
        ['Project', result.get('project_name') or 'Project'],
        ['Data date', _fmt_date(result.get('data_date'))],
        ['Overall verdict', _TONE_WORD.get(narr.get('tone'), '—')],
        ['SPI · Schedule', _round2(result.get('spi'))],
        ['CPI · Cost', _round2(result.get('cpi'))],
        ['Planned complete (%)', _pct_whole(result.get('overall_planned_pct'))],
        ['Actual complete (%)', _pct_whole(result.get('overall_actual_pct'))],
        ['Delay (days)', delay if delay is not None else '—'],
    ]
    return {
        'title': 'Baseline Narrative',
        'note': 'A plain-English status summary generated from this update’s metrics — '
                'the same figures the dashboards and PDF use. Deterministic and offline.',
        'headers': ['Field', 'Value'],
        'rows': rows,
    }


def _section_block(section):
    """One narrative section → a titled table whose rows are its paragraphs, mirroring the
    <h3> + prose the screen renders. Empty section → a single 'No narrative text.' row."""
    section = section or {}
    paras = [p for p in (section.get('paragraphs') or []) if str(p).strip()]
    tone = section.get('tone')
    tone_word = _TONE_WORD.get(tone) if tone and tone != 'neutral' else None
    block = {
        'title': section.get('title') or 'Section',
        'headers': ['Narrative'],
        'rows': [[p] for p in paras] or [['No narrative text.']],
    }
    if tone_word:
        block['note'] = f'Verdict: {tone_word}'
    return block


def narrative_excel(report):
    """(report dict the client holds) → `sheets` list for write_sections_xlsx.

    One 'Baseline Narrative' sheet: the header/figures block, then one titled table per
    narrative section. Never raises — no narrative and no result yields a 'No data' sheet.
    """
    report = report or {}
    narr = report.get('narrative') or {}
    result = report.get('result') or {}
    sections = narr.get('sections') or []

    if not sections and not result:
        return [{
            'name': 'Baseline Narrative',
            'blocks': [{
                'title': 'Baseline Narrative',
                'headers': ['Field', 'Value'],
                'rows': [['No data', 'Import a P6 schedule and open Baseline Narrative first.']],
            }],
        }]

    blocks = [_header_block(result, narr)]
    for s in sections:
        blocks.append(_section_block(s))

    return [{
        'name': 'Baseline Narrative',
        'blocks': blocks,
        'col_widths': {0: 30, 1: 96},
    }]
