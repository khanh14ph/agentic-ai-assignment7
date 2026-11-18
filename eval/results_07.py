"""Assignment 7, Part B, task 1: one line per run, in results/<arm>.jsonl
(checks/FORMATS.md, section 15.4); and the report those lines make.

    python -m eval.results_07 --arm A --way planned --claim plan
    python -m eval.results_07 --arm B --way planned --switch TOOL_EXAMPLES=off --claim examples
    python -m eval.results_07 --report                 # the numbers for reports/LAB_07.*
    python -m eval.results_07 --report --write         # ... and write them into reports/LAB_07.json

Reads the arm's finished runs on your subset's golden tasks in runs/, checks each with your
grounded check, computes Part C's measure and the five metrics, and writes one line
per run. The helpers below find the runs and read them; the rest is yours.

A line (section 15.4):

    {"arm": "A", "way": "planned", "switches": {...}, "run_id": "...", "task": "g07",
     "stratum": "routine", "sweep": 1, "passed": true, "facts": {"present": 6, "total": 6},
     "measure": 0, "tokens": 31234, "cost_usd": 0.0412, "wall_clock_s": 18.2,
     "metrics": {"step_count": 2, "precision": 1.0, "recall": 1.0, "repeats": 0,
                 "orphans": 1, "no_tools": false, "cost_usd": 0.0412, "latency_s": 18.2}}

Each line also carries `why`: the facts the grounded check did not find, for Part C's
first failures.

Part C's measure, per run, by claim (section 15.4): tokens, the run_end line's
totals.total_tokens; plan, the run's repeats; examples, its wasted calls: the lines of
its call record (runs/<run_id>.calls.jsonl) whose outcome is "rejected", "error" or
"protocol", plus the search calls whose result has "count": 0; checkpoint, its duplicate
writes: the comments beyond one, plus the open pull requests beyond one, on its issue
in its end state; split, 100 when the run passed and 0 when it did not.

The end state is read from the tracker, never from the run's own words: the run's
writes are found in tracker/tracker.db or, after a `make reset`, in the archive under
tracker/archive/ that holds them (read only), and harness.tasks.end_state turns them
into the state eval/grounded.py checks.

The report (--report) reads results/A.jsonl and results/B.jsonl and
eval/thresholds/claim.yaml, and computes what section 15.8 asks, the way the checker
recomputes it: a sweep's value is the measure's mean over its runs, its score 100 x
passes / runs; each arm's mean and SD over its sweeps; pass@k and pass^k averaged over
tasks; the gain, signed as claim.yaml's `gain` says, with its 95% interval, overall and
on each stratum's tasks alone; and the verdict by the bar.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import yaml

from eval.grounded import check
from eval.metrics import metrics
from eval.stats import interval, mean, over_tasks, spread
from harness import LAB, ROOT
from harness import switches as switch_board
from harness.formats import STRATA, UNFINISHED
from harness.tasks import end_state, load_tasks, read_subset
from harness.trace import read_trace
from harness.tracker import Tracker

CLAIMS = ("tokens", "plan", "examples", "checkpoint", "split")
WASTED_OUTCOMES = ("rejected", "error", "protocol")
SEARCH_EMPTY = re.compile(r'"count":\s*0\b')
TRACKER_TABLES = ("comments", "prs", "labels", "closes", "pushes")
CLAIM_FILE = "eval/thresholds/claim.yaml"
REPORT_JSON = "reports/LAB_07.json"


def finished_runs(way: str, switches: dict | None = None, root: Path = ROOT,
                  scripted: bool = False) -> list[list[dict]]:
    """Every finished Assignment 7 run of `way` with these switches (unset ones at their
    defaults), on a real model, as its trace's lines: one list per run. A run is finished
    when its last line is run_end and it did not end quota or rate_limited. With
    scripted=True, the runs on a scripted model instead, to test your code for free."""
    want = {**switch_board.DEFAULTS, **(switches or {})}
    out = []
    for path in sorted((root / "runs").glob("*.jsonl")):
        if path.name.startswith("_") or path.name.count(".") > 1:
            continue
        lines = read_trace(path)
        start = lines[0] if lines else {}
        if start.get("type") != "run_start" or start.get("lab") != LAB or start.get("way") != way:
            continue
        if {**switch_board.DEFAULTS, **(start.get("switches") or {})} != want:
            continue
        free = str(start.get("backend", "")).startswith("harness.scripted:") or start.get("backend") == "never-stops"
        if free != scripted:
            continue
        ends = [r.get("terminal_reason") for r in lines if r.get("type") == "end"]
        if lines[-1].get("type") != "run_end" or set(ends) & set(UNFINISHED):
            continue
        out.append(lines)
    return out


def call_record(run_id: str, root: Path = ROOT) -> list[dict]:
    """A run's call record, runs/<run_id>.calls.jsonl, one dict per line."""
    path = root / "runs" / f"{run_id}.calls.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


