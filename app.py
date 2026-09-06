import threading
import webview
from utils import resource_path, APP_TITLE


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
            file_types=('Excel Files (*.xlsx;*.xlsm)', 'All Files (*.*)')
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

        file_type ∈ {'pdf', 'xlsx', 'xml', 'xer', 'json'} chooses the dialog filter.
        """
        types = {
            'pdf':  ('PDF Files (*.pdf)',),
            'doc':  ('Word Files (*.doc)',),
            'xlsx': ('Excel Files (*.xlsx)',),
            'xml':  ('P6 XML Files (*.xml)',),
            'xer':  ('P6 XER Files (*.xer)',),
            'json': ('JSON Files (*.json)',),
        }.get(file_type, ('All Files (*.*)',))
        result = webview.windows[0].create_file_dialog(
            webview.SAVE_DIALOG,
            file_types=types,
            save_filename=default_name
        )
        return result[0] if result else None

    def quit(self):
        """Close the application window (File ▸ Exit)."""
        for w in list(webview.windows):
            w.destroy()


if __name__ == '__main__':
    from server import make_server

    server = make_server()
    port = server.server_address[1]

    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    api = Api()
    webview.create_window(
        APP_TITLE,
        f'http://localhost:{port}/',
        js_api=api,
        width=1100,
        height=720,
        min_size=(800, 550),
    )
    webview.start()
