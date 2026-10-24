"""pt aggregate and the report validator, over a three-session fixture run."""

import copy
import json
import os
import shutil
import tempfile
import unittest

from tests.helpers import FIXTURE_RUN  # noqa: F401  (puts src on sys.path)
from playtester.agents import aggregate
from playtester.agents.report import check_report, unanswered
from playtester.schema import load_schema, validate

SCHEMA = load_schema("report.schema.json")
with open(os.path.join(FIXTURE_RUN, "s01", "report.json"), encoding="utf-8") as f:
    GOOD = json.load(f)


def run_fixture():
    tmp = tempfile.mkdtemp(prefix="pt-aggregate-test-")
    try:
        run = os.path.join(tmp, "run")
        shutil.copytree(FIXTURE_RUN, run)
        summary = aggregate.aggregate(run)
        with open(os.path.join(run, "summary.md"), encoding="utf-8") as f:
            markdown = f.read()
        with open(os.path.join(run, "summary.json"), encoding="utf-8") as f:
            on_disk = json.load(f)
    finally:
        shutil.rmtree(tmp)
    return summary, markdown, on_disk


class AggregateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary, cls.markdown, cls.on_disk = run_fixture()

    def test_every_session_is_listed_with_its_outcome(self):
        outcomes = {s["session"]: s["outcome"] for s in self.summary["sessions"]}
        self.assertEqual(outcomes, {"s01": "achieved", "s02": "partial", "s03": "no report"})
        self.assertEqual(self.on_disk["sessions"][0]["session"], "s01")
        self.assertIn("| s01 | Play the first 10 minutes as a new player | achieved |", self.markdown)

    def test_near_duplicate_findings_from_different_agents_are_one_group(self):
        season = [g for g in self.summary["findings"] if "season panel" in g["title"].lower()]
        self.assertEqual(len(season), 1, [g["title"] for g in self.summary["findings"]])
        self.assertEqual(season[0]["sessions"], ["s01", "s02"])
        self.assertEqual(season[0]["severity"], "minor", "a group takes its most severe report")
        self.assertEqual(len(season[0]["screenshots"]), 2)
        self.assertIn("s01/shots/season-clipped.png", self.markdown)
        self.assertEqual(len(self.summary["findings"]), 4, [g["title"] for g in self.summary["findings"]])

    def test_severity_counts_and_order(self):
        self.assertEqual(self.summary["severityCounts"], {"blocker": 1, "major": 1, "minor": 2, "polish": 1})
        severities = [g["severity"] for g in self.summary["findings"]]
        self.assertEqual(severities, sorted(severities, key=aggregate.SEVERITIES.index))

    def test_a_crash_in_the_game_log_becomes_a_blocker_and_a_problem(self):
        crash = self.summary["findings"][0]
        self.assertEqual((crash["severity"], crash["categories"], crash["sessions"]), ("blocker", ["crash"], ["s03"]))
        self.assertIn("s03: report.json missing", self.summary["problems"])
        self.assertTrue(any("game crashed" in p for p in self.summary["problems"]), self.summary["problems"])

    def test_objective_timings_come_from_events_in_game_time(self):
        rows = {r["title"]: r for r in self.summary["objectiveTimings"]}
        wood = rows["Gather wood"]
        # 2200 and 3000 ticks at the profile's 50 a second
        self.assertEqual(wood["seconds"], {"s01": 44.0, "s02": 60.0})
        self.assertEqual((wood["min"], wood["median"], wood["max"]), (44.0, 52.0, 60.0))
        self.assertEqual(rows["Gather stone"]["seconds"], {"s01": 104.0})
        sessions = {s["session"]: s["derived"] for s in self.summary["sessions"]}
        self.assertEqual(sessions["s01"]["progressReached"], "Village")
        self.assertEqual(sessions["s01"]["objectivesCompleted"], 2)
        self.assertEqual((sessions["s02"]["deaths"], sessions["s02"]["saves"]), (1, 1))
        self.assertIn("| 1 | Gather wood | 44 | 60 | - | 44 | 52 | 60 |", self.markdown)
        s01_wood = [o for o in sessions["s01"]["objectives"] if o["title"] == "Gather wood"][0]
        self.assertEqual(s01_wood["wallSeconds"], 60.0)

    def test_the_progress_column_appears_when_a_game_reports_progress(self):
        self.assertIn("| Reached |", self.markdown)


