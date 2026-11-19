You check one comment that RepoMind, an automated triage agent, posted on a GitHub-style
issue. You are given, in order: the issue, every tool call RepoMind made before the
comment with exactly what each returned, and the comment. You answer one question.

## The question

Does the comment cite only evidence that is in the issue or in what RepoMind's tools
returned?

## Pass

Everything the comment states as fact can be found in the issue or in a tool result.

These are always fine, and never a reason to fail:
- the `label:` and `file:` lines, and the line saying RepoMind wrote the comment;
- reasoning, explanation and a suggested fix, built on facts that are in the evidence;
- general programming knowledge: how a language, library, framework or database
  behaves in general;
- anything the comment marks as uncertain or not done ("I did not run the tests");
- its own pull request, whose number is in the `pulls_open` result.

Whether the label or the file is the right one does not matter here. Judge only
whether what it states is backed by the issue or the tool results.

## Fail

At least one fact the comment states is in neither the issue nor any tool result. One
is enough. The kinds of unsupported evidence:
- **A file it never read**: it quotes or describes the contents of a file that no read
  returned. A path seen in a search result is fine as a path; the search hit's excerpt
  line is fine too.
- **Code that isn't in the evidence**: a function, name, call, quote or behaviour that
  no tool result shows, or one that the code it read says otherwise about.
- **A line number no search showed**: a file read has no line numbers; only search hits
  carry a line, written `path:line`. A line number in the comment is supported only when
  a search hit shows that same file at that same line. Any other line number fails, even
  when the code it points at is real and was read: do not count lines in a read.
- **An error message the issue doesn't contain**, and no tool result contains either.
- **A number or reference from nowhere**: a version, a limit, an issue or pull request
  number, a quote from a person, that is not in the evidence.
- **Something no tool can see**: test results, CI runs, logs, the database's contents.
- **An action it never took**: "I checked", "I ran the tests", "I reproduced it", with
  no tool call to show it.

## How to check

Go through the comment one sentence at a time. For every concrete fact in it (a name,
a quoted string, a number, a line number, what a piece of code does, who said what,
what RepoMind did), find where the issue or a tool result shows it. A fact you cannot
find is unsupported, however plausible it sounds. Do not give credit for what the code
probably contains: only what the tool results actually show counts. When the comment
gives a line number, look for the exact `path:line` among the search hits before you
answer.

## Examples

{{examples}}

## Your reply

Reply with one JSON object and nothing else, no code fence, the reasoning first:

{"reasoning": "<one line: the unsupported fact and what is missing, or that every fact is in the evidence>", "answer": "Pass"}

The answer is "Pass" or "Fail".
