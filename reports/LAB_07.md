# Assignment 7 · The evaluation harness, and a judge you have checked

Model: Google `gemini-3.5-flash-lite`, through its OpenAI-compatible API, the same for every run and for the judge. (The 60 recorded runs in `fixtures/traces7/` were made on `claude-haiku-5-5`, the course's model, not this one.)

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
- One table from your Part C results, as the harness reports it (runs, spread, pass@k and pass^k with *k*), from `python -m eval.results_07 --report`:

  | Arm | Runs | Sweeps | Wasted calls: mean (SD) | Score: mean (SD) | pass@3 | pass^3 | Facts right | Cost per run |
  |---|---|---|---|---|---|---|---|---|
  | A, planned | 50 | 5 | 2.98 (0.78) | 26.0 (11.4) | 0.50 | 0.05 | 0.765 | $0.0069 |
  | B, planned, examples off | 50 | 5 | 4.76 (0.86) | 2.0 (4.5) | 0.06 | 0.00 | 0.658 | $0.0059 |

  The five trajectory metrics, as means per run:

  | Arm | Step count | Precision | Recall | Repeats | Orphans | Latency (s) | No tools |
  |---|---|---|---|---|---|---|---|
  | A | +0.90 | 0.85 | 0.91 | 0.48 | 2.56 | 7.5 | 1 |
  | B | +1.26 | 0.84 | 0.82 | 1.22 | 3.88 | 7.7 | 1 |

  Every SD is over five sweep values; a sweep is one run of the arm on each of the subset's ten tasks. Arm A's gap between pass@3 (0.50) and pass^3 (0.05) is the difference between "can it?" and "does it, every time?". Half of the tasks have at least one passing run in three, but almost none pass in all three.

## Part C · Settle one claim

- The claim, its two arms, the measure and the sign of the gain: Lecture 3's claim that **tool examples improved parameter handling**. Arm A is the planned way as it is, with every tool description ending in its examples. Arm B is the same way with `TOOL_EXAMPLES=off`. The measure is **wasted calls per run**: calls the registry refused or that failed in the tool, plus searches that found nothing. The claim predicts fewer in A, so the gain is **B − A**. The subset is 10 tasks, 2 or 3 per stratum (`eval/subsets/claim.txt`, commit `6ba051e`, pushed before any Part C run).
- The first three sweeps: each arm's *s*, and the cost of one sweep: from those sweeps I took only the spreads and the cost, and did not compare the arms. **s_A = 0.31** and **s_B = 0.81** wasted calls per run. One sweep cost **$0.0624** on average over both arms. Three values make a rough SD, and it showed: over all five sweeps s_A came out 0.78, so the first three underestimated arm A's spread.
- *δ*, the sweeps it needs, and the price (slide 55): **δ = 0.2** wasted calls per run, chosen before the spreads were seen. The examples lengthen every tool definition on every model call, and a smaller saving would not repay that. **n ≥ (0.31² + 0.81²) × (2.80 / 0.2)² = 148.3, so 149 sweeps per arm**, priced at 149 × 2 × $0.0624 = **$18.60**, against $0.62 for the five sweeps run. Sized for a gain as small as δ, this budget could not settle the claim. It could only settle a much larger gain, which is what came.
- The bar and the group rule, as committed, and the commit: the claim holds if the interval's low end is above **0** and no stratum's gain is below **−0.3**. A 2-task stratum moves by 0.5 for one extra wasted call in one sweep, so −0.3 allows that much noise and no more. k = 3, five sweeps. Prediction: arm A, by 0.2, largest in the unusual stratum. In `eval/thresholds/claim.yaml`, commit `d998e29` at 04:30:27, eight seconds before the first fourth-sweep run started (04:30:35), and pushed.

**The results**, from `results/`.

| Arm | Runs | Measure: mean (SD) | Score: mean (SD) | pass@3 | pass^3 | Facts right | Cost per run |
|---|---|---|---|---|---|---|---|
| A | 50 | 2.98 (0.78) | 26.0 (11.4) | 0.50 | 0.05 | 0.765 | $0.0069 |
| B | 50 | 4.76 (0.86) | 2.0 (4.5) | 0.06 | 0.00 | 0.658 | $0.0059 |

| Arm | Stratum | Runs | Measure | Score | pass@3 | pass^3 |
|---|---|---|---|---|---|---|
| A | routine | 15 | 2.80 | 20.0 | 0.50 | 0.00 |
| A | unusual | 10 | 3.40 | 0.0 | 0.00 | 0.00 |
| A | adversarial | 15 | 2.27 | 60.0 | 0.97 | 0.17 |
| A | should-not-act | 10 | 3.90 | 10.0 | 0.30 | 0.00 |
| B | routine | 15 | 4.87 | 6.7 | 0.20 | 0.00 |
| B | unusual | 10 | 4.20 | 0.0 | 0.00 | 0.00 |
| B | adversarial | 15 | 5.07 | 0.0 | 0.00 | 0.00 |
| B | should-not-act | 10 | 4.70 | 0.0 | 0.00 | 0.00 |

| Stratum | Gain (B − A) | 95% interval |
|---|---|---|
| All tasks | 1.78 | 0.76 to 2.80 |
| routine | 2.07 | 0.59 to 3.55 |
| unusual | 0.80 | −1.14 to 2.74 |
| adversarial | 2.80 | 1.88 to 3.72 |
| should-not-act | 0.80 | −0.78 to 2.38 |

- The verdict, by your bar, and why: **holds.** The interval's low end, 0.76, clears the bar of 0, and every stratum's gain is positive, so none breaks the −0.3 floor. Unusual and should-not-act cannot show a gain on their own: their intervals cross 0. Most of the waste is **refused calls, not empty searches**. Of the 149 wasted calls in arm A, 19 were searches that found nothing; of 238 in B, 15. The rest were calls the registry refused, almost all for **empty arguments (`{}`)** or **the wrong issue form (`"4601"`, `"#4615"` instead of `issue-4601`)**. They trace back to the plan. The planner writes each step's arguments as a JSON string (`args_json`). When that string does not parse, `agent/diff.py`'s `step_args` silently turns it into `{}`, and a step with nothing to fill calls its tool with `{}`. In the first plan's first step, the arguments were usable in 33 of 50 runs with examples and in 11 of 50 without. In B, 22 were unparsable and 16 named the issue wrongly; the issue-ID form is exactly what the examples show. So the examples do help parameter handling, by a lot, on this model. The refusals also explain the low scores. A run whose same step is refused three times escalates and ends held, with no comment: 27 of B's 50 runs ended held, and 4 of A's.
- Cost beside the score (slide 54): arm A costs about 17% more per run ($0.0069 against $0.0059) because every tool definition carries its examples: 11,895 tokens per run against 8,759. It is far more accurate, 26% against 2%. Per passing run that is **$0.027 for A against $0.29 for B**, so the extra cost buys accuracy. Neither arm is good, though: on this model, RepoMind passes a quarter of the subset at best.
- Each part of your prediction that missed, and the run that shows why:
  - **The arm: right.** A wastes fewer calls.
  - **"By 0.2": missed; the gain was 1.78.** I believed the waste would be mostly empty searches, about 0.25 per run in the recorded planned runs, so examples could save at most a fraction of that. That baseline came from another model. On Gemini the waste is malformed arguments, and there are many more of them. `planned-g01-s05-a04b2f` (arm B) shows it: `issues_read` with `"4601"`, then `code_search`, `issues_read`, `code_read_file` and `issues_comment` all with `{}`, all refused. The only call that went through was the label.
  - **"Largest in unusual": missed.** Adversarial had the largest gap (2.80) and unusual one of the smallest (0.80). I reasoned that unusual issues have no quoted error text, so unexampled searches would miss there. But the waste does not come from searches; it comes from broken plans, which are no likelier on one issue than another. Unusual's gap is small because arm A had broken plans there too. `planned-g12-s02-a0e82d` (arm A, with examples) had an unparsable plan: 7 refused calls and one search for the issue's own ID, `issue-4615`. Adversarial's gap is large mostly because arm A's plans happened to work there: g23 passed 4 of 5 in A and 0 of 5 in B. With 2 or 3 tasks a stratum, where the gap is largest is mostly chance.

**Where the failed runs first went wrong** (slide 29), last good step down the side, first wrong step across.

```
Arm A (37 failed runs)  code_read_file  code_search  issues_label  issues_read  pulls_open
  code_read_file                                            3
  code_search                       10            1
  issues_label                                                                          1
  issues_read                                     6
  start                                                                   16

Arm B (49 failed runs)  code_read_file  code_search  issues_label  issues_read  pulls_open  stop
  code_read_file                                            3
  code_search                        1            1
  issues_label                                                                          1     1
  issues_read                                     3
  start                                                                   38                  1
```

`python -m eval.failures_07` marks every failed run, 86 in all, and prints each mark with its reason. The rule:
- A refused call is the first wrong step **unless the run later makes the same call successfully**.
- On a stop task, the first call after reading the issue is the first wrong step.
- Otherwise it is the first triage write made before the run read the file at fault, or one that says what the label does not.

Reading the marks: `issues_read → code_search` is the should-not-act runs going on to triage after reading an issue they should leave alone. `code_search → code_read_file` in A is a file-read step sent with `{}`.

- The biggest count, and whether its cause is local, upstream or structural: **start → `issues_read`**, 16 in A and 38 in B. The run's very first call, reading the issue, went out malformed and was never made right, so it never saw the issue and everything after was a guess. The cause is **upstream**: the executor forwards the arguments the planner wrote, and those were unparsable or named the issue wrongly before any call ran. A **structural** flaw lets it through: `step_args` turns arguments it cannot parse into `{}` instead of failing the plan's schema check, so a plan that cannot run passes validation. A's `code_search → code_read_file` count (10) is the same cause, one step later.
- How a replay from Assignment 4's checkpoints would confirm it: resume a failed run from its checkpoint, for example `python run.py --resume planned-g12-s05-212e1c`. The checkpoint holds the plan and each step's status. A step with no `$fill` calls its tool with the plan's arguments and never asks the model, so a replay with the plan unchanged should reproduce the same refused `{}` call every time. That would show the fault is in the plan, not in the executor's sampling. A replay of the same checkpoint with only step 1's `args_json` corrected to `{"issue": "issue-4615"}` should then read the issue and go on. If it does, the plan's argument was the cause.
- Runs that called no tool: **2, one in each arm** (`planned-g28-s01-4cf8b5` in A, `planned-g09-s04-88a08a` in B). In both, the planner wrote steps with no tool names three times, the run escalated with no valid plan, and it never made a call (slide 28). A's was on the closed duplicate (g28), where changing nothing is right, so it **passed by accident**, as `planned-issue-4621` did in Part A. The grounded check sees only the end state; the trajectory shows there was no decision at all.

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
- Part C, run and drafted with Claude Code (Claude Opus 5.5). You chose the claim (tool examples) and let it draft the prediction. It wrote the subset, `claim.yaml` (bar, group rule, δ and prediction), `eval/failures_07.py`, and section C. It ran the 100 runs and committed and pushed at the required points. Before writing the bar it computed only the spreads and the cost; the arms were compared only after the bar was pushed. *To check:* the δ and bar reasoning in `claim.yaml`, and a few of the first-failure marks against their traces (`python -m eval.failures_07` prints each with its reason).
