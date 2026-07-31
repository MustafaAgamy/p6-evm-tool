import threading
import webview
from utils import resource_path


class Api:
    def choose_file(self):
        """Open native file picker; returns absolute path string or None."""
        result = webview.windows[0].create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=('P6 Schedule Files (*.xml;*.xer)', 'P6 XML Files (*.xml)', 'P6 XER Files (*.xer)')
        )
        return result[0] if result else None

    def choose_save_path(self, default_name='report.pdf', file_type='pdf'):
        """Open native save dialog; returns absolute path string or None.

        file_type ∈ {'pdf', 'xlsx'} chooses the dialog filter.
        """
        types = {
            'pdf':  ('PDF Files (*.pdf)',),
            'xlsx': ('Excel Files (*.xlsx)',),
        }.get(file_type, ('All Files (*.*)',))
        result = webview.windows[0].create_file_dialog(
            webview.SAVE_DIALOG,
            file_types=types,
            save_filename=default_name
        )
        return result[0] if result else None


if __name__ == '__main__':
    from server import make_server

    server = make_server()
    port = server.server_address[1]

    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    api = Api()
    webview.create_window(
        'P6 EVM Tool',
        f'http://localhost:{port}/',
        js_api=api,
        width=1100,
        height=720,
        min_size=(800, 550),
    )
    webview.start()
