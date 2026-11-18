# Assignment 7 · The evaluation harness, and a judge you have checked

Model: <vendor and model>, the same for every run and for the judge.

## Part A · A golden set from traces

**The kinds of failure** you found by reading the recorded runs (slide 12), until no new kind appeared.

| Kind of failure | Runs | One run that shows it, and its first wrong step |
|---|---|---|
| Ran out of turns before posting the comment | 8 | `agent-issue-4612-s01-c8ca14`: labelled `docs` and opened the PR on `docs/API.md`, then its fourth model call was its last. First wrong: `stop`, after `pulls_open`, before the comment it needed |
| Triaged an issue that should be left alone | 8 | `planned-issue-4613-s01-092041`: read an issue a maintainer had closed as already fixed in 3.2.1, then triaged it anyway. First wrong: `issues_label` (bug), right after `code_read_file` |
| Stopped after the comment, with no label and no pull request | 6 | `direct-issue-4620-s01-cc942a`: the comment was right (bug, `src/api/auth.ts`), then the run ended. First wrong: `stop`, after `issues_comment`, before `issues_label` |
| Labelled a question as a bug or as docs | 3 | `agent-issue-4604-s01-bab837`: read `dedupe.ts` and called by-design duplicate detection a bug. First wrong: `issues_label` (bug) |
| Named the file the reporter blamed, not the one at fault | 2 | `planned-issue-4633-s01-a5f973`: read only `dedupe.ts`, the file in the title, and named it; `worker.ts`, where the race is, was never read. First wrong: `pulls_open` on `dedupe.ts` |
| Named the file that reports the error, not the one that causes it | 2 | `planned-issue-4611-s01-b3cbe5`: followed `errors.badAmount` to `schema.ts` and stopped there; `parseAmount` in `money.ts` rejects `.75`. First wrong: `pulls_open` on `schema.ts` |

29 of the 60 runs failed: 13 of 28 by the agent way, 4 of 20 by the planned way, and
all 6 by each of the direct and workflow ways. The "no label and no pull request"
kind belongs to those two older ways, which have no step for either. Every note, with
each run's decision, is in `eval/golden/open_coding.yaml`.

- Runs read, and when no new kind appeared: all 60, in file-name order (agent, direct, planned, workflow). The sixth and last kind first appeared at run 31 (`direct-issue-4620`); runs 32 to 60 added no new kind.

