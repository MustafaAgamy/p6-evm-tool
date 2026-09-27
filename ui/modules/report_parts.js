// ── Report Contents picker — the pure part (no DOM) ──────────────────────────
// Two levels: SECTIONS (the caller's list; each rendered as a [data-sec="key"] block) and
// PARTS inside them (any element with data-part="<sec>.<part>", label from data-part-label
// or its first heading/caption). Everything here works on HTML STRINGS, so the exact same
// code prunes the preview in the WebView and runs in plain node tests.
//
//   scanReport(html)                 → { sections:[{key,label}], parts:[{id,sec,label,empty}] }
//   buildTree(sections, scan, prev)  → [{key,label,empty,parts:[{id,label,empty}]}]
//   restoreState(saved, tree, sel)   → state {v:2, order, sections, offParts}
//   toggleSection / togglePart / selectAll / clearAll / moveSection   (return a NEW state)
//   sectionCheck(state, tree, key)   → 'all' | 'some' | 'none'   (tri-state checkbox)
//   serverKeys(state, tree)          → ticked section keys, in the user's order
//   pruneHtml(html, state, opts)     → the FINAL report: unticked parts/sections REMOVED
//                                      (absent, not hidden), sections in the chosen order,
//                                      a ticked-but-empty part shows "No data available".
// The final HTML is the ONE document every output (PDF · Word · HTML · Excel · Print) is made
// from — see p6_export and docs/report-picker-adoption.md.

const VOID = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta',
  'param', 'source', 'track', 'wbr']);
const RAW = new Set(['script', 'style', 'textarea', 'title']);
export const NO_DATA_HTML = '<div class="rpt-nodata">No data available</div>';

function decode(s) {
  return String(s || '')
    .replace(/&nbsp;/g, ' ').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'").replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(+n))
    .replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16)))
    .replace(/&amp;/g, '&');
}

export function textOf(html) {
  return decode(String(html || '')
    .replace(/<(script|style)\b[\s\S]*?<\/\1\s*>/gi, ' ')
    .replace(/<!--[\s\S]*?-->/g, ' ')
    .replace(/<[^>]*>/g, ' ')).replace(/\s+/g, ' ').trim();
}

