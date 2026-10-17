---
job: <short-kebab-slug>
created: <YYYY-MM-DD>
domain: <domain the job belongs to>
agent: claude            # claude | codex
subscription: <which plan runs it>
workstream: <workstream the job serves>
sandbox: <sandbox the job runs in>
deliverable: none        # none | commit | pr | repo
stop_and_ask: []         # conditions under which the job stops instead of assuming
review:                  # optional: converge each Deliverable part with a reviewer
  reviewer: codex
  max_rounds: 5
---

# <Title: the question this job answers>

## Goal
<One or two sentences: what the reader wants to be able to decide or do with the result.>

## Context
<Every input the job may use, one line each, with what it is and why it matters.>
- `context/<file>` — <what it is>
- Repository `<url>` at `<ref>`, cloned to `<path>` — <what it is>
- Web research: <allowed | not allowed>

## Background
<What the agent cannot find in the inputs: constraints, history, people's intentions, things already decided.>

## Scope
<What to do.>

## Out of scope
<What to leave alone.>

## Deliverable
<What the result must contain beyond the standard shape (TL;DR, options, recommendation, assumptions, open questions, sources, appendix).>

## Done when
<Checkable conditions.>
