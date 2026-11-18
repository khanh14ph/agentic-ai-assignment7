"""Assignment 7, Part D, task 3: split the 60 labelled outputs into examples, tuning and
test (slide 42; checks/FORMATS.md, section 15.9), once, before the judge is written.

    python -m eval.split_07            # writes eval/labels/split.yaml from eval/labels/labels.csv

The split is seeded and stratified: the outputs are grouped by your label and by the
system that wrote them, each group is shuffled with a fixed seed, and the groups are
dealt out in turn, so every set gets its share of passes and fails from both systems.
The first 9 dealt (15%) are the examples set, the next 25 (42%) the tuning set and the
last 26 (43%) the test set, held out. The examples set must hold at least one pass and
one fail, for the judge's prompt; the script refuses otherwise. Commit the file on its
own, before eval/judge.py or prompts/judge.md changes:

    git add eval/labels/split.yaml && git commit -m "Assignment 7, Part D: the split"
"""

from __future__ import annotations

import random
import sys

from eval.label_tool import LABELS, load_outputs, read_labels
from harness import ROOT

SEED = 7
SIZES = {"examples": 9, "tuning": 25, "test": 26}
SPLIT = ROOT / "eval" / "labels" / "split.yaml"


def deal(labels: dict[str, dict], outputs: dict[str, dict], seed: int = SEED) -> list[str]:
    """Every ID once, groups (label, system) shuffled and dealt in turn."""
    rng = random.Random(seed)
    groups: dict[tuple, list[str]] = {}
    for i in sorted(outputs):
        groups.setdefault((labels[i]["label"], outputs[i].get("system")), []).append(i)
    for ids in groups.values():
        rng.shuffle(ids)
    order, queues = [], [groups[k] for k in sorted(groups)]
    while any(queues):
        for q in queues:
            if q:
                order.append(q.pop())
    return order


def main() -> int:
    outputs, labels = load_outputs(), read_labels()
    missing = sorted(set(outputs) - set(labels))
    if missing or any(r["label"] not in ("pass", "fail") or not r["reason"] for r in labels.values()):
        sys.exit(f"label every output first, each pass or fail with a reason ({LABELS.relative_to(ROOT)}); "
                 f"missing: {', '.join(missing) or 'none'}")
    order = deal(labels, outputs)
    a, b = SIZES["examples"], SIZES["examples"] + SIZES["tuning"]
    parts = {"examples": sorted(order[:a]), "tuning": sorted(order[a:b]), "test": sorted(order[b:])}
    if {labels[i]["label"] for i in parts["examples"]} != {"pass", "fail"}:
        sys.exit("the examples set needs a pass and a fail; your labels may be nearly all one way")
    lines = ["# Part D's split (slide 42), made by eval/split_07.py from eval/labels/labels.csv:",
             f"# stratified by label and system, seed {SEED}. Committed on its own, before the judge.", ""]
    for name, ids in parts.items():
        lines.append(f"{name}: [{', '.join(ids)}]")
    SPLIT.write_text("\n".join(lines) + "\n")
    for name, ids in parts.items():
        passes = sum(labels[i]["label"] == "pass" for i in ids)
        systems = sorted({outputs[i].get("system") for i in ids})
        print(f"{name:<9} {len(ids):>2} outputs: {passes} pass, {len(ids) - passes} fail; systems {systems}")
    print(f"wrote {SPLIT.relative_to(ROOT)}; commit it on its own before the judge is written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
