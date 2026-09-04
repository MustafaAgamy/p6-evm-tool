// Calendar Audit renderer — Calendar Timeline & Audit + Weather Impact.

// ── Pure helpers (unit-tested in tests/js/test_calendar.js) ───────────────

const _MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
              'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function fmtCalDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d)) return '—';
  return `${String(d.getUTCDate()).padStart(2, '0')} ${_MON[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

export function statusClass(status) {
  return { work: 'cs-work', weekend: 'cs-weekend', holiday: 'cs-holiday',
           shutdown: 'cs-shutdown', special: 'cs-special' }[status] || 'cs-work';
}

// Build a Mon-first grid: `first_weekday` leading blanks, then one cell per day.
export function monthGridCells(month) {
  const cells = [];
  const pad = ((month.first_weekday % 7) + 7) % 7;
  for (let i = 0; i < pad; i++) cells.push({ blank: true });
  for (const day of (month.days || [])) cells.push({ d: day.d, status: day.status, name: day.name });
  return cells;
}

export function conflictSeverityClass(sev) {
  return { High: 'cf-high', Medium: 'cf-med', Low: 'cf-low' }[sev] || 'cf-low';
}

// Per-month bar geometry for the Calendar Timeline histogram (Feature 1 §2). Heights are in
// px, scaled so the tallest month (working + non-working) fills ~100px; the non-working
// segment stacks under the working one. Shared by the primary and the compare histogram.
export function histBarGeom(months) {
  const mx = Math.max(1, ...months.map(m => (m.working_days || 0) + (m.nonworking_days || 0)));
  return months.map(m => {
    const wd = m.working_days || 0, nw = m.nonworking_days || 0, tot = wd + nw;
    const totPx = Math.round(tot / mx * 100);
    const nwPx = tot ? Math.round(nw / tot * totPx) : 0;
    const wPx = Math.max(0, totPx - nwPx);
    return { label: m.label, wd, nw, totPx, nwPx, wPx };
  });
}

// Per-month segment geometry for the Feature 2 3-colour histogram (net working / bad-weather /
// non-working). Heights in px, scaled so the tallest month (net + bad + non-working) fills `H`
// px; the label above each bar is the NET working days. Pure — unit-tested.
export function hist3Geom(histogram, H = 130) {
  const rows = histogram || [];
  const maxTot = Math.max(1, ...rows.map(m => (m.net || 0) + (m.bad || 0) + (m.nonworking || 0)));
  const px = v => Math.round((v || 0) / maxTot * H);
  return rows.map(m => ({
    label: m.label, net: m.net || 0, bad: m.bad || 0, nonworking: m.nonworking || 0,
    netPx: px(m.net), badPx: px(m.bad), nwPx: px(m.nonworking),
  }));
}

// ── Site-type presets — mirror of p6_calendar/weather.py SITE_TYPES ──────────
// One pick loads the stop-work limits that fit that kind of work. DESERT equals the
// app default (wind off / heat 42), so a project that never picks a type is unchanged.
// Keep the numbers in sync with weather.py (tests guard both sides).
export const SITE_TYPES = {
  desert:   { label: 'Desert / inland civil', icon: '🏜️',
              blurb: 'Heat & dust drive stoppages; wind rarely halts inland civil work.',
              thresholds: { rain_mm: 5, temp_max_c: 42, wind_kmh: null, dust: true } },
  marine:   { label: 'Marine / Port', icon: '⚓',
              blurb: 'Cranes & marine works stop for high wind — the main risk for a port / terminal.',
              thresholds: { rain_mm: 5, temp_max_c: 40, wind_kmh: 35, dust: true } },
  coastal:  { label: 'Coastal / general', icon: '🌊',
              blurb: 'A mix of wind and rain; heat reaches the limit less often than inland.',
              thresholds: { rain_mm: 5, temp_max_c: 42, wind_kmh: 40, dust: true } },
  building: { label: 'Building / enclosed', icon: '🏢',
              blurb: 'Least weather-exposed once enclosed; only heavy rain / extreme heat stop work.',
              thresholds: { rain_mm: 10, temp_max_c: 45, wind_kmh: null, dust: false } },
};
export const SITE_TYPE_ORDER = ['marine', 'desert', 'coastal', 'building'];

const _eqLim = (a, b) => (a == null ? null : a) === (b == null ? null : b);

// Do these limits exactly match a site-type preset? null → the user has a Custom set.
export function matchSiteType(t) {
  if (!t) return null;
  for (const key of SITE_TYPE_ORDER) {
    const p = SITE_TYPES[key].thresholds;
    if (_eqLim(p.rain_mm, t.rain_mm) && _eqLim(p.temp_max_c, t.temp_max_c) &&
        _eqLim(p.wind_kmh, t.wind_kmh) && !!p.dust === !!t.dust) return key;
  }
  return null;
}

// The 'criteria in full' rows — mirror of build_criteria() in weather.py. Wind first
// (the dominant driver on a port). Reflects the ACTUAL limits, so Custom shows truly.
export function buildSiteCriteria(siteType, t) {
  const marine = siteType === 'marine';
  const num = (key, icon, label, v, unit, expl) => ({
    key, icon, label, value: (v == null ? 'off' : `≥ ${v} ${unit}`), on: v != null, explain: expl });
  return [
    num('wind', '💨', 'Wind', t.wind_kmh, 'km/h',
        marine ? 'High wind stops crane lifts, tower-crane and marine works'
               : 'High wind stops crane lifts and work at height'),
    num('heat', '🌡', 'Heat', t.temp_max_c, '°C', 'Extreme heat halts outdoor labour'),
    num('rain', '🌧', 'Rain', t.rain_mm, 'mm', 'Work-stopping rain (light drizzle below the limit is ignored)'),
    { key: 'dust', icon: '🌫', label: 'Dust / sandstorm', value: (t.dust ? 'on' : 'off'),
      on: !!t.dust, explain: 'Sandstorm days (near-term air-quality PM10) counted as a lost day' },
  ];
}

// ── DOM rendering (browser only) ──────────────────────────────────────────

import { escapeHtml } from './format.js';
import { state } from './state.js';
import { geocodePlace, reverseGeocode, computeWeather, saveCalendarSettings } from './api.js';

const DEFAULT_THRESHOLDS = { rain_mm: 5, temp_max_c: 42, wind_kmh: null, dust: true };

let _ca = null;
let _sel = null;
let _sel2 = null;         // 2nd calendar to compare in the timeline histogram (Feature 1 §2)
let _weather = null;      // last computed weather impact
let _pendingLoc = null;   // location chosen in the picker, not yet applied
let _thresholds = null;   // stop-work limits (rain/heat/wind/dust)
let _siteType = null;     // chosen site type (marine/desert/coastal/building/custom); null = default
let _map = null;          // Leaflet map instance (location picker)
let _marker = null;       // the draggable location pin
let _leafletPromise = null;
let _mapRO = null;        // ResizeObserver that re-measures the map when the tab is shown
const _openMonths = new Set();

export function renderCalendar(ca) {
  _ca = ca || null;
  _weather = null;
  _pendingLoc = null;
  _thresholds = { ...DEFAULT_THRESHOLDS };
  _siteType = null;
  _openMonths.clear();
  const body = document.getElementById('calendar-body');
  if (!body) return;
  if (!_ca || !_ca.dashboard) {
    body.innerHTML = '<p style="color:var(--muted);font-size:13px">No calendar data for this schedule.</p>';
    return;
  }
  _sel = _ca.primary_calendar_id;
  _sel2 = null;
  const settings = (state.currentResult && state.currentResult.calendar_settings) || {};
  if (settings.location) _pendingLoc = settings.location;
  if (settings.weather_thresholds) _thresholds = { ...DEFAULT_THRESHOLDS, ...settings.weather_thresholds };
  if (settings.site_type) _siteType = settings.site_type;        // restore the picked site type
  else if (settings.weather_thresholds) _siteType = matchSiteType(_thresholds);  // infer from saved limits
  if (settings.last_weather) _weather = settings.last_weather;   // show the last saved estimate on re-open
  _renderCalendarBody();
}

// Feature 1 — P6 Calendar Audit → its own tab (calendar-body). No weather here.
// Five numbered sections (mockup): 1 Execution Dashboard · 2 Calendar Timeline & Statistics ·
// 3 Calendar Non-working days · 4 Working-hours Profile · 5 Calendar Comparison & Usage.
function _renderCalendarBody() {
  const body = document.getElementById('calendar-body');
  if (!body) return;
  body.innerHTML =
    _calDdBanner() +
    _dashboard(_ca.dashboard) +
    _timelineSection() +
    _exceptionsSection() +
    _hoursSection() +
    _comparisonSection(_ca.comparison);
  _wireCalendar();
}

// The data-date banner — every Calendar-Audit result starts from it. Emitted at the very top
// (mirrors the weather view's _ddBanner; kept separate so the two features stay independent).
function _calDdBanner() {
  const dd = (_ca && _ca.dashboard && _ca.dashboard.data_date) ? fmtCalDate(_ca.dashboard.data_date) : '';
  return dd
    ? `<div class="cal-ddbanner">📅 All results (statistics, histograms, tables) start from the <b>Data Date · ${dd}</b> — nothing before it is shown.</div>`
    : '';
}

// Feature 2 — Bad Weather effect on Forecast Finish → its own tab (weather-body).
export function renderWeatherView(ca) {
  if (ca) _ca = ca;
  const body = document.getElementById('weather-body');
  if (!body) return;
  if (!_ca || !_ca.dashboard) {
    body.innerHTML = '<p style="color:var(--muted);font-size:13px">No schedule loaded — import a file first.</p>';
    return;
  }
  _renderWeatherBody();
}

function _renderWeatherBody() {
  const body = document.getElementById('weather-body');
  if (!body) return;
  // Mockup order: data-date banner → compact entry bar (type + location + Calculate) →
  // the map (demoted to a secondary, expandable control) → the numbered weather sections.
  body.innerHTML = _ddBanner() + _entryBar() + _locationCard() + _weatherSection();
  _wireWeatherView();
}

// The data-date banner — every weather result starts from it. Emitted at the very top.
function _ddBanner() {
  const dd = (_ca && _ca.dashboard && _ca.dashboard.data_date) ? fmtCalDate(_ca.dashboard.data_date) : '';
  return dd
    ? `<div class="cal-ddbanner">📅 All results start from the <b>Data Date · ${dd}</b> — nothing before it. Weather window: data date → finish.</div>`
    : '';
}

// The project / scope name shown above the 3-colour histogram (falls back gracefully).
function _scopeName() {
  const r = state.currentResult || {};
  return r.project_name || (_ca && _ca.project && _ca.project.name) || 'Project scope';
}

// The Location readout used inside the compact entry bar (mirrors _locationReadoutHtml, compact).
function _entryLocHtml() {
  const loc = _pendingLoc;
  return loc
    ? `📍 <b>${escapeHtml(loc.name || 'Selected location')}</b> · ${(+loc.lat).toFixed(2)}°, ${(+loc.lon).toFixed(2)}°`
    : '<span class="cal-muted">No location set — open the map below to place a pin</span>';
}

// Compact entry bar (mockup): Project-Type selector + Location readout + Calculate button.
// The Project-Type choice loads the stop-work limits (SITE_TYPES); Calculate runs the estimate.
function _entryBar() {
  const st = _siteType;
  const opts = SITE_TYPE_ORDER.map(key => {
    const s = SITE_TYPES[key];
    return `<option value="${key}" ${st === key ? 'selected' : ''}>${s.icon} ${escapeHtml(s.label)}</option>`;
  }).join('');
  const customOpt = st === 'custom'
    ? '<option value="custom" selected>⚙️ Custom limits</option>' : '';
  const placeholder = st ? '' : '<option value="" selected>— pick site type —</option>';
  const loc = _pendingLoc;
  return `<div class="cal-entry">
    <div class="cal-entry-fld"><label>Project Type</label>
      <select class="cal-entry-sel" id="cal-entry-site">${placeholder}${opts}${customOpt}</select></div>
    <div class="cal-entry-fld grow"><label>Location</label>
      <div class="cal-entry-box" id="cal-entry-loc">${_entryLocHtml()}</div></div>
    <button class="cal-entry-go" id="cal-entry-go" ${loc ? '' : 'disabled'}>Calculate weather →</button>
    <div class="cal-entry-hint">Start here — the project type loads the stop-work limits that fit the work, and the location drives the weather. Fine-tune the exact spot on the map below.</div>
  </div>`;
}

function _sec(n, title, extra = '') {
  return `<div class="cal-sec-label"><span class="cal-num">${n}</span> ${escapeHtml(title)}
    ${extra ? `<span class="cal-sec-extra">${extra}</span>` : ''}</div>`;
}

function _tile(lab, val, sub = '', cls = '') {
  return `<div class="cal-kpi ${cls}"><div class="cal-k">${lab}</div>
    <div class="cal-v">${escapeHtml(String(val))}</div>
    ${sub ? `<div class="cal-k2">${sub}</div>` : ''}</div>`;
}

// ── Report Contents (#06) — the sections the Calendar Audit PDF can print. Shown as the
// in-preview "Include sections" picker (shared showReportPreview), matching every other
// module's report picker. ──
// Feature 1 — P6 Calendar Audit PDF (no weather; that's the Bad Weather report).
export const CAL_SECTIONS = [
  ['dashboard', '1 Execution Dashboard'], ['timeline', '2 Calendar Timeline & Statistics'],
  ['exceptions', '3 Calendar Non-working days'], ['hours', '4 Working-hours Profile'],
  ['comparison', '5 Calendar Comparison & Usage'],
];
// Feature 2 — Bad Weather effect on Forecast Finish PDF (weather-only).
export const WEATHER_SECTIONS = [
  ['weather', 'Bad Weather Impact'],
];

// ── Location picker (top — drives the Weather-Adjusted Finish + Section 9) ──
function _locationReadoutHtml() {
  const loc = _pendingLoc;
  return loc
    ? `<div class="cal-loc-read">📌 <b>${escapeHtml(loc.name || 'Selected location')}</b><br>
        <span class="cal-muted">Coordinates: ${(+loc.lat).toFixed(4)}° , ${(+loc.lon).toFixed(4)}°</span></div>`
    : '<div class="cal-loc-read cal-muted">No location set yet — search, or click the map to drop a pin.</div>';
}

// Secondary/expandable location control — demoted below the entry bar (mockup). The entry
// bar is the primary path; open this to search or drop a pin on the exact site.
function _locationCard() {
  const loc = _pendingLoc;
  return `
    <details class="cal-loc-details"${loc ? '' : ' open'}>
      <summary>🗺️ Set the exact site on the map${loc ? ` — <b>${escapeHtml(loc.name || 'pin set')}</b>` : ''}</summary>
      <div class="cal-loc-card">
        <div class="cal-loc-left">
          <div class="cal-muted" style="font-size:12px;margin-bottom:8px"><b>Search a place, or click the map to drop a pin on the exact site</b> (drag it to fine-tune). Saved with the project.</div>
          <div class="cal-loc-search">
            <input id="cal-loc-q" placeholder="Search a place or address… (e.g. Jubail, Saudi Arabia)" value="">
            <button class="cal-btn pri" id="cal-loc-search-btn">Search</button>
          </div>
          <div id="cal-loc-results" class="cal-loc-results"></div>
          <div id="cal-loc-readout">${_locationReadoutHtml()}</div>
          <button class="cal-btn pri" id="cal-loc-use" style="margin-top:10px" ${loc ? '' : 'disabled'}>✓ Use this location &amp; calculate weather</button>
          <span id="cal-loc-status" class="cal-muted" style="font-size:12px;margin-left:8px"></span>
        </div>
        <div class="cal-loc-right">
          <div id="cal-map" class="cal-map"></div>
          <div class="cal-map-hint cal-muted">🖱️ Click the map to place the pin · drag to fine-tune</div>
        </div>
      </div>
    </details>`;
}

function _dashboard(d) {
  const dates = [
    _tile('Baseline Start', fmtCalDate(d.baseline_start), '', 'hl'),
    _tile('Baseline Finish / Completion', fmtCalDate(d.baseline_finish), 'plan of record', 'hl'),
  ].join('');
  // Row 1 (3 tiles): the calendar-day split. Row 2 (4 tiles): holidays, averages + normal hours.
  const stats1 = [
    _tile('Total Calendar Days', d.total_calendar_days),
    _tile('Working Days', d.total_working_days),
    _tile('Non-Working Days', d.total_nonworking_days),
  ].join('');
  const stats2 = [
    _tile('Holidays', d.total_holidays, 'incl. expected + shutdowns'),
    _tile('Avg Working Days / Month', d.avg_working_days_per_month),
    _tile('Avg Working Hours / Day', `${d.avg_working_hours_per_day} hrs`),
    _tile('Normal Hours', d.normal_hours || '—'),
  ].join('');
  return _sec(1, 'Execution Dashboard') +
    `<div class="cal-subhead">Key Dates</div>
     <div class="cal-kpi-grid" style="grid-template-columns:repeat(2,1fr)">${dates}</div>
     <div class="cal-subhead">Calendar Statistics</div>
     <div class="cal-kpi-grid" style="grid-template-columns:repeat(3,1fr)">${stats1}</div>
     <div class="cal-kpi-grid" style="grid-template-columns:repeat(4,1fr);margin-top:10px">${stats2}</div>`;
}

// Selectable calendar CHIPS (§2, mockup) — one per assigned calendar: full name + meta
// "Xh · Yd/wk · N acts". The primary (`_sel`) and an optional comparison (`_sel2`) get `.sel`.
// Clicking a 2nd chip adds a comparison histogram below; clicking a selected chip toggles it off.
function _calChips() {
  const chips = (_ca.assigned_calendars || []).map(c => {
    const on = (c.object_id === _sel || c.object_id === _sel2);
    const acts = Number(c.activity_count || 0).toLocaleString();
    const meta = `${c.hours_per_day}h · ${c.days_per_week}d/wk · ${acts} acts`;
    return `<div class="cal-chip ${on ? 'sel' : ''}" data-cal="${escapeHtml(c.object_id)}">
      ${escapeHtml(c.name)}<span class="meta">${escapeHtml(meta)}</span></div>`;
  }).join('');
  return `<div class="cal-chips">${chips}</div>`;
}

function _monthsFor(calId) {
  const bc = (_ca.by_calendar || {})[calId];
  return (bc && bc.monthly_stats) || [];
}
function _selMonths() { return _monthsFor(_sel); }

// One calendar's net-working / non-working days-per-month histogram. `clickable` months
// open their full calendar grid (primary only); the comparison histogram is view-only.
function _histBars(months, clickable) {
  return histBarGeom(months).map((g, i) => {
    const open = clickable && _openMonths.has(i);
    const cls = clickable ? `cal-whc ${open ? 'open' : ''}` : 'cal-whc static';
    const dm = clickable ? ` data-month="${i}"` : '';
    return `<div class="${cls}"${dm} title="${escapeHtml(g.label)}: ${g.wd} net working · ${g.nw} non-working${clickable ? ' — click to open its calendar' : ''}">
      <div class="cal-wht">${g.wd}</div>
      <div class="cal-whcol"><div class="cal-whn" style="height:${g.nwPx}px"></div><div class="cal-whw" style="height:${g.wPx}px"></div></div>
      <div class="cal-whl">${escapeHtml(g.label)}${open ? ' ▾' : ''}</div></div>`;
  }).join('');
}
function _histBlock(calId, clickable) {
  const c = (_ca.assigned_calendars || []).find(x => x.object_id === calId);
  const bars = _histBars(_monthsFor(calId), clickable);
  return `<div class="cal-histblock"><div class="cal-histtitle">${escapeHtml(c ? c.name : '')}</div>
    <div class="cal-whist">${bars || '<span class="cal-muted">No months.</span>'}</div></div>`;
}

// Section 2 — Calendar Timeline & Statistics (Feature 1). Selectable calendar chips choose the
// calendar; the net working vs non-working days-per-month histogram follows. Clicking a month's
// bar opens its full calendar grid; clicking a 2nd chip adds a comparison histogram below.
function _timelineSection() {
  const hleg = `<div class="cal-whleg"><span><i class="wsw wsw-w"></i>Working days</span><span><i class="wsw wsw-n"></i>Non-working (weekends + holidays + shutdowns)</span><span>▲ number above bar = <b>net working days</b></span></div>`;
  const detail = _monthDetailHtml();
  const dayLegend = _openMonths.size ? `<div class="cal-legend" style="margin-top:10px">
    <span><i class="dot cs-work"></i>Working</span>
    <span><i class="dot cs-weekend"></i>Weekend</span>
    <span><i class="dot cs-holiday"></i>Holiday</span>
    <span><i class="dot cs-shutdown"></i>Shutdown</span>
    <span><i class="dot cs-special"></i>Special hours</span></div>` : '';
  const proj = _ca.project || {};
  const hidden = proj.hidden_months || 0;
  const dd = _ca.dashboard && _ca.dashboard.data_date;
  const hiddenChip = hidden
    ? `<div class="cal-hidden-note">◀ <b>${hidden} earlier month${hidden === 1 ? '' : 's'}</b> hidden — everything before the data date${dd ? ` (${fmtCalDate(dd)})` : ''}</div>`
    : '';
  const bc = (_ca.by_calendar || {})[_sel] || {};
  const totHrs = Number((bc.totals && bc.totals.working_hours) || 0)
    .toLocaleString(undefined, { maximumFractionDigits: 0 });
  const totLine = `<div class="cal-tothrs">Total working hours (selected calendar): <b>${totHrs} hrs</b></div>`;
  const compare = _sel2 ? _histBlock(_sel2, false) : '';
  return _sec(2, 'Calendar Timeline & Statistics',
      `<span class="cal-sec-note">net working vs non-working days per month · click a month to open its calendar</span>`) +
    _calChips() + totLine +
    hiddenChip + hleg + _histBlock(_sel, true) + compare +
    dayLegend + `<div id="cal-month-detail">${detail}</div>`;
}

function _monthDetailHtml() {
  if (!_openMonths.size) return '';
  const dows = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const months = _selMonths();
  return [..._openMonths].sort((a, b) => a - b).map(i => {
    const m = months[i];
    if (!m) return '';
    const head = dows.map(d => `<div class="cal-mh">${d}</div>`).join('');
    const cells = monthGridCells(m).map(c => c.blank
      ? '<div class="cal-mcell blank"></div>'
      : `<div class="cal-mcell ${statusClass(c.status)}"><span class="cal-dn">${c.d}</span>${c.name ? `<div class="cal-cn">${escapeHtml(c.name)}</div>` : ''}</div>`).join('');
    return `<div class="cal-month-open"><div class="cal-month-open-t">${escapeHtml(m.label)} —
      ${m.working_days} working · ${m.holidays} holiday${m.holidays === 1 ? '' : 's'} · ${m.working_hours} hrs</div>
      <div class="cal-month-grid">${head}${cells}</div></div>`;
  }).join('');
}

// Section 3 — Calendar Non-working days (holidays only). One row per holiday DATE (runs are
// expanded to individual dates with their weekday); the Description is editable via the existing
// cal-reason / saveCalendarSettings({shutdown_reasons}) plumbing. The "+ Add shutdown" capability
// is preserved as a small demoted affordance below the table.
function _exceptionsSection() {
  const bc = (_ca.by_calendar || {})[_sel] || {};
  const exc = bc.exceptions || { holidays: [], holiday_dates: [] };
  const hd = exc.holiday_dates || [];
  const rows = hd.map(h =>
    `<tr><td>${fmtCalDate(h.date)}</td><td>${escapeHtml(h.weekday || '')}</td>
     <td><input class="cal-reason" data-key="${escapeHtml(h.key || '')}" value="${escapeHtml(h.reason || '')}" placeholder="Add a description for this holiday…"></td></tr>`).join('');
  const body = rows || '<tr><td colspan="3" class="cal-empty">No holidays in the project window.</td></tr>';
  const addBtn = '<button class="cal-btn sec mini" id="cal-add-shutdown-btn">+ Add shutdown</button>';
  const addForm = `<div id="cal-add-shutdown" class="cal-addform hidden">
      <input type="date" id="cal-sd-start"><span>→</span><input type="date" id="cal-sd-end">
      <input id="cal-sd-reason" placeholder="reason (e.g. Plant turnaround)">
      <button class="cal-btn pri mini" id="cal-sd-save">Add</button></div>`;
  return _sec(3, 'Calendar Non-working days', '<span class="cal-sec-note">holidays only</span>') +
    `<div class="cal-card p0"><table class="cal-table"><thead><tr>
      <th>Date</th><th>Day</th><th style="width:55%">Description <span class="cal-edit-tag">✎ editable</span></th></tr></thead>
      <tbody>${body}</tbody>
      <tfoot><tr><td colspan="3" class="cal-tfoot">Total holidays: <b>${hd.length}</b> &nbsp;·&nbsp;
        <span class="cal-muted">the Description is editable — type/adjust each holiday's name; saved with the project and printed in the PDF.</span></td></tr></tfoot>
      </table></div>
     <div class="cal-add-demote">${addBtn}${addForm}</div>`;
}

// Section 4 — Working-hours Profile as a TABLE: Period | Hours | Days/week | Hrs/day | Note.
// One row per distinct working-time profile; the Note is editable (cal-hnote / hours_notes).
function _hoursSection() {
  const bc = (_ca.by_calendar || {})[_sel] || {};
  const profs = bc.hours_profiles || [];
  const rows = profs.map(p =>
    `<tr><td>${escapeHtml(p.name)}</td><td>${escapeHtml(p.hours)}</td>
     <td class="num">${escapeHtml(String(p.days_per_week != null ? p.days_per_week : (p.sub || '')))}</td>
     <td class="num">${escapeHtml(String(p.hours_per_day))}</td>
     <td><input class="cal-hnote" data-key="${escapeHtml(p.key || '')}" value="${escapeHtml(p.note || '')}" placeholder="note (e.g. Summer / Ramadan reduced hours)…"></td></tr>`).join('');
  const body = rows || '<tr><td colspan="5" class="cal-empty">No working-hours profile.</td></tr>';
  return _sec(4, 'Working-hours Profile') +
    `<div class="cal-card p0"><table class="cal-table"><thead><tr>
      <th>Period</th><th>Hours</th><th class="num">Days / week</th><th class="num">Hrs / day</th>
      <th style="width:34%">Note <span class="cal-edit-tag">✎ editable</span></th></tr></thead>
      <tbody>${body}</tbody></table></div>
     <div class="cal-note" style="font-style:normal">Shows each distinct working-time period in the calendar (P6 calendars can change hours over time). The <b>Note</b> column is editable — type the justification for a reduced-hours period; it's saved with the project and printed in the PDF.</div>`;
}

