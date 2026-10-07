// Owner comment 57: the print preview lays a landscape report out on the landscape page
// width (its wide tables were trimmed at the portrait width).
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const src = fs.readFileSync(path.join(__dirname, '..', '..', 'ui', 'modules', 'preview.js'), 'utf8');
const m = src.match(/export function pageWidthFor\(html\) \{([\s\S]*?)\n\}/);
assert(m, 'pageWidthFor is exported by preview.js');
const PAGE_W = Number(src.match(/const PAGE_W = (\d+);/)[1]);
const PAGE_W_LANDSCAPE = Number(src.match(/const PAGE_W_LANDSCAPE = (\d+);/)[1]);
const pageWidthFor = new Function('PAGE_W', 'PAGE_W_LANDSCAPE', 'html', m[1]);
const w = (html) => pageWidthFor(PAGE_W, PAGE_W_LANDSCAPE, html);
assert.strictEqual(w('<style>@page { size: A4 landscape; margin: 12mm; }</style>'), PAGE_W_LANDSCAPE);
assert.strictEqual(w('<style>@page{margin:11mm;size:A4 landscape}</style>'), PAGE_W_LANDSCAPE);
assert.strictEqual(w('<style>@page { size: A4; margin: 12mm; }</style>'), PAGE_W);
assert.strictEqual(w('<p>landscape photo</p>'), PAGE_W);
assert.strictEqual(w(''), PAGE_W);
assert(PAGE_W_LANDSCAPE > PAGE_W);
assert(/pageW = pageWidthFor\(/.test(src), 'the preview applies it when a report loads');
console.log('test_preview_page_width: ok');
