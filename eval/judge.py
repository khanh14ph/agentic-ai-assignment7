"""Assignment 7, Part D: the judge, its rates and its correction (checks/FORMATS.md,
section 15.10).

    python -m eval.judge tune tuning     # refine the prompt: the tuning set, scored against the labels
    python -m eval.judge tune examples   # ... or the examples set
    python -m eval.judge test 1          # run 1 on the test set: eval/judge/verdicts/test_1.jsonl
    python -m eval.judge versions        # the test items' list and long versions: versions.jsonl
    python -m eval.judge recorded        # the agent way's recorded comments: recorded.jsonl
    python -m eval.judge report [--write]   # every number, for_a_person.txt, and LAB_07.json's judge

Your judge reads one output, its issue and what RepoMind's tools returned, and
answers with slide 36's fixed reply: JSON with a one-line "reasoning", then an
"answer", "Pass" or "Fail". Every call goes through a metered judge session, so its
tokens and cost are recorded and priced, and count against lab_token_ceiling.
To test the plumbing for nothing, pass --backend harness.scripted:PassEverything, a
judge that passes everything: a coin. Its verdicts go to eval/judge/scripted/, never
into verdicts/.

The judge is its model (settings.yaml), its prompt (prompts/judge.md with the examples
below filled in) and its settings, together. Each verdict line carries the prompt's
hash, so a change between runs shows. `tune` reads only the examples and tuning sets;
`test` and `versions` only the test set, after the prompt is frozen.

The checker calls `correct`, `rates` and `bootstrap` on cases of its own, and
`correct` on a coin, so keep their names, arguments and returns.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from harness import ROOT
from harness.meter import judge_session

OUTPUTS = ROOT / "fixtures" / "judge" / "outputs"
VERDICTS = ROOT / "eval" / "judge" / "verdicts"
SCRATCH = ROOT / "eval" / "judge" / "scripted"
TUNING = ROOT / "eval" / "judge" / "tuning"
PROMPT = ROOT / "prompts" / "judge.md"
SPLIT = ROOT / "eval" / "labels" / "split.yaml"
LABELS = ROOT / "eval" / "labels" / "labels.csv"
PERSON = ROOT / "eval" / "judge" / "for_a_person.txt"
REPORT_JSON = ROOT / "reports" / "LAB_07.json"
TRACES = ROOT / "fixtures" / "traces7"
POOL = ROOT / "fixtures" / "issues" / "pool"

# The prompt's examples, from the examples set, as labelled: a clear pass and two clear
# fails of different kinds (an error message from nowhere, a function never searched).
EXAMPLES = ("j17", "j13", "j03")
COMMENT_WRITES = {"issues_comment", "post_comment"}
WORKERS = 4


class CoinJudge(ValueError):
    """TPR + TNR is within 0.1 of 1: the judge is no better than a coin. Fix it, do not
    correct it (slide 44)."""


# -- the maths ---------------------------------------------------------------------------------------

def correct(p: float, tpr: float, tnr: float) -> float:
    """The share you would pass, labelling by hand, from the judge's pass rate p on
    outputs nobody labelled: (p + TNR - 1) / (TPR + TNR - 1) (slide 44), clipped to
    0 to 1. Raises CoinJudge when TPR + TNR is within 0.1 of 1."""
    if abs(tpr + tnr - 1) <= 0.1:
        raise CoinJudge(f"TPR + TNR is {tpr + tnr:.2f}, within 0.1 of 1: the judge is no better than a coin; "
                        "fix it, do not correct it")
    return min(1.0, max(0.0, (p + tnr - 1) / (tpr + tnr - 1)))


def rates(verdicts: dict[str, str], labels: dict[str, str]) -> tuple[float, float]:
    """(TPR, TNR) of the judge's verdicts against your labels, each "pass" or "fail",
    on the items both cover (slide 43): TPR is the share of the labelled passes the
    judge passed, TNR the share of the labelled fails it failed."""
    passes = [i for i in labels if labels[i] == "pass" and i in verdicts]
    fails = [i for i in labels if labels[i] == "fail" and i in verdicts]
    tpr = sum(verdicts[i] == "pass" for i in passes) / len(passes) if passes else 0.0
    tnr = sum(verdicts[i] == "fail" for i in fails) / len(fails) if fails else 0.0
    return tpr, tnr


def bootstrap(verdicts: dict[str, str], labels: dict[str, str], p: float,
              resamples: int = 2000, seed: int = 0) -> tuple[float, float]:
    """The middle 95% of the corrected rate over resamples of the test items, drawn
    with replacement, as many as there are, each time recomputing TPR and TNR
    (slide 44). A resample on which the judge is a coin is left out, and so is one
    with no pass or no fail in it, on which TPR or TNR cannot be computed."""
    items = [i for i in labels if i in verdicts]
    rng = random.Random(seed)
    got = []
    for _ in range(resamples):
        draw = [rng.choice(items) for _ in items]
        n_pass = sum(labels[i] == "pass" for i in draw)
        n_fail = len(draw) - n_pass
        if not n_pass or not n_fail:
            continue
        tpr = sum(labels[i] == "pass" and verdicts[i] == "pass" for i in draw) / n_pass
        tnr = sum(labels[i] == "fail" and verdicts[i] == "fail" for i in draw) / n_fail
        try:
            got.append(correct(p, tpr, tnr))
        except CoinJudge:
            continue
    if not got:
        raise CoinJudge("every resample was a coin, or lacked a pass or a fail")
    got.sort()
    return got[int(0.025 * (len(got) - 1))], got[int(0.975 * (len(got) - 1))]


# -- the inputs --------------------------------------------------------------------------------------

def load_outputs(root: Path = ROOT) -> dict[str, dict]:
    """The 60 outputs to label, by ID (section 15.9)."""
    return {p.stem: json.loads(p.read_text()) for p in sorted((root / "fixtures" / "judge" / "outputs").glob("*.json"))}


def load_labels() -> dict[str, dict]:
    from eval.label_tool import read_labels
    return read_labels()


def load_split() -> dict[str, list[str]]:
    import yaml
    data = yaml.safe_load(SPLIT.read_text()) or {}
    return {k: list(data.get(k) or []) for k in ("examples", "tuning", "test")}


def _result(tool: str, result) -> str:
    """A tool's result as it came back; a search's JSON laid out one hit per line."""
    text = str(result)
    if tool == "code_search":
        try:
            data = json.loads(text)
            head = {k: v for k, v in data.items() if k != "results"}
            hits = [f"{h.get('path')}:{h.get('line')}  {h.get('excerpt')}" for h in data.get("results") or []]
            return json.dumps(head) + "\n" + "\n".join(hits)
        except (ValueError, AttributeError):
            pass
    return text


def render(o: dict, comment: str | None = None) -> str:
    """What the judge reads: the issue, every tool call with its result, the comment."""
    issue = o["issue"]
    out = [f"=== THE ISSUE: #{issue.get('number')}: {issue.get('title')}", str(issue.get("body") or "").rstrip(), "",
           "=== WHAT REPOMIND'S TOOLS RETURNED, IN ORDER"]
    for n, e in enumerate(o["evidence"], 1):
        out += ["", f"--- [{n}] {e['tool']} {json.dumps(e.get('input'))}",
                _result(e["tool"], e.get("result", "")).rstrip()]
    out += ["", "=== THE COMMENT", (comment if comment is not None else o["comment"]).rstrip()]
    return "\n".join(out)


def recorded_outputs() -> dict[str, dict]:
    """The last comment of every recorded run of the agent way that posted one, with
    its issue and every tool call before it, in the outputs' own shape."""
    from harness.trace import read_trace
    out = {}
    for path in sorted(TRACES.glob("*.jsonl")):
        if path.name.startswith("s27"):
            continue
        lines = read_trace(path)
        if not lines or lines[0].get("way") != "agent":
            continue
        calls = [x for x in lines if x.get("type") == "tool_call"]
        posted = [i for i, c in enumerate(calls) if c.get("name") in COMMENT_WRITES and not c.get("is_error")]
        if not posted:
            continue
        last = posted[-1]
        number = int(lines[0].get("issue"))
        out[lines[0].get("run_id") or path.stem] = {
            "id": lines[0].get("run_id") or path.stem, "system": lines[0].get("model"),
            "issue": _pool_issue(number),
            "evidence": [{"tool": c.get("name"), "input": c.get("input"), "result": c.get("result", "")}
                         for c in calls[:last]],
            "comment": str((calls[last].get("input") or {}).get("body") or "")}
    return out


