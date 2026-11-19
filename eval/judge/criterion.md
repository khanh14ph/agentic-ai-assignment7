# The judge's criterion

<!-- Drafted with Claude Code at the student's request (see reports/LAB_07.md, AI
     assistance). Add a line under "Added while labelling" when an output doesn't fit. -->

## The question

Does the comment cite only evidence that is in the issue or in what RepoMind's tools
returned?

## Pass

Everything the comment states as fact can be found in the issue or in a tool result.

These are always fine: the `label:`, `file:` and disclosure lines; reasoning and
suggested fixes; general programming knowledge; anything marked as uncertain ("I did
not run the tests").

Whether the label or file is correct does not matter here.

## Fail

At least one fact is in neither the issue nor any tool result. One is enough.

## Kinds of unsupported evidence

- **A file it never read**: it quotes or describes a file that no read returned. (A
  path seen in a search result is fine as a path.)
- **Code that isn't in the evidence**: a function, name, quote or behaviour that no
  tool result shows.
- **A line number no search showed**: file reads have no line numbers; only search
  results do.
- **An error message the issue doesn't contain**: and no tool result contains either.
- **A number or reference from nowhere**: a version, limit, or issue or PR number not
  in the evidence. (Its own PR, from the `pulls_open` result, is fine.)
- **Something no tool can see**: test results, CI runs, logs, the database.
- **An action it never took**: "I checked", "I ran the tests", with no call to show it.

## Added while labelling

<!-- each line labelling adds, and the outputs it changed -->
