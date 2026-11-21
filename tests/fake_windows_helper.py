"""A stand-in for the Windows driver's PowerShell helper, for tests without Windows.

    python fake_windows_helper.py PORT TOKEN

It connects to the relay, says the token, swallows the helper script up to
the marker, and then answers the helper's ops against a pretend desktop with
one game process. What it was asked to do is appended, one JSON line an op,
to ``$FAKE_WIN_LOG``. ``$FAKE_WIN_RUNNING`` (a pid) pretends the game is
already running; ``$FAKE_WIN_REGISTRY`` (JSON ``{"KEY\\\\name": value}``) seeds
the registry. Screenshots are solid PNGs of the requested size. ``look`` and ``strokes``
check the same bounds as the real helper.
"""

import json
import os
import socket
import struct
import subprocess
import sys
import zlib

MARKER = "#PT-END-OF-SCRIPT"
CLIENT = [0, 0, 1920, 1080]


def png(path, width, height):
    raw = b"".join(b"\x00" + b"\x40\x80\x40" * width for _ in range(height))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def local_path(path):
    if path.startswith("\\\\"):
        try:
            return subprocess.run(["wslpath", "-u", path], stdout=subprocess.PIPE, universal_newlines=True).stdout.strip()
        except OSError:
            return path
    return path


def main():
    port, token = int(sys.argv[1]), sys.argv[2]
    log = os.environ.get("FAKE_WIN_LOG")
    running = os.environ.get("FAKE_WIN_RUNNING")
    game = {"pid": int(running), "alive": True, "ticks": "111"} if running else None
    registry = json.loads(os.environ.get("FAKE_WIN_REGISTRY") or "{}")
    policy = None
    sock = socket.create_connection(("127.0.0.1", port))
    f = sock.makefile("rwb")
    f.write((token + "\n").encode())
    f.flush()
    for line in f:
        if line.decode().strip() == MARKER:
            break
    for line in f:
        req = json.loads(line.decode())
        op = req.get("op")
        if log:
            with open(log, "a") as out:
                out.write(json.dumps(req) + "\n")
        reply = {"ok": True, "op": op}
        refused = None
        if op in ("regget", "regset", "regdel") and (policy is None or req["key"] not in policy["registry"]):
            refused = "the profile does not name this registry key"
        elif op == "launch" and (policy is None or req["path"] != policy["exe"]):
            refused = "only the profile's game may be launched"
        elif op in ("close", "kill") and not (game and game.get("launched") and game["pid"] == req["pid"]):
            refused = "only a game pt launched may be closed"
        bad = None
        if op == "look":
            moves = req.get("moves") or []
            if not 1 <= len(moves) <= 1000:
                bad = "look takes 1 to 1000 moves"
            elif any(abs(int(m[0])) > 10000 or abs(int(m[1])) > 10000 for m in moves):
                bad = "a look move is at most 10000 pixels"
            else:
                reply["moves"] = len(moves)
        elif op == "strokes":
            strokes = req.get("strokes") or []
            if not 1 <= len(strokes) <= 500:
                bad = "strokes takes 1 to 500 keys"
            elif any(not 1 <= len(s) <= 4 for s in strokes):
                bad = "a stroke is 1 to 4 keys"
            else:
                reply["strokes"] = len(strokes)
        if refused:
            reply = {"ok": False, "op": op, "error": "refused: " + refused}
        elif bad:
            reply = {"ok": False, "op": op, "error": bad}
        elif op == "policy":
            if policy is not None:
                reply = {"ok": False, "op": op, "error": "refused: the policy is already set"}
            else:
                policy = {"registry": [k for k in req.get("registry") or [] if k.startswith("HKCU:")],
                          "shotDir": req.get("shotDir"), "exe": req.get("exe")}
        elif op == "processes":
            reply["processes"] = ([{"pid": game["pid"], "startTicks": game["ticks"], "title": "Fake Game", "hwnd": 77}]
                                  if game and game["alive"] else [])
        elif op == "alive":
            reply["alive"] = bool(game and game["alive"] and game["pid"] == req["pid"])
        elif op in ("windows", "window", "focus"):
            win = {"hwnd": 77, "pid": game["pid"] if game else 0, "title": "Fake Game", "class": "Fake",
                   "client": CLIENT, "minimized": False, "foreground": True}
            reply.update({"windows": [win, dict(win, hwnd=78, title="Proxy")]} if op == "windows" else {"window": win})
            if op == "focus":
                reply["foreground"] = True
        elif op == "launch":
            game = {"pid": 4242, "alive": True, "ticks": "222", "launched": True}
            reply.update({"pid": 4242, "startTicks": "222"})
        elif op in ("close", "kill"):
            if game:
                game["alive"] = False
        elif op == "shot":
            png(local_path(req["path"]), int(req["width"]) or CLIENT[2], int(req["height"]) or CLIENT[3])
        elif op == "regget":
            key = req["key"] + "\\" + req["name"]
            reply.update({"exists": key in registry, "value": registry.get(key)})
        elif op == "regset":
            registry[req["key"] + "\\" + req["name"]] = req["value"]
        elif op == "regdel":
            registry.pop(req["key"] + "\\" + req["name"], None)
        elif op == "bye":
            reply["bye"] = True
        f.write((json.dumps(reply) + "\n").encode())
        f.flush()
        if op == "bye":
            break


if __name__ == "__main__":
    main()