// Feature 1 — Calendar Comparison & Usage (merged): each calendar's hours/day, days/week,
// activities assigned, % of activities, and role.
function _comparisonSection(cmp) {
  const dd = (_ca.dashboard && _ca.dashboard.data_date) ? fmtCalDate(_ca.dashboard.data_date) : '';
  const usage = {};
  (_ca.usage || []).forEach(u => { usage[u.name] = u; });
  const rows = (cmp || []).map(c => {
    const u = usage[c.name] || {};
    const roleCls = u.role === 'Default' ? 'def' : (u.role === 'Unused' ? 'warn' : '');
    const acts = u.activities != null ? u.activities : 0;
    const pct = (u.role === 'Unused' || u.pct == null) ? (acts ? `${u.pct}%` : '0%') : `${u.pct}%`;
    return `<tr><td>${escapeHtml(c.name)}${c.is_default ? ' <span class="cal-pill mini def">Default</span>' : ''}</td>
     <td class="num">${c.hours_per_day}</td><td class="num">${c.days_per_week}</td>
     <td class="num">${acts}</td><td class="num">${pct}</td>
     <td class="num">${c.nonworking_days != null ? c.nonworking_days : 0}</td>
     <td>${u.role ? `<span class="cal-pill mini ${roleCls}">${escapeHtml(u.role)}</span>` : ''}</td></tr>`;
  }).join('');
  return _sec(5, 'Calendar Comparison & Usage') +
    `<div class="cal-card p0"><table class="cal-table"><thead><tr>
      <th>Calendar</th><th class="num">Hours/Day</th><th class="num">Days/Week</th>
      <th class="num">Assigned to</th><th class="num">% of Activities</th>
      <th class="num">Non-Working Days</th><th>Role</th></tr></thead>
      <tbody>${rows}</tbody></table>${_conflictsBlock(_ca.conflicts)}</div>
     <div class="cal-note" style="font-style:normal"><b>% of Activities</b> — share of the schedule's activities on each calendar. <b>Non-Working Days</b> — weekends, holidays and shutdowns still ahead${dd ? `, from the data date (${dd}) to finish` : ''}. <b>Unused</b> calendars carry 0 activities and can be removed.</div>`;
}