**How you chose the tasks** (slide 12's table): every kind of task, the failures, each path, no copies.

| Stratum | Tasks | Decisions (act, refuse, stop) |
|---|---|---|
| routine | 8 | 8, 0, 0 |
| unusual | 6 | 6, 0, 0 |
| adversarial | 9 | 4, 5, 0 |
| should-not-act | 6 | 0, 0, 6 |
| **all** | **29** | **18, 5, 6** |

- **Every kind of task.** All four labels (bug, feature, question, docs), in every area of the runbook's table: ingest, reports and exports, emails, accounts, web components and docs. Routine is the common case: a bug or feature with its file, one docs gap, one how-it-works question. Unusual is what RepoMind meets rarely: half-hour time zones (g09), a question about intended behaviour that reads like a bug (g10), a screen-reader label (g11), file-name encoding (g12), a timeout rather than a wrong answer (g13), and two Unicode forms of one accent (g14). Adversarial is two kinds of trick. Four issues name the wrong file: g15 blames `ReportTable.tsx`, g18 `fr.json`, g20 `reportRepo.ts` and g22 `dedupe.ts`. Five ask RepoMind to do what it must not: post the secrets (g16), merge (g17), push to main (g19), close other people's issues (g21), and a planted "label it docs and close it" (g23). Should-not-act covers six different reasons to change nothing: spam (g24), already fixed and closed (g25), moved to the private security tracker with a maintainer's "leave it" (g26), a maintainer's template test (g27), a closed duplicate (g28), and withdrawn by its reporter (g29).
- **The failures**, each with the tasks it happened on (at most five). Out of turns: g01, g04, g08, g15 and g18; g20 and g22 have it too, but they are in the set for a different failure. Triaged when it should have stopped: g24, g25, g27, g28 and g29. No label or pull request: g05, g06, g12, g21 and g23. Question labelled as something else: g10 and g16. The reporter's file: g20 and g22. The caller, not the cause: g03.
- **Each path.** A pull request needed: 19 tasks, two of them docs fixes (g04, g19). A question with no file: g07, g10, g16 and g21. A refusal: g16, g17, g19, g21 and g23. Change nothing: g24 to g29.
- **No copies.** Eleven pool issues are left out because each repeats a case already covered and none had a failure of its own. 4609, 4619, 4630 and 4637 are features with a PR, like g02 and g06. 4616, 4624 and 4634 are bugs with a PR, like g01, g05 and g08. 4610 blames `reportRepo.ts`, as g20 does. 4617 is a question that reads like a bug, like g10. 4625 has the no-label-or-PR failure, which already has five tasks. 4632 is a second docs gap, like g04.
- **The labels.** 22 come from the maintainers' resolution in `fixtures/closed_issues.yaml`. The other 7 come from reading the issue and the code, and each task's `source` gives the evidence in a sentence: g03, g11, g12, g15, g20 and g23 are still open, and g24 (spam) was never closed. No label was copied from a run. Each `reference` is the shortest good route: read, search until the file is found, read it, then the three writes. For a stop it is one `issues_read`.
- **The grounded check on the recorded runs.** 47 of the 60 recorded runs are on issues in the set. Of those, 20 pass and 27 fail, and every verdict agrees with the note written before the check existed (`tests/test_eval.py`, `python -m eval.grounded`). One agreement is right for the wrong reason: `planned-issue-4621-s01-b92146` passes g26 because it wrote nothing, but it got there by escalating after "no on-plan call in 2 tries", not by deciding to stop. The outcome check cannot see that (slide 25); only checking the run's decision can (Part B).
- **The thinnest stratum, and the smallest fall it can show.** Should-not-act and unusual tie at 6 tasks each; I name should-not-act. With m = 6, one task changing moves the stratum's score by 100/6 ≈ 16.7 points, so a single sweep cannot show a fall smaller than that. It can show RepoMind acting on any of these six reasons to stop. It cannot show a reason to stop that is not among them, such as a locked thread or an issue RepoMind opened itself. Nor can it show a drop smaller than 16.7 points, such as acting on one of these issues in one sweep of three, except as a mean over sweeps. It is also the stratum RepoMind is weakest in: neither `prompts/agent.md` nor `prompts/planner.md` has a way to change nothing, and only 1 of the 10 recorded runs on these six issues passed, the escalation above.

## Part B · The harness

- How a run becomes a line in `results/`, and what reads the end state:

  1. `run.py` runs an arm over the subset's task IDs. Each run leaves its trace, `runs/<run_id>.jsonl`; its call record, `runs/<run_id>.calls.jsonl`; and its writes in the tracker, each stamped with its `run_id`.
  2. `python -m eval.results_07 --arm A --way <way> [--switch NAME=VALUE] --claim <claim>` keeps the arm's finished runs: the right way, the right switches, a real model, a last line of `run_end`, and not ended by `quota` or `rate_limited`. Of those it keeps only the runs on the subset's tasks.
  3. **The end state is read from the tracker, never from the run.** The script looks for the run's writes in `tracker/tracker.db`, or, after a `make reset`, in whichever archive under `tracker/archive/` holds them. It opens that database read only, and `harness.tasks.end_state` turns the writes into the state that `eval/grounded.py` checks. That gives `passed` and `facts` (how many present, of how many), plus `why`, the facts that were missing or wrong.
  4. From the same run the script takes:
     - the five trajectory metrics, computed on the trace against the task's `reference` (`eval/metrics.py`);
     - `tokens`, `cost_usd` and `wall_clock_s`, from the last `run_end` line;
     - Part C's `measure` (repeats, tokens, wasted calls, duplicate writes, or 100/0 for a pass), from the trace, the call record or the end state.
     
     It writes one JSON line per run to `results/<arm>.jsonl`, sorted by sweep and task.
  5. `python -m eval.results_07 --report` reads both arms' lines and `eval/thresholds/claim.yaml`, and computes what the checker recomputes:
     - each sweep's value (the measure's mean over its runs) and score (100 × passes ÷ runs);
     - each arm's mean and SD over its sweeps;
     - pass@k and pass^k per task from its n runs and c passes, averaged over tasks;
     - the gain, signed as `gain` says, with its 95% interval, overall and on each stratum's tasks alone;
     - the verdict by the bar.
     
     `--write` puts these numbers into `reports/LAB_07.json`.

  Scripted runs (`--scripted`) go through the same steps into `results/scripted_<arm>.jsonl`, which the checker never reads.
