import threading
import webview
from utils import resource_path


class Api:
    def choose_file(self):
        """Open native file picker; returns absolute path string or None."""
        result = webview.windows[0].create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=('P6 XML Files (*.xml)',)
        )
        return result[0] if result else None

    def choose_save_path(self, default_name='report.pdf'):
        """Open native save dialog; returns absolute path string or None."""
        result = webview.windows[0].create_file_dialog(
            webview.SAVE_DIALOG,
            file_types=('PDF Files (*.pdf)',),
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