// The "Calendar Conflicts — to be removed" list, appended INSIDE the Comparison & Usage card
// (mockup §5). Empty conflicts → nothing rendered.
function _conflictsBlock(conflicts) {
  conflicts = conflicts || [];
  if (!conflicts.length) return '';
  const pill = t => (t === 'unused'
    ? '<span class="cal-pill holiday">Unused</span>'
    : '<span class="cal-pill shutdown">Review</span>');
  const lines = conflicts.map(c =>
    `<div class="cal-confline">${pill(c.type)} <b>${escapeHtml(c.title)}</b> — ${escapeHtml(c.detail)}</div>`).join('');
  return `<div class="cal-conflicts-foot">
    <div class="cal-conflicts-h">Calendar Conflicts — to be removed</div>${lines}</div>`;
}

function _usageSection(usage) {
  const rows = (usage || []).map(u => {
    const roleCls = u.role === 'Default' ? 'def' : (u.role === 'Unused' ? 'warn' : '');
    return `<tr><td>${escapeHtml(u.name)}</td><td class="num">${u.activities}</td>
      <td>${u.role === 'Unused' ? '—' : `${u.pct}%`}</td>
      <td><span class="cal-pill mini ${roleCls}">${escapeHtml(u.role)}</span></td></tr>`;
  }).join('');
  return _sec(7, 'Calendar Usage') +
    `<div class="cal-card p0"><table class="cal-table"><thead><tr>
      <th>Calendar</th><th class="num">Activities</th><th>% of Activities</th><th>Role</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
     <div class="cal-note" style="font-style:normal"><b>Roles:</b> <b>Default</b> — the project's default calendar; new activities are created on it automatically. <b>Non-default</b> — a calendar deliberately assigned to specific activities instead of the default. <b>Unused</b> — defined in the file but no activity uses it.</div>`;
}