def _pool_issue(number: int) -> dict:
    text = (POOL / f"{number}.md").read_text()
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    head, body = (m.group(1), m.group(2)) if m else ("", text)
    title = next((x.split(":", 1)[1].strip() for x in head.splitlines() if x.startswith("title:")), "")
    return {"number": number, "title": title, "body": body}


# -- the prompt --------------------------------------------------------------------------------------

def prompt_text() -> str:
    """prompts/judge.md with its examples filled in, each as labelled, with its reason."""
    split, labels, outputs = load_split(), load_labels(), load_outputs()
    stray = [i for i in EXAMPLES if i not in split["examples"]]
    if stray:
        sys.exit(f"the prompt's examples must come from the examples set; {', '.join(stray)} do not")
    blocks = []
    for n, i in enumerate(EXAMPLES, 1):
        reply = json.dumps({"reasoning": labels[i]["reason"], "answer": labels[i]["label"].capitalize()})
        blocks.append(f"### Example {n}\n\n{render(outputs[i])}\n\n=== THE REPLY\n{reply}")
    return PROMPT.read_text().replace("{{examples}}", "\n\n".join(blocks))


def prompt_hash() -> str:
    return hashlib.sha256(prompt_text().encode()).hexdigest()[:12]


def parse_reply(text: str) -> tuple[str | None, str]:
    """(answer, reasoning) from the judge's reply; answer None when there is none."""
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    m = re.search(r"\{.*\}", t, re.S)
    if m:
        try:
            data = json.loads(m.group())
            answer = str(data.get("answer") or "").strip().lower()
            if answer in ("pass", "fail"):
                return answer, " ".join(str(data.get("reasoning") or "").split())
        except ValueError:
            pass
    m = re.search(r'"answer"\s*:\s*"(pass|fail)"', t, re.I)
    return (m.group(1).lower(), "") if m else (None, "")


