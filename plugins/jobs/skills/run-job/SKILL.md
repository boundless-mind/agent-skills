---
name: run-job
description: Run a delegated job unattended from its brief and deliver a result in the standard shape.
disable-model-invocation: true
---

# Run job

You are working on a **job**: a delegated assignment that runs while nobody is watching. The argument is the job directory (default: the current directory if it contains `brief.md`). Its layout:

```
<job>/
  brief.md      the assignment: goal, inputs, scope, deliverable
  context/      inputs staged for you; read them, leave them unchanged
  out/          everything you deliver goes here
```

Nobody will answer questions while you work. Wherever you would ask, make the most reasonable **assumption**, record it, and carry on. Recorded assumptions are a first-class part of the result: the reader corrects them in a follow-up round, so a visible assumption is worth more than a hidden guess.

## Steps

1. **Read the brief** (`brief.md`, format in [brief-template.md](brief-template.md)) and every input it lists. Done when each listed input is read, or recorded as missing. A missing input that the goal cannot do without ends the job: write `out/summary.md` with `status: failed` and the reason.

   **When the brief has a `review` block**, check the reviewer before any work: the **converge** skill (plugin `converge`) must be available, and its prerequisite check must report `ready`. If either fails, end the job the same way, with the check's error as the reason. A brief that asks for review is never delivered unreviewed because a prerequisite was missing at the start.

2. **Do the work** the brief's scope describes, and nothing outside it. Record a **source** for every factual claim as you go: a file path and line, a document and page, or a URL. Record every assumption with why you made it and what changes if it is wrong.

   If one of the brief's `stop_and_ask` conditions occurs, stop there: write `out/summary.md` with `status: needs-input`, the question, and what you finished so far.

   **When the brief has a `review` block**, work part by part instead of all at once. The parts are the items of the brief's Deliverable section, in order. Write each part to `out/parts/<NN>-<slug>.md`, then use the **converge** skill on it (job directory `<job>`, review directory `log/review/<NN>-<slug>/`, round limit `review.max_rounds`, criteria quoted from the brief's Deliverable item and Done-when section) before starting the next part. Carry each part's disagreements forward to the result.

3. **Write `out/result.html`** from [result-template.html](result-template.html): a single HTML file in its fixed section order (TL;DR, options, recommendation, assumptions, disagreements, open questions, sources, appendix), plus whatever the brief's Deliverable section adds. Put diagrams in as Mermaid blocks where they explain structure or flow better than prose. The appendix holds long material; everything above it should be readable on a phone in a few minutes.

4. **Write `out/summary.md`** in the format below. Other artifacts (spreadsheets, diagrams, code) also go in `out/` and are listed in the summary.

   **When the brief has a `review` block**, converge once more on the whole result (`out/result.html` and `out/summary.md`) with a **fresh** Codex thread and a **checklist**, job directory `<job>`, review directory `log/review/final/`, and the criteria quoted from the brief's Goal, Deliverable, and Done-when sections.

5. **Check the result** against the brief before finishing. Done when all of these hold:
   - every item in the brief's Deliverable and Done-when sections is present;
   - every assumption appears in both `result.html` and `summary.md`;
   - with a `review` block: every part and the whole result went through converge, and each remaining disagreement appears in both files;
   - every recommendation traces to a source or an assumption;
   - the TL;DR has at most three bullets, and the summary fits on one screen.

   Then set `status: done`.

Delivery is someone else's job: leave pushing, pull requests, and messages to anyone out of it. If the brief's deliverable is code, commit it in your working clone and name the branch in the summary.

## `out/summary.md` format

```markdown
---
job: <job slug from the brief>
status: done | needs-input | failed
finished: <ISO 8601 timestamp>
---

# <result title>

## TL;DR
<at most three bullets>

## Assumptions
- <assumption> — <why> — <impact if wrong>

## Disagreements
- <part>: <Codex's position> — <your position and reason>   (omit the section without review)

## Open questions
- <question> — <who or what can answer it>

## Artifacts
- `out/result.html` — <one line>
```