// Section 9 — Weather Impact (estimate).
function _thr() { return _thresholds || DEFAULT_THRESHOLDS; }

function _weatherControls() {
  const t = _thr();
  const connected = _weather
    ? `<span class="dot-ok"></span> <b>Weather source: ${escapeHtml((_weather.source || 'Open-Meteo').split(' (')[0])}</b>
       <span class="cal-muted">— free &amp; open · no key · no bill</span>
       <span class="cal-pill ok" style="margin-left:auto">connected ✓</span>`
    : '<span class="cal-muted"><b>Weather source: Open-Meteo</b> (free, open, no key) — will connect when you calculate.</span>';
  const from = _weather && _weather.from_date ? ` · upcoming from cutoff <b>${fmtCalDate(_weather.from_date)}</b>` : '';
  const num = (id, lab, val) =>
    `<div class="thr-f"><label>${lab}</label><input type="number" id="${id}" value="${val == null ? '' : val}" placeholder="${val == null ? 'off' : ''}"></div>`;
  return `<div class="cal-src">${connected}</div>
    <div class="cal-muted" style="font-size:12px;margin:6px 0 10px">Location: <b>${escapeHtml((_pendingLoc && _pendingLoc.name) || '')}</b>${from} · <span class="loc-change" onclick="window.scrollTo(0,0)">change ↑</span></div>
    <div class="cal-wx-method">
      <div class="cal-wx-mh">📡 How the estimate is built — three free Open-Meteo feeds</div>
      <div class="cal-wx-feed"><span class="ic">🛰️</span><div><b>Live forecast</b> — the real daily forecast (rain, heat, wind) for the next ~16 days from the update's cutoff.<span class="cal-pill mini def">Forecast</span></div></div>
      <div class="cal-wx-feed"><span class="ic">📚</span><div><b>Multi-year climate history</b> — beyond ~16 days, each date is drawn from the site's recorded weather over the <b>last 5 years</b> (Open-Meteo ERA5). The day-list follows a <b>typical (representative) year</b> so a fluke year can't skew it; months show the <b>5-year average and range</b>.<span class="cal-pill mini warn">Expected · climate</span></div></div>
      <div class="cal-wx-feed"><span class="ic">🌫️</span><div><b>Air-quality</b> — near-term PM10 / dust concentration, to flag sandstorm days.</div></div>
    </div>
    ${_criteriaPanelHtml()}
    <div class="cal-grp" style="margin-top:0"><span class="cal-pill warn">✎ Fine-tune the limits</span>
      <span class="cal-grp-meta">the site type sets these — change any number to match your site (blank = off; switches to “Custom”)</span></div>
    <div class="cal-thr">
      ${num('thr-rain', '🌧 Rain ≥ (mm)', t.rain_mm)}
      ${num('thr-heat', '🌡 Heat ≥ (°C)', t.temp_max_c)}
      ${num('thr-wind', '💨 Wind ≥ (km/h)', t.wind_kmh)}
      <div class="thr-f"><label>🌫 Dust</label><span class="thr-sw"><input type="checkbox" id="thr-dust" ${t.dust ? 'checked' : ''}> count sandstorm days</span></div>
      <button class="cal-btn pri" id="thr-apply">Apply &amp; recalculate</button>
      <span id="thr-status" class="cal-muted" style="font-size:12px"></span>
    </div>
    <div class="cal-note" style="margin-top:8px">Each flagged day below shows the measured value against your limit. Applied to <b>construction</b> activities only; a day already off (weekend / holiday / shutdown) is never double-counted — kept separate from the exact P6 Delay.</div>`;
}