# -- the end state, from whichever tracker database holds the run -----------------------------------

class _ReadOnlyTracker(Tracker):
    """The tracker's queries on one database file, opened read only: Tracker's own
    connection runs its schema script, which would change an archive."""

    def __init__(self, path: Path, root: Path = ROOT):
        super().__init__(root=root, flaky=False, readback_fail=False)
        self.db_path = Path(path)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(f"{self.db_path.resolve().as_uri()}?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()


def databases(root: Path = ROOT) -> list[Path]:
    """tracker/tracker.db and every archive of it, the live one first."""
    live = root / "tracker" / "tracker.db"
    return [p for p in [live, *sorted((root / "tracker" / "archive").glob("*.db"))] if p.exists()]


def _holds(path: Path, run_id: str) -> bool:
    db = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        for table in TRACKER_TABLES:
            try:
                if db.execute(f"SELECT 1 FROM {table} WHERE run_id = ? LIMIT 1", (run_id,)).fetchone():
                    return True
            except sqlite3.OperationalError:      # an older archive without this table
                continue
        return False
    finally:
        db.close()


def state_of(run_id: str, task, root: Path = ROOT) -> dict:
    """The run's end state on the task's issues (section 15.3). A run that wrote
    nothing has no rows anywhere, and its end state is empty."""
    for path in databases(root):
        if _holds(path, run_id):
            return end_state(_ReadOnlyTracker(path, root), run_id, task)
    return {int(n): {"comments": [], "labels": [], "prs": [], "closed": False, "merges": 0, "pushes": [],
                     "elsewhere": []} for n in task.issues}


# -- one run's line ---------------------------------------------------------------------------------

def wasted(record: list[dict]) -> int:
    """Claim 3's measure: calls refused, failed in the tool, or naming no tool, and
    searches that found nothing; each call record line counted once."""
    out = 0
    for line in record:
        if line.get("outcome") in WASTED_OUTCOMES:
            out += 1
        elif line.get("role") == "search" and SEARCH_EMPTY.search(str(line.get("result") or "")):
            out += 1
    return out


def duplicates(state: dict, task) -> int:
    """Claim 4's measure: the comments beyond one and the open pull requests beyond one."""
    s = state.get(int(task.issues[0])) or {}
    return max(0, len(s.get("comments") or []) - 1) + max(0, len(s.get("prs") or []) - 1)


def measure_of(claim: str, *, end: dict, trajectory: dict, record: list[dict], state: dict, task,
               passed: bool) -> float:
    if claim == "tokens":
        return int((end.get("totals") or {}).get("total_tokens") or 0)
    if claim == "plan":
        return trajectory["repeats"]
    if claim == "examples":
        return wasted(record)
    if claim == "checkpoint":
        return duplicates(state, task)
    if claim == "split":
        return 100 if passed else 0
    raise ValueError(f"claim is one of {CLAIMS}, not {claim!r}")


def result_line(arm: str, lines: list[dict], task, claim: str, state: dict, record: list[dict]) -> dict:
    """One run's line in results/<arm>.jsonl, from its trace, its end state and its call record."""
    start = lines[0]
    ends = [line for line in lines if line.get("type") == "run_end"]
    end = ends[-1] if ends else {}
    got = check(task, state)
    trajectory = metrics(lines, task)
    return {
        "arm": arm, "way": start.get("way"),
        "switches": {**switch_board.DEFAULTS, **(start.get("switches") or {})},
        "run_id": start.get("run_id"), "task": task.id, "stratum": task.stratum, "sweep": start.get("sweep"),
        "passed": got["passed"],
        "facts": {"present": sum(v == "present" for v in got["facts"].values()), "total": len(got["facts"])},
        "measure": measure_of(claim, end=end, trajectory=trajectory, record=record, state=state, task=task,
                              passed=got["passed"]),
        "tokens": int((end.get("totals") or {}).get("total_tokens") or 0),
        "cost_usd": float((end.get("totals") or {}).get("cost_usd") or 0.0),
        "wall_clock_s": float(end.get("elapsed_s") or 0.0),
        "metrics": trajectory,
        "why": got["why"],
    }


def parse_switches(pairs: list[str]) -> dict:
    """--switch TOOL_EXAMPLES=off -> {"tool_examples": "off"}, by run_start's names."""
    out = {}
    for pair in pairs:
        name, _, value = pair.partition("=")
        key = name.strip().lower()
        if key not in switch_board.DEFAULTS or not value:
            raise SystemExit(f"--switch {pair!r}: NAME=VALUE, NAME one of {sorted(switch_board.DEFAULTS)}")
        if isinstance(switch_board.DEFAULTS[key], bool):
            out[key] = value.strip().lower() in ("1", "true", "on", "yes")
        else:
            out[key] = value.strip().lower()
    return out


def task_ids(tasks_dir: str, subset: str, root: Path = ROOT) -> tuple[dict, list[str]]:
    """The golden tasks by ID, and the IDs to keep: the subset's, or every task when the
    subset file does not exist yet (a note says so)."""
    tasks = {t.id: t for t in load_tasks(root / tasks_dir)}
    path = root / subset
    if subset == "all" or not path.exists():
        if subset != "all":
            print(f"note: {subset} does not exist yet, so every task in {tasks_dir} is kept")
        return tasks, sorted(tasks)
    ids = read_subset(path)
    unknown = [i for i in ids if i not in tasks]
    if unknown:
        raise SystemExit(f"{subset} names tasks the golden set does not have: {unknown}")
    return tasks, ids


def collect(arm: str, way: str, switches: dict, claim: str, tasks_dir: str, subset: str,
            scripted: bool = False, root: Path = ROOT) -> list[dict]:
    tasks, keep = task_ids(tasks_dir, subset, root)
    out = []
    for lines in finished_runs(way, switches, root=root, scripted=scripted):
        tid = lines[0].get("task")
        if tid not in keep:
            continue
        run_id = lines[0].get("run_id")
        task = tasks[tid]
        out.append(result_line(arm, lines, task, claim, state_of(run_id, task, root), call_record(run_id, root)))
    return sorted(out, key=lambda r: (r["sweep"] or 0, r["task"], r["run_id"]))


# -- the report ------------------------------------------------------------------------------------

def read_results(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []


def _sweeps(rows: list[dict]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for r in rows:
        if r.get("sweep") is not None:
            out.setdefault(int(r["sweep"]), []).append(r)
    return dict(sorted(out.items()))


def sweep_values(rows: list[dict], score: bool = False) -> list[float]:
    """One value per sweep, in sweep order: the measure's mean, or 100 x passes / runs."""
    out = []
    for runs in _sweeps(rows).values():
        out.append(100.0 * sum(bool(r["passed"]) for r in runs) / len(runs) if score
                   else mean([r["measure"] for r in runs]))
    return out


def pass_rates(rows: list[dict], k: int) -> tuple[float | None, float | None]:
    """pass@k and pass^k over the rows' tasks; None while a task has fewer than k runs."""
    counts: dict[str, list[int]] = {}
    for r in rows:
        n_c = counts.setdefault(r["task"], [0, 0])
        n_c[0] += 1
        n_c[1] += bool(r["passed"])
    if not counts or any(n < k for n, _ in counts.values()):
        return None, None
    return over_tasks({t: tuple(v) for t, v in counts.items()}, k)


def arm_numbers(rows: list[dict], k: int) -> dict:
    """An arm's numbers, as section 15.8 names them, plus the five metrics' means."""
    meas, score = sweep_values(rows), sweep_values(rows, score=True)
    at, hat = pass_rates(rows, k)
    present = sum(r["facts"]["present"] for r in rows)
    total = sum(r["facts"]["total"] for r in rows)
    sweeps = _sweeps(rows)
    m = [r["metrics"] for r in rows]
    precisions = [x["precision"] for x in m if x["precision"] is not None]
    by_stratum = {}
    for s in STRATA:
        rs = [r for r in rows if r["stratum"] == s]
        if rs:
            s_at, s_hat = pass_rates(rs, k)
            by_stratum[s] = {"runs": len(rs), "measure": mean(sweep_values(rs)),
                             "score": mean(sweep_values(rs, score=True)), "pass_at_k": s_at, "pass_hat_k": s_hat}
    return {
        "runs": len(rows), "sweeps": len(sweeps),
        "measure": {"mean": mean(meas), "sd": spread(meas)}, "score": {"mean": mean(score), "sd": spread(score)},
        "measure_first_3": {"sd": spread(meas[:3])}, "score_first_3": {"sd": spread(score[:3])},
        "pass_at_k": at, "pass_hat_k": hat, "facts_share": present / total if total else None,
        "cost_per_run_usd": mean([r["cost_usd"] for r in rows]),
        "cost_per_sweep_usd": mean([sum(r["cost_usd"] for r in rs) for rs in sweeps.values()]),
        "tokens_per_run": mean([r["tokens"] for r in rows]),
        "no_tools": sum(bool(x["no_tools"]) for x in m),
        "trajectory": {"step_count": mean([x["step_count"] for x in m]),
                       "precision": mean(precisions) if precisions else None,
                       "recall": mean([x["recall"] for x in m]), "repeats": mean([x["repeats"] for x in m]),
                       "orphans": mean([x["orphans"] for x in m]), "latency_s": mean([x["latency_s"] for x in m])},
        "by_stratum": by_stratum,
    }


def signed_interval(gain: str, a_vals: list[float], b_vals: list[float]) -> tuple[float, float, float]:
    """The gain as claim.yaml signs it: B - A, or A - B."""
    return interval(b_vals, a_vals) if gain.replace(" ", "") == "B-A" else interval(a_vals, b_vals)


def summarize(a_rows: list[dict], b_rows: list[dict], spec: dict) -> dict:
    """The arms' numbers, the difference and its interval overall and by stratum, and the verdict."""
    k, gain = int(spec.get("k") or 3), str(spec.get("gain") or "B - A")
    out = {"k": k, "gain": gain, "arms": {}, "claim": None}
    for arm, rows in (("A", a_rows), ("B", b_rows)):
        if rows:
            out["arms"][arm] = arm_numbers(rows, k)
    a_vals, b_vals = sweep_values(a_rows), sweep_values(b_rows)
    if len(a_vals) < 2 or len(b_vals) < 2:
        return out
    diff, lo, hi = signed_interval(gain, a_vals, b_vals)
    by = {}
    for s in STRATA:
        av = sweep_values([r for r in a_rows if r["stratum"] == s])
        bv = sweep_values([r for r in b_rows if r["stratum"] == s])
        if len(av) >= 2 and len(bv) >= 2:
            d, l, h = signed_interval(gain, av, bv)
            by[s] = {"difference": d, "interval": [l, h]}
    claim = {"difference": diff, "interval": [lo, hi], "by_stratum": by, "verdict": None}
    bar, floor = spec.get("bar"), spec.get("group_floor")
    if isinstance(bar, (int, float)) and isinstance(floor, (int, float)):
        claim["verdict"] = ("holds" if lo > bar and all(v["difference"] >= floor for v in by.values())
                            else "fails" if hi < bar else "cannot_settle")
    out["claim"] = claim
    return out


def _f(x, places=3) -> str:
    return "n/a" if x is None else f"{x:.{places}f}"


def print_report(summary: dict, spec: dict) -> None:
    k = summary["k"]
    measure = spec.get("measure") or "the claim's (no claim.yaml yet)"
    print(f"k = {k}; the gain is {summary['gain']}; the measure is {measure}\n")
    print(f"| Arm | Runs | Sweeps | Measure: mean (SD) | Score: mean (SD) | pass@{k} | pass^{k} | Facts right "
          "| Cost per run | No tools |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for arm, a in summary["arms"].items():
        print(f"| {arm} | {a['runs']} | {a['sweeps']} | {_f(a['measure']['mean'])} ({_f(a['measure']['sd'])}) | "
              f"{_f(a['score']['mean'], 1)} ({_f(a['score']['sd'], 1)}) | {_f(a['pass_at_k'])} | "
              f"{_f(a['pass_hat_k'])} | {_f(a['facts_share'])} | ${a['cost_per_run_usd']:.4f} | {a['no_tools']} |")
    print("\nThe five trajectory metrics, mean per run:\n")
    print("| Arm | Step count | Precision | Recall | Repeats | Orphans | Latency (s) | Tokens per run |")
    print("|---|---|---|---|---|---|---|---|")
    for arm, a in summary["arms"].items():
        t = a["trajectory"]
        print(f"| {arm} | {_f(t['step_count'], 2)} | {_f(t['precision'])} | {_f(t['recall'])} | "
              f"{_f(t['repeats'], 2)} | {_f(t['orphans'], 2)} | {_f(t['latency_s'], 1)} | {a['tokens_per_run']:.0f} |")
    print("\nBy stratum:\n")
    print(f"| Arm | Stratum | Runs | Measure | Score | pass@{k} | pass^{k} |")
    print("|---|---|---|---|---|---|---|")
    for arm, a in summary["arms"].items():
        for s, v in a["by_stratum"].items():
            print(f"| {arm} | {s} | {v['runs']} | {_f(v['measure'])} | {_f(v['score'], 1)} | "
                  f"{_f(v['pass_at_k'])} | {_f(v['pass_hat_k'])} |")
    print("\nFor Part C's tasks 3 and 4: each arm's SD over its first three sweeps, and the cost of a sweep:")
    for arm, a in summary["arms"].items():
        print(f"  {arm}: s of the measure {_f(a['measure_first_3']['sd'], 4)}, s of the score "
              f"{_f(a['score_first_3']['sd'], 2)}; one sweep costs ${a['cost_per_sweep_usd']:.4f}")
    c = summary["claim"]
    if c is None:
        print("\nNo interval yet: each arm needs at least two sweeps.")
        return
    print(f"\n| Stratum | Gain ({summary['gain']}) | 95% interval |")
    print("|---|---|---|")
    print(f"| All tasks | {_f(c['difference'])} | {_f(c['interval'][0])} to {_f(c['interval'][1])} |")
    for s, v in c["by_stratum"].items():
        print(f"| {s} | {_f(v['difference'])} | {_f(v['interval'][0])} to {_f(v['interval'][1])} |")
    print(f"\nThe verdict by the bar {spec.get('bar')} and group floor {spec.get('group_floor')}: "
          f"{c['verdict'] or 'no bar in claim.yaml yet'}")


def _r(x, places=4):
    return None if x is None else round(float(x), places)


def write_report_json(summary: dict, spec: dict, root: Path = ROOT) -> Path:
    """Fill reports/LAB_07.json's claim and arms from the summary and claim.yaml; leave
    golden, failures, grid and judge as they are."""
    path = root / REPORT_JSON
    report = json.loads(path.read_text())
    for arm in ("A", "B"):
        a = summary["arms"].get(arm)
        if a is None:
            continue
        side = spec.get(f"arm_{arm.lower()}") or {}
        report["arms"][arm] = {
            "way": side.get("way"), "switches": side.get("switches") or {}, "runs": a["runs"],
            "measure": {"mean": _r(a["measure"]["mean"]), "sd": _r(a["measure"]["sd"])},
            "score": {"mean": _r(a["score"]["mean"]), "sd": _r(a["score"]["sd"])},
            "pass_at_k": _r(a["pass_at_k"]), "pass_hat_k": _r(a["pass_hat_k"]),
            "facts_share": _r(a["facts_share"]), "cost_per_run_usd": _r(a["cost_per_run_usd"], 6),
            "no_tools": a["no_tools"],
            "by_stratum": {s: {"runs": v["runs"], "measure": _r(v["measure"]), "score": _r(v["score"]),
                               "pass_at_k": _r(v["pass_at_k"]), "pass_hat_k": _r(v["pass_hat_k"])}
                           for s, v in a["by_stratum"].items()},
        }
    claim = report.setdefault("claim", {})
    for key in ("claim", "measure", "gain", "k", "sweeps", "s_a", "s_b", "delta", "n_needed", "price_usd"):
        claim[key] = spec.get(key)
    c = summary["claim"]
    if c is not None:
        claim["difference"] = _r(c["difference"])
        claim["interval"] = [_r(c["interval"][0]), _r(c["interval"][1])]
        claim["by_stratum"] = {s: {"difference": _r(v["difference"]), "interval": [_r(v["interval"][0]),
                                                                                    _r(v["interval"][1])]}
                               for s, v in c["by_stratum"].items()}
        claim["verdict"] = c["verdict"]
    path.write_text(json.dumps(report, indent=2) + "\n")
    return path


def report(scripted: bool, write: bool, k: int | None, gain: str | None, root: Path = ROOT) -> int:
    prefix = "scripted_" if scripted else ""
    a_rows = read_results(root / "results" / f"{prefix}A.jsonl")
    b_rows = read_results(root / "results" / f"{prefix}B.jsonl")
    if not a_rows and not b_rows:
        raise SystemExit(f"no lines in results/{prefix}A.jsonl or results/{prefix}B.jsonl yet")
    spec_path = root / CLAIM_FILE
    spec = (yaml.safe_load(spec_path.read_text()) or {}) if spec_path.exists() else {}
    if k is not None:
        spec["k"] = k
    if gain is not None:
        spec["gain"] = gain
    if scripted:
        print("scripted runs: these test the harness and score nothing\n")
    summary = summarize(a_rows, b_rows, spec)
    print_report(summary, spec)
    if write:
        if scripted:
            raise SystemExit("--write fills reports/LAB_07.json, from real runs only: drop --scripted")
        if not spec_path.exists():
            raise SystemExit(f"--write needs {CLAIM_FILE}: its k, gain, bar and the rest go in the report")
        print(f"\nwrote {write_report_json(summary, spec, root).relative_to(root)}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--arm", choices=["A", "B"])
    p.add_argument("--way")
    p.add_argument("--switch", action="append", default=[], metavar="NAME=VALUE")
    p.add_argument("--claim", choices=list(CLAIMS))
    p.add_argument("--tasks", default="eval/golden/v1/tasks")
    p.add_argument("--subset", default="eval/subsets/claim.txt", help="only these task IDs (Part C); 'all' for every task")
    p.add_argument("--scripted", action="store_true",
                   help="the runs on a scripted model, to test this script for free: writes "
                        "results/scripted_<arm>.jsonl, which the checker never reads")
    p.add_argument("--report", action="store_true", help="print the numbers results/A.jsonl and B.jsonl make")
    p.add_argument("--write", action="store_true", help="with --report: write them into reports/LAB_07.json")
    p.add_argument("--k", type=int, help="with --report, when claim.yaml does not give k yet")
    p.add_argument("--gain", help="with --report, when claim.yaml does not give the gain yet: 'B - A' or 'A - B'")
    args = p.parse_args(argv)
    if args.report:
        return report(args.scripted, args.write, args.k, args.gain)
    if not (args.arm and args.way and args.claim):
        p.error("--arm, --way and --claim are required (or --report)")
    rows = collect(args.arm, args.way, parse_switches(args.switch), args.claim, args.tasks, args.subset,
                   scripted=args.scripted)
    out = ROOT / "results" / f"{'scripted_' if args.scripted else ''}{args.arm}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    passed = sum(r["passed"] for r in rows)
    print(f"{out.relative_to(ROOT)}: {len(rows)} runs of {args.way} on {len({r['task'] for r in rows})} tasks, "
          f"{len({r['sweep'] for r in rows})} sweep(s); {passed} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