# -- running it --------------------------------------------------------------------------------------

def judge_all(name: str, items: dict[str, str], backend: str | None = None) -> list[dict]:
    """Judge every rendered item in one metered session; one verdict each."""
    system, digest = prompt_text(), prompt_hash()
    with judge_session(name, backend=backend) as session:
        def one(key: str) -> dict:
            for _ in range(2):                  # one retry on a reply with no answer
                response = session.client.create(system=system, messages=[{"role": "user", "content": items[key]}])
                session.trace.model_call(0, response, purpose="judge")
                answer, reasoning = parse_reply(response.text)
                if answer:
                    break
            return {"id": key, "answer": answer or "fail",
                    "reasoning": reasoning or f"no answer in the reply: {response.text[:120]!r}",
                    "session": session.id, "model": response.model, "prompt": digest}
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            return list(pool.map(one, sorted(items)))


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(f"wrote {len(rows)} verdicts to {path.relative_to(ROOT)}")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []


def where(name: str, backend: str | None) -> Path:
    return (SCRATCH if backend else VERDICTS) / f"{name}.jsonl"


def cmd_tune(which: str, backend: str | None) -> None:
    if which not in ("examples", "tuning"):
        sys.exit("tune reads the examples or the tuning set only; the test set is held out")
    ids, outputs, labels = load_split()[which], load_outputs(), load_labels()
    rows = judge_all(f"tune-{which}", {i: render(outputs[i]) for i in ids}, backend)
    TUNING.mkdir(parents=True, exist_ok=True)
    n = len(list(TUNING.glob(f"{which}_*.jsonl"))) + 1
    write_jsonl((SCRATCH if backend else TUNING) / f"{which}_{n}.jsonl", rows)
    verdicts = {r["id"]: r["answer"] for r in rows}
    tpr, tnr = rates(verdicts, {i: labels[i]["label"] for i in ids})
    print(f"{which}: TPR {tpr:.3f}, TNR {tnr:.3f}")
    for r in rows:
        if r["answer"] != labels[r["id"]]["label"]:
            print(f"  {r['id']}: judge {r['answer']}, label {labels[r['id']]['label']}: {r['reasoning']}")


def cmd_test(k: int, backend: str | None) -> None:
    ids, outputs = load_split()["test"], load_outputs()
    write_jsonl(where(f"test_{k}", backend), judge_all(f"test-{k}", {i: render(outputs[i]) for i in ids}, backend))


def cmd_versions(backend: str | None) -> None:
    ids, outputs = load_split()["test"], load_outputs()
    items = {f"{i}|{v}": render(outputs[i], outputs[i]["versions"][v]) for i in ids for v in ("list", "long")}
    rows = judge_all("versions", items, backend)
    for r in rows:
        r["id"], r["version"] = r["id"].split("|")
    write_jsonl(where("versions", backend), rows)


def cmd_recorded(backend: str | None) -> None:
    outs = recorded_outputs()
    write_jsonl(where("recorded", backend), judge_all("recorded", {i: render(o) for i, o in outs.items()}, backend))


# -- the numbers -------------------------------------------------------------------------------------