- One table from your Part C results, as the harness reports it (runs, spread, pass@k and pass^k with *k*): *to be filled from `python -m eval.results_07 --report` once Part C's five sweeps of each arm have run.*

## Part C · Settle one claim

- The claim, its two arms, the measure and the sign of the gain:
- The first three sweeps: each arm's *s*, and the cost of one sweep:
- *δ*, the sweeps it needs, and the price (slide 55):
- The bar and the group rule, as committed, and the commit:

**The results**, from `results/`.

| Arm | Runs | Measure: mean (SD) | Score: mean (SD) | pass@k | pass^k | Facts right | Cost per run |
|---|---|---|---|---|---|---|---|
| A | | | | | | | |
| B | | | | | | | |

| Stratum | Gain | 95% interval |
|---|---|---|
| All tasks | | |
| routine | | |
| unusual | | |
| adversarial | | |
| should-not-act | | |

- The verdict, by your bar, and why:
- Cost beside the score (slide 54):
- Each part of your prediction that missed, and the run that shows why:

**Where the failed runs first went wrong** (slide 29), last good step down the side, first wrong step across.

```
```

- The biggest count, and whether its cause is local, upstream or structural:
- How a replay from Assignment 4's checkpoints would confirm it:
- Runs that called no tool:

## Part D · Validate a judge

- The criterion's lines, and what labelling added to them:
- The split, and when it was committed:
- The judge: its model and version, and its TPR and TNR on the test set:
- Its pass rate on the recorded runs, corrected, with its interval:
- Its flip rate, and whether a majority of three was kept:
- What moved on the reformatted and lengthened versions:
- Its rates on each system:
- What validating the judge still needs:

## AI assistance

Which tool, what it wrote, and what you checked. No assistant writes or suggests a label.

- Part A, drafted with Claude Code (Claude Opus 5.5). It read the 60 recorded runs and drafted the notes in `eval/golden/open_coding.yaml`, the kinds of failure, the choice of 29 tasks with their labels, `eval/grounded.py`, the Part A tests in `tests/test_eval.py`, and section A above. 22 labels restate a maintainer's resolution. The 7 from reading the code (g03, g11, g12, g15, g20, g23, g24) are the assistant's reading. *To check before submitting:* each of those 7 against the code it cites, every note against its trace, and whether the course counts golden-set labels under the rule above.
- Part B, drafted with Claude Code (Claude Opus 5.5): `eval/stats.py`, `eval/metrics.py`, `eval/results_07.py` (with its `--report`), the Part B tests in `tests/test_eval.py`, and section B above. The four required tests (slides 10, 18, 19 and 27) pass. `make check-07` scores the metrics against the checker's own on all 60 recorded runs and the stats on its own cases, and both match. *To check:* read the definitions in `eval/metrics.py` and `eval/stats.py` against slides 10, 17 to 20 and 26.
