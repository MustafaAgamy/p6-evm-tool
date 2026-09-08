// Reporting Studio — Dashboard view (Slice 1, view-only).
//
// One selection in the builder feeds both outputs; this module draws the merged
// visual "Dashboard view" in the APPROVED Professional Dashboard `.pd-*` one-pager
// style. It computes nothing: it POSTs the picked item ids to /api/special/tiles
// and renders the per-item "tiles" the server returns.
//
// The pure helpers below return HTML strings and never touch document/window, so
// they are unit-testable in plain node (see tests/js/test_studio_dash.js). Only
// renderStudioDashboard() reaches the DOM / the local server.
//
// This slice is VIEW-ONLY: no edit mode, no catalog, no export buttons — those
// arrive in a later slice.

import { state } from './state.js';
import { escapeHtml } from './format.js';
import { showReportPreview } from './preview.js';
import { getSavedMode } from './appearance.js';

export { escapeHtml };

// last rendered board (so Export can rebuild it) + a tiny POST helper
let _last = { tiles: [], meta: {} };
function post(path, body) {
  return fetch(`http://localhost:${state.serverPort}/${path}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  }).then(r => r.json());
}

// ── tone / severity mapping ──────────────────────────────────────────────────
// semantic tone -> a `.pd-*` colour class (colours resolve to app appearance tokens)
export function toneClass(tone) {
  return { good: 'pd-good', warn: 'pd-warn', bad: 'pd-bad', accent: 'pd-accent' }[tone] || 'pd-neutral';
}

// finding severity -> the dot's colour class (the dot paints from currentColor)
export function sevClass(sev) {
  return { high: 'pd-bad', medium: 'pd-warn', low: 'pd-neutral', info: 'pd-accent' }[sev] || 'pd-neutral';
}

// tone -> a concrete theme token, for a filled segment/bar background
function toneToken(tone, i) {
  const m = { good: 'var(--success)', warn: 'var(--warning)', bad: 'var(--danger)', accent: 'var(--accent)' };
  return m[tone] || `var(--chart-${((i || 0) % 6) + 1})`;
}

// table cell alignment (l|r|c) -> inline text-align, or '' for the default (left)
function alignStyle(a) {
  const m = { l: 'left', r: 'right', c: 'center' };
  return m[a] ? ` style="text-align:${m[a]}"` : '';
}

function naHtml() { return '<div class="pd-na">No data available.</div>'; }

// ── RAG rail + redundant letter (accessible: colour is never the only channel) ─
function railClass(tone) { return { good: 'rail-good', warn: 'rail-warn', bad: 'rail-bad' }[tone] || ''; }
export function ragLetter(tone) { return { good: 'G', warn: 'A', bad: 'R' }[tone] || ''; }
function ragBadge(tone) {
  const l = ragLetter(tone);
  return l ? `<span class="rag ${{ good: 'good', warn: 'warn', bad: 'bad' }[tone]}">${l}</span>` : '';
}

// axis-less mini line drawn under a KPI value (neutral colour until a change
// threshold is confirmed — see payloads.kpi delta_tone).
export function sparkHtml(points) {
  const p = (points || []).map(Number).filter(v => !Number.isNaN(v));
  if (p.length < 2) return '';
  const W = 92, H = 20, mn = Math.min(...p), mx = Math.max(...p), rng = (mx - mn) || 1;
  const x = i => 2 + (W - 4) * (i / (p.length - 1));
  const y = v => H - 3 - (H - 6) * ((v - mn) / rng);
  const pts = p.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  return `<svg class="spark" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">` +
    `<polyline points="${pts}" fill="none" stroke="var(--muted)" stroke-width="1.5"/></svg>`;
}

// multi-series line chart (trends across the weekly updates); null points = gaps.
function lineHtml(data) {
  const series = data.series || [];
  const n = series.reduce((m, s) => Math.max(m, (s.points || []).length), 0);
  if (n < 2) return naHtml();
  const W = 300, H = 140, padL = 28, padR = 8, padT = 10, padB = 22;
  const vals = series.flatMap(s => (s.points || []).filter(v => v != null).map(Number));
  let ymax = data.y_max || (vals.length ? Math.max(...vals) : 1) || 1;
  if (data.ref && data.ref.value != null) ymax = Math.max(ymax, Number(data.ref.value));
  ymax = ymax * 1.08 || 1;
  const x = i => padL + (W - padL - padR) * (n === 1 ? 0 : i / (n - 1));
  const y = v => (H - padB) - (H - padB - padT) * (Number(v) / ymax);
  const axes = `<line x1="${padL}" y1="${H - padB}" x2="${W - padR}" y2="${H - padB}" stroke="var(--border)"/>` +
    `<line x1="${padL}" y1="${padT}" x2="${padL}" y2="${H - padB}" stroke="var(--border)"/>`;
  let ref = '';
  if (data.ref && data.ref.value != null) {
    const ry = y(data.ref.value);
    ref = `<line x1="${padL}" y1="${ry.toFixed(1)}" x2="${W - padR}" y2="${ry.toFixed(1)}" stroke="var(--muted)" stroke-dasharray="4 4"/>` +
      `<text x="${W - padR}" y="${(ry - 3).toFixed(1)}" font-size="7" fill="var(--muted)" text-anchor="end">${escapeHtml(data.ref.label || '')}</text>`;
  }
  const lines = series.map((s, si) => {
    const pts = (s.points || []).map((v, i) => v == null ? null : `${x(i).toFixed(1)},${y(v).toFixed(1)}`).filter(Boolean).join(' ');
    return pts ? `<polyline points="${pts}" fill="none" stroke="${toneToken(s.tone, si)}" stroke-width="2" stroke-linejoin="round"/>` : '';
  }).join('');
  const leg = series.map((s, si) => `<span><i style="background:${toneToken(s.tone, si)}"></i>${escapeHtml(s.label)}</span>`).join('');
  let out = `<svg width="100%" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">${axes}${ref}${lines}</svg>` +
    `<div class="pd-legend">${leg}</div>`;
  if (data.note) out += `<div class="pd-note">${escapeHtml(data.note)}</div>`;
  return out;
}

// discipline-gap variance row: bar to actual, tick at planned, shortfall shaded.
function varianceBarsHtml(data) {
  const rows = data.rows || [];
  if (!rows.length) return naHtml();
  const axisMax = data.axis_max;
  const clamp = v => Math.max(0, Math.min(100, v));
  const scale = v => clamp(axisMax ? (Number(v) / axisMax * 100) : Number(v));
  let out = rows.map(row => {
    const actual = scale((row.values || [])[0] || 0);
    const target = row.target != null ? scale(row.target) : null;
    const disp = (row.display && row.display[0] != null) ? row.display[0] : ((row.values || [])[0]);
    const fill = toneToken(row.tone, 0);
    const short = (target != null && target > actual)
      ? `<div class="pd-fl-short" style="left:${actual.toFixed(1)}%;width:${(target - actual).toFixed(1)}%"></div>` : '';
    const tick = target != null ? `<div class="pd-tick" style="left:${target.toFixed(1)}%"></div>` : '';
    return `<div class="pd-bar"><div class="pd-bl">${escapeHtml(row.label)}</div>` +
      `<div class="pd-trk"><div class="pd-fl" style="width:${actual.toFixed(1)}%;background:${fill}"></div>${short}${tick}</div>` +
      `<div class="pd-bv ${toneClass(row.tone)}">${escapeHtml(disp)}</div></div>`;
  }).join('');
  out += `<div class="pd-legend"><span>bar = actual</span><span>│ tick = planned</span><span>▨ shortfall</span></div>`;
  if (data.note) out += `<div class="pd-note">${escapeHtml(data.note)}</div>`;
  return out;
}

// informational freshness chip on the letterhead — days since the data date.
// Neutral by design (no staleness threshold is invented here).
function freshChip(dataDate) {
  if (!dataDate) return '';
  const d = new Date(String(dataDate).slice(0, 10) + 'T00:00:00');
  if (Number.isNaN(d.getTime())) return '';
  const days = Math.max(0, Math.round((Date.now() - d.getTime()) / 86400000));
  const txt = days === 0 ? 'today' : `${days} day${days === 1 ? '' : 's'} ago`;
  return `<span class="pd-fresh">· ${txt}</span>`;
}

// ── letterhead ────────────────────────────────────────────────────────────────
export function letterheadHtml(meta) {
  meta = meta || {};
  let sub = 'Weekly Management Dashboard';
  if (meta.data_date) sub += ' · Data date ' + String(meta.data_date).slice(0, 10);
  if (meta.activity_count) sub += ' · ' + meta.activity_count + ' activities';
  return `<div class="pd-letterhead">` +
    `<div class="pd-logo-slot">LOGO</div>` +
    `<div class="pd-ttl">` +
      `<div class="pd-h-title pd-b">${escapeHtml(meta.project_name || '')}</div>` +
      `<div class="pd-h-sub">${escapeHtml(sub)}${freshChip(meta.data_date)}</div>` +
    `</div>` +
    `<div class="pd-logo-slot">LOGO</div>` +
  `</div>`;
}

// ── tile body (per kind) ──────────────────────────────────────────────────────
// Shared by panels and by group blocks. Data semantics mirror p6_special/render_html.py.
export function tileBodyHtml(kind, data) {
  data = data || {};
  switch (kind) {
    case 'kpis': {
      // Normally flattened into the KPI row at board level; this is a fallback.
      const items = data.items || [];
      if (!items.length) return naHtml();
      return items.map(it =>
        `<div class="pd-kv ${toneClass(it.tone)}">${escapeHtml(it.value)}</div>` +
        `<div class="pd-note">${escapeHtml(it.sub || it.label || '')}</div>`
      ).join('');
    }
    case 'table': {
      const cols = data.columns || [];
      const rows = data.rows || [];
      if (!cols.length && !rows.length) return naHtml();
      const aligns = data.aligns || null;
      const al = i => alignStyle(aligns && aligns[i]);
      const thead = `<thead><tr>${cols.map((c, i) => `<th${al(i)}>${escapeHtml(c)}</th>`).join('')}</tr></thead>`;
      const tbody = `<tbody>${rows.map(r => `<tr>${(r || []).map((cell, i) => {
        let text = cell, tone = null;
        if (Array.isArray(cell)) { text = cell[0]; tone = cell[1]; }
        const cls = tone ? ` class="${toneClass(tone)}"` : '';
        return `<td${cls}${al(i)}>${escapeHtml(text)}</td>`;
      }).join('')}</tr>`).join('')}</tbody>`;
      return `<table class="pd-tbl">${thead}${tbody}</table>`;
    }
    case 'line': return lineHtml(data);
    case 'bars': {
      if (data.style === 'variance') return varianceBarsHtml(data);
      const series = data.series || [];
      const rows = data.rows || [];
      if (!series.length || !rows.length) return naHtml();
      const axisMax = data.axis_max;
      const multi = series.length > 1;
      const clamp = v => Math.max(0, Math.min(100, v));
      let out = '';
      for (const row of rows) {
        const values = row.values || [];
        const display = row.display || null;
        series.forEach((s, i) => {
          const v = Number(values[i] || 0);
          const pct = clamp(axisMax ? (v / axisMax * 100) : v);
          const shown = (display && display[i] != null) ? display[i] : v;
          const label = multi ? `${row.label} · ${s.label}` : row.label;
          const color = `var(--chart-${(i % 6) + 1})`;
          out += `<div class="pd-bar"><div class="pd-bl">${escapeHtml(label)}</div>` +
            `<div class="pd-trk"><div class="pd-fl" style="width:${pct.toFixed(1)}%;background:${color}"></div></div>` +
            `<div class="pd-bv">${escapeHtml(shown)}</div></div>`;
        });
      }
      if (multi) {
        out += `<div class="pd-legend">${series.map((s, i) =>
          `<span><i style="background:var(--chart-${(i % 6) + 1})"></i>${escapeHtml(s.label)}</span>`).join('')}</div>`;
      }
      if (data.note) out += `<div class="pd-note">${escapeHtml(data.note)}</div>`;
      return out;
    }
    case 'segbar': {
      const segs = (data.segments || []).filter(s => Number(s.value || 0) > 0);
      if (!segs.length) return naHtml();
      const total = segs.reduce((a, s) => a + Number(s.value || 0), 0) || 1;
      const parts = segs.map((s, i) => {
        const pct = 100 * Number(s.value || 0) / total;
        const color = toneToken(s.tone, i);
        return `<div class="pd-seg-part" style="width:${pct.toFixed(1)}%;background:${color}" title="${escapeHtml(s.label)}">` +
          `${escapeHtml(s.label)} ${escapeHtml(s.value)}</div>`;
      }).join('');
      const legend = segs.map((s, i) =>
        `<span><i style="background:${toneToken(s.tone, i)}"></i>${escapeHtml(s.label)} ${escapeHtml(s.value)}</span>`).join('');
      let out = `<div class="pd-seg">${parts}</div><div class="pd-legend">${legend}</div>`;
      if (data.note) out += `<div class="pd-note">${escapeHtml(data.note)}</div>`;
      return out;
    }
    case 'findings': {
      const items = data.items || [];
      if (!items.length) return `<div class="pd-na">${escapeHtml(data.empty || 'No findings.')}</div>`;
      return `<div class="pd-finds">${items.map(it => {
        const detail = it.detail ? `<div class="pd-fsrc">${escapeHtml(it.detail)}</div>` : '';
        return `<div class="pd-find"><span class="pd-dot ${sevClass(it.severity)}"></span>` +
          `<div><div>${escapeHtml(it.title)}</div>${detail}</div></div>`;
      }).join('')}</div>`;
    }
    case 'keyvals': {
      const pairs = data.pairs || [];
      if (!pairs.length) return naHtml();
      return `<div class="pd-stats">${pairs.map(p => {
        const label = Array.isArray(p) ? p[0] : '';
        const value = Array.isArray(p) ? p[1] : '';
        return `<div><div class="pd-stat-l">${escapeHtml(label)}</div><div class="pd-stat-v">${escapeHtml(value)}</div></div>`;
      }).join('')}</div>`;
    }
    case 'text': {
      const paras = data.paragraphs || [];
      if (!paras.length) return naHtml();
      return `<div class="pd-usertext">${paras.map(p => `<p>${escapeHtml(p)}</p>`).join('')}</div>`;
    }
    case 'note': {
      // render_html.py treats an 'info' tone as the accent tone.
      const tone = data.tone === 'info' ? 'accent' : data.tone;
      return `<div class="pd-note ${toneClass(tone)}">${escapeHtml(data.message)}</div>`;
    }
    case 'group': {
      const blocks = data.blocks || [];
      if (!blocks.length) return naHtml();
      return blocks.map(b => tileBodyHtml(b.kind, b.data)).join('<div class="pd-gap"></div>');
    }
    case 'no_data':
    default:
      return naHtml();
  }
}

// ── KPI tile ──────────────────────────────────────────────────────────────────
export function kpiTileHtml(item) {
  item = item || {};
  const rail = railClass(item.tone);
  const delta = item.delta ? `<span class="pd-trend ${toneClass(item.delta_tone)}">${escapeHtml(item.delta)}</span>` : '';
  return `<div class="pd-kpi${rail ? ' ' + rail : ''}">${ragBadge(item.tone)}` +
    `<div class="pd-k-head">${escapeHtml(item.label)}</div>` +
    `<div class="pd-k-body"><div class="pd-kv ${toneClass(item.tone)}">${escapeHtml(item.value)}${delta}</div>` +
    `${sparkHtml(item.spark)}<div class="pd-note">${escapeHtml(item.sub || '')}</div></div></div>`;
}

// A panel's RAG tone (for the accent rail) is taken ONLY from a status a provider
// already set — worst finding severity, or a note's tone — never invented here.
function panelTone(tile) {
  const d = tile.data || {};
  if (tile.kind === 'findings') {
    const sev = (d.items || []).map(i => i.severity);
    if (sev.includes('high')) return 'bad';
    if (sev.includes('medium')) return 'warn';
    return '';
  }
  if (tile.kind === 'note') {
    const t = d.tone === 'info' ? 'accent' : d.tone;
    return { good: 'good', warn: 'warn', bad: 'bad' }[t] || '';
  }
  return '';
}

// ── panel ─────────────────────────────────────────────────────────────────────
export function panelHtml(tile) {
  tile = tile || {};
  const span = (tile.shape && tile.shape.w === 2) ? ' span2' : '';
  const tone = panelTone(tile);
  const rail = railClass(tone);
  return `<div class="pd-panel${span}${rail ? ' ' + rail : ''}">${ragBadge(tone)}` +
    `<div class="pd-p-head">${escapeHtml(tile.title)}</div>` +
    `<div class="pd-p-body">${tileBodyHtml(tile.kind, tile.data || {})}</div></div>`;
}

// ── executive status header (full-width band; rendered above the KPI row) ──────
export function statusHeaderHtml(data) {
  data = data || {};
  const chips = (data.domains || []).map(dm => {
    const cls = { good: 'good', warn: 'warn', bad: 'bad' }[dm.tone] || 'grey';
    const letter = ragLetter(dm.tone) || '–';
    return `<div class="pd-chip ${cls}"><span class="cl">${letter}</span>` +
      `<div><div class="cn">${escapeHtml(dm.domain)}</div><div class="cv">${escapeHtml(dm.headline)}</div></div></div>`;
  }).join('');
  const v = data.verdict;
  let head;
  if (v) {
    head = `<div><div class="pd-verdict-lab ${toneClass(v.tone)}">${escapeHtml(v.label)}${ragBadge(v.tone)}</div>` +
      (v.note ? `<div class="pd-verdict-note">${escapeHtml(v.note)}</div>` : '') + `</div>`;
  } else {
    // Honest: no single verdict until its rule is set — show each area's own status.
    head = `<div><div class="pd-verdict-lab">Status by area</div>` +
      `<div class="pd-verdict-note">Each area shows its own status; the single overall verdict is set up separately.</div></div>`;
  }
  const rail = v ? railClass(v.tone) : '';
  return `<div class="pd-exec${rail ? ' ' + rail : ''}">${head}<div class="pd-chips">${chips}</div></div>`;
}

// ── whole board (one-pager sheet) ─────────────────────────────────────────────
export function boardHtml(tiles, meta) {
  tiles = tiles || [];
  let inner;
  if (!tiles.length) {
    inner = `<div class="pd-empty-state">Pick results in the builder, then switch to Dashboard to see them here.</div>`;
  } else {
    const headers = [];
    const kpiItems = [];
    const panels = [];
    for (const t of tiles) {
      if (t.kind === 'status_header') headers.push(t);
      else if (t.kind === 'kpis') {
        for (const it of ((t.data && t.data.items) || [])) kpiItems.push(it);
      } else {
        panels.push(t);
      }
    }
    const head = headers.map(t => statusHeaderHtml(t.data)).join('');
    const kpirow = kpiItems.length ? `<div class="pd-kpirow">${kpiItems.map(kpiTileHtml).join('')}</div>` : '';
    const grid = panels.length ? `<div class="pd-grid">${panels.map(panelHtml).join('')}</div>` : '';
    inner = `${letterheadHtml(meta)}${head}${kpirow}${grid}`;
  }
  return `<div class="studio-dash-wrap">` +
    `<div class="pd-toolbar"><span class="pd-mode">View mode</span>` +
    `<span class="pd-actions"><button type="button" class="btn-secondary" data-dash="pdf">⬇ PDF</button></span></div>` +
    `<div class="pd-sheet">${inner}</div>` +
  `</div>`;
}

// Export the current board as a PDF that matches the screen across all 6 looks.
async function exportDashPdf() {
  const title = (_last.meta && _last.meta.project_name) || 'Dashboard';
  const board = () => boardHtml(_last.tiles, _last.meta);
  const first = await post('api/special/dash-report', { html: board(), theme: getSavedMode(), preview: true, title });
  if (!first || !first.ok) return;
  showReportPreview({
    title: `${title} — Dashboard`, subtitle: 'Dashboard', html: first.html, initialMode: getSavedMode(),
    onThemeChange: async (m) => {
      const r = await post('api/special/dash-report', { html: board(), theme: m, preview: true, title });
      return r && r.ok ? r.html : '';
    },
    onSave: async (m) => {
      const out = await window.pywebview.api.choose_save_path('dashboard.pdf', 'pdf');
      if (!out) return false;
      const r = await post('api/special/dash-report', { html: board(), theme: m, output_path: out, title });
      return !!(r && r.ok);
    },
  });
}

// ── DOM entry (not unit-tested) ───────────────────────────────────────────────
// opts: { itemIds, inputs, snapshotId, mode }
export async function renderStudioDashboard(host, opts) {
  if (!host) return;
  opts = opts || {};
  host.innerHTML = `<div class="pd-loading">Building your dashboard…</div>`;
  try {
    const res = await post('api/special/tiles', {
      snapshot_id: opts.snapshotId ?? state.currentSnapshotId,
      item_ids: opts.itemIds || [],
      inputs: opts.inputs || {},
    });
    if (!res || !res.ok) {
      host.innerHTML = `<div class="pd-na">${escapeHtml((res && res.error) || 'Could not build the dashboard.')}</div>`;
      return;
    }
    _last = { tiles: res.tiles || [], meta: res.meta || {} };
    host.innerHTML = boardHtml(res.tiles, res.meta);
    const pdfBtn = host.querySelector('[data-dash="pdf"]');
    if (pdfBtn) pdfBtn.addEventListener('click', exportDashPdf);
  } catch {
    host.innerHTML = `<div class="pd-na">Could not reach the local server. Try restarting the app.</div>`;
  }
}
