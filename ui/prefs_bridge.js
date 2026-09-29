/* Screen preferences survive an app restart (owner comment 31 b).
 *
 * The page remembers the Appearance mode, Report Contents picks, table columns, chart
 * styles ... in its own browser storage (localStorage). In the app that storage is wiped at
 * every restart: the WebView2 window runs in private mode and the page comes from a new
 * random local port each launch (a new, empty storage). So those settings kept going back
 * to their defaults.
 *
 * server.py INLINES this classic script at the top of <head> (before the early Appearance
 * script and every module), right after window.__UI_PREFS__ = <the saved preferences from
 * <app data>/ui_prefs.json>. It
 *   1. loads the saved preferences into the page's storage (the saved copy wins), so the
 *      Appearance is applied before the first paint and every module reads its setting as
 *      before;
 *   2. sends keys only this page holds (a browser that kept them) to the app once;
 *   3. mirrors every later setItem / removeItem / clear to POST /api/ui-prefs (batched,
 *      retried with backoff when the local service is busy, flushed when the page closes).
 * No module changes are needed: they keep using localStorage. ES5 only; never throws.
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) { module.exports = api; }
  else if (root) { api.install(root); }
}(typeof window !== 'undefined' ? window : null, function () {
  'use strict';

  var URL_PATH = '/api/ui-prefs';
  var DEBOUNCE_MS = 400;
  var RETRY_MS = [1000, 3000, 8000, 20000];

  function hasOwn(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }
  function any(o) { for (var k in o) { if (hasOwn(o, k)) return true; } return false; }
  function keys(o) { var a = []; for (var k in o) { if (hasOwn(o, k)) a.push(k); } return a; }

  function create(win, opts) {
    opts = opts || {};
    var setT = opts.setTimeout || function (f, ms) { return win.setTimeout(f, ms); };
    var post = opts.post || function (body, keepalive) {
      return win.fetch(URL_PATH, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body), keepalive: !!keepalive,
      }).then(function (r) { return r.json(); });
    };
    var ls = null;
    try { ls = win.localStorage || null; } catch (e) { ls = null; }   // blocked storage
    var proto = win.Storage && win.Storage.prototype;

    var pendSet = {};
    var pendRem = {};
    var timer = null;
    var inflight = false;
    var tries = 0;
    var b = { installed: false, failures: 0 };

    function schedule(ms) {
      if (timer) return;
      timer = setT(function () { timer = null; flush(false); }, ms == null ? DEBOUNCE_MS : ms);
    }

    function flush(closing) {
      if (!any(pendSet) && !any(pendRem)) return;
      if (inflight && !closing) { schedule(); return; }     // one request at a time: order kept
      var body = { set: pendSet, remove: keys(pendRem) };
      pendSet = {};
      pendRem = {};
      inflight = true;
      var p;
      try { p = post(body, closing); } catch (e) { p = null; }
      if (!p || typeof p.then !== 'function') { p = { then: function (ok, bad) { bad(new Error('not sent')); } }; }
      p.then(function (res) {
        inflight = false;
        if (!res || !res.ok) { requeue(body); return; }
        tries = 0;
        if (any(pendSet) || any(pendRem)) schedule();
      }, function () { inflight = false; requeue(body); });
    }

    // Put back what was not saved without overwriting a newer change, then retry later.
    function requeue(body) {
      var k, i;
      for (k in body.set) {
        if (hasOwn(body.set, k) && !hasOwn(pendSet, k) && !hasOwn(pendRem, k)) pendSet[k] = body.set[k];
      }
      for (i = 0; i < body.remove.length; i++) {
        k = body.remove[i];
        if (!hasOwn(pendSet, k)) pendRem[k] = 1;
      }
      b.failures++;
      var ms = RETRY_MS[Math.min(tries, RETRY_MS.length - 1)];
      tries++;
      schedule(ms);
    }

    b.install = function () {
      if (b.installed || !ls || !proto) return b;
      var nativeSet = proto.setItem;
      var nativeRem = proto.removeItem;
      var nativeClear = proto.clear;
      var saved = win.__UI_PREFS__ || {};
      var k, i;
      // 1. the app's saved copy -> this page (the saved copy wins)
      try {
        for (k in saved) {
          if (hasOwn(saved, k) && typeof saved[k] === 'string' && ls.getItem(k) !== saved[k]) {
            nativeSet.call(ls, k, saved[k]);
          }
        }
      } catch (e) { /* storage full / blocked: modules fall back to their defaults */ }
      // 2. keys only this page holds -> the app (once)
      try {
        for (i = 0; i < ls.length; i++) {
          k = ls.key(i);
          if (k != null && !hasOwn(saved, k)) pendSet[k] = ls.getItem(k);
        }
      } catch (e) { /* ignore */ }
      // 3. every later change -> the app
      proto.setItem = function (key, value) {
        nativeSet.apply(this, arguments);                 // a quota error throws: nothing recorded
        if (this === ls) {
          key = String(key);
          pendSet[key] = String(value);
          delete pendRem[key];
          schedule();
        }
      };
      proto.removeItem = function (key) {
        nativeRem.apply(this, arguments);
        if (this === ls) {
          key = String(key);
          delete pendSet[key];
          pendRem[key] = 1;
          schedule();
        }
      };
      proto.clear = function () {
        var gone = [];
        if (this === ls) { try { for (var j = 0; j < ls.length; j++) gone.push(ls.key(j)); } catch (e) { /* ignore */ } }
        nativeClear.apply(this, arguments);
        if (this === ls) {
          for (var n = 0; n < gone.length; n++) { delete pendSet[gone[n]]; pendRem[gone[n]] = 1; }
          schedule();
        }
      };
      try {
        if (win.addEventListener) win.addEventListener('pagehide', function () { flush(true); });
      } catch (e) { /* ignore */ }
      b.installed = true;
      if (any(pendSet)) schedule();
      return b;
    };
    b.flush = function () { flush(false); };
    b.pending = function () { return { set: pendSet, remove: keys(pendRem) }; };
    return b;
  }

  function install(win) {
    if (win.__cxPrefs) return win.__cxPrefs;
    var b = create(win);
    win.__cxPrefs = b;
    try { b.install(); } catch (e) { /* never block the page */ }
    return b;
  }

  return { create: create, install: install, URL_PATH: URL_PATH,
           DEBOUNCE_MS: DEBOUNCE_MS, RETRY_MS: RETRY_MS };
}));
