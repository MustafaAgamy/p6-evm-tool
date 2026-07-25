'use strict';

// ── State ──────────────────────────────────────────────────────────────────
let serverPort = null;
let currentResult = null;
let currentXmlPath = null;
let currentCachedPath = null;  // fallback for PDF if original file is moved/deleted

// ── Theme ──────────────────────────────────────────────────────────────────
function initTheme() {
  const saved = localStorage.getItem('p6_evm_theme') || 'light';
  if (saved === 'light') document.documentElement.classList.add('light');
  document.getElementById('theme-toggle').addEventListener('click', toggleTheme);
}

function toggleTheme() {
  const isLight = document.documentElement.classList.toggle('light');
  localStorage.setItem('p6_evm_theme', isLight ? 'light' : 'dark');
}

// ── File selection ─────────────────────────────────────────────────────────
document.getElementById('browse-btn').addEventListener('click', async () => {
  const path = await window.pywebview.api.choose_file();
  if (path) importFile(path);
});

const dropTarget = document.getElementById('drop-target');
const dropStrip  = document.getElementById('drop-strip');

dropTarget.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropStrip.classList.add('drag-over');
});
dropTarget.addEventListener('dragleave', (e) => {
  if (!dropTarget.contains(e.relatedTarget)) {
    dropStrip.classList.remove('drag-over');
  }
});
dropTarget.addEventListener('drop', (e) => {
  e.preventDefault();
  dropStrip.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (!file) return;
  const filePath = file.path;
  if (!filePath || !filePath.toLowerCase().endsWith('.xml')) {
    showError('Please drop a .xml file exported from Primavera P6.');
    return;
  }
  importFile(filePath);
});

// ── Import ─────────────────────────────────────────────────────────────────
async function importFile(filePath) {
  clearError();
  setLoading(true);
  try {
    const resp = await fetch(`http://localhost:${serverPort}/api/parse`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ path: filePath, overrides_path: null }),
    });
    const data = await resp.json();
    if (!data.ok) {
      showError(data.error || 'Parse failed.');
      return;
    }
    currentResult     = data.result;
    currentXmlPath    = filePath;
    currentCachedPath = data.cached_path || null;
    renderResults(data.result, filePath);
    loadHistory();
  } catch (err) {
    showError('Could not reach the local server. Try restarting the app.');
  } finally {
    setLoading(false);
  }
}

function setLoading(active) {
  document.getElementById('browse-btn').classList.toggle('hidden', active);
  document.getElementById('browse-spinner').classList.toggle('hidden', !active);
  if (active) {
    document.getElementById('topbar-sub').textContent = 'Parsing…';
  } else if (!currentResult) {
    document.getElementById('topbar-sub').textContent = 'Home · Import';
  }
  // If turning off while result exists, renderResults already set the subtitle correctly
}

// ── Error helpers ──────────────────────────────────────────────────────────
function showError(msg) {
  document.getElementById('error-text').textContent = msg;
  document.getElementById('error-banner').classList.remove('hidden');
}

function clearError() {
  document.getElementById('error-banner').classList.add('hidden');
}

// ── Load another ───────────────────────────────────────────────────────────
function loadAnother() {
  document.getElementById('results-section').classList.add('hidden');
  document.getElementById('topbar-sub').textContent = 'Home · Import';
  currentResult     = null;
  currentXmlPath    = null;
  currentCachedPath = null;
  loadHistory();
}

