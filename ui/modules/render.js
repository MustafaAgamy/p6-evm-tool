import { state }                                   from './state.js';
import { fmtEGP, fmtDate, kpiColor, escapeHtml }  from './format.js';
import { renderAudit, renderOosPanel, renderLagPanel, showChooser } from './audit.js';
import { renderEvm }                                from './evm.js';
import { renderCalendar, renderWeatherView }        from './calendar.js';

const KPI_TOOLTIPS = {
  'Finish Delay':  'Days behind schedule — positive = late, negative = ahead',
  'SPI':           'Schedule Performance Index: Earned Value ÷ Planned Value',
  'Planned Value': 'Budgeted cost of work scheduled to date',
  'Earned Value':  'Budgeted cost of work actually completed',
  'Actual Cost':   'Real cost incurred to date',
  'CPI':           'Cost Performance Index: Earned Value ÷ Actual Cost',
};

export function setLoading(active) {
  document.getElementById('browse-btn')?.classList.toggle('hidden', active);
  document.getElementById('browse-spinner')?.classList.toggle('hidden', !active);
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
  document.getElementById('import-section')?.classList.remove('hidden');  // Aurora+ landing back
  document.getElementById('topbar-sub').textContent = 'Home · Import';
  document.getElementById('feature-gate')?.classList.add('hidden');       // clear any open Run gate
  if (state.ranFeatures && typeof state.ranFeatures.clear === 'function') state.ranFeatures.clear();
  // Back to the import screen: clear any active module in the navigator (Aurora+ shell).
  document.querySelectorAll('#nav-tree .tnode[data-nav]').forEach(n =>
    n.classList.toggle('on', n.dataset.nav === 'home'));
  state.currentResult      = null;
  state.currentXmlPath     = null;
  state.currentCachedPath  = null;
  state.currentSnapshotId  = null;
  state.currentModules     = null;
  state.currentModule      = null;
  state.aiReport           = null;
  state.aiReferencePath    = null;
  state.aiReferenceName    = null;
  state.constructReport    = null;
  state.constructForcedType = null;
}

export function renderResults(result, filePath, { previousImport = null } = {}) {
  // A newly shown schedule must never inherit the previous one's review.
  state.aiReport = null;
  state.aiReferencePath = null;
  state.aiReferenceName = null;
  state.constructReport = null;
  state.constructForcedType = null;
  const filename = filePath.split(/[\\/]/).pop();
  const dataDate = fmtDate(result.data_date);
  const actCount = result.activity_count ?? '?';
  const calCount = result.calendar_count  ?? '?';

  const prevNote = previousImport
    ? `  ·  Previously imported ${fmtDate(previousImport.slice(0, 10))} · results updated`
    : '';
  document.getElementById('file-info-bar').textContent =
    `${filename}  ·  Data date: ${dataDate}  ·  ${actCount} activities  ·  ${calCount} calendars${prevNote}`;
  document.getElementById('topbar-sub').textContent = `${filename} · ${dataDate}`;

  // Issues #3/#4: importing must NOT run or display any feature's analysis. We only
  // show a light read-only snapshot + the "Choose a feature to analyze" prompt. Each
  // feature computes and renders on its own explicit Run (see app.js openView/runFeature).
  if (state.ranFeatures && typeof state.ranFeatures.clear === 'function') state.ranFeatures.clear();
  renderImportSummary(result);
  showChooser();   // "Choose a feature to analyze" — the user picks; nothing auto-runs

  document.getElementById('import-section')?.classList.add('hidden');   // Aurora+: landing gives way to results
  document.getElementById('results-section').classList.remove('hidden');
}

// Light read-only snapshot shown right after import — headline metrics only, from the
// EVM figures already computed by parse. The full features stay gated behind their Run.
function renderImportSummary(result) {
  const el = document.getElementById('import-summary');
  if (!el) return;
  const num = (v, d = 2) => (v == null || Number.isNaN(Number(v))) ? '—' : Number(v).toFixed(d);
  const spi = result.spi, cpi = result.cpi, delay = result.delay_days, pct = result.overall_actual_pct;
  const cls = (v, good) => v == null ? '' : (good ? 'pos' : 'neg');
  const tiles = [
    ['Progress',     pct != null ? `${num(pct, 1)}%` : '—', ''],
    ['Finish delay', delay != null ? `${delay}d` : '—', delay == null ? '' : (delay > 0 ? 'neg' : (delay < 0 ? 'pos' : ''))],
    ['SPI',          spi != null ? num(spi) : '—', cls(spi, spi >= 1)],
    ['CPI',          cpi != null ? num(cpi) : '—', cls(cpi, cpi >= 1)],
  ];
  el.innerHTML =
    `<div class="isum-lbl">Schedule snapshot <span>headline metrics · open a feature for the full analysis</span></div>
     <div class="isum-row">${tiles.map(([k, v, c]) =>
       `<div class="isum-tile"><span class="isum-k">${k}</span><span class="isum-v ${c}">${v}</span></div>`).join('')}</div>`;
}

export function renderHistory(history) {
  const tbody = document.getElementById('recent-tbody');
  const totalEl = document.getElementById('recent-total');
  if (totalEl) totalEl.textContent = history.length
    ? `${history.length} project${history.length === 1 ? '' : 's'}`
    : 'none yet';
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
              title="Re-open this schedule"
            >Open</button>
            <button
              class="delete-btn"
              data-project-id="${escapeHtml(h.project_id)}"
              title="Remove all history for this project"
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