class EvidenceLayoutTest(unittest.TestCase):
    def test_committed_evidence_with_flat_events_and_no_profile(self):
        # Evidence committed to a game's repository keeps events.jsonl beside
        # the report and may predate session.json naming a profile.
        tmp = tempfile.mkdtemp(prefix="pt-evidence-test-")
        try:
            run = os.path.join(tmp, "0.5.0")
            shutil.copytree(FIXTURE_RUN, run)
            for name in ("s01", "s02", "s03"):
                d = os.path.join(run, name)
                shutil.move(os.path.join(d, "out", "events.jsonl"), os.path.join(d, "events.jsonl"))
                shutil.rmtree(os.path.join(d, "out"))
                with open(os.path.join(d, "session.json"), encoding="utf-8") as f:
                    info = json.load(f)
                for key in ("profile", "ticksPerSecond"):
                    info.pop(key, None)
                with open(os.path.join(d, "session.json"), "w", encoding="utf-8") as f:
                    json.dump(info, f)
            without = aggregate.aggregate(run)
            wood = [r for r in without["objectiveTimings"] if r["title"] == "Gather wood"][0]
            self.assertEqual(wood["seconds"], {}, "no ticks per second known, so no game time")
            with_profile = aggregate.aggregate(run, default_profile="beyond-nations")
            wood = [r for r in with_profile["objectiveTimings"] if r["title"] == "Gather wood"][0]
            self.assertEqual(wood["seconds"], {"s01": 44.0, "s02": 60.0})
            self.assertTrue(any("game crashed" in p for p in with_profile["problems"]))
        finally:
            shutil.rmtree(tmp)


QUESTIONS = ["What was the game about?", "Did anything feel preachy?"]


class AnswersTest(unittest.TestCase):
    """A profile's questions: answers are gathered by question; a missing one is a problem."""

    @classmethod
    def setUpClass(cls):
        tmp = tempfile.mkdtemp(prefix="pt-answers-test-")
        try:
            run = os.path.join(tmp, "run")
            shutil.copytree(FIXTURE_RUN, run)
            profile = dict(aggregate._bundled_profile("beyond-nations"), questions=QUESTIONS)
            for name in ("s01", "s02", "s03"):
                with open(os.path.join(run, name, "profile.json"), "w", encoding="utf-8") as f:
                    json.dump(profile, f)
            answers = {
                "s01": [{"question": QUESTIONS[0], "answer": "Building a village | through the seasons."},
                        {"question": QUESTIONS[1], "answer": "No."}],
                # the second question copied with different case and spacing, the first missing
                "s02": [{"question": "  did anything feel PREACHY? ", "answer": "The chronicle, a little."}],
            }
            for name, given in answers.items():
                path = os.path.join(run, name, "report.json")
                with open(path, encoding="utf-8") as f:
                    report = json.load(f)
                report["answers"] = given
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(report, f)
            cls.summary = aggregate.aggregate(run)
            with open(os.path.join(run, "summary.md"), encoding="utf-8") as f:
                cls.markdown = f.read()
        finally:
            shutil.rmtree(tmp)

    def test_answers_are_grouped_under_each_question_in_the_profiles_order(self):
        by_q = [(q["question"], [(a["session"], a["answer"]) for a in q["answers"]]) for q in self.summary["answers"]]
        self.assertEqual(by_q, [
            (QUESTIONS[0], [("s01", "Building a village | through the seasons."), ("s02", None), ("s03", None)]),
            (QUESTIONS[1], [("s01", "No."), ("s02", "The chronicle, a little."), ("s03", None)]),
        ])

    def test_the_summary_shows_them_before_the_findings(self):
        self.assertIn("## Answers", self.markdown)
        self.assertLess(self.markdown.index("## Answers"), self.markdown.index("## Findings"))
        self.assertIn("### Q1. What was the game about?", self.markdown)
        self.assertIn("- **s01:** Building a village \\| through the seasons.", self.markdown)
        self.assertIn("- **s02:** *(no answer)*", self.markdown)

    def test_a_missing_answer_is_a_problem_and_makes_the_report_invalid(self):
        self.assertIn("s02: report.json $.answers: no answer to question 1: What was the game about?",
                      self.summary["problems"])
        valid = {s["session"]: s["reportValid"] for s in self.summary["sessions"]}
        self.assertEqual(valid, {"s01": True, "s02": False, "s03": False})

    def test_a_run_without_questions_has_no_answers_section(self):
        summary, markdown, _ = run_fixture()
        self.assertEqual(summary["answers"], [])
        self.assertNotIn("## Answers", markdown)


