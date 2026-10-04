---
name: resume
description: Resume work on this project from its handoff note, thoughts, and current state.
disable-model-invocation: true
---

# Resume

Brief the user so they are back in the details of this project within minutes, then agree on what to do now.

## Steps

1. **Find the newest handoff.** It may live on another branch than the current one: `git log --all -1 --format='%H %D %cs' -- HANDOFF.md`. Read it from that commit (`git show <sha>:HANDOFF.md`). If there is none, say so and build the briefing from the remaining steps alone.

2. **Find what changed since.** Commits after the handoff commit on its branch and on the current branch, other branches with newer activity, open pull requests (`gh pr list` or `glab mr list`), uncommitted work, and the project's own progress tracking (for BMAD, `_bmad-output/implementation-artifacts/sprint-status.yaml`). Done when you know whether the handoff's "Next step" is still the next step.

3. **Read `THOUGHTS.md`** if present.

4. **Brief the user**, in this shape and no longer than a screen:
   - **Where we are**: 2–4 bullets, from the handoff, corrected by what changed since.
   - **Reasoning to remember**: the handoff's decisions and rejected approaches that bear on the next step.
   - **Open questions** still open.
   - **Thoughts waiting**: how many, oldest date, one line each.
   - **Proposed next step**, and why.

5. **Offer to file thoughts.** For each thought, ask the user whether to keep it, turn it into work in the project's process (a story, an issue), mark it as a job candidate (prefix the entry with `[job]`), or delete it. Apply their choices to `THOUGHTS.md`. Skip this step if they decline.

6. **Agree on the next step** with the user. Done when they confirm it or name another.
