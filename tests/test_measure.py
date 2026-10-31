"""pt measure: /proc readers and the result it prints (no display needed: sessions are mocked)."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

import tests.helpers  # noqa: F401  (puts src on sys.path)
from playtester.harness import measure

LINUX = os.path.isdir("/proc/self")

# /proc/<pid>/stat with a ")" inside the command name; utime=17, stime=25
STAT = "4242 (odd) name) S 1 2 3 4 5 6 7 8 9 10 17 25 0 0 20 0 1 0\n"


def fake_open(text):
    return mock.patch.object(measure, "open", mock.mock_open(read_data=text), create=True)


class ProcReadersTest(unittest.TestCase):
    def test_cpu_ticks_is_utime_plus_stime_after_the_last_paren(self):
        with fake_open(STAT):
            self.assertEqual(measure.cpu_ticks(4242), 42)

    def test_cpu_ticks_of_no_pid_or_a_gone_one_is_none(self):
        self.assertIsNone(measure.cpu_ticks(None))
        with mock.patch.object(measure, "open", side_effect=FileNotFoundError, create=True):
            self.assertIsNone(measure.cpu_ticks(4242))
        with fake_open("4242 (truncated"):
            self.assertIsNone(measure.cpu_ticks(4242))

    def test_rss_mb_reads_vmrss_in_kib(self):
        with fake_open("Name:\tgame\nVmPeak:\t9999 kB\nVmRSS:\t2048 kB\n"):
            self.assertEqual(measure.rss_mb(4242), 2.0)

    def test_rss_mb_without_vmrss_or_pid_is_none(self):
        with fake_open("Name:\tzombie\n"):
            self.assertIsNone(measure.rss_mb(4242))
        self.assertIsNone(measure.rss_mb(None))

    def test_mem_available_mb(self):
        with fake_open("MemTotal: 8388608 kB\nMemAvailable: 1048576 kB\n"):
            self.assertEqual(measure.mem_available_mb(), 1024.0)
        with fake_open("MemTotal: 8388608 kB\n"):
            self.assertIsNone(measure.mem_available_mb())

    @unittest.skipUnless(LINUX, "needs /proc")
    def test_the_real_proc_of_this_process(self):
        self.assertIsInstance(measure.cpu_ticks(os.getpid()), int)
        self.assertGreater(measure.rss_mb(os.getpid()), 0)
        self.assertGreater(measure.mem_available_mb(), 0)


class MeasureMainTest(unittest.TestCase):
    """main() with Popen, Session and the /proc readers replaced."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"PT_ROOT": self.tmp.name})
        self.env.start()
        for key in ("PT_WIDTH", "PT_HEIGHT", "PT_LP_THREADS", "PT_PROFILE"):
            os.environ.pop(key, None)
        self.started = []
        self.stopped = []
        self.roots = set()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def run_main(self, args, fail=(), states=None, dead=()):
        """Runs measure.main; sessions in fail don't start, those in dead have no game pid."""
        test = self
        states = states or {}
        names = ["m%02d" % i for i in range(1, int(args[0]) + 1)]
        game_pid = {name: 1000 + i for i, name in enumerate(names)}
        xvfb_pid = {name: 2000 + i for i, name in enumerate(names)}
        window = float(args[2])
        # per pid, the ticks at the first and the second sample: game 0.5 cores, Xvfb 0.1
        ticks = {}
        for name in names:
            ticks[game_pid[name]] = iter([1000, 1000 + int(0.5 * measure.TICK * window)])
            ticks[xvfb_pid[name]] = iter([50, 50 + int(0.1 * measure.TICK * window)])

        class FakePopen:
            def __init__(self, cmd, env=None, **kwargs):
                self.name = env["PT_SESSION"]
                test.roots.add(env["PT_ROOT"])
                test.started.append((self.name, cmd))
                self.returncode = 1 if self.name in fail else 0
                if self.name in states:
                    out = os.path.join(env["PT_ROOT"], self.name, "out")
                    os.makedirs(out)
                    with open(os.path.join(out, "state.json"), "w") as f:
                        json.dump(states[self.name], f)

            def communicate(self):
                return ("boom from %s" % self.name if self.returncode else "", None)

        class FakeSession:
            def __init__(self, name, root):
                self.name = name

            def _pid(self, kind):
                if kind == "game":
                    return None if self.name in dead else game_pid[self.name]
                return xvfb_pid[self.name]

            def stop(self):
                test.stopped.append(self.name)

        def cpu_ticks(pid):
            return next(ticks[pid]) if pid in ticks else None

        def rss_mb(pid):
            if pid is None:
                return None
            return 100.0 if pid < 2000 else 20.0

        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(measure.subprocess, "Popen", FakePopen), \
                mock.patch.object(measure, "Session", FakeSession), \
                mock.patch.object(measure, "cpu_ticks", cpu_ticks), \
                mock.patch.object(measure, "rss_mb", rss_mb), \
                mock.patch.object(measure, "mem_available_mb", side_effect=[1000.0, 700.0]), \
                mock.patch.object(measure.os, "getloadavg", return_value=(1.23, 0.0, 0.0)), \
                mock.patch.object(measure.time, "sleep"), \
                redirect_stdout(out), redirect_stderr(err):
            code = measure.main(["--profile", "demo"] + list(args))
        return code, out.getvalue(), err.getvalue()

    def test_no_arguments_prints_usage(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(measure.main([]), 2)
        self.assertIn("pt measure N", out.getvalue())

    def test_the_result_summarises_the_sessions_that_started(self):
        states = {"m01": {"fps": 60, "tps": 30, "screen": "WORLD"},
                  "m02": {"fps": 50, "tps": 29, "screen": "WORLD"},
                  "m03": {"fps": 1, "tps": 1}}
        code, out, err = self.run_main(["3", "0", "10"], fail={"m03"}, states=states)
        self.assertEqual(code, 0)
        self.assertIn("start failed for m03", err)
        self.assertIn("boom from m03", err)
        result = json.loads(out)
        self.assertEqual((result["profile"], result["sessions"], result["started"]), ("demo", 3, 2))
        self.assertEqual([r["session"] for r in result["rows"]], ["m01", "m02"])
        row = result["rows"][0]
        self.assertEqual((row["gameCpuCores"], row["xvfbCpuCores"]), (0.5, 0.1))
        self.assertEqual((row["gameRssMb"], row["xvfbRssMb"]), (100.0, 20.0))
        self.assertEqual((row["fps"], row["tps"], row["screen"]), (60, 30, "WORLD"))
        self.assertEqual(result["totalCpuCores"], 1.2)
        self.assertEqual(result["perSessionCpuCores"], 0.6)
        self.assertEqual(result["perSessionRssMb"], 120)
        self.assertEqual(result["memUsedMb"], 300)
        self.assertEqual((result["fpsMin"], result["fpsMedian"], result["fpsMax"], result["tpsMin"]), (50, 55, 60, 29))
        self.assertEqual((result["size"], result["lpThreads"], result["loadBefore"]), ("640x360", 2, 1.2))

    def test_each_session_gets_its_own_seed_in_one_fresh_root(self):
        self.run_main(["3", "0", "10"])
        self.assertEqual([name for name, _ in self.started], ["m01", "m02", "m03"])
        for i, (_, cmd) in enumerate(self.started):
            self.assertEqual(cmd[cmd.index("--seed") + 1], str(100 + i))
            self.assertTrue(cmd[cmd.index("--profile") + 1].endswith("demo.json"))
        self.assertEqual(len(self.roots), 1)
        root = self.roots.pop()
        self.assertEqual(os.path.dirname(root), self.tmp.name)
        self.assertTrue(os.path.basename(root).startswith("measure-3-"))

    def test_every_session_is_stopped_even_one_that_failed_to_start(self):
        self.run_main(["3", "0", "10"], fail={"m02"})
        self.assertEqual(self.stopped, ["m01", "m02", "m03"])

    def test_sessions_are_stopped_when_sampling_raises(self):
        with mock.patch.object(measure.statistics, "mean", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_main(["2", "0", "10"])
        self.assertEqual(self.stopped, ["m01", "m02"])

    def test_a_session_without_a_game_pid_has_no_cpu_figure(self):
        code, out, _ = self.run_main(["2", "0", "10"], dead={"m02"})
        self.assertEqual(code, 0)
        result = json.loads(out)
        self.assertIsNone(result["rows"][1]["gameCpuCores"])
        self.assertEqual(result["rows"][1]["gameRssMb"], 0)
        self.assertEqual(result["totalCpuCores"], 0.6)
        self.assertIsNone(result["fpsMin"])

    def test_size_and_threads_come_from_the_environment(self):
        os.environ.update({"PT_WIDTH": "800", "PT_HEIGHT": "450", "PT_LP_THREADS": "4"})
        _, out, _ = self.run_main(["1", "0", "10"])
        result = json.loads(out)
        self.assertEqual((result["size"], result["lpThreads"]), ("800x450", "4"))

    def test_brief_prints_one_line_without_rows(self):
        _, out, _ = self.run_main(["2", "0", "10", "--brief"])
        self.assertEqual(len(out.strip().splitlines()), 1)
        self.assertNotIn("rows", json.loads(out))


if __name__ == "__main__":
    unittest.main()
