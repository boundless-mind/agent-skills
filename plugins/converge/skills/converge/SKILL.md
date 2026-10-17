---
name: converge
description: Converge with Codex on a piece of work through review rounds until no material findings remain. Use when a job's brief asks for review, or the user asks for a Codex or GPT review loop on a document, section, or plan.
---

# Converge

Get a piece of work (a **part**: a section, a table, a design, a document) reviewed by Codex, and iterate until Codex has no **material** findings left or the round limit is reached. Codex reviews read-only and classifies each finding as material (changes a verdict, number, recommendation, or conclusion; a factual error; an unsupported claim; a required item missing) or minor.

`review-round.mjs` in this skill's directory runs one round: it enforces the round limit, calls Codex with a fixed rubric and schema, stores the findings, and reports the result. Leave the round counting and the stored findings to it.

## Prerequisites

Claude Code with the codex-plugin-cc fork (`task --output-schema`) enabled, and a Codex login. Check them before unattended work, and whenever a round reports an error about the companion, the session, or the login:

```bash
node "<this skill's directory>/review-round.mjs" --check --cwd "<workspace root>"
```

`"status":"ready"` means rounds can run. Otherwise the `error` names what is missing.

## Inputs

- **The part**, written to disk.
- **A review directory** for this part: in a job, `<job>/log/review/<NN>-<part-slug>/`; elsewhere, `.converge/<part-slug>/` at the repository root.
- **Criteria**: what the part must achieve, quoted from the brief or from the user.
- **Round limit**: from the brief's `review.max_rounds`, or what the user says; default 5.
- **Job**: in a job, its directory. The script then points Codex at the brief, the staged inputs, and every part written so far, whatever the request names.
- **Fresh**: whether the first round starts a new Codex thread. Use it for a final review of a whole result, so the reviewer reads it without the history of earlier rounds. Otherwise rounds continue the session's Codex thread, which keeps the earlier parts in the reviewer's view.
- **Checklist**: whether Codex first writes its own list of what a good answer must contain, before it reads the work. Use it with fresh for a final review.

## Steps

1. **Write the request** for round N to `<dir>/round-<N>-request.md`. Its job is to name the work and its yardstick; the reviewer finds its own context, so leave choosing what Codex should read to Codex. Format:

   ```markdown
   ## Under review
   - <paths of the part's files; paths, not pasted content>

   ## Criteria
   > <the brief's or the user's words, quoted, not paraphrased>

   ## Out of scope
   - <what this review should not judge, if anything>

   ## Author's notes
   <optional: your view, what you were unsure about; from round 2 on, what changed since the last round>
   ```

   The script refuses a request without "Under review" and "Criteria".

2. **Run the round**, as one Bash call with `timeout: 600000`:

   ```bash
   node "<this skill's directory>/review-round.mjs" --dir "<dir>" --request "<dir>/round-<N>-request.md" --max <limit> [--job "<job dir>"] [--fresh --checklist on round 1 only] --cwd "<workspace root>"
   ```

   It prints one JSON line with `status`. A round that runs past `--timeout` (default 540 seconds) fails and cancels its Codex task, so a retry can start; raise the timeout only together with the Bash timeout. Each round first cancels Codex tasks of this session that were left marked running by a killed process, and lists them as `recovered`.

3. **Act on the status:**
   - `converged`: no material findings. Apply minor findings you agree with when they are cheap; the part is done.
   - `open` with rounds left: read the findings file. For **every** finding, either fix it or reject it with a reason, then write `<dir>/round-<N>-response.md` with one line per finding id (`F3 fixed: …` or `F3 rejected: …`). The next round refuses to run without this file. Go to step 1.
   - `open` with `rounds_left: 0`, or `max-rounds` (exit 3): stop iterating. Each remaining material finding becomes a **disagreement**: record Codex's position and yours, with your reason.
   - `error` (exit 2): fix what the error names when it is yours to fix (a missing or incomplete response file, a missing request), then rerun. Otherwise retry once; if it fails again, record "review unavailable" with the error for this part and continue without review.
   - A `warning` alongside any status says the round ran in a different Codex thread than the previous one. The findings still stand; mention it in the report.

4. **Report** for the part: rounds used, and either "converged" or its list of disagreements. In a job, disagreements go into the result's Disagreements section; interactively, show them to the user.

A rejected finding needs a reason that would convince a careful reader, not just a different opinion. When Codex maintains a finding after your rejection, weigh it again before rejecting it a second time: a disagreement that survives to the end is a signal for the reader that the question is genuinely uncertain.
