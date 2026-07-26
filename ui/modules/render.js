import { state }                                   from './state.js';
import { fmtEGP, fmtDate, kpiColor, escapeHtml }  from './format.js';

const KPI_TOOLTIPS = {
  'Finish Delay':  'Days behind schedule — positive = late, negative = ahead',
  'SPI':           'Schedule Performance Index: Earned Value ÷ Planned Value',
  'Planned Value': 'Budgeted cost of work scheduled to date',
  'Earned Value':  'Budgeted cost of work actually completed',
  'Actual Cost':   'Real cost incurred to date',
  'CPI':           'Cost Performance Index: Earned Value ÷ Actual Cost',
};

export function setLoading(active) {
  document.getElementById('browse-btn').classList.toggle('hidden', active);
  document.getElementById('browse-spinner').classList.toggle('hidden', !active);
  if (active) {
    document.getElementById('topbar-sub').textContent = 'Parsing…';
  } else if (!state.currentResult) {
    document.getElementById('topbar-sub').textContent = 'Home · Import';
  }
}

export function showError(msg) {
  document.getElementById('error-text').textContent = msg;
  document.getElementById('error-banner').classList.remove('hidden');
}

export function clearError() {
  document.getElementById('error-banner').classList.add('hidden');
}

export function loadAnother() {
  document.getElementById('results-section').classList.add('hidden');
  document.getElementById('topbar-sub').textContent = 'Home · Import';
  state.currentResult      = null;
  state.currentXmlPath     = null;
  state.currentCachedPath  = null;
}

export function renderResults(result, filePath) {
  const filename = filePath.split(/[\\/]/).pop();
  const dataDate = fmtDate(result.data_date);
  const actCount = result.activity_count ?? '?';
  const calCount = result.calendar_count  ?? '?';

  document.getElementById('file-info-bar').textContent =
    `${filename}  ·  Data date: ${dataDate}  ·  ${actCount} activities  ·  ${calCount} calendars`;
  document.getElementById('topbar-sub').textContent = `${filename} · ${dataDate}`;

  const delay  = result.delay_days;
  const cpiVal = result.cpi;
  const cpiNote = (cpiVal != null && Math.abs(cpiVal - 1) < 0.02) ? '≈ 1 (AutoComputeActuals)' : '';

  const kpis = [
    { label: 'Finish Delay',  value: delay      != null ? `${delay}d`             : '—', color: kpiColor(delay,      'delay') },
    { label: 'SPI',           value: result.spi != null ? result.spi.toFixed(2)   : '—', color: kpiColor(result.spi, 'index') },
    { label: 'Planned Value', value: fmtEGP(result.pv), color: 'color-neutral' },
    { label: 'Earned Value',  value: fmtEGP(result.ev), color: 'color-neutral' },
    { label: 'Actual Cost',   value: fmtEGP(result.ac), color: 'color-neutral' },
    { label: 'CPI',           value: cpiVal     != null ? cpiVal.toFixed(2)        : '—', color: kpiColor(cpiVal,     'index'), note: cpiNote },
  ];

  document.getElementById('kpi-row').innerHTML = kpis.map(k => `
    <div class="kpi-tile" data-tooltip="${KPI_TOOLTIPS[k.label] || ''}">
      <div class="kpi-label">${k.label}</div>
      <div class="kpi-value ${k.color}">${k.value}</div>
      ${k.note ? `<div class="kpi-note">${k.note}</div>` : ''}
    </div>
  `).join('');

  const categories = result.categories || {};
  const catHTML = Object.entries(categories).map(([name, cat]) => {
    const planned = ((cat.planned_pct ?? 0) * 100);
    const actual  = ((cat.actual_pct  ?? 0) * 100);
    return `
      <div class="cat-row">
        <div class="cat-name">${name}</div>
        <div class="cat-bars">
          <div class="bar-track"><div class="bar-fill bar-planned" style="width:${Math.min(planned, 100).toFixed(1)}%"></div></div>
          <div class="bar-track"><div class="bar-fill bar-actual"  style="width:${Math.min(actual,  100).toFixed(1)}%"></div></div>
        </div>
        <div class="cat-pcts">
          <span>${planned.toFixed(1)}%</span> planned<br>
          <strong>${actual.toFixed(1)}%</strong> actual
        </div>
      </div>
    `;
  }).join('');

  document.getElementById('category-progress').innerHTML =
    catHTML || '<p style="color:var(--muted);font-size:12px">No category data found in config.json</p>';

  document.getElementById('results-section').classList.remove('hidden');
}

export function renderHistory(history) {
  const tbody = document.getElementById('recent-tbody');
  if (!history.length) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="6">No recent projects — import a P6 XML file to get started.</td></tr>';
    return;
  }
  tbody.innerHTML = history.map(h => {
    const delay    = h.delay;
    const delayTxt = delay != null ? `${delay}d` : '—';
    const delayCol = delay != null && delay > 0 ? 'color-red' : (delay != null && delay < 0 ? 'color-green' : '');
    const spiTxt   = h.spi != null ? h.spi.toFixed(2) : '—';
    const spiCol   = h.spi != null ? kpiColor(h.spi, 'index') : '';
    const pct      = h.construction_pct != null ? (h.construction_pct * 100) : null;
    return `
      <tr>
        <td title="${escapeHtml(h.path)}">${escapeHtml(h.filename)}</td>
        <td>${fmtDate(h.data_date)}</td>
        <td class="${delayCol}">${delayTxt}</td>
        <td class="${spiCol}">${spiTxt}</td>
        <td>
          ${pct != null ? `
            <div class="mini-progress">
              <div class="mini-progress-fill" style="width:${Math.min(pct, 100).toFixed(1)}%"></div>
            </div>
            <span style="font-size:11px;color:var(--muted)">${pct.toFixed(1)}%</span>
          ` : '<span style="color:var(--muted)">—</span>'}
        </td>
        <td>
          <div class="row-actions">
            <button
              class="open-btn"
              data-path="${escapeHtml(h.path)}"
              data-cached="${escapeHtml(h.cached_path)}"
              data-project-id="${escapeHtml(h.project_id)}"
              data-tooltip="Re-open this schedule"
            >Open</button>
            <button
              class="delete-btn"
              data-project-id="${escapeHtml(h.project_id)}"
              data-tooltip="Remove all history for this project"
              aria-label="Delete project"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="3 6 5 6 21 6"/>
                <path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/>
                <path d="M10 11v6M14 11v6"/>
                <path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2"/>
              </svg>
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}