function parseAttrs(src) {
  const out = {};
  const re = /([^\s"'=<>\/]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?/g;
  let m;
  while ((m = re.exec(src))) {
    const k = m[1].toLowerCase();
    if (!(k in out)) out[k] = decode(m[2] ?? m[3] ?? m[4] ?? '');
  }
  return out;
}

// Every element that carries data-sec or data-part, with its exact source range.
// { tag, attrs, start, end, innerStart, innerEnd, parent (index or -1), depth }
export function scanElements(html) {
  const s = String(html || '');
  const recs = [];
  const stack = [];          // { tag, rec (index|null) }
  let i = 0;
  const n = s.length;
  const nearestRec = () => { for (let k = stack.length - 1; k >= 0; k--) if (stack[k].rec != null) return stack[k].rec; return -1; };
  const closeTo = (k, at, endAt) => {       // pop stack down to index k (inclusive)
    while (stack.length > k) {
      const top = stack.pop();
      if (top.rec != null) {
        const r = recs[top.rec];
        const explicit = stack.length === k;             // the element named by the close tag
        r.innerEnd = at;
        r.end = explicit ? endAt : at;
      }
    }
  };
  while (i < n) {
    const lt = s.indexOf('<', i);
    if (lt < 0) break;
    if (s.startsWith('<!--', lt)) { const e = s.indexOf('-->', lt + 4); i = e < 0 ? n : e + 3; continue; }
    if (s[lt + 1] === '!' || s[lt + 1] === '?') { const e = s.indexOf('>', lt); i = e < 0 ? n : e + 1; continue; }
    if (s[lt + 1] === '/') {
      const m = /^<\/\s*([a-zA-Z][\w:-]*)\s*[^>]*>/.exec(s.slice(lt, lt + 200));
      if (!m) { i = lt + 1; continue; }
      const tag = m[1].toLowerCase();
      let k = stack.length - 1;
      while (k >= 0 && stack[k].tag !== tag) k--;
      if (k >= 0) closeTo(k, lt, lt + m[0].length);
      i = lt + m[0].length;
      continue;
    }
    const m = /^<([a-zA-Z][\w:-]*)/.exec(s.slice(lt, lt + 64));
    if (!m) { i = lt + 1; continue; }
    const tag = m[1].toLowerCase();
    // find the end of the start tag, respecting quotes
    let j = lt + m[0].length, q = null;
    for (; j < n; j++) {
      const c = s[j];
      if (q) { if (c === q) q = null; }
      else if (c === '"' || c === "'") q = c;
      else if (c === '>') break;
    }
    const tagEnd = Math.min(j + 1, n);
    const attrSrc = s.slice(lt + m[0].length, j);
    const selfClose = /\/\s*$/.test(attrSrc) || VOID.has(tag);
    let recIdx = null;
    if (/\bdata-(sec|part)\s*=/i.test(attrSrc)) {
      const attrs = parseAttrs(attrSrc);
      if (attrs['data-sec'] != null || attrs['data-part'] != null) {
        recIdx = recs.length;
        recs.push({ tag, attrs, start: lt, end: tagEnd, innerStart: tagEnd, innerEnd: tagEnd,
          parent: nearestRec(), depth: stack.length });
      }
    }
    if (selfClose) { i = tagEnd; continue; }
    if (RAW.has(tag)) {
      const close = s.toLowerCase().indexOf(`</${tag}`, tagEnd);
      const e = close < 0 ? n : s.indexOf('>', close);
      if (recIdx != null) { recs[recIdx].innerEnd = close < 0 ? n : close; recs[recIdx].end = e < 0 ? n : e + 1; }
      i = e < 0 ? n : e + 1;
      continue;
    }
    stack.push({ tag, rec: recIdx });
    i = tagEnd;
  }
  closeTo(0, n, n);
  return recs;
}

function firstHeading(inner) {
  const m = /<(h[1-6]|caption)\b[^>]*>([\s\S]*?)<\/\1\s*>/i.exec(inner) ||
            /<div\b[^>]*class\s*=\s*["'][^"']*\b(sub2|sec|title|h3title)\b[^"']*["'][^>]*>([\s\S]*?)<\/div>/i.exec(inner);
  return m ? textOf(m[2]) : '';
}

function isEmptyInner(inner) {
  if (/<(svg|img|canvas|table)\b/i.test(inner)) return false;
  return !textOf(inner);
}

export function scanReport(html) {
  const s = String(html || '');
  const recs = scanElements(s);
  const sections = [];
  const parts = [];
  const secOf = (r) => { let p = r.parent; while (p >= 0) { if (recs[p].attrs['data-sec'] != null) return recs[p].attrs['data-sec']; p = recs[p].parent; } return null; };
  for (const r of recs) {
    const inner = s.slice(r.innerStart, r.innerEnd);
    if (r.attrs['data-sec'] != null && !sections.some(x => x.key === r.attrs['data-sec'])) {
      sections.push({ key: r.attrs['data-sec'], label: r.attrs['data-sec-label'] || firstHeading(inner) || r.attrs['data-sec'] });
    }
    if (r.attrs['data-part'] != null) {
      const id = r.attrs['data-part'];
      if (parts.some(p => p.id === id)) continue;
      const sec = secOf(r) || (id.includes('.') ? id.split('.')[0] : id);
      const label = (r.attrs['data-part-label'] || firstHeading(inner) || textOf(inner).slice(0, 60) || id).trim();
      parts.push({ id, sec, label, empty: r.attrs['data-empty'] === '1' || isEmptyInner(inner) });
    }
  }
  return { sections, parts };
}

// Merge the caller's sections with what the rendered HTML showed. `prev` (an earlier tree)
// keeps the parts of sections that are not in the current render (unticked sections).
export function buildTree(sections, scan, prev) {
  const tree = [];
  const byKey = new Map();
  for (const s of sections || []) {
    const node = { key: s.key, label: s.label || s.key, empty: !!s.empty, parts: [] };
    tree.push(node); byKey.set(s.key, node);
  }
  for (const s of (scan && scan.sections) || []) {
    if (!byKey.has(s.key)) {
      const node = { key: s.key, label: s.label || s.key, empty: false, parts: [] };
      tree.push(node); byKey.set(s.key, node);
    }
  }
  for (const node of prev || []) {
    const cur = byKey.get(node.key);
    if (!cur) { const copy = { ...node, parts: node.parts.map(p => ({ ...p })) }; tree.push(copy); byKey.set(node.key, copy); continue; }
    for (const p of node.parts) if (!cur.parts.some(x => x.id === p.id)) cur.parts.push({ ...p });
  }
  for (const p of (scan && scan.parts) || []) {
    const node = byKey.get(p.sec);
    if (!node) continue;
    const had = node.parts.find(x => x.id === p.id);
    if (had) { had.label = p.label; had.empty = p.empty; }
    else node.parts.push({ id: p.id, label: p.label, empty: p.empty });
  }
  return tree;
}

const uniq = (a) => [...new Set(a)];
const secOfPart = (tree, id) => (tree.find(s => s.parts.some(p => p.id === id)) || {}).key
  || (String(id).includes('.') ? String(id).split('.')[0] : null);

// Saved selection → state. Accepts the legacy format (an array of ticked section keys) and
// the v2 object {v:2, order, sections, offParts}. `selected` = the caller's initial ticks.
export function restoreState(saved, tree, selected) {
  const keys = tree.map(s => s.key);
  const usable = new Set(tree.filter(s => !s.empty).map(s => s.key));
  let order = keys.slice();
  let secs = Array.isArray(selected) && selected.length ? selected : keys;
  let off = [];
  if (Array.isArray(saved)) secs = saved;
  else if (saved && typeof saved === 'object' && saved.v === 2) {
    if (Array.isArray(saved.sections)) secs = saved.sections;
    if (Array.isArray(saved.offParts)) off = saved.offParts;
    if (Array.isArray(saved.order)) order = uniq([...saved.order.filter(k => keys.includes(k)), ...keys]);
  }
  return {
    v: 2,
    order,
    sections: order.filter(k => usable.has(k) && secs.includes(k)),
    offParts: uniq(off.filter(id => keys.includes(secOfPart(tree, id)))),
  };
}

export function sectionCheck(state, tree, key) {
  const node = tree.find(s => s.key === key);
  if (!node || !state.sections.includes(key)) return 'none';
  const on = node.parts.filter(p => !state.offParts.includes(p.id)).length;
  if (!node.parts.length || on === node.parts.length) return 'all';
  return on === 0 ? 'none' : 'some';
}

export function partChecked(state, tree, id) {
  const sec = secOfPart(tree, id);
  return state.sections.includes(sec) && !state.offParts.includes(id);
}

export function toggleSection(state, tree, key, on) {
  const node = tree.find(s => s.key === key);
  if (!node || node.empty) return state;
  const ids = new Set(node.parts.map(p => p.id));
  const offParts = state.offParts.filter(id => !ids.has(id));
  const sections = on ? state.order.filter(k => k === key || state.sections.includes(k))
                      : state.sections.filter(k => k !== key);
  return { ...state, sections, offParts };
}

export function togglePart(state, tree, id, on) {
  const key = secOfPart(tree, id);
  const node = tree.find(s => s.key === key);
  if (!node || node.empty) return state;
  if (on) {
    const sections = state.sections.includes(key) ? state.sections : state.order.filter(k => k === key || state.sections.includes(k));
    // ticking one part of an unticked section: only that part goes in
    const offParts = state.sections.includes(key)
      ? state.offParts.filter(x => x !== id)
      : uniq([...state.offParts.filter(x => secOfPart(tree, x) !== key), ...node.parts.map(p => p.id).filter(x => x !== id)]);
    return { ...state, sections, offParts };
  }
  const offParts = uniq([...state.offParts, id]);
  if (node.parts.every(p => offParts.includes(p.id))) {       // nothing left → the section goes
    const ids = new Set(node.parts.map(p => p.id));
    return { ...state, sections: state.sections.filter(k => k !== key), offParts: offParts.filter(x => !ids.has(x)) };
  }
  return { ...state, offParts };
}

export function selectAll(state, tree) {
  return { ...state, sections: state.order.filter(k => tree.some(s => s.key === k && !s.empty)), offParts: [] };
}

export function clearAll(state) {
  return { ...state, sections: [], offParts: [] };
}

// Move section `from` to the position of section `to` (drag-and-drop).
export function moveSection(state, from, to) {
  if (from === to) return state;
  const order = state.order.filter(k => k !== from);
  const at = order.indexOf(to);
  if (at < 0) return state;
  const fromIdx = state.order.indexOf(from), toIdx = state.order.indexOf(to);
  order.splice(fromIdx < toIdx ? at + 1 : at, 0, from);
  return { ...state, order, sections: order.filter(k => state.sections.includes(k)) };
}

export function serverKeys(state) {
  return state.order.filter(k => state.sections.includes(k));
}

export function countTicked(state, tree) {
  let n = 0;
  for (const s of tree) {
    if (!state.sections.includes(s.key)) continue;
    n += s.parts.length ? s.parts.filter(p => !state.offParts.includes(p.id)).length : 1;
  }
  return n;
}

// The FINAL report. opts.knownSections = keys the picker manages (a [data-sec] block the
// picker doesn't know about is left alone).
export function pruneHtml(html, state, opts = {}) {
  let s = String(html || '');
  const managed = new Set(opts.knownSections || state.order);
  const ticked = new Set(state.sections);
  const off = new Set(state.offParts);
  // pass 1 — remove unticked sections / parts; fill ticked-but-empty parts
  const recs = scanElements(s);
  const edits = [];                 // [start, end, replacement]
  const removed = [];               // ranges already removed (skip nested)
  const inside = (r) => removed.some(([a, b]) => r.start >= a && r.end <= b);
  for (const r of recs) {
    if (inside(r)) continue;
    const sec = r.attrs['data-sec'];
    const part = r.attrs['data-part'];
    if (sec != null && managed.has(sec) && !ticked.has(sec)) {
      edits.push([r.start, r.end, '']); removed.push([r.start, r.end]); continue;
    }
    if (part != null) {
      const psec = (() => { let p = r.parent; while (p >= 0) { if (recs[p].attrs['data-sec'] != null) return recs[p].attrs['data-sec']; p = recs[p].parent; } return part.includes('.') ? part.split('.')[0] : null; })();
      if (off.has(part) || (psec != null && managed.has(psec) && !ticked.has(psec))) {
        edits.push([r.start, r.end, '']); removed.push([r.start, r.end]); continue;
      }
      const inner = s.slice(r.innerStart, r.innerEnd);
      if (r.attrs['data-empty'] === '1' || isEmptyInner(inner)) {
        edits.push([r.innerStart, r.innerEnd, (r.attrs['data-empty'] === '1' ? inner : '') + NO_DATA_HTML]);
        removed.push([r.start, r.end]);
      }
    }
  }
  edits.sort((a, b) => b[0] - a[0]);
  for (const [a, b, rep] of edits) s = s.slice(0, a) + rep + s.slice(b);
  // pass 2 — reorder the top-level sections into the user's order (slot by slot)
  const recs2 = scanElements(s).filter(r => r.attrs['data-sec'] != null && r.parent === -1 && managed.has(r.attrs['data-sec']));
  if (recs2.length > 1) {
    const rank = (k) => { const i = state.order.indexOf(k); return i < 0 ? 1e6 : i; };
    const blocks = recs2.map(r => ({ key: r.attrs['data-sec'], html: s.slice(r.start, r.end) }));
    const sorted = blocks.slice().sort((a, b) => rank(a.key) - rank(b.key));
    if (sorted.some((b, i) => b !== blocks[i])) {
      let out = '', pos = 0;
      recs2.forEach((r, i) => { out += s.slice(pos, r.start) + sorted[i].html; pos = r.end; });
      s = out + s.slice(pos);
    }
  }
  return s;
}
