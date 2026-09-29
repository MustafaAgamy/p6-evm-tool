/* Startup guard: the window must never sit on a silent black screen.
 *
 * server.py INLINES this classic script into index.html (at its cx:startup-guard marker), so it
 * runs even when the ES-module graph (ui/app.js + ~38 modules, fetched at every launch)
 * fails. Before this guard, the near-black anti-flash cover (#brand-splash) was removed
 * only by boot.js once every module had loaded; one failed module file left the window
 * black forever with no message (startup audit BLACK-1).
 *
 *   app.js first line        -> __cxStartup.booted()   (every module loaded and evaluated)
 *   end of app.js startup    -> __cxStartup.ready()    (the shell is built)
 *
 * A program file that fails to load, or an error before ready(), reloads the page
 * automatically with backoff (BACKOFF_MS; the attempt count survives the reload in
 * sessionStorage); after that, a visible card with a Retry button. A slow start shows
 * "Still starting..." instead of a blank cover; a start that stalls is treated as a
 * failure. Every event is reported to POST /api/client-log (the app's startup log), and
 * ready() completes the app's readiness handshake. After ready, GET /api/health reports
 * whether the history database had to be recovered; if so a dismissible notice says so.
 * No alert/confirm/prompt anywhere (they are no-ops in WebView2). ES5 only.
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) { module.exports = api; }
  else if (root) { api.install(root); }
}(typeof window !== 'undefined' ? window : null, function () {
  'use strict';

  var KEY = 'cx_boot_attempt';
  var BACKOFF_MS = [600, 1500, 3500];   // automatic reloads before the Retry card
  var SLOW_MS = 12000;                  // show "Still starting..."
  var STALL_MS = 40000;                 // never booted by now: treat as a failure

  function create(win, opts) {
    opts = opts || {};
    var doc = win.document;
    var setT = opts.setTimeout || function (f, ms) { return win.setTimeout(f, ms); };
    var clearT = opts.clearTimeout || function (id) { win.clearTimeout(id); };
    var now = opts.now || function () { return Date.now(); };
    var reload = opts.reload || function () { win.location.reload(); };
    var post = opts.post || defaultPost;
    var getJson = opts.getJson || defaultGetJson;
    var storage = opts.storage || safeSession();
    var t0 = now();
    var timers = [];
    var g = {
      phase: 'loading',          // loading | slow | retrying | failed | ready
      isBooted: false,
      detail: null,
      attempt: readAttempt(),
      events: [],
    };

    function readAttempt() {
      var n = 0;
      try { n = parseInt(storage.getItem(KEY), 10) || 0; } catch (e) { n = 0; }
      return n < 0 ? 0 : n;
    }
    function writeAttempt(n) { try { storage.setItem(KEY, String(n)); } catch (e) { /* private mode */ } }

    function defaultPost(payload) {
      try {
        if (typeof win.fetch === 'function') {
          win.fetch('/api/client-log', {
            method: 'POST', keepalive: true,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          }).catch(function () {});
        }
      } catch (e) { /* logging is best-effort */ }
    }
    function defaultGetJson(url, cb) {
      try {
        if (typeof win.fetch !== 'function') return;
        win.fetch(url).then(function (r) { return r.json(); })
          .then(function (j) { cb(j); }).catch(function () {});
      } catch (e) { /* best-effort */ }
    }
    function report(kind, message, detail) {
      var rec = { kind: kind, message: message || '', detail: detail || '',
                  attempt: g.attempt, ms: now() - t0 };
      g.events.push(rec);
      post(rec);
    }

    function appName() { return win.__APP_NAME__ || 'The app'; }

    // ── overlay ──────────────────────────────────────────────────────────
    function overlay() {
      var el = doc.getElementById('cx-startup');
      if (el) return el;
      el = doc.createElement('div');
      el.id = 'cx-startup';
      el.setAttribute('role', 'alertdialog');
      el.setAttribute('aria-live', 'assertive');
      el.style.cssText = 'position:fixed;inset:0;z-index:2147483000;display:flex;' +
        'align-items:center;justify-content:center;background:#06090f;color:#e6ecf8;' +
        'font:14px/1.5 "Segoe UI",system-ui,sans-serif;padding:16px;';
      (doc.body || doc.documentElement).appendChild(el);
      return el;
    }
    function removeOverlay() {
      var el = doc.getElementById('cx-startup');
      if (el && el.parentNode) el.parentNode.removeChild(el);
    }
    function esc(s) {
      return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
      });
    }
    function render(title, message, detail, button) {
      var el = overlay();
      el.innerHTML =
        '<div style="max-width:520px;width:100%;background:#111a2e;border:1px solid #2a3a5e;' +
        'border-radius:12px;padding:22px 24px;box-shadow:0 12px 40px rgba(0,0,0,.5)">' +
        '<div style="font-size:17px;font-weight:600;color:#fff;margin-bottom:6px">' + esc(title) + '</div>' +
        '<div style="color:#c3cde3">' + esc(message) + '</div>' +
        (detail ? '<div style="margin-top:10px;font:12px/1.4 Consolas,monospace;color:#8fa0c4;' +
          'word-break:break-all">' + esc(detail) + '</div>' : '') +
        (button ? '<div style="margin-top:16px"><button type="button" id="cx-startup-retry" ' +
          'style="background:#3b82f6;color:#fff;border:0;border-radius:8px;padding:8px 18px;' +
          'font:600 13px/1 \'Segoe UI\',system-ui,sans-serif;cursor:pointer">' + esc(button) +
          '</button></div>' : '') +
        '</div>';
      var b = doc.getElementById('cx-startup-retry');
      if (b) b.onclick = function () { g.retry(); };
    }

    // ── state machine ────────────────────────────────────────────────────
    function clearTimers() { for (var i = 0; i < timers.length; i++) clearT(timers[i]); timers = []; }

    g.fail = function (kind, detail) {
      if (g.phase === 'ready' || g.phase === 'retrying' || g.phase === 'failed') return g.phase;
      clearTimers();
      g.detail = detail || '';
      report(kind, 'startup failed', g.detail);
      if (g.attempt < BACKOFF_MS.length) {
        var n = g.attempt + 1;
        writeAttempt(n);
        g.phase = 'retrying';
        render('Starting ' + appName() + '…',
               'Part of the program did not load — trying again automatically (attempt ' +
               n + ' of ' + BACKOFF_MS.length + ').', null, null);
        report('retry', 'automatic reload', 'attempt ' + n);
        timers.push(setT(function () { reload(); }, BACKOFF_MS[g.attempt]));
        return g.phase;
      }
      g.phase = 'failed';
      render(appName() + ' couldn’t finish starting',
             'Part of the program did not load. Your projects and data are safe. Click Retry; ' +
             'if this keeps happening, close the app and open it again.',
             g.detail, 'Retry');
      return g.phase;
    };

    g.retry = function () {
      writeAttempt(0);
      report('retry', 'manual retry', '');
      reload();
    };

    g.booted = function () {
      g.isBooted = true;
      report('booted', 'program files loaded', '');
    };

    g.ready = function () {
      if (g.phase === 'ready') return;
      if (g.phase === 'retrying' || g.phase === 'failed') return;   // a reload is underway
      clearTimers();
      g.phase = 'ready';
      writeAttempt(0);
      removeOverlay();
      report('ready', 'shell ready', g.attempt ? 'after ' + g.attempt + ' automatic reload(s)' : '');
      getJson('/api/health', function (h) { g.notice(h); });
    };

    g.notice = function (h) {
      var d = h && h.db;
      if (!d || (d.status !== 'recovered' && d.status !== 'degraded')) return null;
      var msg = d.status === 'recovered'
        ? 'Your project history database was damaged and could not be read. It was set aside as “' +
          (d.backup || 'a backup file') + '” and a fresh one was started — re-import your ' +
          'schedules to rebuild Recent Projects.'
        : 'The project history database could not be opened (' + (d.detail || 'unknown reason') +
          '). Analyses still work; Recent Projects may stay empty until the app is restarted.';
      var el = doc.createElement('div');
      el.id = 'cx-db-notice';
      el.setAttribute('role', 'status');
      el.style.cssText = 'position:fixed;left:50%;bottom:18px;transform:translateX(-50%);' +
        'z-index:2147482000;max-width:640px;width:calc(100% - 32px);background:#fff7e6;' +
        'color:#5a3b00;border:1px solid #f0b95a;border-radius:10px;padding:10px 40px 10px 14px;' +
        'font:13px/1.45 "Segoe UI",system-ui,sans-serif;box-shadow:0 6px 24px rgba(0,0,0,.25)';
      el.innerHTML = esc(msg) + '<button type="button" aria-label="Dismiss" ' +
        'style="position:absolute;top:6px;right:8px;border:0;background:none;color:#5a3b00;' +
        'font-size:18px;line-height:1;cursor:pointer">×</button>';
      el.getElementsByTagName('button')[0].onclick = function () {
        if (el.parentNode) el.parentNode.removeChild(el);
      };
      (doc.body || doc.documentElement).appendChild(el);
      report('notice', 'database ' + d.status, d.detail || '');
      return el;
    };

    // A module deep in the graph that fails is reported on app.js's <script> element; name
    // the actual file(s) when the browser recorded an error status for them.
    function failedFiles() {
      try {
        var perf = win.performance;
        if (!perf || !perf.getEntriesByType) return '';
        var out = [], list = perf.getEntriesByType('resource');
        for (var i = 0; i < list.length && out.length < 4; i++) {
          var r = list[i];
          if (r.responseStatus >= 400 && /\/ui\//.test(r.name)) {
            out.push(r.name.replace(/^https?:\/\/[^\/]+/, '') + ' → ' + r.responseStatus);
          }
        }
        return out.join(', ');
      } catch (e) { return ''; }
    }

    function onError(e) {
      if (g.phase === 'ready') return;
      var t = e && e.target;
      if (t && t !== win && t.tagName) {
        var tag = String(t.tagName).toUpperCase();
        if (tag === 'SCRIPT' || (tag === 'LINK' && /stylesheet/i.test(t.rel || ''))) {
          var bad = failedFiles();
          g.fail('load-failed', 'Could not load ' + (t.src || t.href || tag) +
                 (bad ? ' (' + bad + ')' : ''));
        }
        return;                                    // images etc. are not fatal
      }
      var where = e && e.filename ? ' (' + e.filename + ':' + (e.lineno || 0) + ')' : '';
      g.fail('error', ((e && e.message) || 'Script error') + where);
    }
    function onRejection(e) {
      if (g.phase === 'ready') return;
      var r = e && e.reason;
      report('rejection', 'unhandled promise rejection', r && (r.message || String(r)));
    }
    function checkStylesheet() {
      if (g.phase === 'ready' || g.phase === 'retrying' || g.phase === 'failed') return;
      var links = doc.querySelectorAll ? doc.querySelectorAll('link[rel="stylesheet"]') : [];
      for (var i = 0; i < links.length; i++) {
        var href = links[i].getAttribute('href') || '';
        if (href.indexOf('/ui/') === 0 && !links[i].sheet) {
          g.fail('load-failed', 'Could not load ' + href);
          return;
        }
      }
    }

    g.start = function () {
      if (win.addEventListener) {
        win.addEventListener('error', onError, true);             // capture: element errors
        win.addEventListener('unhandledrejection', onRejection);
      }
      if (doc.addEventListener) {
        if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', checkStylesheet);
        else checkStylesheet();
      }
      timers.push(setT(function () {
        if (g.phase !== 'loading') return;
        g.phase = 'slow';
        report('timeout', 'slow start', 'not ready after ' + SLOW_MS + ' ms');
        render('Still starting…',
               'This can take a little longer the first time, or while antivirus scans the app. ' +
               'You can keep waiting or reload now.', null, 'Reload now');
      }, SLOW_MS));
      timers.push(setT(function () {
        if (g.phase !== 'loading' && g.phase !== 'slow') return;
        g.fail('timeout', g.isBooted
          ? 'The program loaded but the screen was not built within ' + (STALL_MS / 1000) + ' s.'
          : 'The program files did not finish loading within ' + (STALL_MS / 1000) + ' s.');
      }, STALL_MS));
      return g;
    };

    return g;
  }

  function safeSession() {
    try {
      if (typeof sessionStorage !== 'undefined' && sessionStorage) return sessionStorage;
    } catch (e) { /* blocked */ }
    var mem = {};
    return { getItem: function (k) { return mem[k] == null ? null : mem[k]; },
             setItem: function (k, v) { mem[k] = String(v); } };
  }

  function install(win) {
    if (win.__cxStartup) return win.__cxStartup;
    var g = create(win);
    win.__cxStartup = g;
    g.start();
    return g;
  }

  return { create: create, install: install, KEY: KEY, BACKOFF_MS: BACKOFF_MS,
           SLOW_MS: SLOW_MS, STALL_MS: STALL_MS };
}));
