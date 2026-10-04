---
name: thought
description: Capture a loose thought about this project in THOUGHTS.md without acting on it.
disable-model-invocation: true
---

# Thought

Append the thought the user gives you to `THOUGHTS.md` at the repository root and return to what you were doing. Capturing is the whole job: leave the thought unexplored and unacted on unless they ask.

If the file is missing, create it with this header:

```markdown
# Thoughts

Unprocessed ideas and concerns about this project that have no place in its process documents yet. Newest at the bottom. `/resume` offers to file them.
```

Append one entry:

```markdown
- **<YYYY-MM-DD>** — <the thought in the user's words, tightened to one or two sentences> <optional: link to the file, story, or PR it concerns>
```

Leave the file uncommitted; `/suspend` commits it.
