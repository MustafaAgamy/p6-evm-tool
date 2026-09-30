"""Total Float rebuilt the way P6 computes it (finding P8) - calendars.total_float_hours.

P6 XML writes no activity float, so the XML parser rebuilds it; the XER stores P6's own
total_float_hr_cnt. Both must agree: working HOURS between the early and late dates on the
activity's calendar, on the project's 'Compute Total Float as' basis (Finish Float by default).
"""
from datetime import datetime

from p6_evm.calendars import Calendar, float_basis, total_float_hours

EIGHT_H = [(480, 720), (780, 1020)]        # 08:00-12:00, 13:00-17:00


def _cal(intraday=True):
    week = {d: EIGHT_H for d in ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday')}
    return Calendar(object_id='1', name='5d8h', nonworking_days={'Saturday', 'Sunday'},
                    day_hours=8.0, work_intervals=week if intraday else {})


def _dt(s):
    return datetime.strptime(s, '%Y-%m-%d %H:%M')


# Early Mon 03 08:00 -> Tue 04 17:00; late start Tue 04 13:00, late finish Thu 06 12:00.
ES, EF, LS, LF = _dt('2025-03-03 08:00'), _dt('2025-03-04 17:00'), _dt('2025-03-04 13:00'), _dt('2025-03-06 12:00')


def test_basis_vocabulary_is_the_same_for_xml_and_xer():
    assert float_basis('Finish Float = Late Finish - Early Finish') == 'finish'
    assert float_basis('FT_FF') == 'finish'
    assert float_basis('Start Float = Late Start - Early Start') == 'start'
    assert float_basis('FT_SF') == 'start'
    assert float_basis('Smallest of Start Float and Finish Float') == 'smallest'
    assert float_basis('FT_SM') == 'smallest'
    assert float_basis(None) == 'finish' and float_basis('') == 'finish'   # P6 default


def test_finish_float_is_working_hours_late_finish_minus_early_finish():
    # Tue 17:00 -> Thu 12:00 = Wed 8 h + Thu 4 h = 12 h (1.5 days), fractional like P6's 12/8
    assert total_float_hours(_cal(), ES, EF, LS, LF, 'finish') == 12.0


def test_start_float_and_smallest():
    ls = _dt('2025-03-05 08:00')                      # Mon 08:00 -> Wed 08:00 = 8 + 8 = 16 h
    assert total_float_hours(_cal(), ES, EF, ls, LF, 'start') == 16.0
    assert total_float_hours(_cal(), ES, EF, ls, LF, 'smallest') == 12.0


def test_negative_float_is_signed():
    # late finish BEFORE early finish: Thu 06 12:00 early vs Tue 04 17:00 late = -12 h
    assert total_float_hours(_cal(), ES, LF, LS, EF, 'finish') == -12.0


def test_no_remaining_dates_means_no_float():
    # a Completed activity has no remaining early/late dates - P6 shows no float, nor do we
    assert total_float_hours(_cal(), None, None, None, None, 'finish') is None
    assert total_float_hours(None, ES, EF, LS, LF, 'finish') is None


def test_calendar_without_work_times_falls_back_to_whole_days():
    # Tue -> Thu = 2 working days x 8 h
    assert total_float_hours(_cal(intraday=False), ES, EF, LS, LF, 'finish') == 16.0
