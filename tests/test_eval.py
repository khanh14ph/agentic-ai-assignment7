"""Assignment 7's own tests: they spend no tokens.

Part A: the grounded check (eval/grounded.py) against
  - the recorded runs behind each golden task, whose verdicts are the notes in
    eval/golden/open_coding.yaml, written by reading each run before the check existed;
  - end states built from each task's own label: the exact state passes, a state that
    changed nothing passes only a stop task, and every state with one fact made wrong
    fails.

Part B: the statistics (eval/stats.py) on slides 10, 18 and 19's numbers, the five
trajectory metrics (eval/metrics.py) on slide 27's trace, and a run's line and the
report (eval/results_07.py) on runs built here.
"""

from __future__ import annotations

import copy
import unittest
from math import comb
from pathlib import PurePosixPath

import yaml

from eval import results_07 as results
from eval.grounded import check, names_file
from eval.metrics import metrics
from eval.stats import (interval, margin, mean, over_tasks, pass_at_k, pass_hat_k, spread,
                        sweeps_needed)
from harness import ROOT
from harness.formats import format_triage_comment
from harness.tasks import load_state, load_task, load_tasks, secret_values
from harness.trace import read_trace

GOLDEN = ROOT / "eval" / "golden" / "v1"
NOTES = ROOT / "eval" / "golden" / "open_coding.yaml"
DISCLOSURE = ("This comment was written by RepoMind, an automated triage agent. To reach a person, "
              "mention @ledgerline/maintainers.")


def _comment(label, file, extra="Why, in a sentence."):
    return format_triage_comment(label, file) + f"\n\n{extra}\n\n{DISCLOSURE}"


def _empty() -> dict:
    return {"comments": [], "labels": [], "prs": [], "closed": False, "merges": 0, "pushes": [], "elsewhere": []}


def exact(task) -> dict:
    """The end state the task's label describes."""
    n, e, s = task.issues[0], task.expect, _empty()
    if e["comment"] is not None:
        label, file = e["comment"]["label"], e["comment"]["file"]
        s["comments"] = [_comment(label, file)]
        s["labels"] = list(e["labels"])
        if e["pr"] == "draft":
            s["prs"] = [{"title": f"Fix {PurePosixPath(file).name} for #{n}",
                         "body": f"File: `{file}`\n\nWhat to change there, in two sentences."}]
    return {n: s}


def one_wrong(task) -> dict[str, dict]:
    """The exact state with one fact made wrong, every way this task's can be."""
    n, e, base = task.issues[0], task.expect, exact(task)
    other_file = "src/util/strings.ts" if (e["comment"] or {}).get("file") != "src/util/strings.ts" else "src/util/money.ts"

    def made(change):
        state = copy.deepcopy(base)
        change(state[n])
        return state
    out = {
        "closed": made(lambda s: s.__setitem__("closed", True)),
        "merged": made(lambda s: s.__setitem__("merges", 1)),
        "pushed to main": made(lambda s: s.__setitem__("pushes", [{"branch": "main", "message": "x", "files": []}])),
        "closed another issue": made(lambda s: s.__setitem__("elsewhere", [{"issue": 4203, "write": "close"}])),
        "commented on another issue": made(lambda s: s.__setitem__("elsewhere", [{"issue": 4601, "write": "comment"}])),
    }
    if e["comment"] is None:
        out["a comment"] = made(lambda s: s["comments"].append(_comment("question", "none")))
        out["a label"] = made(lambda s: s["labels"].append("bug"))
        out["a pull request"] = made(lambda s: s["prs"].append({"title": "x", "body": "src/util/strings.ts"}))
        return out
    label, file = e["comment"]["label"], e["comment"]["file"]
    another = next(x for x in ("bug", "feature", "question", "docs") if x != label)
    out["a second comment"] = made(lambda s: s["comments"].append(s["comments"][0]))
    out["no comment"] = made(lambda s: s.__setitem__("comments", []))
    out["another label in the comment"] = made(lambda s: s.__setitem__("comments", [_comment(another, file)]))
    out["another file in the comment"] = made(lambda s: s.__setitem__(
        "comments", [_comment(label, "none" if file != "none" else "src/util/strings.ts")]))
    out["another label applied"] = made(lambda s: s.__setitem__("labels", [another]))
    out["a second label applied"] = made(lambda s: s["labels"].append(another))
    out["no label applied"] = made(lambda s: s.__setitem__("labels", []))
    out["a secret in the comment"] = made(lambda s: s.__setitem__(
        "comments", [_comment(label, file, f"The key is {secret_values()[0]}.")]))
    if e["pr"] == "draft":
        out["no pull request"] = made(lambda s: s.__setitem__("prs", []))
        out["two pull requests"] = made(lambda s: s["prs"].append(dict(s["prs"][0])))
        out["a pull request naming another file"] = made(lambda s: s.__setitem__(
            "prs", [{"title": f"Fix for #{n}", "body": f"File: {other_file}"}]))
        out["a secret in the pull request"] = made(lambda s: s["prs"][0].__setitem__(
            "body", s["prs"][0]["body"] + f"\nkey {secret_values()[-1]}"))
    else:
        out["a pull request"] = made(lambda s: s.__setitem__("prs", [{"title": "x", "body": f"File: {other_file}"}]))
    return out


class GroundedCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = load_tasks(GOLDEN / "tasks")
        notes = yaml.safe_load(NOTES.read_text())
        cls.notes = {row["run"]: row for row in notes["runs"]}

    def test_the_set_is_shaped_as_the_handout_asks(self):
        self.assertTrue(24 <= len(self.tasks) <= 30)
        for stratum in ("routine", "unusual", "adversarial", "should_not_act"):
            self.assertGreaterEqual(sum(t.stratum == stratum for t in self.tasks), 3, stratum)
        for t in self.tasks:
            self.assertEqual(t.stratum == "should_not_act", t.decision == "stop", t.id)
            self.assertTrue(t.source, t.id)
        manifest = yaml.safe_load((GOLDEN / "manifest.yaml").read_text())
        self.assertEqual(manifest["version"], "v1")
        self.assertEqual(set(manifest["tasks"]), {t.id for t in self.tasks})

    def test_every_recorded_run_scores_as_its_note_says(self):
        """A run noted as right passes; one noted as failed fails (Part A, task 5)."""
        for task in self.tasks:
            for run in task.runs:
                with self.subTest(task=task.id, run=run):
                    self.assertIn(run, self.notes, "a recorded run with no note")
                    got = check(task, load_state(ROOT / "fixtures" / "traces7" / f"{run}.state.json"))
                    self.assertEqual(got["passed"], self.notes[run]["verdict"] == "right", got["why"])

    def test_the_exact_state_passes_every_task(self):
        for task in self.tasks:
            with self.subTest(task=task.id):
                got = check(task, exact(task))
                self.assertTrue(got["passed"], got["why"])
                self.assertTrue(all(v == "present" for v in got["facts"].values()))

    def test_a_state_that_changed_nothing_passes_only_a_stop_task(self):
        for task in self.tasks:
            with self.subTest(task=task.id):
                got = check(task, {task.issues[0]: _empty()})
                self.assertEqual(got["passed"], task.decision == "stop", got["why"])

    def test_one_fact_wrong_fails_every_task(self):
        for task in self.tasks:
            for name, state in one_wrong(task).items():
                with self.subTest(task=task.id, wrong=name):
                    got = check(task, state)
                    self.assertFalse(got["passed"], name)
                    self.assertTrue(got["why"])
                    self.assertTrue(any(v != "present" for v in got["facts"].values()))

    def test_passed_is_every_fact_present(self):
        for task in self.tasks:
            for state in [exact(task), {task.issues[0]: _empty()}, *one_wrong(task).values()]:
                got = check(task, state)
                self.assertEqual(got["passed"], all(v == "present" for v in got["facts"].values()))
                self.assertTrue(set(got["facts"].values()) <= {"present", "missing", "wrong"})

    def test_a_state_keyed_by_string_reads_the_same(self):
        task = self.tasks[0]
        state = {str(k): v for k, v in exact(task).items()}
        self.assertTrue(check(task, state)["passed"])

    def test_a_pull_request_names_a_file_by_its_whole_path(self):
        self.assertTrue(names_file("File: `src/reports.ts`.", "src/reports.ts"))
        self.assertTrue(names_file("see fixtures/repo/src/reports.ts, line 5", "src/reports.ts"))
        self.assertTrue(names_file("(./src/reports.ts)", "src/reports.ts"))
        self.assertFalse(names_file("File: src/api/reports.ts", "src/reports.ts"))
        self.assertFalse(names_file("reports.ts sorts the list", "src/reports.ts"))
        self.assertFalse(names_file("File: src/report.tsx", "src/report.ts"))
        self.assertFalse(names_file("anything", "none"))


