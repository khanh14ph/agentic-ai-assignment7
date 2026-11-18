"""Assignment 7, Part D, task 2: read the 60 outputs and record your hand labels.

    python -m eval.label_tool export          # one readable page per output: eval/labels/view/jNN.md
    python -m eval.label_tool label           # label the outputs not yet labelled, one by one
    python -m eval.label_tool label j07       # (re)label one output
    python -m eval.label_tool status          # how many are labelled, and which are not

This tool only shows each output and writes down what you decide. It analyses
nothing and suggests nothing: no label in eval/labels/labels.csv may come from a
model or from code, because the judge is measured against these labels.

A page shows, in order: the issue as RepoMind read it; every tool call RepoMind made
before its comment, with exactly what it returned (a file read returns the file's
text without line numbers; a search hit carries its line); and the comment.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from harness import ROOT

OUTPUTS = ROOT / "fixtures" / "judge" / "outputs"
LABELS = ROOT / "eval" / "labels" / "labels.csv"
VIEW = ROOT / "eval" / "labels" / "view"


def load_outputs() -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text()) for p in sorted(OUTPUTS.glob("*.json"))}


def read_labels() -> dict[str, dict]:
    if not LABELS.exists():
        return {}
    with LABELS.open(newline="") as fh:
        return {row["id"].strip(): {"label": row["label"].strip().lower(), "reason": row["reason"].strip()}
                for row in csv.DictReader(fh) if row.get("id")}


def write_labels(labels: dict[str, dict]) -> None:
    LABELS.parent.mkdir(parents=True, exist_ok=True)
    with LABELS.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "label", "reason"])
        for i in sorted(labels):
            w.writerow([i, labels[i]["label"], labels[i]["reason"]])


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


def page(o: dict) -> str:
    issue = o["issue"]
    out = [f"# {o['id']}", "", f"## The issue: #{issue.get('number')}: {issue.get('title')}", "", "```text",
           str(issue.get("body") or "").rstrip(), "```", "",
           "## What RepoMind's tools returned, in order", ""]
    for n, e in enumerate(o["evidence"], 1):
        out += [f"### [{n}] {e['tool']} {json.dumps(e.get('input'))}", "", "```text",
                _result(e["tool"], e.get("result", "")).rstrip(), "```", ""]
    out += ["## The comment", "", "```text", o["comment"].rstrip(), "```", ""]
    return "\n".join(out)


def export() -> None:
    VIEW.mkdir(parents=True, exist_ok=True)
    outputs = load_outputs()
    for i, o in outputs.items():
        (VIEW / f"{i}.md").write_text(page(o))
    print(f"wrote {len(outputs)} pages to {VIEW.relative_to(ROOT)}/ (open them in your editor's Markdown preview)")


def ask(prompt: str, allowed: set[str] | None = None) -> str:
    while True:
        try:
            answer = input(prompt).strip()
        except EOFError:
            sys.exit("\nstopped; what you labelled so far is saved")
        if allowed is None and answer:
            return answer
        if allowed is not None and answer.lower() in allowed:
            return answer.lower()


def label(only: str | None) -> None:
    outputs, labels = load_outputs(), read_labels()
    todo = [only] if only else [i for i in outputs if i not in labels]
    if only and only not in outputs:
        sys.exit(f"no output {only}")
    for i in todo:
        print("\n" + "=" * 100 + "\n" + page(outputs[i]))
        if i in labels:
            print(f"(now: {labels[i]['label']}, {labels[i]['reason']})")
        choice = ask(f"{i}: [p]ass, [f]ail, [s]kip, [q]uit? ", {"p", "f", "s", "q"})
        if choice == "q":
            break
        if choice == "s":
            continue
        reason = ask("one line, how you know: ")
        labels[i] = {"label": "pass" if choice == "p" else "fail", "reason": reason}
        write_labels(labels)
    status()


def status() -> None:
    outputs, labels = load_outputs(), read_labels()
    missing = [i for i in outputs if i not in labels]
    bad = [i for i, r in labels.items() if r["label"] not in ("pass", "fail") or not r["reason"]]
    print(f"{len(labels)} of {len(outputs)} labelled; missing: {', '.join(missing) or 'none'}; "
          f"without a pass/fail or a reason: {', '.join(bad) or 'none'}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["export", "label", "status"])
    p.add_argument("id", nargs="?")
    args = p.parse_args(argv)
    {"export": export, "status": status}.get(args.command, lambda: label(args.id))()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
