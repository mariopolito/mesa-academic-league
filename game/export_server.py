"""Serve the MAL folder on localhost:8765; POST /save writes the body to game/items.json."""
import http.server, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

class H(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/save":
            self.send_error(404); return
        body = self.rfile.read(int(self.headers["Content-Length"]))
        with open(os.path.join(ROOT, "game", "items.json"), "wb") as f:
            f.write(body)
        self.send_response(200); self.send_header("Content-Type", "text/plain"); self.end_headers()
        self.wfile.write(b"saved %d bytes" % len(body))

http.server.ThreadingHTTPServer(("127.0.0.1", 8765), H).serve_forever()
