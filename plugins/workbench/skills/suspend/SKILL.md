---
name: suspend
description: Suspend work on this project, writing a handoff note so a later session can pick it up.
disable-model-invocation: true
---

# Suspend

Write `HANDOFF.md` so that someone with no access to this conversation (a fresh session, or the user weeks from now) can pick the work up without re-deriving anything. This conversation is the only place most of that knowledge exists; once the session ends it is gone.

## Steps

1. **Read the project state.** Current branch, `git status`, commits made this session, unpushed commits, the open pull request for this branch if `gh` or `glab` is available, and where the project's own process tracks progress (for BMAD, `_bmad-output/implementation-artifacts/sprint-status.yaml`). Done when you can state the project's position without guessing.

2. **Write `HANDOFF.md`** at the repository root, replacing any previous one (git keeps the history). Use the format below. Done when every decision made in this session appears with its reason, and the next step is a single concrete action.

3. **Capture loose thoughts.** Ideas, concerns, or "we should also…" remarks from this session that nobody acted on and that belong nowhere in the process documents go into `THOUGHTS.md`, in the format the `thought` skill defines (dated entry, appended at the end; create the file with its header if missing). Done when each such remark is either captured there or already reflected elsewhere.

4. **Commit** `HANDOFF.md` and `THOUGHTS.md`, and nothing else, on the current branch with the message `docs: handoff`. Leave other uncommitted work as it is and say so in the handoff. Do not push.

5. **Show the user the handoff** and the list of captured thoughts.

## `HANDOFF.md` format

```markdown
# Handoff — <YYYY-MM-DD>, branch `<branch>`

## Where things stand
<2–5 bullets: what this session achieved, what state the work is in, uncommitted or unpushed work, open PR>

## Reasoning worth keeping
<Decisions taken and why; approaches tried and rejected, and why; constraints discovered. The part git history cannot reconstruct.>

## Open questions
<Questions that block or shape the next step, each with who or what can answer it>

## Next step
<One concrete first action for the next session>

## Environment
<Only what is non-obvious and was needed this session: which sandbox, a workaround, a service that must be running. Omit the section if nothing applies.>
```

Link to files, stories, PRs, and ADRs rather than restating them. Keep it under about 60 lines: the reader wants to be productive in five minutes, not to re-read the session.