// The stop-work criteria shown IN FULL — every limit, its value, and what work it stops.
function _criteriaPanelHtml() {
  const st = _siteType;
  const meta = st === 'custom' ? { label: 'Custom limits', icon: '⚙️' }
    : (SITE_TYPES[st] || { label: 'Default limits (Desert / inland)', icon: '🏜️' });
  const rows = buildSiteCriteria(st, _thr()).map(r =>
    `<div class="cal-crit-row">
      <div class="cal-crit-lim ${r.on ? 'on' : 'off'}">${r.icon} ${escapeHtml(r.label)} <b>${escapeHtml(r.value)}</b></div>
      <div class="cal-crit-exp">${escapeHtml(r.explain)}${r.on ? '' : ' <span class="cal-muted">(not counted)</span>'}</div>
    </div>`).join('');
  return `<div class="cal-crit">
    <div class="cal-crit-top"><span class="cal-crit-t">${meta.icon} ${escapeHtml(meta.label)} — what stops work here</span>
      <span class="cal-pill mini def" style="margin-left:auto">criteria in full</span></div>
    <div class="cal-crit-lead">A construction <b>working</b> day between the data date and finish is a <b>lost day</b> when <b>any</b> limit below is met. Days already off (weekend / holiday / shutdown) are never double-counted.</div>
    ${rows}
    <div class="cal-crit-any">⚠️ Any one limit met → that day is a lost construction day. These exact limits are carried into the PDF.</div>
  </div>`;
}

const _PERF_IC = { wind: '💨', heat: '🌡', rain: '🌧', dust: '🌫' };

// "Why this result" — how each limit performed, so a near-zero is never a silent black box.
function _whyResultHtml() {
  const w = _weather;
  if (!w || !w.limit_performance) return '';
  const unit = u => (u ? ' ' + u : '');
  const rows = w.limit_performance.map(p => {
    const ic = `<span class="mk">${_PERF_IC[p.key] || '•'}</span>`;
    if (!p.on) {
      const peak = p.peak != null ? ` — highest seen ${p.peak}${unit(p.unit)}` : '';
      return `<div class="cal-why-row">${ic}<span class="noflag"><b>${escapeHtml(p.label)}</b> — off (not counted)${peak}</span></div>`;
    }
    const flagged = p.flagged || 0;
    const limTxt = p.limit != null ? ` ≥ ${p.limit}${unit(p.unit)}` : '';
    const peak = p.peak != null ? ` · peak ${p.peak}${unit(p.unit)}` : '';
    return `<div class="cal-why-row">${ic}<span class="${flagged ? 'flag' : 'noflag'}">
      <b>${escapeHtml(p.label)}${limTxt} → flagged ${flagged} ${flagged === 1 ? 'day' : 'days'}.</b>${peak}</span></div>`;
  }).join('');
  return _sec(3, 'Why this result',
      'how each limit performed over the project window — a near-zero is explained, not hidden') +
    `<div class="cal-why">${rows}</div>`;
}

// Source & climate reference — where the bad-weather days come from (shown on import).
function _climateRefHtml() {
  const r = _weather && _weather.climate_reference;
  if (!r) return '';
  const loc = (r.place_name ? escapeHtml(r.place_name) + ' · ' : '') +
    (r.lat != null ? `${(+r.lat).toFixed(2)}°, ${(+r.lon).toFixed(2)}°` : '');
  const yrs = (r.year_start && r.year_end) ? `${r.year_start}–${r.year_end} (${r.years} years)` : `${r.years} years`;
  const row = (k, v) => `<div class="cal-ref-row"><div class="cal-ref-k">${k}</div><div class="cal-ref-v">${v}</div></div>`;
  // Demoted to a footnote (collapsible) below §7 — reference, not a headline section.
  return `<details class="cal-foot-details">
      <summary>🔗 Where these bad-weather days come from — data source &amp; climate reference</summary>
    <div class="cal-ref">
      ${row('Climate history', `<b>${escapeHtml(r.history_source)}</b> — <span class="cal-ref-url">${escapeHtml(r.history_url)}</span>`)}
      ${row('History window', `<b>${yrs}</b>, averaged per month`)}
      ${loc ? row('Location', loc) : ''}
      ${row('Live forecast', `${escapeHtml(r.forecast_source)} — <span class="cal-ref-url">${escapeHtml(r.forecast_url)}</span> (next ~16 days)`)}
      ${row('Dust / sandstorm', escapeHtml(r.dust_source))}
      <div class="cal-ref-note">Beyond ~16 days these are <b>climate-based expectations</b> (5-year average for this site) — not a guaranteed forecast. Kept separate from the exact P6 Delay.</div>
    </div></details>`;
}

// The construction activities a bad-weather day hits (#07).
function _actsCell(d) {
  const names = d.activities || [];
  const extra = (d.activities_count != null ? d.activities_count : names.length) - names.length;
  if (names.length) {
    return escapeHtml(names.join(', ')) + (extra > 0 ? ` <span class="cal-muted">(+${extra} more)</span>` : '');
  }
  if ((d.effect || '').startsWith('Non-working')) {
    return '<span class="cal-muted">No construction activity scheduled</span>';
  }
  return `<span class="cal-muted">${escapeHtml(d.effect || '')}</span>`;
}

// Calendar days between two ISO dates (b − a); 0 if either missing.
function _daysBetween(a, b) {
  if (!a || !b) return 0;
  return Math.round((new Date(b) - new Date(a)) / 86400000);
}

