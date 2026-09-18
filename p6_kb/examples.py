"""Generate example baseline schedules from a Knowledge Base standard.

Two variants per type:
  • **clean**  — the full standard, logic satisfied (scores ~100).
  • **gappy**  — the same baseline with a few *typical* gaps deliberately left in
    (some activities dropped → "missing", a couple of logic rules not satisfied →
    "illogical"), so the user can import it and watch the Constructability review
    flag exactly those gaps.

Built by composing on top of ``starter.build_starter_xml`` — the gappy variant just
feeds it a lightly-thinned copy of the standard; the review runs against the *full*
Knowledge Base, so the dropped items show up as gaps.
"""
import copy

from p6_kb.starter import build_starter_xml

MAX_MISSING = 3     # activities to drop for the gappy example
MAX_ILLOGICAL = 2   # logic rules to leave unsatisfied


def build_example_xml(entry, gappy=False):
    """Return (xml_text, seeded) where seeded counts the gaps deliberately left in."""
    if not gappy:
        return build_starter_xml(entry), {'illogical_seeded': 0, 'missing_seeded': 0}

    e = copy.deepcopy(entry)
    acts = e.get('activities', [])
    drop = min(MAX_MISSING, max(0, len(acts) - 2))   # keep at least two activities
    if drop:
        e['activities'] = acts[:len(acts) - drop]

    kept = ' '.join(a.get('name', '').lower() for a in e['activities'])
    seeded_illog, new_rules = 0, []
    for r in e.get('logic_rules', []):
        alive = any(k.lower() in kept for k in r.get('after_keywords', []))
        if seeded_illog < MAX_ILLOGICAL and alive:
            seeded_illog += 1          # drop this rule → the review flags it illogical
            continue
        new_rules.append(r)
    e['logic_rules'] = new_rules

    return build_starter_xml(e), {'illogical_seeded': seeded_illog, 'missing_seeded': drop}


def write_example_xml(entry, output_path, gappy=False):
    xml, seeded = build_example_xml(entry, gappy=gappy)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(xml)
    return {'path': output_path, 'type': entry.get('type', ''), 'gappy': bool(gappy), **seeded}
