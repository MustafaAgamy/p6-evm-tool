import threading
import webbrowser
import webview
from utils import resource_path, APP_TITLE, is_allowed_external_url


class Api:
    def choose_file(self):
        """Open native file picker; returns absolute path string or None."""
        result = webview.windows[0].create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=('P6 Schedule Files (*.xml;*.xer)', 'P6 XML Files (*.xml)', 'P6 XER Files (*.xer)')
        )
        return result[0] if result else None

    def choose_excel(self):
        """Open native picker for one or more Excel logs (E1 / Design / Shop drawing
        logs); returns a list of paths (empty if cancelled)."""
        result = webview.windows[0].create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=True,
            file_types=('Engineering logs (*.xlsx;*.xlsm;*.csv)', 'Excel Files (*.xlsx;*.xlsm)',
                        'CSV Files (*.csv)', 'All Files (*.*)')
        )
        return list(result) if result else []

    def choose_open_path(self, file_type='json'):
        """Open native file picker filtered by type; returns a path or None. Used for
        importing a Constructability knowledge file (.json)."""
        types = {
            'json': ('Knowledge Files (*.json)', 'All Files (*.*)'),
            'xml':  ('P6 XML Files (*.xml)',),
        }.get(file_type, ('All Files (*.*)',))
        result = webview.windows[0].create_file_dialog(webview.OPEN_DIALOG, file_types=types)
        return result[0] if result else None

    def choose_save_path(self, default_name='report.pdf', file_type='pdf'):
        """Open native save dialog; returns absolute path string or None.

        file_type ∈ {'pdf', 'docx', 'doc', 'xlsx', 'xml', 'xer', 'json', 'html'} chooses the
        dialog filter (unknown types fall back to All Files).
        """
        types = {
            'pdf':  ('PDF Files (*.pdf)',),
            'docx': ('Word Files (*.docx)',),
            'doc':  ('Word Files (*.doc)',),
            'xlsx': ('Excel Files (*.xlsx)',),
            'xml':  ('P6 XML Files (*.xml)',),
            'xer':  ('P6 XER Files (*.xer)',),
            'json': ('JSON Files (*.json)',),
            'html': ('HTML Files (*.html)',),
        }.get(file_type, ('All Files (*.*)',))
        result = webview.windows[0].create_file_dialog(
            webview.SAVE_DIALOG,
            file_types=types,
            save_filename=default_name
        )
        return result[0] if result else None

    def open_external(self, url):
        """Open an allow-listed https link (utils.EXTERNAL_LINK_HOSTS: LinkedIn, the map's
        Leaflet / OpenStreetMap attribution, Open-Meteo) in the user's default browser
        instead of inside the app window. Returns True when handed over."""
        if not is_allowed_external_url(url):
            return False
        try:
            return bool(webbrowser.open(url.strip(), new=2))
        except Exception:
            return False

    def open_log_folder(self):
        """Help ▸ Contact & Support ▸ 'Open log folder': show the folder holding
        startup.log in Explorer. Returns {'ok', 'path'}."""
        import app_startup
        return app_startup.open_log_folder()

    def quit(self):
        """Close the application window (File ▸ Exit)."""
        for w in list(webview.windows):
            w.destroy()


def _watch_startup(window, url):
    """Started by webview.start(func): the readiness handshake. The page reports 'ready'
    once its shell is built (ui/startup_guard.js -> /api/client-log); if it never does,
    reload once and record it (app_startup.watch_startup). Then attach the WebView2
    renderer-crash recovery. Runs on a DAEMON thread (pywebview's func thread is not
    one) so closing the window never leaves the process waiting on the watchdog."""
    import app_startup

    # The backend is loaded now: stop pywebview deleting the KEPT WebView2 folder at close.
    if app_startup.keep_profile_on_close():
        app_startup.log('WebView2 profile kept for the next launch')

    def run():
        closed = window.events.closed
        # WebView2 GPU / browser / renderer process failures are watched from the moment
        # the WebView2 core exists — not only after the page said 'ready' (a page can run
        # and say ready while a dead GPU process leaves the window black). S4.
        threading.Thread(target=app_startup.attach_renderer_recovery_early,
                         args=(window,), kwargs={'closed': closed},
                         name='renderer-recovery', daemon=True).start()
        res = app_startup.watch_startup(window, url, closed=closed, second_s=20.0,
                                        abort=app_startup.WEBVIEW_INIT_FAILED,
                                        contact=app_startup.PAGE_CONTACT)
        if res == 'closed':
            return
        # WebView2 never ran the page at all (it failed to start, or stayed blank through a
        # reload): start ONE fresh copy in safe graphics mode and close this black window,
        # instead of leaving the owner to close and reopen it. A page that runs but fails
        # shows its own Retry card, so it is never relaunched over.
        if res == 'failed' and not app_startup.PAGE_CONTACT.is_set() and not closed.is_set():
            if app_startup.relaunch_safe_graphics('WebView2 never showed the page'):
                window.destroy()
                return
        if not closed.is_set() and window.events.loaded.wait(5):
            app_startup.hook_renderer_recovery(window)      # no-op once attached early

    threading.Thread(target=run, name='startup-watchdog', daemon=True).start()


if __name__ == '__main__':
    import os
    import sys
    import app_startup
    from utils import APP_NAME, APP_EDITION, APP_VERSION

    app_startup.enable_file_log()      # <app data>/logs/startup.log
    app_startup.log('%s %s starting (pid %s, frozen=%s)', APP_TITLE, APP_VERSION,
                    os.getpid(), bool(getattr(sys, 'frozen', False)))
    # One running copy: a second launch brings the running window to the front instead of
    # opening another (never blocks when the other copy has no usable window).
    if not app_startup.single_instance('Local\\' + f'{APP_NAME}-{APP_EDITION}-instance', APP_TITLE):
        app_startup.close_splash('another copy brought forward')
        sys.exit(0)
    previous = app_startup.begin_launch()
    graphics = app_startup.apply_graphics_mode()      # WebView2 --disable-gpu only when a
    app_startup.log('graphics mode: %s', graphics)    # launch on THIS PC never became ready
    # ONE WebView2 folder kept between launches (not a new temporary profile every time);
    # a fresh one when another copy runs or after a relaunch (app_startup.webview_profile).
    profile = app_startup.webview_profile(graphics, previous=previous)
    app_startup.log('WebView2 profile: %s %s (%s)', profile['kind'],
                    profile['path'] or '<pywebview temp folder>', profile['reason'])
    app_startup.attach_library_loggers()
    app_startup.splash_text('Opening your projects...')

    from server import make_server

    server = make_server()             # never raises on a damaged/locked database
    port = server.server_address[1]

    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    url = f'http://localhost:{port}/'
    api = Api()
    window = webview.create_window(
        APP_TITLE,
        url,
        js_api=api,
        width=1100,
        height=720,          # restore-down size (window opens maximized)
        min_size=(800, 550),
        maximized=True,       # open maximized by default, not the small default window
        background_color='#06090f',  # match the startup splash so the window never flashes black on cold-start
    )
    window.events.closed += app_startup.end_launch
    window.events.closed += app_startup.close_splash
    window.events.shown += app_startup.on_window_shown     # closes the exe's splash
    window.events.loaded += app_startup.on_page_loaded
    app_startup.log('window created (%s)', url)
    app_startup.splash_text('Opening the window...')
    # private_mode=True keeps the PAGE's storage per launch exactly as before (preferences
    # live in ui_prefs.json / the database); storage_path only fixes WebView2's own folder.
    webview.start(_watch_startup, (window, url), private_mode=True,
                  storage_path=profile['path'])
