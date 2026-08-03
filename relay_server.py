"""
Relay Server for Clipboard Share
Runs on a cloud server to relay clipboard data between sender and receiver.
No dependencies — uses only Python stdlib (http.server).

Usage:
    python relay_server.py              # port 5000
    python relay_server.py --port 8080
    python relay_server.py --cleanup 60 # auto-clean rooms older than 60 min
"""

import http.server
import json
import time
import sys
import os
import threading
import urllib.parse

HOST = "0.0.0.0"
# Cloud hosts such as Render provide the listening port through PORT.  Local
# runs still default to 5000.
PORT = int(os.environ.get("PORT", "5000"))
CLEANUP_MINUTES = 60

# In-memory store: {room: {"text": str, "timestamp": float}}
rooms = {}
rooms_lock = threading.Lock()


class RelayHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_OPTIONS(self):
        self._respond(204, None)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        parts = parsed.path.strip("/").split("/")

        if len(parts) == 2 and parts[0] == "send":
            room = parts[1]
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(body)
                text = data.get("text", "")
            except Exception:
                self._respond(400, {"error": "invalid json"})
                return

            with rooms_lock:
                rooms[room] = {"text": text, "timestamp": time.time()}

            self._respond(200, {"status": "ok", "room": room})
            self.server.log_message(f"[SEND] room={room} len={len(text)}")
        else:
            self._respond(404, {"error": "use POST /send/<room>"})

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        parts = parsed.path.strip("/").split("/")

        if len(parts) == 2 and parts[0] == "receive":
            room = parts[1]
            with rooms_lock:
                entry = rooms.get(room)
            if entry:
                self._respond(200, {"text": entry["text"], "timestamp": entry["timestamp"]})
            else:
                self._respond(404, {"error": "room not found"})
        elif len(parts) == 1 and parts[0] == "health":
            self._respond(200, {"status": "alive", "rooms": len(rooms)})
        else:
            self._respond(404, {"error": "use GET /receive/<room> or GET /health"})

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        parts = parsed.path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "clear":
            room = parts[1]
            with rooms_lock:
                rooms.pop(room, None)
            self._respond(200, {"status": "cleared", "room": room})
        else:
            self._respond(404, {"error": "use DELETE /clear/<room>"})

    def _respond(self, code, data):
        if data is not None:
            body = json.dumps(data).encode()
        else:
            body = b""
        self.send_response(code)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        if data is not None:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[{time.strftime('%H:%M:%S')}] {fmt % args}\n")


def cleanup_loop(interval_min):
    """Periodically remove rooms older than interval_min minutes."""
    while True:
        time.sleep(interval_min * 60)
        now = time.time()
        cutoff = now - interval_min * 60
        with rooms_lock:
            expired = [r for r, d in rooms.items() if d["timestamp"] < cutoff]
            for r in expired:
                del rooms[r]
            if expired:
                print(f"[Cleanup] removed {len(expired)} expired rooms")


def run(host, port, cleanup_min):
    server = http.server.ThreadingHTTPServer((host, port), RelayHandler)
    print(f"[Relay Server] running on http://{host}:{port}")
    print(f"[Relay Server] POST  /send/<room>     — sender posts clipboard")
    print(f"[Relay Server] GET   /receive/<room>   — receiver fetches data")
    print(f"[Relay Server] GET   /health           — health check")
    print(f"[Relay Server] Rooms auto-clean after {cleanup_min} min\n")

    t = threading.Thread(target=cleanup_loop, args=(cleanup_min,), daemon=True)
    t.start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Relay Server] shutting down...")
        server.shutdown()


if __name__ == "__main__":
    port = PORT
    cleanup = CLEANUP_MINUTES
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
        if arg == "--cleanup" and i + 1 < len(args):
            cleanup = int(args[i + 1])
    run(HOST, port, cleanup)