// ── Formatters ─────────────────────────────────────────────────────────────
function fmtEGP(n) {
  if (n == null) return '—';
  const abs = Math.abs(n);
  if (abs >= 1e9) return `EGP ${(n / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `EGP ${(n / 1e6).toFixed(1)}M`;
  return `EGP ${Math.round(n).toLocaleString()}`;
}

function fmtDate(iso) {
  if (!iso) return '—';
  // handle both ISO strings and plain date strings
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

function kpiColor(val, type) {
  if (val == null) return 'color-neutral';
  if (type === 'delay') return val > 0 ? 'color-red' : 'color-green';
  if (type === 'index') {
    if (val < 0.85) return 'color-red';
    if (val < 1.0)  return 'color-amber';
    return 'color-green';
  }
  return 'color-neutral';
}

// ── Results rendering ──────────────────────────────────────────────────────
function renderResults(result, filePath) {
  const filename   = filePath.split(/[\\/]/).pop();
  const dataDate   = fmtDate(result.data_date);
  const actCount   = result.activity_count ?? '?';
  const calCount   = result.calendar_count  ?? '?';

  // File info bar
  document.getElementById('file-info-bar').textContent =
    `${filename}  ·  Data date: ${dataDate}  ·  ${actCount} activities  ·  ${calCount} calendars`;

  // Topbar subtitle
  document.getElementById('topbar-sub').textContent = `${filename} · ${dataDate}`;

  // KPI tiles
  const delay = result.delay_days;
  const cpiVal = result.cpi;
  const cpiNote = (cpiVal != null && Math.abs(cpiVal - 1) < 0.02) ? '≈ 1 (AutoComputeActuals)' : '';

  const kpis = [
    { label: 'Finish Delay',   value: delay != null ? `${delay}d` : '—', color: kpiColor(delay, 'delay'), note: '' },
    { label: 'SPI',            value: result.spi != null ? result.spi.toFixed(2) : '—', color: kpiColor(result.spi, 'index'), note: '' },
    { label: 'Planned Value',  value: fmtEGP(result.pv),  color: 'color-neutral', note: '' },
    { label: 'Earned Value',   value: fmtEGP(result.ev),  color: 'color-neutral', note: '' },
    { label: 'Actual Cost',    value: fmtEGP(result.ac),  color: 'color-neutral', note: '' },
    { label: 'CPI',            value: cpiVal != null ? cpiVal.toFixed(2) : '—', color: kpiColor(cpiVal, 'index'), note: cpiNote },
  ];

  document.getElementById('kpi-row').innerHTML = kpis.map(k => `
    <div class="kpi-tile">
      <div class="kpi-label">${k.label}</div>
      <div class="kpi-value ${k.color}">${k.value}</div>
      ${k.note ? `<div class="kpi-note">${k.note}</div>` : ''}
    </div>
  `).join('');

  // Category progress
  const categories = result.categories || {};
  const catHTML = Object.entries(categories).map(([name, cat]) => {
    const planned = ((cat.planned_pct ?? 0) * 100);
    const actual  = ((cat.actual_pct  ?? 0) * 100);
    return `
      <div class="cat-row">
        <div class="cat-name">${name}</div>
        <div class="cat-bars">
          <div class="bar-track"><div class="bar-fill bar-planned" style="width:${Math.min(planned,100).toFixed(1)}%"></div></div>
          <div class="bar-track"><div class="bar-fill bar-actual"  style="width:${Math.min(actual, 100).toFixed(1)}%"></div></div>
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

  // Show results with animation
  document.getElementById('results-section').classList.remove('hidden');
}

// ── History / Recent projects ──────────────────────────────────────────────
async function loadHistory() {
  try {
    const resp = await fetch(`http://localhost:${serverPort}/api/history`);
    const history = await resp.json();
    renderHistory(history);
  } catch {
    // Non-fatal — table stays as-is
  }
}

function renderHistory(history) {
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
    // Escape the path for use in inline onclick
    const safePath   = (h.path || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
    const safeCached = (h.cached_path || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");

    return `
      <tr>
        <td title="${h.path}">${h.filename}</td>
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
          <button class="open-btn" onclick="openFromHistory('${safePath}','${safeCached}')">Open</button>
        </td>
      </tr>
    `;
  }).join('');
}

async function openFromHistory(filePath, cachedPath) {
  // Use original path if it still exists, otherwise fall back to the cached copy
  const path = filePath || cachedPath;
  currentCachedPath = cachedPath || null;
  await importFile(path);
}

// ── PDF generation ─────────────────────────────────────────────────────────
async function generatePdf() {
  if (!currentXmlPath) return;

  const btn = document.getElementById('pdf-btn');
  btn.disabled = true;
  btn.textContent = 'Generating…';

  try {
    const outputPath = await window.pywebview.api.choose_save_path('weekly_report.pdf');
    if (!outputPath) return;

    const resp = await fetch(`http://localhost:${serverPort}/api/report`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        xml_path:      currentXmlPath,
        cached_path:   currentCachedPath,
        output_path:   outputPath,
        overrides_path: null,
      }),
    });
    const data = await resp.json();
    if (!data.ok) {
      showError(`PDF generation failed: ${data.error}`);
    } else {
      btn.textContent = '✓ PDF Saved';
      setTimeout(() => { btn.textContent = 'Generate PDF Report'; }, 2500);
    }
  } catch (err) {
    showError('PDF generation failed. Check the output path and try again.');
  } finally {
    btn.disabled = false;
    if (btn.textContent === 'Generating…') btn.textContent = 'Generate PDF Report';
  }
}

// ── Init ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  serverPort = window.__SERVER_PORT__;
  initTheme();
  loadHistory();
  document.getElementById('sb-home-btn').addEventListener('click', loadAnother);
});