// Feature 2 §1 — Execution Dashboard: Baseline Finish → Forecast Completion → Bad-weather
// Completion, with the variance on each step (schedule's own slip, then what weather adds).
function _weatherDashboard() {
  const d = (_ca && _ca.dashboard) || {};
  const w = _weather;
  const slip = _daysBetween(d.baseline_finish, d.project_finish);   // schedule's own slip (cal. days)
  const wxAdd = w.net_finish_delay || 0;                            // weather adds (working days)
  return _sec(1, 'Execution Dashboard', '<span class="cal-pill warn">Estimate · not a P6 figure</span>') +
    `<div class="cal-flow">
      <div class="cal-step bl"><div class="cal-k">Baseline Finish</div><div class="cal-v">${fmtCalDate(d.baseline_finish)}</div></div>
      <div class="cal-arrow"><div class="cal-alab">Schedule slip</div><div class="cal-avar ${slip > 0 ? 'pos' : 'zero'}">${slip > 0 ? '+' : ''}${slip} d</div><div class="cal-aln">→</div></div>
      <div class="cal-step fc"><div class="cal-k">Forecast Completion</div><div class="cal-v">${fmtCalDate(d.project_finish)}</div></div>
      <div class="cal-arrow"><div class="cal-alab">Weather adds</div><div class="cal-avar ${wxAdd > 0 ? 'pos' : 'zero'}">+${wxAdd} wd</div><div class="cal-aln">→</div></div>
      <div class="cal-step bw"><div class="cal-k">Bad-weather Completion</div><div class="cal-v">${fmtCalDate(w.weather_adjusted_finish)}</div></div>
    </div>
    <div class="cal-note">Reads left → right: the baseline finish, the schedule's own forecast finish, then the weather-adjusted finish. Each arrow shows that step's variance — the schedule's own slip, then, separately, what bad weather adds.</div>`;
}

// Feature 2 §2 — 3-colour monthly histogram: net working (green) / bad-weather (amber) /
// non-working (red) days; the number above each bar is the NET working days that month.
function _weatherHistogram() {
  const geom = hist3Geom((_weather && _weather.histogram) || []);
  if (!geom.length) return '';
  const bars = geom.map(m =>
    `<div class="cal-3bar" title="${escapeHtml(m.label)}: ${m.net} net working · ${m.bad} bad-weather · ${m.nonworking} non-working">
      <div class="cal-3v">${m.net}</div>
      <div class="cal-3col">
        <div class="s-bad" style="height:${m.badPx}px"></div>
        <div class="s-nw" style="height:${m.nwPx}px"></div>
        <div class="s-net" style="height:${m.netPx}px"></div>
      </div>
      <div class="cal-3l">${escapeHtml(m.label)}</div></div>`).join('');
  return _sec(2, 'Calendar Timeline &amp; Statistics') +
    `<div class="cal-3title">${escapeHtml(_scopeName())}</div>
     <div class="cal-3sub">Net-working (green) · non-working (red) · bad-weather (amber) days per month · the number above each bar = <b>net working days</b> (working − bad-weather)</div>
     <div class="cal-3leg"><span><i class="sw sw-net"></i>Net working days</span>
       <span><i class="sw sw-nw"></i>Non-working days</span>
       <span><i class="sw sw-bad"></i>Bad-weather days (expected)</span>
       <span>▲ number above bar = <b>net working days</b></span></div>
     <div class="cal-3hist">${bars}</div>`;
}

function _weatherSection() {
  // The data-date banner + compact entry bar are emitted by _renderWeatherBody (above this).
  if (!_pendingLoc) {
    return `<div class="cal-card"><p style="color:var(--muted);font-size:13px;margin:0">
      Pick a <b>Project Type</b> and set the <b>Location</b> in the bar above (or drop a pin on the map), then click <b>Calculate weather</b> to see the expected bad-weather days, milestone impact and recovery options.</p></div>`;
  }
  const controls = `<div class="cal-card" style="margin-bottom:12px">${_weatherControls()}</div>`;
  if (!_weather) {
    return controls + `<div class="cal-card"><p style="color:var(--muted);font-size:13px;margin:0">
      Adjust the stop-work limits above if needed, then click <b>Apply &amp; recalculate</b> (or <b>Calculate weather</b> in the entry bar).</p></div>`;
  }
  const w = _weather;
  const dashboard = _weatherDashboard();      // §1 Execution Dashboard (waterfall)
  const histogram = _weatherHistogram();      // §2 Calendar Timeline & Statistics (3-colour)
  // §5 — Upcoming bad weather
  const dayRows = (w.bad_days || []).slice(0, 200).map(d =>
    `<tr><td>${fmtCalDate(d.date)}</td><td>${escapeHtml(d.day_name)}</td>
      <td>${escapeHtml(d.condition)}</td>
      <td><span class="cal-pill mini ${d.confidence === 'forecast' ? 'def' : 'warn'}">${d.confidence === 'forecast' ? 'Forecast' : 'Expected'}</span></td>
      <td>${_actsCell(d)}</td></tr>`).join('');
  const dayTable = _sec(5, 'Upcoming bad weather',
      'next ~16 days = live forecast · beyond = a typical year from the 5-year climate history') +
    `<div class="cal-card p0" style="max-height:300px;overflow-y:auto"><table class="cal-table"><thead><tr>
      <th>Date</th><th>Day</th><th>Why it's a lost day (measured)</th><th>Confidence</th><th>Affected work (by WBS)</th></tr></thead>
      <tbody>${dayRows || '<tr><td colspan="5" class="cal-empty">No bad-weather days expected.</td></tr>'}</tbody></table></div>`;
  // §6 — Impact on milestones
  const msRows = (w.milestones || []).map(m =>
    `<tr><td>${escapeHtml(m.name)}</td><td>${fmtCalDate(m.planned)}</td>
      <td class="num">${m.bad_days_before}</td><td class="num">${m.already_allowed}</td>
      <td class="num"><span class="cal-pill mini ${m.net_delay > 0 ? 'shutdown' : 'def'}">+${m.net_delay} d</span></td>
      <td>${fmtCalDate(m.adjusted)}</td></tr>`).join('');
  const msTable = _sec(6, 'Impact on milestones') +
    `<div class="cal-card p0"><table class="cal-table"><thead><tr>
      <th>Milestone</th><th>Planned completion</th><th class="num">Bad-weather days before it</th>
      <th class="num">Already in calendar</th><th class="num">Net weather delay</th><th>Weather-adjusted completion</th></tr></thead>
      <tbody>${msRows || '<tr><td colspan="6" class="cal-empty">No milestones found.</td></tr>'}</tbody></table></div>
     <div class="cal-note" style="font-style:normal"><b>How to read this table:</b> <b>Bad-weather days before it</b> — expected bad-weather days between the data date and the milestone's planned finish. <b>Already in calendar</b> — of those, the ones landing on a day already off (weekend / holiday / shutdown), so they cost nothing extra. <b>Net weather delay</b> — the rest, hitting real working days (<b>Net = Before − Already in calendar</b>): the actual days weather adds. <i>Example — 6 bad-weather days before finish; 4 already fell on off-days, so only 2 hit working days → +2 working days.</i></div>`;
  // §7 — Recovery recommendation
  const recRows = (w.recovery || []).map(r =>
    `<tr><td>${escapeHtml(r.period)}</td><td class="num"><span class="cal-pill mini shutdown">${r.days} d</span></td>
      <td>${escapeHtml(r.option_longer_days)}</td><td>${escapeHtml(r.option_extra_days)}</td><td>${escapeHtml(r.option_shift)}</td></tr>`).join('');
  const recTable = _sec(7, 'Recovery recommendation', 'advisory — one option per period, computed from the estimated lost hours') +
    `<div class="cal-card p0"><table class="cal-table"><thead><tr>
      <th>Period / milestone</th><th class="num">Days</th><th>Longer days</th><th>Extra working days</th><th>Add shift</th></tr></thead>
      <tbody>${recRows || '<tr><td colspan="5" class="cal-empty">No recovery needed — no net weather delay.</td></tr>'}</tbody></table></div>`;
  // §4 — What's causing the lost days, by weather type
  const totalBad = w.expected_bad_days_total || 0;
  const causeColor = { Heat: 'var(--danger)', Dust: 'var(--warning)', Rain: 'var(--chart-1)', Wind: 'var(--muted)' };
  const causeRows = (w.by_cause || []).map(c => {
    const off = !!c.off;
    const cnt = off ? 0 : (c.count || 0);
    const pct = (!off && totalBad) ? Math.round(cnt / totalBad * 100) : 0;
    const val = off ? 'off' : `${cnt} ${cnt === 1 ? 'day' : 'days'}${totalBad ? ` · ${pct}%` : ''}`;
    return `<div class="cal-cause"><div class="cal-cause-l">${escapeHtml(c.label)}</div>
      <div class="cal-cause-track"><div class="cal-cause-fill" style="width:${off ? 0 : pct}%;background:${causeColor[c.label] || 'var(--accent)'}"></div></div>
      <div class="cal-cause-n">${val}</div></div>`;
  }).join('');
  const causeCard = (w.by_cause || []).length
    ? _sec(4, "What's causing the lost days — by weather type", 'which condition to plan around (heat → shift hours earlier; rain → drainage)') +
      `<div class="cal-card">${causeRows}</div>`
    : '';
  // Footnotes (after §7) — auto weather-conclusion, then the source & climate reference. Demoted.
  const conclHtml = w.conclusion
    ? `<div class="cal-foot"><span class="cal-foot-lab">Weather conclusion — auto-generated</span>
        <p style="margin:2px 0 0;font-size:12px;line-height:1.55">${escapeHtml(w.conclusion)}</p></div>`
    : '';
  const note = '<div class="cal-note">Applies to construction activities only (auto-detected), and only to Finish/completion milestones. A forward-looking risk, kept separate from the exact P6 Delay. Needs an internet connection.</div>';
  return controls + dashboard + histogram +
    _whyResultHtml() + causeCard + dayTable + msTable + recTable +
    conclHtml + _climateRefHtml() + note;
}

