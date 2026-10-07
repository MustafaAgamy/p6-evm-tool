/**
 * Owner comment 58: the Bad Weather recovery recommendation is ONE summary (total impact +
 * second shift). recoverySummary() must give an older saved estimate the same summary the
 * server writes (p6_calendar/weather.py recovery_summary) — same months, same sentence.
 * Run: node tests/js/test_weather_recovery_summary.js
 */
import assert from 'node:assert/strict';
import { recoverySummary } from '../../ui/modules/calendar.js';

const w = { net_finish_delay: 10, weather_adjusted_finish: '2027-05-19', project_finish: '2027-05-02', day_hours: 8,
  histogram: [{ label: 'Dec 2026', bad: 2 }, { label: 'Jan 2027', bad: 3 }, { label: 'Feb 2027', bad: 3 },
              { label: 'Mar 2027', bad: 1 }, { label: 'Apr 2027', bad: 1 }] };
const s = recoverySummary(w);
assert.deepEqual(s.shift_months, ['Jan 2027', 'Feb 2027']);
assert.equal(s.shift_days, 6);
assert.equal(s.days, 10);
assert.equal(s.planned_finish, '2027-05-02');
assert.equal(s.text, 'Add a second shift in Jan 2027 and Feb 2027 — the months with the most bad weather — ' +
  'to recover the 10 working days lost (about 80 work-hours).');
assert.equal(recoverySummary({ ...w, expected_bad_days_total: 14 }).basis,
  '14 bad-weather days expected − 4 on days already off (weekend / holiday) = 10 working days lost');
// the server's summary wins when present; no delay → no recommendation
assert.equal(recoverySummary({ ...w, recovery_summary: { days: 3, text: 'x' } }).text, 'x');
assert.equal(recoverySummary({ net_finish_delay: 0 }), null);
assert.equal(recoverySummary(null), null);
// one peak month reads in the singular
const one = recoverySummary({ net_finish_delay: 1, weather_adjusted_finish: '2027-01-02', histogram: [{ label: 'Jan 2027', bad: 1 }] });
assert.equal(one.text, 'Add a second shift in Jan 2027 — the month with the most bad weather — to recover the 1 working day lost.');
console.log('test_weather_recovery_summary: ok');

// Owner, comment 58 (second round): the Project Type stays as chosen when a limit is edited;
// no result before Project Type + Location + Apply & Recalculate; exports wait for it.
import fs from 'node:fs';
const src = fs.readFileSync(new URL('../../ui/modules/calendar.js', import.meta.url), 'utf8');
assert.ok(!/_siteType = matchSiteType\(_thresholds\) \|\| 'custom'/.test(src), 'editing a limit must not change the Project Type');
assert.ok(!/_weather = settings\.last_weather/.test(src), 'a saved estimate is never shown before Apply & Recalculate');
assert.ok(/function _wxReady\(\) \{ return !!\(_pendingLoc && _siteType\); \}/.test(src), 'Apply needs type + location');
const api = fs.readFileSync(new URL('../../ui/modules/api.js', import.meta.url), 'utf8');
assert.equal((api.match(/if \(!hasWeatherResult\(\)\)/g) || []).length, 2, 'PDF and Excel wait for the on-screen result');
console.log('test_weather_recovery_summary (round 2): ok');