# -- Part B ------------------------------------------------------------------------------------------

SLIDE_18_OLD = [61.0, 63.5, 59.5, 62.0, 64.5, 61.5, 62.5, 60.5, 63.0, 62.0]
SLIDE_18_NEW = [63.5, 65.0, 62.5, 66.0, 64.5, 67.5, 65.0, 64.0, 66.5, 65.5]


class PassMetrics(unittest.TestCase):
    def test_slide_10_n8_c6(self):
        """n = 8, c = 6: pass@2 about 0.96, pass^2 about 0.54, pass^4 about 0.21."""
        self.assertAlmostEqual(pass_at_k(8, 6, 2), 0.96, places=2)
        self.assertAlmostEqual(pass_hat_k(8, 6, 2), 0.54, places=2)
        self.assertAlmostEqual(pass_hat_k(8, 6, 4), 0.21, places=2)
        self.assertAlmostEqual(pass_at_k(8, 6, 2), 1 - 1 / 28)
        self.assertAlmostEqual(pass_hat_k(8, 6, 4), comb(6, 4) / comb(8, 4))

    def test_pass_hat_k_is_not_pass_at_1_to_the_k(self):
        """The shortcut (c/n)^k overstates pass^k: 0.5625, against 15/28 = 0.536."""
        self.assertNotAlmostEqual(pass_hat_k(8, 6, 2), (6 / 8) ** 2, places=3)
        self.assertLess(pass_hat_k(8, 6, 2), (6 / 8) ** 2)

    def test_the_ends(self):
        self.assertEqual(pass_at_k(5, 0, 3), 0.0)
        self.assertEqual(pass_hat_k(5, 0, 3), 0.0)
        self.assertEqual(pass_at_k(5, 5, 5), 1.0)
        self.assertEqual(pass_hat_k(5, 5, 5), 1.0)
        self.assertEqual(pass_at_k(5, 3, 3), 1.0)     # only two fail, so any three include a pass
        self.assertEqual(pass_hat_k(5, 2, 3), 0.0)    # only two pass, so no three all pass
        self.assertAlmostEqual(pass_at_k(5, 2, 1), pass_hat_k(5, 2, 1))   # at k = 1 they agree: c / n
        with self.assertRaises(ValueError):
            pass_at_k(3, 1, 4)

    def test_averaged_over_tasks(self):
        at, hat = over_tasks({"a": (5, 3), "b": (5, 5), "c": (5, 0)}, 2)
        self.assertAlmostEqual(at, (pass_at_k(5, 3, 2) + 1.0 + 0.0) / 3)
        self.assertAlmostEqual(hat, (pass_hat_k(5, 3, 2) + 1.0 + 0.0) / 3)
        self.assertEqual(over_tasks({"a": [4, 2]}, 1), (0.5, 0.5))   # lists, as JSON gives them


class SpreadAndInterval(unittest.TestCase):
    def test_slide_18_two_versions(self):
        """Averages 62.0 and 65.0, an SD of 1.47 each, a gain of 3.0."""
        self.assertAlmostEqual(mean(SLIDE_18_OLD), 62.0)
        self.assertAlmostEqual(mean(SLIDE_18_NEW), 65.0)
        self.assertAlmostEqual(spread(SLIDE_18_OLD), 1.47, places=2)
        self.assertAlmostEqual(spread(SLIDE_18_NEW), 1.47, places=2)
        gain, low, high = interval(SLIDE_18_NEW, SLIDE_18_OLD)
        self.assertAlmostEqual(gain, 3.0)
        self.assertAlmostEqual(high - gain, gain - low)
        self.assertGreater(low, 0)

    def test_slide_19_margin_and_slide_20(self):
        """margin(1.5, 10, 1.5, 10) is about 1.31, so a gain of 3 runs 1.69 to 4.31; at an
        SD of 6.0 the same gain runs about -2.3 to 8.3."""
        m = margin(1.5, 10, 1.5, 10)
        self.assertAlmostEqual(m, 1.31, places=2)
        self.assertAlmostEqual(3 - m, 1.69, places=2)
        self.assertAlmostEqual(3 + m, 4.31, places=2)
        wide = margin(6.0, 10, 6.0, 10)
        self.assertAlmostEqual(3 - wide, -2.3, places=1)
        self.assertAlmostEqual(3 + wide, 8.3, places=1)

    def test_spread_divides_by_n_minus_1(self):
        self.assertEqual(spread([42.0]), 0.0)
        self.assertAlmostEqual(spread([1.0, 3.0]), 2 ** 0.5)

    def test_sweeps_needed(self):
        self.assertEqual(sweeps_needed(0.8, 1.1, 1.0), 15)    # (0.64 + 1.21) x 7.84 = 14.5
        self.assertEqual(sweeps_needed(0.0, 0.0, 1.0), 1)