// Read the stop-work-limit inputs → thresholds object (blank = off).
function _readThresholds() {
  const n = id => {
    const v = document.getElementById(id);
    if (!v || v.value === '') return null;
    const f = parseFloat(v.value);
    return isNaN(f) ? null : f;
  };
  return {
    rain_mm: n('thr-rain'), temp_max_c: n('thr-heat'), wind_kmh: n('thr-wind'),
    dust: !!(document.getElementById('thr-dust') && document.getElementById('thr-dust').checked),
  };
}

// ── wiring ─────────────────────────────────────────────────────────────────
function _wireCalendar() {
  // §2 calendar chips: _sel is the primary (main histogram), _sel2 the optional comparison.
  // Click an unselected chip → it becomes the comparison (2nd histogram); click a selected
  // chip → toggle it off (primary clicked with a compare present promotes the compare).
  document.querySelectorAll('#calendar-body .cal-chip').forEach(chip =>
    chip.addEventListener('click', () => {
      const id = chip.dataset.cal;
      if (!id) return;
      if (id === _sel) { if (_sel2) { _sel = _sel2; _sel2 = null; } }
      else if (id === _sel2) { _sel2 = null; }
      else { _sel2 = id; }
      _openMonths.clear();
      _renderCalendarBody();
    }));

  document.querySelectorAll('#calendar-body .cal-whc').forEach(bar =>
    bar.addEventListener('click', () => {
      const i = +bar.dataset.month;
      if (_openMonths.has(i)) _openMonths.delete(i); else _openMonths.add(i);
      _renderCalendarBody();
    }));

  _wireShutdowns();
}

function _wireWeatherView() {
  _wireEntry();
  _wireLocation();
  _wireWeather();
}

// Entry bar — the Project-Type dropdown loads the preset stop-work limits; Calculate runs it.
function _wireEntry() {
  const sel = document.getElementById('cal-entry-site');
  if (sel) sel.addEventListener('change', () => {
    const key = sel.value;
    if (!SITE_TYPES[key]) return;                       // '' placeholder / 'custom' — not a choice
    _siteType = key;
    _thresholds = { ...SITE_TYPES[key].thresholds };
    _renderWeatherBody();                               // reloads the criteria panel + limit inputs
  });
  const go = document.getElementById('cal-entry-go');
  if (go) go.addEventListener('click', () => _runWeather(go, document.getElementById('cal-loc-status')));
}

function _wireLocation() {
  const q = document.getElementById('cal-loc-q');
  const searchBtn = document.getElementById('cal-loc-search-btn');
  const results = document.getElementById('cal-loc-results');
  const useBtn = document.getElementById('cal-loc-use');
  const statusEl = document.getElementById('cal-loc-status');
  const doSearch = async () => {
    const term = (q.value || '').trim();
    if (!term) return;
    results.innerHTML = '<div class="cal-muted" style="font-size:12px">Searching…</div>';
    const resp = await geocodePlace(term);
    if (!resp.ok || !(resp.results || []).length) {
      results.innerHTML = `<div class="cal-muted" style="font-size:12px">No matches (offline?).</div>`;
      return;
    }
    results.innerHTML = resp.results.map((r, i) =>
      `<div class="cal-loc-hit" data-i="${i}">${escapeHtml(r.name)}</div>`).join('');
    results.querySelectorAll('.cal-loc-hit').forEach(el =>
      el.addEventListener('click', () => {
        const r = resp.results[+el.dataset.i];
        // Update the pin in place (no full re-render) so the map stays put while fine-tuning.
        _pendingLoc = { lat: +r.lat, lon: +r.lon, name: r.name };
        _updateLocReadout();
        _panMapTo(+r.lat, +r.lon);
        results.innerHTML = '';
      }));
  };
  if (searchBtn) searchBtn.addEventListener('click', doSearch);
  if (q) q.addEventListener('keydown', e => { if (e.key === 'Enter') doSearch(); });
  if (useBtn) useBtn.addEventListener('click', () => _runWeather(useBtn, statusEl));
  _initMap();
}

// Refresh the coordinates read-out (map card + entry bar) + enable both Calculate buttons
// (no full re-render, so the map stays put while the pin is fine-tuned).
function _updateLocReadout() {
  const el = document.getElementById('cal-loc-readout');
  if (el) el.innerHTML = _locationReadoutHtml();
  const use = document.getElementById('cal-loc-use');
  if (use && _pendingLoc) use.disabled = false;
  const eb = document.getElementById('cal-entry-loc');
  if (eb) eb.innerHTML = _entryLocHtml();
  const go = document.getElementById('cal-entry-go');
  if (go && _pendingLoc) go.disabled = false;
}

// Load the vendored Leaflet (local file — ships in the .exe) exactly once.
function _ensureLeaflet() {
  if (window.L) return Promise.resolve(window.L);
  if (_leafletPromise) return _leafletPromise;
  _leafletPromise = new Promise(resolve => {
    const link = document.createElement('link');
    link.rel = 'stylesheet'; link.href = '/ui/vendor/leaflet/leaflet.css';
    document.head.appendChild(link);
    const s = document.createElement('script');
    s.src = '/ui/vendor/leaflet/leaflet.js';
    s.onload = () => resolve(window.L || null);
    s.onerror = () => resolve(null);
    document.head.appendChild(s);
  });
  return _leafletPromise;
}

function _pinIcon(L) {
  return L.divIcon({ className: 'cal-pin', html: '📍', iconSize: [26, 26], iconAnchor: [13, 24] });
}

// Drop or move the pin, set the pending location, then reverse-geocode a friendly name.
async function _setFromMap(latlng) {
  const lat = +latlng.lat.toFixed(6), lon = +latlng.lng.toFixed(6);
  const fallback = `${lat.toFixed(4)}, ${lon.toFixed(4)}`;
  _pendingLoc = { lat, lon, name: fallback };
  _updateLocReadout();
  const resp = await reverseGeocode(lat, lon);
  if (resp && resp.ok && resp.name) {
    _pendingLoc = { lat, lon, name: resp.name };
    _updateLocReadout();
  }
}

