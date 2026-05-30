#!/usr/bin/env python3
"""Launch the self-contained Layout Editor in a browser and wait for confirmation."""

import argparse
import json
import os
import socket
import sys
import threading
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Multi-threaded HTTP server so the editor page can be reopened after tab close."""
    daemon_threads = True
    allow_reuse_address = True
from pathlib import Path


def find_free_port(preferred=8765):
    for port in range(preferred, preferred + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('localhost', port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free port found in range")


def make_handler(html_path, intermediate_path, confirmed_path, confirmation_event, editor_mode='confirmation'):
    # Select the correct HTML file based on mode
    html_dir = Path(html_path).parent
    if editor_mode == 'draft':
        resolved_html = html_dir / 'draft_editor.html'
    else:
        resolved_html = html_dir / 'confirmation_editor.html'

    if not resolved_html.exists():
        raise FileNotFoundError(f"Editor HTML not found at {resolved_html}")

    vendor_dir = html_dir / 'vendor'

    # Pre-load and embed the JSON into the HTML once at startup
    with open(str(resolved_html), 'r', encoding='utf-8') as f:
        html_template = f.read()
    with open(intermediate_path, 'r', encoding='utf-8') as f:
        layout_json_str = f.read()
    # Inject data as global variables into the HTML
    inject_script = f'<script>window.__LAYOUT_DATA__ = {layout_json_str}; window.__EDITOR_MODE__ = \'{editor_mode}\';</script>'
    served_html = html_template.replace('</head>', inject_script + '\n</head>', 1)
    served_html_bytes = served_html.encode('utf-8')

    class EditorHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # Suppress default HTTP logs

        def do_GET(self):
            if self.path == '/' or self.path == '/index.html':
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(served_html_bytes)))
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                self.wfile.write(served_html_bytes)
            elif self.path == '/data':
                self.serve_file(intermediate_path, 'application/json; charset=utf-8')
            elif self.path == '/vendor/react.min.js':
                self.serve_file(str(vendor_dir / 'react.min.js'), 'application/javascript')
            elif self.path == '/vendor/react-dom.min.js':
                self.serve_file(str(vendor_dir / 'react-dom.min.js'), 'application/javascript')
            else:
                self.send_error(404)

        def do_POST(self):
            if self.path == '/confirm':
                try:
                    content_length = int(self.headers.get('Content-Length', 0))
                    body = self.rfile.read(content_length)
                    data = json.loads(body)

                    Path(confirmed_path).parent.mkdir(parents=True, exist_ok=True)
                    with open(confirmed_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)

                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(b'{"status":"ok"}')

                    mode_label = "draft" if editor_mode == "draft" else "confirmed"
                    print(f"[layout_editor] {mode_label.capitalize()} layout saved to {confirmed_path}")
                    confirmation_event.set()
                except Exception as e:
                    self.send_error(500, str(e))
            else:
                self.send_error(404)

        def do_OPTIONS(self):
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()

        def serve_file(self, path, content_type):
            try:
                with open(path, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(content)))
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                self.wfile.write(content)
            except FileNotFoundError:
                self.send_error(404, f"File not found: {path}")

    return EditorHandler


def launch_layout_editor(intermediate_json: str, confirmed_json: str, port: int = 0, no_open: bool = False, mode: str = 'confirmation') -> str:
    """Launch the standalone layout editor and block until confirmed.

    Args:
        intermediate_json: Path to the intermediate editor JSON file.
        confirmed_json: Path where confirmed JSON will be written.
        port: HTTP server port (0=auto).
        no_open: Skip auto-opening browser.
        mode: Editor mode - 'confirmation' (default, full layout) or 'draft' (minimal, no fillers required).

    Returns the path to the confirmed JSON file.
    """
    # Select HTML file based on mode
    html_name = 'draft_editor.html' if mode == 'draft' else 'confirmation_editor.html'
    html_path = Path(__file__).parent / html_name
    if not html_path.exists():
        raise FileNotFoundError(f"draft_editor.html not found at {html_path}")
    if not Path(intermediate_json).exists():
        raise FileNotFoundError(f"Intermediate JSON not found: {intermediate_json}")

    actual_port = port if port else find_free_port()
    confirmation_event = threading.Event()

    handler_class = make_handler(
        str(html_path),
        intermediate_json,
        confirmed_json,
        confirmation_event,
        editor_mode=mode,
    )

    server = ThreadedHTTPServer(('localhost', actual_port), handler_class)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    url = f"http://localhost:{actual_port}/"
    is_draft = mode == 'draft'
    mode_title = "Draft Editor" if is_draft else "Layout Editor"
    confirm_btn = "Confirm Draft" if is_draft else "Confirm & Continue"

    print(f"")
    print(f"╔══════════════════════════════════════════════════════════════╗")
    print(f"║       IO Ring {mode_title} — Action Required                  ║")
    print(f"╠══════════════════════════════════════════════════════════════╣")
    print(f"║  Mode: {mode:<52}║")
    print(f"║  Server running on port: {actual_port:<5}                              ║")
    print(f"║                                                              ║")
    print(f"║  Open in your browser (Ctrl+Click the URL below):           ║")
    print(f"║                                                              ║")
    print(f"║  Then open in your local browser:                           ║")
    print(f"║    {url:<57}║")
    print(f"║                                                              ║")
    print(f"║  Click \"{confirm_btn}\" when done editing.{' ' * (33 - len(confirm_btn))}║")
    if is_draft:
        print(f"║  Note: Fillers and pin connections will be added later.      ║")
    print(f"╚══════════════════════════════════════════════════════════════╝")
    print(f"")

    # Print the URL on its own line so terminals (VS Code, iTerm2, etc.) make it clickable
    print(f"  >>> {url} <<<")
    print(f"")

    if not no_open:
        # Wait longer for VS Code Remote to detect the port and set up forwarding.
        # VS Code's port-auto-detection can take 1-2 seconds.
        print(f"[layout_editor] Waiting for port forwarding to initialize...")
        time.sleep(1.5)
        try:
            result = webbrowser.open(url)
            if result:
                print(f"[layout_editor] Browser open request sent successfully.")
            else:
                print(f"[layout_editor] webbrowser.open() returned False — browser may not be available.")
                print(f"[layout_editor] Please open the URL manually in your browser.")
        except Exception as e:
            print(f"[layout_editor] Could not auto-open browser: {e}")
            print(f"[layout_editor] Please open the URL manually in your browser.")

    print(f"[layout_editor] Waiting for confirmation... (server stays open until you confirm)")

    confirmation_event.wait()
    server.shutdown()
    print(f"[layout_editor] Done. {'Draft' if is_draft else 'Confirmed'} layout saved.")
    return confirmed_json


def main():
    parser = argparse.ArgumentParser(description='Launch the IO Ring Layout Editor')
    parser.add_argument('intermediate_json', help='Path to the intermediate editor JSON file')
    parser.add_argument('confirmed_json', help='Path where confirmed JSON will be written')
    parser.add_argument('--port', type=int, default=0, help='HTTP server port (0=auto)')
    parser.add_argument('--no-open', action='store_true', help='Skip auto-opening browser')
    parser.add_argument('--mode', choices=['draft', 'confirmation'], default='confirmation',
                        help='Editor mode: draft (minimal, no fillers) or confirmation (full layout)')
    args = parser.parse_args()

    try:
        launch_layout_editor(
            intermediate_json=args.intermediate_json,
            confirmed_json=args.confirmed_json,
            port=args.port,
            no_open=args.no_open,
            mode=args.mode,
        )
        sys.exit(0)
    except Exception as e:
        print(f"[layout_editor] Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