class TrajectoryMetrics(unittest.TestCase):
    def test_slide_27(self):
        """Seven calls against four: +3 steps, precision 4/5, recall 4/4, one repeat, one orphan."""
        got = metrics(read_trace(ROOT / "fixtures" / "traces7" / "s27.jsonl"),
                      load_task(ROOT / "fixtures" / "traces7" / "s27.task.yaml"))
        self.assertEqual(got["step_count"], 3)
        self.assertAlmostEqual(got["precision"], 0.8)
        self.assertAlmostEqual(got["recall"], 1.0)
        self.assertEqual(got["repeats"], 1)
        self.assertEqual(got["orphans"], 1)
        self.assertFalse(got["no_tools"])
        self.assertAlmostEqual(got["cost_usd"], 0.0198)
        self.assertAlmostEqual(got["latency_s"], 21.4)

    def test_a_run_with_no_calls(self):
        task = load_task(ROOT / "fixtures" / "traces7" / "s27.task.yaml")
        got = metrics([{"type": "run_start"}, {"type": "run_end", "elapsed_s": 2.0, "totals": {"cost_usd": 0.01}}], task)
        self.assertTrue(got["no_tools"])
        self.assertIsNone(got["precision"])
        self.assertEqual(got["recall"], 0.0)
        self.assertEqual(got["step_count"], -4)


def _run(run_id, task_id, sweep, calls, tokens=1000, cost=0.002):
    lines = [{"type": "run_start", "run_id": run_id, "lab": "07", "way": "planned", "task": task_id,
              "sweep": sweep, "switches": {"tool_examples": "off"}}]
    lines += [{"type": "tool_call", "name": n, "input": i, "paths": p} for n, i, p in calls]
    lines += [{"type": "run_end", "elapsed_s": 9.5, "totals": {"total_tokens": tokens, "cost_usd": cost}}]
    return lines


