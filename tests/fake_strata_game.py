"""A stand-in for a Strata game, speaking the drive protocol (Strata docs/DRIVE.md) with no GL.

Used by tests/test_strata_driver.py so the Strata driver is tested in CI
without building a game. It behaves as a Strata engine does: it connects to
``STRATA_DRIVE`` (never listens), honours ``STRATA_DRIVE_CLOCK`` and
``STRATA_DRIVE_STEP``, waits for grants at the start of each frame when
stepped (reading lines one at a time and stopping at the ``step``), delivers
events on the next frame, answers a step after its last frame, and writes a
small PNG for ``shot``. The "game": a square that moves right while the right
arrow (scancode 79) is held, 60 pixels a second of game time, and quits on a
QUIT event. With ``--playtest-out DIR`` it writes a minimal probe state.json.
"""

import json
import os
import socket
import struct
import sys
import time
import zlib

W, H = 64, 64


def png(path, x, held):
    rows = []
    for row in range(H):
        line = bytearray([0])
        for col in range(W):
            inside = int(x) % W <= col < int(x) % W + 8 and 20 <= row < 28
            line += bytes((230, 120, 40) if inside else (20, 30 + 40 * held, 40))
        rows.append(bytes(line))
    raw = b"".join(rows)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


class Game:
    def __init__(self, path, out_dir):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(path)
        self.buf = b""
        self.mode = os.environ.get("STRATA_DRIVE_CLOCK", "free")
        self.step_s = float(os.environ.get("STRATA_DRIVE_STEP", 1.0 / 60))
        self.granted = 0
        self.pending = False
        self.run = 0
        self.frame = 0
        self.queue = []
        self.held = set()
        self.x = 0.0
        self.out_dir = out_dir
        self.connected = True
        self.running = True

    def send(self, obj):
        if self.connected:
            self.sock.sendall(json.dumps(obj).encode() + b"\n")

    def read(self, block):
        self.sock.setblocking(block)
        try:
            data = self.sock.recv(65536)
        except BlockingIOError:
            return False
        if not data:
            self.connected = False
            self.mode = "free"
            return False
        self.buf += data
        return True

    def next_line(self):
        if b"\n" not in self.buf:
            return None
        line, self.buf = self.buf.split(b"\n", 1)
        return json.loads(line.decode())

    def handle(self, msg):
        op = msg.get("op")
        if op == "hello":
            self.send({"ok": True, "op": op, "protocol": 1, "strata": "fake", "abi": "1.9", "width": W,
                       "height": H, "surface": "headless", "clock": self.mode, "step": self.step_s, "frame": self.frame})
        elif op == "event":
            self.queue.append(msg)
            self.send({"ok": True, "op": op, "queued": len(self.queue)})
        elif op == "clock":
            self.mode = msg["mode"]
            self.step_s = msg.get("step", self.step_s)
            self.send({"ok": True, "op": op, "clock": self.mode, "step": self.step_s})
        elif op == "step":
            if self.mode != "stepped":
                self.send({"ok": False, "op": op, "error": "step needs the stepped clock"})
            else:
                self.granted, self.pending, self.run = int(msg["frames"]), True, 0
        elif op == "shot":
            png(msg["path"], self.x, len(self.held))
            self.send({"ok": True, "op": op, "path": msg["path"], "width": W, "height": H})
        elif op == "stats":
            self.send({"ok": True, "op": op, "frame": self.frame, "clock": self.mode, "step": self.step_s})
        elif op == "bye":
            self.send({"ok": True, "op": op})
            self.sock.close()
            self.connected = False
            self.mode = "free"
        else:
            self.send({"ok": False, "op": op, "error": "unknown op"})

    def frame_start(self):
        if self.connected and self.mode == "stepped":
            while self.connected and self.mode == "stepped" and self.granted == 0:
                msg = self.next_line()
                if msg is None:
                    self.read(True)
                    continue
                self.handle(msg)
            if self.granted > 0:
                self.granted -= 1
        elif self.connected:
            while self.read(False):
                pass
            while self.mode == "free":
                msg = self.next_line()
                if msg is None:
                    break
                self.handle(msg)

    def loop(self):
        last = time.time()
        while self.running:
            self.frame_start()
            for e in self.queue:
                if e["type"] == "key_down":
                    self.held.add(e.get("scancode"))
                elif e["type"] == "key_up":
                    self.held.discard(e.get("scancode"))
                elif e["type"] == "quit":
                    self.running = False
            self.queue = []
            now = time.time()
            dt = self.step_s if (self.connected and self.mode == "stepped") else now - last
            last = now
            if 79 in self.held:
                self.x += 60.0 * dt
            if self.out_dir:
                tmp = os.path.join(self.out_dir, "state.json.tmp")
                with open(tmp, "w") as f:
                    json.dump({"wallTimeMs": int(now * 1000), "version": "0.0.0", "screen": "WORLD",
                               "fps": 60, "tick": self.frame, "x": round(self.x, 3)}, f)
                os.replace(tmp, os.path.join(self.out_dir, "state.json"))
            self.frame += 1
            if self.pending:
                self.run += 1
                if self.granted == 0:
                    self.pending = False
                    self.send({"ok": True, "op": "step", "frame": self.frame, "frames_run": self.run})
            if self.mode == "free":
                time.sleep(1.0 / 60)


def main():
    out_dir = None
    if "--playtest-out" in sys.argv:
        out_dir = sys.argv[sys.argv.index("--playtest-out") + 1]
        os.makedirs(out_dir, exist_ok=True)
    path = os.environ.get("STRATA_DRIVE")
    if not path:
        print("fake game: STRATA_DRIVE is not set", file=sys.stderr)
        return 2
    print("fake game: driven through %s (%s clock)" % (path, os.environ.get("STRATA_DRIVE_CLOCK", "free")))
    sys.stdout.flush()
    Game(path, out_dir).loop()
    print("fake game: quit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
