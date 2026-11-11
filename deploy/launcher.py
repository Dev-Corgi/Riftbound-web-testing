#!/usr/bin/env python3
"""Tiny control plane for the riftbound web server (stdlib only, loopback only).

riftbound runs exactly one game per process and takes decks / AI on its command
line, so choosing them "in the browser" means (re)starting the process. nginx
forwards /api/* here:

  GET  /api/decks   [{id, legend, champion}]
  GET  /api/images  {card name: image url}      (from cards/raw/gallery_raw.json)
  GET  /api/status  {state: idle|running, config, error}
  POST /api/start   {deck1, deck2, level}        -> (re)starts the game
"""
import collections
import glob
import http.server
import json
import os
import re
import signal
import socket
import subprocess
import threading
import time

ROOT = os.environ.get("RIFTBOUND_ROOT", "/app")
GAME_PORT = int(os.environ.get("GAME_PORT", "8081"))
API_PORT = int(os.environ.get("API_PORT", "8082"))

# Only information-set search (ismcts) is used: it does not look at the human's
# hidden cards. "random" is the easy bot.
LEVELS = {
    "easy": "random",
    "normal": "ismcts:sims=50",
    "hard": "ismcts:sims=200",
    "expert": "ismcts:sims=500",
}

lock = threading.Lock()
proc = None
config = None
last_error = None
tail = collections.deque(maxlen=40)


def load_decks():
    out = []
    for path in sorted(glob.glob(os.path.join(ROOT, "decks", "*.txt"))):
        legend = champion = None
        section = None
        with open(path, encoding="utf-8", errors="replace") as f:
            for raw in f:
                line = raw.strip()
                if line.endswith(":"):
                    section = line[:-1]
                    continue
                m = re.match(r"^\d+\s+(.+)$", line)
                if m and section == "Legend" and legend is None:
                    legend = m.group(1)
                elif m and section == "Champion" and champion is None:
                    champion = m.group(1)
        did = os.path.splitext(os.path.basename(path))[0]
        strip = lambda n: re.sub(r"\s*#\d+$", "", n) if n else n  # "Yasuo, Windrider #546"
        legend, champion = strip(legend), strip(champion)
        out.append({"id": did, "legend": legend or did, "champion": champion or did})
    return out


DECKS = load_decks()
DECK_IDS = {d["id"] for d in DECKS}


def load_images():
    out = {}
    try:
        with open(os.path.join(ROOT, "cards", "raw", "gallery_raw.json"), encoding="utf-8") as f:
            for card in json.load(f):
                name = card.get("name")
                url = (card.get("cardImage") or {}).get("url")
                if not (name and url):
                    continue
                # The engine calls champions/legends "<name>, <subtitle>" while the
                # gallery stores them apart; index both. First write wins.
                sub = card.get("subtitle")
                for key in ((f"{name}, {sub}",) if sub else ()) + (name,):
                    out.setdefault(key, url)
    except (OSError, ValueError):
        pass
    return out


IMAGES_JSON = json.dumps(load_images(), separators=(",", ":")).encode()


def alive():
    return proc is not None and proc.poll() is None


def port_open():
    try:
        with socket.create_connection(("127.0.0.1", GAME_PORT), timeout=0.3):
            return True
    except OSError:
        return False


def pump(p):
    for line in iter(p.stdout.readline, b""):
        text = line.decode("utf-8", "replace").rstrip()
        tail.append(text)
        print("[riftbound]", text, flush=True)


def stop():
    global proc
    if alive():
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    proc = None


def start(deck1, deck2, level):
    """Returns (ok, error message)."""
    global proc, config, last_error
    if deck1 not in DECK_IDS or deck2 not in DECK_IDS:
        return False, "unknown deck"
    if level not in LEVELS:
        return False, "unknown level"
    with lock:
        stop()
        tail.clear()
        last_error = None
        cmd = ["stdbuf", "-oL", "./riftbound",
               "--agent1", "human", "--agent2", LEVELS[level],
               "--deck1", f"decks/{deck1}.txt", "--deck2", f"decks/{deck2}.txt",
               "--bind", "127.0.0.1", "--port", str(GAME_PORT), "--god-mode", "off"]
        env = dict(os.environ, RIFTBOUND_ROOT=ROOT)
        proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        threading.Thread(target=pump, args=(proc,), daemon=True).start()
        deadline = time.time() + 40
        while time.time() < deadline:
            if proc.poll() is not None:
                time.sleep(0.2)  # let pump() collect the last lines
                msgs = [l for l in tail if l.strip()][-4:]
                last_error = " / ".join(msgs) or f"exited with code {proc.returncode}"
                config = None
                return False, last_error
            if port_open():
                config = {"deck1": deck1, "deck2": deck2, "level": level}
                return True, None
            time.sleep(0.2)
        stop()
        last_error = "timed out while starting"
        return False, last_error


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "launcher"

    def log_message(self, fmt, *args):  # keep fly logs readable
        pass

    def send_json(self, obj, code=200, cache=None):
        body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache or "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/decks":
            self.send_json(DECKS, cache="max-age=3600")
        elif path == "/api/images":
            self.send_json(IMAGES_JSON, cache="max-age=3600")
        elif path == "/api/status":
            running = alive() and port_open()
            self.send_json({"state": "running" if running else "idle",
                            "config": config if running else None,
                            "error": last_error,
                            "levels": list(LEVELS)})
        else:
            self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/api/start":
            return self.send_json({"error": "not found"}, 404)
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if n > 4096:
                raise ValueError
            body = json.loads(self.rfile.read(n) or b"{}")
            d1, d2, lv = str(body["deck1"]), str(body["deck2"]), str(body["level"])
        except (ValueError, KeyError, TypeError):
            return self.send_json({"ok": False, "error": "bad request"}, 400)
        ok, err = start(d1, d2, lv)
        self.send_json({"ok": ok, "error": err}, 200 if ok else 500)


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    def bye(*_):
        stop()
        os._exit(0)
    signal.signal(signal.SIGTERM, bye)
    signal.signal(signal.SIGINT, bye)
    print(f"[launcher] {len(DECKS)} decks, {len(json.loads(IMAGES_JSON))} card images, "
          f"api on 127.0.0.1:{API_PORT}", flush=True)
    Server(("127.0.0.1", API_PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
