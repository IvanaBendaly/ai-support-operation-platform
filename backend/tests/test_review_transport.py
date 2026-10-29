import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from northstar.ai.transport import post_json


def test_provider_process_enforces_timeout_redirect_block_and_json_contract():
    hits = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            hits.append(self.path)
            if self.path == "/redirect":
                self.send_response(307)
                self.send_header("Location", "/should-not-be-called")
                self.end_headers()
                return
            if self.path == "/slow":
                time.sleep(1)
            body = json.dumps({"ok": True}).encode()
            try:
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        assert post_json(url + "/ok", {"synthetic": True}, 10) == {"ok": True}
        with pytest.raises(ValueError, match="transport failed"):
            post_json(url + "/redirect", {}, 10)
        assert "/should-not-be-called" not in hits
        with pytest.raises(subprocess.TimeoutExpired):
            post_json(url + "/slow", {}, 0.1)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