function _panMapTo(lat, lon) {
  if (!_map || !window.L) return;
  const ll = [+lat, +lon];
  try { _map.invalidateSize(); } catch { /* not visible */ }
  _map.setView(ll, 12);
  _placePin(ll, false);      // search already set the name — don't reverse-geocode over it
}

// Drop or move the location pin. `updateLoc` reverse-geocodes the point into _pendingLoc
// (a map tap); pass false when the caller already set the location (a search result).
function _placePin(latlng, updateLoc = true) {
  const L = window.L;
  if (!_map || !L) return;
  if (!_marker) {
    _marker = L.marker(latlng, { draggable: true, icon: _pinIcon(L) }).addTo(_map);
    _marker.on('dragend', () => _setFromMap(_marker.getLatLng()));
  } else {
    _marker.setLatLng(latlng);
  }
  if (updateLoc) _setFromMap(_marker.getLatLng());
}

async function _initMap() {
  const el = document.getElementById('cal-map');
  if (!el) return;
  const L = await _ensureLeaflet();
  // The body may have re-rendered while Leaflet loaded — bail if this node is gone.
  if (!L || !document.body.contains(el)) {
    if (el && !L) el.innerHTML = '<div class="cal-map-empty">Map needs an internet connection.</div>';
    return;
  }
  if (_mapRO) { try { _mapRO.disconnect(); } catch { /* gone */ } _mapRO = null; }
  if (_map) { try { _map.remove(); } catch { /* stale node */ } _map = null; _marker = null; }
  const hasLoc = _pendingLoc && _pendingLoc.lat != null;
  const center = hasLoc ? [+_pendingLoc.lat, +_pendingLoc.lon] : [24.5, 46.6]; // default: Arabian Peninsula
  _map = L.map(el, { attributionControl: true }).setView(center, hasLoc ? 11 : 5);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19, attribution: '© OpenStreetMap contributors',
  }).addTo(_map);
  if (hasLoc) {
    _marker = L.marker(center, { draggable: true, icon: _pinIcon(L) }).addTo(_map);
    _marker.on('dragend', () => _setFromMap(_marker.getLatLng()));
  }
  // Drop the pin on a tap. Leaflet's own 'click' is swallowed when the press→release moves
  // even a few px — a real trackpad / touch tap is never pixel-perfect — so "clicking a
  // point did nothing". Watch the container's own press→release and drop the pin whenever
  // the movement is small; a genuine pan moves much further. Covers mouse + touch. (#01)
  const cont = _map.getContainer();
  let downXY = null;
  const onDown = ev => {
    if (ev.target.closest('.leaflet-control')) { downXY = null; return; }
    const p = ev.touches ? ev.touches[0] : ev;
    downXY = { x: p.clientX, y: p.clientY };
  };
  const onUp = ev => {
    if (!downXY) return;
    const p = ev.changedTouches ? ev.changedTouches[0] : ev;
    const moved = Math.hypot(p.clientX - downXY.x, p.clientY - downXY.y);
    downXY = null;
    if (moved > 12) return;                                              // a pan, not a tap
    if (ev.target.closest('.leaflet-control') || ev.target.closest('.leaflet-marker-icon')) return;
    const r = cont.getBoundingClientRect();
    _placePin(_map.containerPointToLatLng(L.point(p.clientX - r.left, p.clientY - r.top)));
  };
  cont.addEventListener('mousedown', onDown);
  cont.addEventListener('mouseup', onUp);
  cont.addEventListener('touchstart', onDown, { passive: true });
  cont.addEventListener('touchend', onUp);
  // Leaflet mis-sizes when it inits inside a tab that isn't visible/sized yet (the pin
  // then lands at the edge). Re-measure when the container resizes (tab shown) and on a
  // couple of timed passes, recentring so the pin stays put. (#01)
  const recentre = () => {
    try { _map.invalidateSize(); _map.panTo(_marker ? _marker.getLatLng() : center); } catch { /* hidden */ }
  };
  if (window.ResizeObserver) {
    _mapRO = new ResizeObserver(() => { try { _map.invalidateSize(); } catch { /* hidden */ } });
    _mapRO.observe(el);
  }
  setTimeout(recentre, 80);
  setTimeout(recentre, 400);
}

// Wire the Weather-Impact "Apply & recalculate" (edited stop-work limits).
function _wireWeather() {
  const applyBtn = document.getElementById('thr-apply');
  if (applyBtn) applyBtn.addEventListener('click', () => {
    _thresholds = _readThresholds();
    _siteType = matchSiteType(_thresholds) || 'custom';   // edited away from a preset → Custom
    _runWeather(applyBtn, document.getElementById('thr-status'));
  });
}

async function _runWeather(btn, statusEl) {
  if (!_pendingLoc) return;
  if (btn) btn.disabled = true;
  if (statusEl) statusEl.textContent = 'Calculating weather…';
  try {
    const resp = await computeWeather(_pendingLoc.lat, _pendingLoc.lon, _pendingLoc.name, _thresholds, _siteType);
    if (resp.ok) {
      _weather = resp.weather;
      _pendingLoc = resp.location || _pendingLoc;
      if (resp.weather && resp.weather.thresholds) _thresholds = resp.weather.thresholds;
      if (resp.offline && statusEl) statusEl.textContent = 'No weather data (offline) — location saved.';
      _renderWeatherBody();
    } else if (statusEl) {
      statusEl.textContent = resp.error || 'Weather failed.'; if (btn) btn.disabled = false;
    }
  } catch {
    if (statusEl) statusEl.textContent = 'Weather failed (offline?).';
    if (btn) btn.disabled = false;
  }
}

function _wireShutdowns() {
  const addBtn = document.getElementById('cal-add-shutdown-btn');
  const form = document.getElementById('cal-add-shutdown');
  if (addBtn && form) addBtn.addEventListener('click', () => form.classList.toggle('hidden'));
  const saveBtn = document.getElementById('cal-sd-save');
  if (saveBtn) saveBtn.addEventListener('click', async () => {
    const start = document.getElementById('cal-sd-start').value;
    const end = document.getElementById('cal-sd-end').value;
    const reason = document.getElementById('cal-sd-reason').value;
    if (!start) return;
    const existing = _existingManualShutdowns();
    existing.push({ start, end: end || start, reason });
    const resp = await saveCalendarSettings({ manual_shutdowns: existing });
    if (resp.ok && resp.calendar_audit) { _ca = resp.calendar_audit; _renderCalendarBody(); }
  });
  // reason inline-edit (both P6 and manual shutdowns) → store per project
  document.querySelectorAll('#calendar-body .cal-reason').forEach(inp =>
    inp.addEventListener('change', async () => {
      const key = inp.dataset.key; if (!key) return;
      const reasons = {}; reasons[key] = inp.value;
      const resp = await saveCalendarSettings({ shutdown_reasons: reasons });
      if (resp.ok && resp.calendar_audit) { _ca = resp.calendar_audit; _renderCalendarBody(); }
    }));
  // working-hours note inline-edit (§5) → store per project (mirrors the shutdown reasons)
  document.querySelectorAll('#calendar-body .cal-hnote').forEach(inp =>
    inp.addEventListener('change', async () => {
      const key = inp.dataset.key; if (!key) return;
      const notes = {}; notes[key] = inp.value;
      const resp = await saveCalendarSettings({ hours_notes: notes });
      if (resp.ok && resp.calendar_audit) { _ca = resp.calendar_audit; _renderCalendarBody(); }
    }));
}

function _existingManualShutdowns() {
  const out = [];
  Object.values(_ca.by_calendar || {}).forEach(bc =>
    (bc.exceptions && bc.exceptions.shutdowns || []).forEach(s => {
      if (s.source === 'manual') out.push({ start: s.start, end: s.end, reason: s.reason || '' });
    }));
  // de-dup by start
  const seen = new Set();
  return out.filter(s => (seen.has(s.start) ? false : seen.add(s.start)));
}
