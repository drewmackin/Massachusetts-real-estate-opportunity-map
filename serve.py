#!/usr/bin/env python3
"""
serve.py — tiny stdlib web server for the MA Opportunity Map.

Serves the static map AND persists "liked" homes to data/likes.json (which the nightly
update_listings.py reads to refresh your favorites first). Use this instead of
`python3 -m http.server` so the ♥ Like button survives reloads and feeds the updater.

    python3 serve.py            # -> http://localhost:8000/
    MAP_PORT=8080 python3 serve.py

If you run plain http.server instead, likes still work in the browser (localStorage),
they just won't be written to disk for the nightly job.
"""
import http.server, socketserver, json, os

PORT = int(os.environ.get("MAP_PORT", "8000"))
ROOT = os.path.dirname(os.path.abspath(__file__))
LIKES = os.path.join(ROOT, "data", "likes.json")


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.split("?")[0] == "/api/likes":
            try:
                data = json.load(open(LIKES))
            except Exception:
                data = {"homes": {}, "keys": []}
            return self._json(data)
        return super().do_GET()

    def do_POST(self):
        if self.path.split("?")[0] == "/api/like":
            try:
                ln = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(ln) if ln else b"{}"
                obj = json.loads(raw or b"{}")
                if not isinstance(obj, dict):
                    obj = {}
                obj.setdefault("homes", {})
                obj["keys"] = list((obj.get("homes") or {}).keys())
                os.makedirs(os.path.dirname(LIKES), exist_ok=True)
                tmp = LIKES + ".tmp"
                with open(tmp, "w") as f:
                    json.dump(obj, f, separators=(",", ":"))
                os.replace(tmp, LIKES)
                return self._json({"ok": True, "n": len(obj["keys"])})
            except Exception as e:
                return self._json({"ok": False, "error": str(e)}, 400)
        self.send_response(404)
        self.end_headers()

    def log_message(self, *a):
        pass  # keep the console quiet


def main():
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("", PORT), Handler) as httpd:
        print(f"MA Opportunity Map → http://localhost:{PORT}/   (likes persist to data/likes.json)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nbye")


if __name__ == "__main__":
    main()