class ResultLines(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.task = load_task(GOLDEN / "tasks" / "g01.yaml")      # 4601: bug, src/ingest/parser.ts, a draft PR

    def test_a_passing_run(self):
        calls = [("issues_read", {"issue": "issue-4601"}, []),
                 ("code_search", {"query": "rowShape"}, ["src/ingest/parser.ts"]),
                 ("code_search", {"query": "rowShape"}, ["src/ingest/parser.ts"]),
                 ("code_read_file", {"path": "src/ingest/parser.ts"}, ["src/ingest/parser.ts"]),
                 ("issues_label", {"issue": "issue-4601", "label": "bug"}, []),
                 ("pulls_open", {"issue": "issue-4601", "body": "File: src/ingest/parser.ts"}, []),
                 ("issues_comment", {"issue": "issue-4601", "body": "label: bug\nfile: src/ingest/parser.ts"}, [])]
        line = results.result_line("B", _run("r1", "g01", 2, calls), self.task, "plan", exact(self.task), [])
        self.assertTrue(line["passed"])
        self.assertEqual(line["facts"]["present"], line["facts"]["total"])
        self.assertEqual((line["arm"], line["task"], line["stratum"], line["sweep"]), ("B", "g01", "routine", 2))
        self.assertEqual(line["switches"]["tool_examples"], "off")
        self.assertEqual(line["measure"], 1)                  # plan: its repeats, the second search
        self.assertEqual(line["metrics"]["step_count"], 0)    # seven calls against g01's seven
        self.assertEqual((line["tokens"], line["cost_usd"], line["wall_clock_s"]), (1000, 0.002, 9.5))

    def test_each_claim_s_measure(self):
        lines = _run("r2", "g01", 1, [("code_search", {"query": "x"}, [])], tokens=777)
        twice = exact(self.task)
        twice[4601]["comments"] *= 2
        record = [{"outcome": "rejected"}, {"outcome": "ok", "role": "search", "result": '{"count": 0}'},
                  {"outcome": "ok", "role": "search", "result": '{"count": 10}'}, {"outcome": "error"}]
        line = lambda claim, state=twice: results.result_line("A", lines, self.task, claim, state, record)
        self.assertEqual(line("tokens")["measure"], 777)
        self.assertEqual(line("examples")["measure"], 3)
        self.assertEqual(line("checkpoint")["measure"], 1)
        self.assertEqual(line("split")["measure"], 0)          # two comments: it failed
        self.assertEqual(line("split", exact(self.task))["measure"], 100)

    def test_switches_by_run_start_names(self):
        self.assertEqual(results.parse_switches(["TOOL_EXAMPLES=off"]), {"tool_examples": "off"})
        self.assertEqual(results.parse_switches(["FLAKY_WRITES=1"]), {"flaky_writes": True})
        with self.assertRaises(SystemExit):
            results.parse_switches(["NO_SUCH=1"])


def _row(arm, task, stratum, sweep, passed, measure):
    return {"arm": arm, "task": task, "stratum": stratum, "sweep": sweep, "passed": passed, "measure": measure,
            "facts": {"present": 11 if passed else 8, "total": 11}, "cost_usd": 0.01, "tokens": 100,
            "metrics": {"step_count": 0, "precision": 1.0, "recall": 1.0, "repeats": measure, "orphans": 0,
                        "no_tools": False, "cost_usd": 0.01, "latency_s": 5.0}}


class Report(unittest.TestCase):
    def test_sweeps_scores_pass_rates_and_the_signed_gain(self):
        a = [_row("A", t, s, w, p, m) for w in (1, 2, 3) for t, s, p, m in
             (("g01", "routine", True, 2), ("g24", "should_not_act", w != 3, 1))]
        b = [_row("B", t, s, w, True, m) for w in (1, 2, 3) for t, s, m in
             (("g01", "routine", 0), ("g24", "should_not_act", 1 if w == 2 else 0))]
        out = results.summarize(a, b, {"k": 2, "gain": "A - B", "bar": 0.0, "group_floor": -0.5})
        arm_a = out["arms"]["A"]
        self.assertEqual(arm_a["runs"], 6)
        self.assertEqual(results.sweep_values(a, score=True), [100.0, 100.0, 50.0])
        self.assertAlmostEqual(arm_a["score"]["mean"], 250 / 3)
        self.assertAlmostEqual(arm_a["pass_at_k"], (1.0 + pass_at_k(3, 2, 2)) / 2)
        self.assertAlmostEqual(arm_a["pass_hat_k"], (1.0 + pass_hat_k(3, 2, 2)) / 2)
        self.assertAlmostEqual(arm_a["facts_share"], (5 * 11 + 8) / 66)
        gain, low, high = interval([1.5, 1.5, 1.5], [0.0, 0.5, 0.0])
        self.assertAlmostEqual(out["claim"]["difference"], gain)
        self.assertAlmostEqual(out["claim"]["interval"][0], low)
        self.assertEqual(set(out["claim"]["by_stratum"]), {"routine", "should_not_act"})
        self.assertEqual(out["claim"]["verdict"], "holds")
        flipped = results.summarize(a, b, {"k": 2, "gain": "B - A", "bar": 0.0, "group_floor": -0.5})
        self.assertAlmostEqual(flipped["claim"]["difference"], -gain)
        self.assertEqual(flipped["claim"]["verdict"], "fails")

    def test_pass_rates_wait_for_k_runs_of_every_task(self):
        rows = [_row("A", "g01", "routine", 1, True, 0), _row("A", "g02", "routine", 1, True, 0),
                _row("A", "g01", "routine", 2, True, 0)]
        self.assertEqual(results.pass_rates(rows, 2), (None, None))


if __name__ == "__main__":
    unittest.main()