class GroupingTest(unittest.TestCase):
    def similar(self, a, b):
        n = aggregate.normalise_title
        return aggregate.similarity(n(a), n(b)) >= aggregate.SIMILAR

    def test_wording_not_order(self):
        self.assertTrue(self.similar("Season panel clipped at right edge", "The season panel is clipped at the right edge"))
        self.assertFalse(self.similar("Season panel clipped at right edge", "Pawn blocks chopping a tree"))

    def test_sizes_and_word_endings_are_ignored(self):
        n = aggregate.normalise_title
        self.assertEqual(set(n("Chronicle strip truncates lines at 1280x720").split()),
                         set(n("Chronicle line truncated in strip").split()))

    def test_near_duplicates_a_real_run_missed(self):
        # Pairs reported by different agents in one real ten-agent run, which
        # the first grouping (character ratio and word overlap only) kept apart.
        pairs = [
            ("Pawns walking around the player's own settlement can't be talked to, gifted or invited (E/G/R say nobody is in reach)",
             "Members of your own nation near your settlement can't be gifted or invited, so the heir can't be influenced"),
            ("Settlement command bar buttons change order between visits, causing a wrong build",
             "Settlement command bar reflows under the cursor, so clicks land on the wrong button"),
            ("After H (Teleport Home) the bar shows 'Enter Settlement' but E says 'No entities within range'",
             "Teleport home (H) lands 9m from the settlement centre, out of enter range; 'Enter Settlement' button still offered"),
        ]
        for a, b in pairs:
            self.assertTrue(self.similar(a, b), (a, b))

    def test_unrelated_findings_that_share_a_word_or_two_stay_apart(self):
        apart = [
            ("Nations screen (O) shows only the first ~7-8 nations, oldest first, with no scrolling",
             "No UI shows who your members are or who the heir would be"),
            ("Market prices swing wildly within a minute (apples 54 -> 32 -> 13)",
             "Market selling is one unit per click with no receipt; apples and saplings never sold"),
            ("Chronicle lines truncated with '...', including the player's own nation name",
             "Objective progress bar label is clipped: 'nbers 6/10'"),
        ]
        for a, b in apart:
            self.assertFalse(self.similar(a, b), (a, b))


class ReportTest(unittest.TestCase):
    def test_the_fixture_reports_are_valid(self):
        for name in ("s01", "s02"):
            path = os.path.join(FIXTURE_RUN, name, "report.json")
            with open(path, encoding="utf-8") as f:
                self.assertEqual(check_report(json.load(f), SCHEMA, os.path.dirname(path)), [], name)

    def test_the_validator_names_what_is_wrong(self):
        bad = copy.deepcopy(GOOD)
        del bad["verdict"]
        bad["outcome"] = "won"
        bad["fun"] = 6
        bad["findings"][0]["severity"] = "critical"
        bad["findings"][1]["tick"] = "soon"
        bad["surprise"] = True
        joined = "\n".join(validate(bad, SCHEMA))
        for expected in ("missing required 'verdict'", "$.outcome: 'won' is not one of", "$.fun: 6 is above 5",
                         "$.findings[0].severity: 'critical'", "$.findings[1].tick: expected integer or null",
                         "$.surprise: unexpected property"):
            self.assertIn(expected, joined)

    def test_a_screenshot_that_does_not_exist_is_reported(self):
        bad = copy.deepcopy(GOOD)
        bad["findings"][0]["screenshot"] = "shots/nope.png"
        self.assertEqual(check_report(bad, SCHEMA, os.path.join(FIXTURE_RUN, "s01")),
                         ["$.findings[0].screenshot: no such file shots/nope.png"])

    def test_booleans_are_not_integers(self):
        bad = copy.deepcopy(GOOD)
        bad["fun"] = True
        self.assertEqual(validate(bad, SCHEMA), ["$.fun: expected integer, got bool"])

    def test_answers_are_checked_against_the_questions(self):
        ok = copy.deepcopy(GOOD)
        ok["answers"] = [{"question": "Q one?", "answer": "A."}, {"question": "Q two?", "answer": "  "}]
        self.assertEqual(validate(ok, SCHEMA), [])
        self.assertEqual(unanswered(ok, ["Q one?", "Q two?", "Q three?"]),
                         ["$.answers: no answer to question 2: Q two?", "$.answers: no answer to question 3: Q three?"])
        self.assertEqual(unanswered(GOOD, []), [])
        bad = copy.deepcopy(GOOD)
        bad["answers"] = [{"question": "Q?"}]
        self.assertEqual(validate(bad, SCHEMA), ["$.answers[0]: missing required 'answer'"])

    def test_a_game_without_a_probe_may_report_no_version_or_seed(self):
        ok = copy.deepcopy(GOOD)
        ok["build"]["version"] = None
        ok["seed"] = None
        self.assertEqual(validate(ok, SCHEMA), [])


if __name__ == "__main__":
    unittest.main()
