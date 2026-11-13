"""The Windows driver: key table, helper command line, desktop lock, coordinates, log probe, profile,
and whole sessions against a stand-in helper.

The session tests run ``pt`` with ``PT_WINDOWS_HELPER`` pointing at
tests/fake_windows_helper.py, which speaks the helper's protocol to a
pretend desktop, so they need neither Windows nor WSL.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

from tests.helpers import HERE, SRC
from playtester.harness import profile as profiles
from playtester.harness import windows_driver, windows_keys, windows_log, windows_session
from playtester.harness.session import Session

FAKE_HELPER = os.path.join(HERE, "fake_windows_helper.py")


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class KeyTableTest(unittest.TestCase):
    def test_names_map_to_set_1_scancodes(self):
        self.assertEqual(windows_keys.scancode("a"), (0x1E, False))
        self.assertEqual(windows_keys.scancode("W"), (0x11, False))
        self.assertEqual(windows_keys.scancode("i"), (0x17, False))
        self.assertEqual(windows_keys.scancode("1"), (0x02, False))
        self.assertEqual(windows_keys.scancode("0"), (0x0B, False))
        self.assertEqual(windows_keys.scancode("F1"), (0x3B, False))
        self.assertEqual(windows_keys.scancode("F12"), (0x58, False))
        self.assertEqual(windows_keys.scancode("Escape"), (0x01, False))
        self.assertEqual(windows_keys.scancode("Esc"), (0x01, False))
        self.assertEqual(windows_keys.scancode("Return"), (0x1C, False))
        self.assertEqual(windows_keys.scancode("space"), (0x39, False))
        self.assertEqual(windows_keys.scancode("Tab"), (0x0F, False))

    def test_the_extended_block_is_flagged(self):
        for name in ("Up", "Down", "Left", "Right", "Home", "End", "Insert", "Delete", "Prior", "Next",
                     "Control_R", "Alt_R", "KP_Enter"):
            self.assertTrue(windows_keys.scancode(name)[1], name)
        self.assertFalse(windows_keys.scancode("KP_8")[1])
        self.assertEqual(windows_keys.scancode("Up")[0], windows_keys.scancode("KP_8")[0])

    def test_combos_and_unknown_keys(self):
        self.assertEqual(windows_keys.combo_scancodes(["Shift_L", "w"]), [[0x2A, False], [0x11, False]])
        with self.assertRaises(windows_keys.UnknownKey):
            windows_keys.scancode("Hyper_Q")


class HelperCommandTest(unittest.TestCase):
    def setUp(self):
        self.saved = os.environ.pop("PT_WINDOWS_HELPER", None)

    def tearDown(self):
        if self.saved is not None:
            os.environ["PT_WINDOWS_HELPER"] = self.saved

    def test_the_bootstrap_connects_back_with_the_token_and_fits_a_command_line(self):
        digest = "AB" * 32
        cmd = windows_driver.helper_command("powershell.exe", 40123, "abc123", digest)
        self.assertEqual(cmd[0], "powershell.exe")
        self.assertIn("if($d -ne '%s')" % digest, cmd[-1])   # runs only the script it expects
        with self.assertRaises(ValueError):
            windows_driver.helper_command("powershell.exe", 40123, "abc123")
        self.assertIn("-Command", cmd)
        self.assertNotIn("-EncodedCommand", cmd)
        self.assertEqual(cmd[cmd.index("-InputFormat") + 1], "None")
        script = cmd[-1]
        self.assertIn("TcpClient('127.0.0.1',40123)", script)
        self.assertIn("WriteLine('abc123')", script)
        self.assertIn("#PT-END-OF-SCRIPT", script)
        self.assertNotIn('"', script)  # double quotes do not survive WSL's command-line conversion
        self.assertLess(len(" ".join(cmd)), 2000)  # Windows command lines stop at 32767 characters

    def test_the_digest_is_of_the_script_as_the_bootstrap_rebuilds_it(self):
        import hashlib
        # ReadLine drops each line end, AppendLine adds CRLF; the relay sends the script plus a newline
        self.assertEqual(windows_driver.script_digest("a\nb\n"),
                         hashlib.sha256(b"a\r\nb\r\n\r\n").hexdigest().upper())
        self.assertEqual(windows_driver.script_digest("a\r\nb"), hashlib.sha256(b"a\r\nb\r\n").hexdigest().upper())

    def test_an_override_fills_port_and_token(self):
        os.environ["PT_WINDOWS_HELPER"] = json.dumps(["python3", "fake.py", "{port}", "{token}"])
        self.assertEqual(windows_driver.helper_command("x", 5, "t"), ["python3", "fake.py", "5", "t"])

    def test_interop_sockets_put_the_environments_first(self):
        with tempfile.TemporaryDirectory() as d:
            for name, age in (("1_interop", 300), ("2_interop", 100), ("3_interop", 200)):
                path = os.path.join(d, name)
                open(path, "w").close()
                os.utime(path, (time.time() - age, time.time() - age))
            got = windows_driver.interop_sockets(os.path.join(d, "3_interop"), d)
            self.assertEqual([os.path.basename(p) for p in got], ["3_interop", "2_interop", "1_interop"])
            self.assertEqual(len(windows_driver.interop_sockets("", d)), 3)


class PathsAndCoordinatesTest(unittest.TestCase):
    def test_mnt_paths_become_drive_paths(self):
        self.assertEqual(windows_driver.mnt_to_windows("/mnt/c/Program Files (x86)/Steam/x.exe"),
                         "C:\\Program Files (x86)\\Steam\\x.exe")
        self.assertEqual(windows_driver.mnt_to_windows("/mnt/d"), "D:\\")
        self.assertIsNone(windows_driver.mnt_to_windows("/tmp/x"))

    def test_registry_keys_become_powershell_drives(self):
        self.assertEqual(windows_driver.registry_path("HKCU\\Software\\MountAndBladeWarbandKeys"),
                         "HKCU:\\Software\\MountAndBladeWarbandKeys")
        self.assertEqual(windows_driver.registry_path("HKEY_LOCAL_MACHINE\\Software\\X"), "HKLM:\\Software\\X")
        with self.assertRaises(ValueError):
            windows_driver.registry_path("Software\\X")

    def test_screenshot_pixels_scale_to_the_real_window(self):
        client = [0, 0, 1920, 1080]
        self.assertEqual(windows_driver.scale_point(640, 700, client, (1280, 720)), (960, 1050))
        self.assertEqual(windows_driver.scale_point(0, 0, [100, 50, 800, 600], (800, 600)), (100, 50))
        # never outside the client area
        self.assertEqual(windows_driver.scale_point(5000, -3, client, (1280, 720)), (1919, 0))

    def test_the_game_window_is_the_largest_matching_one(self):
        windows = [{"title": "D3DProxyWindow", "client": [0, 0, 1920, 1080]},
                   {"title": "Mount&Blade Warband", "client": [0, 0, 1920, 1080]},
                   {"title": "Mount&Blade Warband", "client": [600, 300, 640, 480]}]
        self.assertEqual(windows_driver.pick_window(windows, "^Mount&Blade", 1024), windows[1])
        self.assertEqual(windows_driver.pick_window(windows[2:], "^Mount&Blade", 0), windows[2])
        self.assertIsNone(windows_driver.pick_window(windows[2:], "^Mount&Blade", 1024))


class DesktopLockTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "desktop.lock")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_a_live_holder_refuses_another_session(self):
        windows_driver.acquire_lock("s01", "/runs/a", os.getpid(), self.path)
        with self.assertRaises(windows_driver.DesktopLockError) as e:
            windows_driver.acquire_lock("s02", "/runs/a", os.getpid(), self.path)
        self.assertIn("session s01", str(e.exception))
        self.assertIn("only one session", str(e.exception))
        self.assertEqual(windows_driver.read_lock(self.path)["session"], "s01")

    def test_the_same_session_may_take_it_again(self):
        windows_driver.acquire_lock("s01", "/runs/a", os.getpid(), self.path)
        windows_driver.acquire_lock("s01", "/runs/a", os.getpid(), self.path)
        # the same name in another run directory is another session
        with self.assertRaises(windows_driver.DesktopLockError):
            windows_driver.acquire_lock("s01", "/runs/b", os.getpid(), self.path)

    def test_a_stale_lock_is_taken_over(self):
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait()
        with open(self.path, "w") as f:
            json.dump({"session": "old", "root": "/r", "pid": dead.pid, "pidStart": "1"}, f)
        got = windows_driver.acquire_lock("s01", "/runs/a", os.getpid(), self.path)
        self.assertEqual(got["session"], "s01")
        # a pid that now belongs to another process (start time differs) is stale too
        with open(self.path, "w") as f:
            json.dump({"session": "old", "root": "/r", "pid": os.getpid(), "pidStart": "0"}, f)
        windows_driver.acquire_lock("s02", "/runs/a", os.getpid(), self.path)
        # and so is a damaged file
        with open(self.path, "w") as f:
            f.write("{not json")
        windows_driver.acquire_lock("s03", "/runs/a", os.getpid(), self.path)

    def test_release_only_removes_our_own_lock(self):
        windows_driver.acquire_lock("s01", "/runs/a", os.getpid(), self.path)
        self.assertFalse(windows_driver.release_lock("s02", "/runs/a", self.path))
        self.assertTrue(os.path.exists(self.path))
        self.assertTrue(windows_driver.release_lock("s01", "/runs/a", self.path))
        self.assertFalse(os.path.exists(self.path))
        self.assertFalse(windows_driver.release_lock("s01", "/runs/a", self.path))

    def test_update_points_the_lock_at_the_relay(self):
        windows_driver.acquire_lock("s01", "/runs/a", os.getpid(), self.path)
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            windows_driver.update_lock("s01", "/runs/a", child.pid, self.path)
            holder = windows_driver.read_lock(self.path)
            self.assertEqual(holder["pid"], child.pid)
            self.assertTrue(windows_driver.lock_is_live(holder))
        finally:
            child.kill()
            child.wait()
        self.assertFalse(windows_driver.lock_is_live(windows_driver.read_lock(self.path)))


class LogProbeTest(unittest.TestCase):
    def test_key_value_lines(self):
        self.assertEqual(windows_log.parse_probe_line("PTPROBE screen to=WORLD"), {"type": "screen", "to": "WORLD"})
        got = windows_log.parse_probe_line('  PTPROBE: quest_started id=qst_errand title="The smith\'s errand" n=3')
        self.assertEqual(got, {"type": "quest_started", "id": "qst_errand", "title": "The smith's errand", "n": 3})
        got = windows_log.parse_probe_line("PTPROBE state gold=1200.5 player.x=12 player.z=-4 alive=true")
        self.assertEqual(got, {"type": "state", "gold": 1200.5, "player": {"x": 12, "z": -4}, "alive": True})

    def test_json_lines_and_odd_ones(self):
        self.assertEqual(windows_log.parse_probe_line('PTPROBE {"type": "Battle Won", "enemies": 12}'),
                         {"type": "battle_won", "enemies": 12})
        self.assertEqual(windows_log.parse_probe_line("PTPROBE"), {"type": "probe"})
        self.assertEqual(windows_log.parse_probe_line('PTPROBE note "unbalanced quote'),
                         {"type": "note", "text": '"unbalanced quote'})
        self.assertEqual(windows_log.parse_probe_line("PTPROBE hello big world"),
                         {"type": "hello", "text": "big world"})
        self.assertIsNone(windows_log.parse_probe_line(" launch complete."))
        # the prefix may come after other text (a log's own decoration)
        self.assertEqual(windows_log.parse_probe_line("[12:01] PTPROBE x"), {"type": "x"})

    def test_lines_become_events_and_state(self):
        state = {}
        lines = ["PTPROBE screen to=WORLD", "PTPROBE state day=3 tick=40 player.x=1", "PTPROBE state player.z=2",
                 "rgl_post_warning_line: get_skeleton_anim failed for: x", "SCRIPT ERROR ON OPCODE 1700: bad",
                 "PTPROBE town_entered name=Praven"]
        errors = windows_log.compile_patterns(["SCRIPT ERROR", "(?i)^\\s*error\\b", "[unclosed"])
        events, changed = windows_log.process_lines(lines, "PTPROBE", errors, state, 1000)
        self.assertTrue(changed)
        self.assertEqual(state, {"screen": "WORLD", "day": 3, "tick": 40, "player": {"x": 1, "z": 2}})
        self.assertEqual([e["type"] for e in events], ["screen", "log_error", "town_entered"])
        self.assertEqual(events[0], {"type": "screen", "to": "WORLD", "from": None, "tick": 0, "wallTimeMs": 1000})
        self.assertEqual(events[1]["line"], "SCRIPT ERROR ON OPCODE 1700: bad")
        self.assertEqual(events[2]["tick"], 40)
        finished = windows_log.finish_state(state, 5)
        self.assertEqual((finished["wallTimeMs"], finished["version"], finished["world"]), (5, "unknown", False))

    def test_a_partial_last_line_waits(self):
        self.assertEqual(windows_log.complete_lines(b"a\r\nb\nc"), ([b"a", b"b"], 5))
        self.assertEqual(windows_log.complete_lines(b"partial"), ([], 0))
        self.assertEqual(windows_log.decode(b"caf\xe9"), "caf\u00e9")

    def test_sync_reads_new_lines_once_and_restarts_on_a_new_log(self):
        with tempfile.TemporaryDirectory() as root:
            session = Session("s01", root)
            os.makedirs(session.dir)
            log = os.path.join(root, "rgl_log.txt")
            with open(session.path("session.json"), "w") as f:
                json.dump({"driver": "windows", "logPath": log}, f)
            with open(session.path("profile.json"), "w") as f:
                json.dump({"name": "w", "windows": {"log_error_patterns": ["SCRIPT ERROR"]}}, f)
            self.assertEqual(windows_log.sync(session), 0)  # no log yet
            with open(log, "wb") as f:
                f.write(b"Starting new log file.\r\n Module_name =  TestModule \r\nPTPROBE screen to=MAP\r\nhalf")
            self.assertEqual(windows_log.sync(session), 3)
            self.assertEqual(windows_log.sync(session), 0)
            with open(log, "ab") as f:
                f.write(b" a line\r\nSCRIPT ERROR x\r\n")
            self.assertEqual(windows_log.sync(session), 2)
            with open(session.path("game.log")) as f:
                self.assertIn("half a line\n", f.read())
            events = read_jsonl(session.path("out", "events.jsonl"))
            self.assertEqual([e["type"] for e in events], ["screen", "log_error"])
            self.assertEqual(read_json(session.path("out", "state.json"))["screen"], "MAP")
            with open(log, "wb") as f:  # the game started a new, shorter log
                f.write(b"PTPROBE screen to=TITLE\n")
            self.assertEqual(windows_log.sync(session), 1)
            self.assertEqual(read_json(session.path("out", "state.json"))["screen"], "TITLE")
            self.assertEqual(windows_log.module_from_log(log), None)

    def test_the_module_is_read_from_the_log_header(self):
        with tempfile.NamedTemporaryFile("wb", suffix=".txt", delete=False) as f:
            f.write(b"Starting new log file.\r\n Processing Ini File {\r\n Module_name =  TestModule \r\n")
        try:
            self.assertEqual(windows_log.module_from_log(f.name), "TestModule")
        finally:
            os.unlink(f.name)


class ProfileTest(unittest.TestCase):
    def test_the_warband_profile(self):
        p = profiles.load("warband")
        self.assertEqual(p["driver"], "windows")
        self.assertEqual(p["windows"]["process"], "mb_warband")
        self.assertIsNone(p["probe"])
        self.assertIn("click", profiles.agent_notes(p).lower())
        steam = "/mnt/c/Program Files (x86)/Steam/steamapps/common/MountBlade Warband"
        win = windows_session.settings(p, steam, "/runs/r/s01", "TestModule")
        self.assertEqual(win["log"], steam + "/rgl_log.txt")
        self.assertEqual(win["registry"][0]["value"], "TestModule")
        self.assertEqual(windows_session.settings(p, steam, "/s", None)["registry"][0]["value"], "Native")
        plan = profiles.launch_plan(p, steam, "/runs/r/s01", 1280, 720, None, [], False)
        self.assertEqual(plan["command"], [steam + "/mb_warband.exe"])
        self.assertEqual(windows_driver.windows_path(plan["command"][0]),
                         "C:\\Program Files (x86)\\Steam\\steamapps\\common\\MountBlade Warband\\mb_warband.exe")

    def test_the_prompt_says_the_session_drives_the_real_desktop(self):
        from playtester.agents.prompt import fill
        text = fill(profiles.load("warband"), "g", "s01", "/r", None, start_args="--attach")
        self.assertIn("running on this machine's Windows desktop", text)
        self.assertIn("starts the game on the Windows desktop", text)
        self.assertIn("--attach", text)
        self.assertNotIn("virtual display; prints", text)
        self.assertIn("virtual display; prints", fill(profiles.load("demo"), "g", "s01", "/r", None))

    def test_a_windows_profile_needs_a_window_title_and_known_fields(self):
        base = {"name": "w", "title": "W", "description": "d", "driver": "windows",
                "launch": {"command": ["{game_dir}/g.exe"]}, "windows": {"process": "g"}}
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "w.json")
            with open(path, "w") as f:
                json.dump(dict(base, window={}), f)
            with self.assertRaises(profiles.ProfileError) as e:
                profiles.load(path)
            self.assertIn("title_regex", str(e.exception))
            with open(path, "w") as f:
                json.dump(dict(base, window={"title_regex": "W"}, windows={"process": "g", "nope": 1}), f)
            with self.assertRaises(profiles.ProfileError):
                profiles.load(path)
            with open(path, "w") as f:
                json.dump(dict(base, window={"title_regex": "W"},
                               windows={"process": "g", "registry": [{"key": "Software\\X", "name": "n", "value": "v"}]}), f)
            with self.assertRaises(profiles.ProfileError):
                profiles.load(path)


def pt(env, *args, timeout=60):
    return subprocess.run([sys.executable, "-m", "playtester"] + list(args), env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, universal_newlines=True, timeout=timeout)


class FakeDesktopSessionTest(unittest.TestCase):
    """Whole sessions: pt start/shot/key/click/events/stop through the relay and a stand-in helper."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.game = os.path.join(self.dir, "game")
        os.makedirs(self.game)
        open(os.path.join(self.game, "fake.exe"), "w").close()
        self.log = os.path.join(self.game, "game_log.txt")
        self.helper_log = os.path.join(self.dir, "helper.jsonl")
        profile = {
            "name": "fake-windows", "title": "Fake", "description": "a pretend Windows game", "driver": "windows",
            "windows": {"process": "fake", "min_width": 1024, "module": "Native", "log": "{game_dir}/game_log.txt",
                        "log_error_patterns": ["SCRIPT ERROR"], "close_timeout_sec": 2,
                        "registry": [{"key": "HKCU\\Software\\Fake", "name": "last_module", "value": "{module}"}]},
            "launch": {"command": ["{game_dir}/fake.exe"], "cwd": "{game_dir}", "start_timeout_sec": 20},
            "window": {"title_regex": "^Fake", "width": 1280, "height": 720},
        }
        self.profile = os.path.join(self.dir, "fake-windows.json")
        with open(self.profile, "w") as f:
            json.dump(profile, f)
        self.env = dict(os.environ, PT_ROOT=os.path.join(self.dir, "runs"), PYTHONPATH=SRC,
                        PT_WINDOWS_LOCK=os.path.join(self.dir, "desktop.lock"),
                        PT_WINDOWS_HELPER=json.dumps([sys.executable, FAKE_HELPER, "{port}", "{token}"]),
                        PT_POWERSHELL="powershell.exe", FAKE_WIN_LOG=self.helper_log,
                        FAKE_WIN_REGISTRY=json.dumps({"HKCU:\\Software\\Fake\\last_module": "Other"}))
        self.env.pop("PT_MODULE", None)

    def tearDown(self):
        import shutil
        for name in ("s01", "s02"):
            pt(dict(self.env, PT_SESSION=name), "stop")
        shutil.rmtree(self.dir, ignore_errors=True)

    def ops(self, op):
        try:
            return [r for r in read_jsonl(self.helper_log) if r["op"] == op]
        except OSError:
            return []

    def test_attach_drives_the_running_copy_and_stop_leaves_it_running(self):
        env = dict(self.env, PT_SESSION="s01", FAKE_WIN_RUNNING="999")
        with open(self.log, "w") as f:
            f.write("old line from before the session\nPTPROBE screen to=OLD\n")
        r = pt(env, "start", "--profile", self.profile, "--game-dir", self.game, "--attach")
        self.assertEqual(r.returncode, 0, r.stderr)
        info = json.loads(r.stdout)
        self.assertEqual((info["driver"], info["attached"], info["gamePid"], info["hwnd"]), ("windows", True, 999, 77))
        self.assertEqual(self.ops("launch"), [])
        self.assertEqual(self.ops("regset"), [])  # attaching changes nothing
        self.assertTrue(os.path.exists(os.path.join(self.dir, "desktop.lock")))

        # a second session may not drive the desktop meanwhile
        r2 = pt(dict(env, PT_SESSION="s02"), "start", "--profile", self.profile, "--game-dir", self.game, "--attach")
        self.assertEqual(r2.returncode, 1)
        self.assertIn("being driven by session s01", r2.stderr)

        r = pt(env, "shot", "first")
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(r.stdout.strip(), "rb") as f:
            head = f.read(24)
        self.assertEqual(head[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(self.ops("shot")[-1]["width"], 1280)
        self.assertEqual(self.ops("shot")[-1]["rect"], [0, 0, 1920, 1080])

        self.assertEqual(pt(env, "key", "i", "Shift_L+Up").returncode, 0)
        keys = self.ops("key")
        self.assertEqual(keys[0], {"op": "key", "keys": [[0x17, False]], "up": False})
        self.assertEqual(keys[1]["up"], True)
        self.assertEqual(keys[2]["keys"], [[0x2A, False], [0x48, True]])
        r = pt(env, "key", "Hyper_Q")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no scancode", r.stderr)

        self.assertEqual(pt(env, "click", "640", "700").returncode, 0)
        self.assertEqual(self.ops("move")[-1], {"op": "move", "x": 960, "y": 1050})
        self.assertEqual([b["up"] for b in self.ops("button")], [False, True])
        self.assertEqual(pt(env, "scroll", "2").returncode, 0)
        self.assertEqual([w["amount"] for w in self.ops("wheel")], [-120, -120])
        self.assertEqual(pt(env, "drag", "10", "10", "20", "20", "0.1", "1").returncode, 0)
        self.assertGreaterEqual(len(self.ops("focus")), 5)  # every command brings the game to the front

        # only what the game logs after the start counts
        with open(self.log, "a") as f:
            f.write("PTPROBE screen to=WORLD\nSCRIPT ERROR ON OPCODE 1\nPTPROBE state day=2\n")
        r = pt(env, "events")
        events = [json.loads(l) for l in r.stdout.splitlines()]
        self.assertEqual([e["type"] for e in events], ["screen", "log_error"])
        r = pt(env, "state")
        self.assertEqual(json.loads(r.stdout)["screen"], "WORLD")
        self.assertEqual(json.loads(r.stdout)["day"], 2)
        self.assertIn("SCRIPT ERROR", pt(env, "log").stdout)
        self.assertNotIn("old line", pt(env, "log").stdout)

        status = json.loads(pt(env, "status").stdout)
        self.assertTrue(status["running"])
        self.assertEqual(status["lock"]["session"], "s01")

        r = pt(env, "stop")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.ops("close"), [])
        self.assertEqual(self.ops("kill"), [])
        self.assertFalse(os.path.exists(os.path.join(self.dir, "desktop.lock")))
        self.assertEqual(pt(env, "shot", "after").returncode, 1)

    def test_launch_sets_the_module_and_stop_closes_the_game_and_puts_it_back(self):
        env = dict(self.env, PT_SESSION="s01")
        with open(self.log, "w") as f:
            f.write("a log from the last time the game ran\n")
        r = pt(env, "start", "--profile", self.profile, "--game-dir", self.game, "--module", "TestModule")
        self.assertEqual(r.returncode, 0, r.stderr)
        info = json.loads(r.stdout)
        self.assertEqual((info["attached"], info["gamePid"]), (False, 4242))
        self.assertEqual(self.ops("regset"), [{"op": "regset", "key": "HKCU:\\Software\\Fake", "name": "last_module",
                                               "value": "TestModule"}])
        policy = self.ops("policy")[0]
        self.assertEqual(policy["registry"], ["HKCU:\\Software\\Fake"])
        self.assertTrue(policy["exe"].endswith("fake.exe"))
        self.assertEqual(policy["shotDir"], windows_driver.windows_path(os.path.join(self.dir, "runs", "s01")))
        launch = self.ops("launch")[0]
        self.assertTrue(launch["path"].endswith("fake.exe"))
        self.assertEqual(launch["args"], [])
        # the old log was moved into the session, so nothing in it counts
        self.assertFalse(os.path.exists(self.log))
        session_dir = os.path.join(self.dir, "runs", "s01")
        self.assertTrue(os.path.exists(os.path.join(session_dir, "log-before-start.txt")))

        r = pt(env, "stop")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.ops("close")), 1)
        self.assertEqual(self.ops("regset")[-1]["value"], "Other")
        self.assertFalse(os.path.exists(os.path.join(self.dir, "desktop.lock")))

    def test_launching_refuses_when_the_game_already_runs(self):
        env = dict(self.env, PT_SESSION="s01", FAKE_WIN_RUNNING="999")
        r = pt(env, "start", "--profile", self.profile, "--game-dir", self.game)
        self.assertEqual(r.returncode, 1)
        self.assertIn("already running", r.stderr)
        self.assertIn("--attach", r.stderr)
        self.assertEqual(self.ops("close"), [])
        self.assertFalse(os.path.exists(os.path.join(self.dir, "desktop.lock")))

    def test_attach_and_module_need_the_windows_driver(self):
        r = pt(dict(self.env, PT_SESSION="s01"), "start", "--profile", "demo", "--attach")
        self.assertEqual(r.returncode, 1)
        self.assertIn("windows", r.stderr)


if __name__ == "__main__":
    unittest.main()
