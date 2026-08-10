from p6_evm.parser import parse_file
from p6_claims.tia import compute_impact


def _prog(tmp_path, name, milestone_finish, extra_activity=None):
    """A tiny P6 XML with a 7-day (all-working) calendar and a finish milestone."""
    extra = ''
    if extra_activity:
        aid, finish = extra_activity
        extra = f'''
    <Activity>
      <ObjectId>O-{aid}</ObjectId><Id>{aid}</Id><Name>{aid}</Name>
      <Type>Task Dependent</Type><Status>Not Started</Status>
      <CalendarObjectId>CAL1</CalendarObjectId><PercentComplete>0</PercentComplete>
      <PlannedDuration>80</PlannedDuration>
      <PlannedStartDate>2026-01-05T00:00:00</PlannedStartDate>
      <PlannedFinishDate>{finish}</PlannedFinishDate>
    </Activity>'''
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<APIBusinessObjects>
  <Calendar><ObjectId>CAL1</ObjectId><Name>7-day</Name></Calendar>
  <Project>
    <ObjectId>1</ObjectId><Id>PRJ</Id><Name>P</Name>
    <DataDate>2026-01-01T00:00:00</DataDate>
    <Activity>
      <ObjectId>OFM</ObjectId><Id>FIN</Id><Name>Project complete</Name>
      <Type>Finish Milestone</Type><Status>Not Started</Status>
      <CalendarObjectId>CAL1</CalendarObjectId><PercentComplete>0</PercentComplete>
      <PlannedDuration>0</PlannedDuration>
      <PlannedStartDate>{milestone_finish}</PlannedStartDate>
      <PlannedFinishDate>{milestone_finish}</PlannedFinishDate>
    </Activity>{extra}
  </Project>
</APIBusinessObjects>'''
    p = tmp_path / name
    p.write_text(xml, encoding='utf-8')
    return parse_file(str(p))


def test_impact_is_the_working_days_the_completion_moved(tmp_path):
    base = _prog(tmp_path, 'base.xml', '2026-02-28T00:00:00')
    impacted = _prog(tmp_path, 'impacted.xml', '2026-03-14T00:00:00')
    r = compute_impact(base, impacted)
    assert r['impact_days'] == 14           # 14 days later; every day works on the 7-day calendar
    assert r['milestone_id'] == 'FIN'
    assert r['before_finish'].isoformat() == '2026-02-28T00:00:00'
    assert r['after_finish'].isoformat() == '2026-03-14T00:00:00'


def test_no_movement_is_zero(tmp_path):
    base = _prog(tmp_path, 'b.xml', '2026-02-28T00:00:00')
    same = _prog(tmp_path, 's.xml', '2026-02-28T00:00:00')
    assert compute_impact(base, same)['impact_days'] == 0


def test_completion_tracks_the_finish_milestone_not_a_later_activity(tmp_path):
    # a plain activity finishes AFTER the milestone; the milestone still anchors completion
    base = _prog(tmp_path, 'b2.xml', '2026-02-28T00:00:00', extra_activity=('LATE', '2026-05-01T00:00:00'))
    impacted = _prog(tmp_path, 'i2.xml', '2026-03-07T00:00:00', extra_activity=('LATE', '2026-05-01T00:00:00'))
    r = compute_impact(base, impacted)
    assert r['milestone_id'] == 'FIN'
    assert r['impact_days'] == 7