def numbers() -> dict:
    """Every number of LAB_07.json's judge, from the verdict files and the labels."""
    split, outputs = load_split(), load_outputs()
    labels = {i: r["label"] for i, r in load_labels().items()}
    test = split["test"]
    on_test = {i: labels[i] for i in test}
    runs = [{r["id"]: r for r in read_jsonl(VERDICTS / f"test_{k}.jsonl")} for k in (1, 2, 3)]
    if not all(sorted(r) == sorted(test) for r in runs):
        sys.exit("test_1, test_2 and test_3 must each judge exactly the test set")
    hashes = {r["prompt"] for run in runs for r in run.values()}
    v1 = {i: runs[0][i]["answer"] for i in test}
    tpr, tnr = rates(v1, on_test)
    recorded = read_jsonl(VERDICTS / "recorded.jsonl")
    p = sum(r["answer"] == "pass" for r in recorded) / len(recorded) if recorded else None
    try:
        corrected = correct(p, tpr, tnr) if p is not None else None
        lo, hi = bootstrap(v1, on_test, p) if p is not None else (None, None)
        coin = False
    except CoinJudge as exc:
        print(f"refused to correct: {exc}")
        corrected, lo, hi, coin = None, None, None, True
    flips = [i for i in test if len({run[i]["answer"] for run in runs}) > 1]
    maj = {i: "pass" if sum(run[i]["answer"] == "pass" for run in runs) >= 2 else "fail" for i in test}
    m_tpr, m_tnr = rates(maj, on_test)
    versions = read_jsonl(VERDICTS / "versions.jsonl")
    moved = sorted({v["id"] for v in versions if v["answer"] != v1[v["id"]]})
    moved_by = {k: sorted(v["id"] for v in versions if v["version"] == k and v["answer"] != v1[v["id"]])
                for k in ("list", "long")}
    by_system = {}
    for system in sorted({outputs[i].get("system") for i in test}):
        s_tpr, s_tnr = rates(v1, {i: on_test[i] for i in test if outputs[i].get("system") == system})
        by_system[system] = {"tpr": round(s_tpr, 4), "tnr": round(s_tnr, 4)}
    model = sorted({r["model"] for run in runs for r in run.values()})
    r4 = lambda x: None if x is None else round(x, 4)
    return {
        "split": {k: len(v) for k, v in split.items()},
        "model": model[0] if len(model) == 1 else model, "tpr": r4(tpr), "tnr": r4(tnr), "p": r4(p),
        "corrected": r4(corrected), "interval": None if lo is None else [r4(lo), r4(hi)], "coin": coin,
        "flip_rate": r4(len(flips) / len(test)),
        "majority": {"tpr": r4(m_tpr), "tnr": r4(m_tnr), "kept": (m_tpr + m_tnr) > (tpr + tnr)},
        "moved_share": r4(len(moved) / len(test)),
        "by_system": by_system,
        "_detail": {"flips": flips, "moved": moved, "moved_by_version": moved_by, "prompt_hashes": sorted(hashes),
                    "n_recorded": len(recorded), "test_passes": sum(x == "pass" for x in on_test.values()),
                    "test_fails": sum(x == "fail" for x in on_test.values()),
                    "wrong_run1": {i: (v1[i], on_test[i], runs[0][i]["reasoning"]) for i in test if v1[i] != on_test[i]},
                    "by_system_n": {s: {"pass": sum(on_test[i] == "pass" for i in test if outputs[i].get("system") == s),
                                        "fail": sum(on_test[i] == "fail" for i in test if outputs[i].get("system") == s)}
                                    for s in by_system}}}


def cmd_report(write: bool) -> None:
    n = numbers()
    detail = n.pop("_detail")
    print(json.dumps(n, indent=2))
    print(json.dumps(detail, indent=2))
    if write:
        PERSON.write_text("".join(f"{i}\n" for i in detail["flips"]))
        report = json.loads(REPORT_JSON.read_text())
        report["judge"] = n
        REPORT_JSON.write_text(json.dumps(report, indent=2) + "\n")
        print(f"wrote {PERSON.relative_to(ROOT)} ({len(detail['flips'])} items) and the judge into "
              f"{REPORT_JSON.relative_to(ROOT)}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["tune", "test", "versions", "recorded", "report", "prompt"])
    p.add_argument("arg", nargs="?")
    p.add_argument("--backend", help="e.g. harness.scripted:PassEverything, to test the plumbing for nothing")
    p.add_argument("--write", action="store_true", help="report: write for_a_person.txt and LAB_07.json's judge")
    args = p.parse_args(argv)
    if args.command == "tune":
        cmd_tune(args.arg or "tuning", args.backend)
    elif args.command == "test":
        cmd_test(int(args.arg or 1), args.backend)
    elif args.command == "versions":
        cmd_versions(args.backend)
    elif args.command == "recorded":
        cmd_recorded(args.backend)
    elif args.command == "prompt":
        print(prompt_text())
        print(f"\n(prompt hash {prompt_hash()}, {len(prompt_text()):,} characters)")
    else:
        cmd_report(args.write)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
