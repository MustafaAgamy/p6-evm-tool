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

export { escapeHtml };

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
      `<div class="pd-h-sub">${escapeHtml(sub)}</div>` +
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
    case 'bars': {
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
  return `<div class="pd-kpi"><div class="pd-k-head">${escapeHtml(item.label)}</div>` +
    `<div class="pd-k-body"><div class="pd-kv ${toneClass(item.tone)}">${escapeHtml(item.value)}</div>` +
    `<div class="pd-note">${escapeHtml(item.sub || '')}</div></div></div>`;
}

// ── panel ─────────────────────────────────────────────────────────────────────
export function panelHtml(tile) {
  tile = tile || {};
  const span = (tile.shape && tile.shape.w === 2) ? ' span2' : '';
  return `<div class="pd-panel${span}"><div class="pd-p-head">${escapeHtml(tile.title)}</div>` +
    `<div class="pd-p-body">${tileBodyHtml(tile.kind, tile.data || {})}</div></div>`;
}

// ── whole board (one-pager sheet) ─────────────────────────────────────────────
export function boardHtml(tiles, meta) {
  tiles = tiles || [];
  let inner;
  if (!tiles.length) {
    inner = `<div class="pd-empty-state">Pick results in the builder, then switch to Dashboard to see them here.</div>`;
  } else {
    const kpiItems = [];
    const panels = [];
    for (const t of tiles) {
      if (t.kind === 'kpis') {
        for (const it of ((t.data && t.data.items) || [])) kpiItems.push(it);
      } else {
        panels.push(t);
      }
    }
    const kpirow = kpiItems.length ? `<div class="pd-kpirow">${kpiItems.map(kpiTileHtml).join('')}</div>` : '';
    const grid = panels.length ? `<div class="pd-grid">${panels.map(panelHtml).join('')}</div>` : '';
    inner = `${letterheadHtml(meta)}${kpirow}${grid}`;
  }
  return `<div class="studio-dash-wrap">` +
    `<div class="pd-toolbar"><span class="pd-mode">View mode</span></div>` +
    `<div class="pd-sheet">${inner}</div>` +
  `</div>`;
}

// ── DOM entry (not unit-tested) ───────────────────────────────────────────────
// opts: { itemIds, inputs, snapshotId, mode }
export async function renderStudioDashboard(host, opts) {
  if (!host) return;
  opts = opts || {};
  host.innerHTML = `<div class="pd-loading">Building your dashboard…</div>`;
  try {
    const resp = await fetch(`http://localhost:${state.serverPort}/api/special/tiles`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        snapshot_id: opts.snapshotId ?? state.currentSnapshotId,
        item_ids: opts.itemIds || [],
        inputs: opts.inputs || {},
      }),
    });
    const res = await resp.json();
    if (!res || !res.ok) {
      host.innerHTML = `<div class="pd-na">${escapeHtml((res && res.error) || 'Could not build the dashboard.')}</div>`;
      return;
    }
    host.innerHTML = boardHtml(res.tiles, res.meta);
  } catch {
    host.innerHTML = `<div class="pd-na">Could not reach the local server. Try restarting the app.</div>`;
  }
}
