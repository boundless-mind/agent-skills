# agent-skills

Skills for Claude Code, Codex, and OpenCode that help you pause work, pick it up in a new session, save ideas for later, converge with Codex through review rounds, and run delegated jobs unattended.

## Plugins

The **workbench** plugin includes three skills:

- **suspend** saves the current state, reasoning, open questions, and next step in `HANDOFF.md`, and collects loose remarks in `THOUGHTS.md`.
- **resume** reads the latest handoff, reviews what changed, and brings you up to date on saved thoughts.
- **thought** captures an idea in `THOUGHTS.md` without acting on it.

The **converge** plugin runs a review loop with Codex:

- **converge** has Codex review a part of your work (a section, table, design, or document), you fix or rebut each finding, and the loop repeats until Codex has no material findings or the round limit (default 5) is reached. Findings that survive the last round are reported as disagreements. A bundled script enforces the round limit and stores each round's findings. It runs in Claude Code only, and needs the [codex-plugin-cc fork](https://github.com/skress/codex-plugin-cc) with `task --output-schema` and a Codex login:

  ```sh
  claude plugin marketplace add skress/codex-plugin-cc
  claude plugin install codex@skress-codex --scope user
  claude plugin install converge@boundless-mind --scope user
  codex login
  ```

The **jobs** plugin runs delegated work unattended:

- **run-job** works through a job directory (`brief.md`, `context/`, `out/`) without asking questions, records its assumptions instead, and writes `out/result.html` plus `out/summary.md`. The brief and result templates live next to the skill. Install it with `claude plugin install jobs@boundless-mind` or `codex plugin add jobs@boundless-mind`, and run it headless, for example `claude -p "/jobs:run-job jobs/<slug>"`. A brief with a `review` block makes it converge with Codex on each part and on the whole result. Such jobs need Claude Code with **converge** and its prerequisites installed as shown above; without them, the job fails at the start instead of running unreviewed.

## Install

Follow the instructions for each tool you use. Claude Code and Codex support native plugin installation; OpenCode uses the [skills CLI](https://github.com/vercel-labs/skills). To share one copy across tools, use the [shared installation](#shared-installation) option.

### Claude Code

Install for your user account (all projects):

```sh
claude plugin marketplace add boundless-mind/agent-skills
claude plugin install workbench@boundless-mind --scope user
```

Alternatively, run either of these from the target project:

```sh
claude plugin install workbench@boundless-mind --scope project  # shared project settings
claude plugin install workbench@boundless-mind --scope local    # just you, in this project
```

Add the marketplace first in either case. Project scope saves settings in `.claude/settings.json` for sharing with your team; local scope saves them in `.claude/settings.local.json` for your own use.

To update:

```sh
claude plugin marketplace update boundless-mind
claude plugin update workbench@boundless-mind
```

Then restart Claude Code or run `/reload-plugins`.

See [Claude Code installation scopes](https://code.claude.com/docs/en/discover-plugins#choose-an-install-scope).

### Codex

Install for your user account with a Codex version that supports `codex plugin`:

```sh
codex plugin marketplace add boundless-mind/agent-skills
codex plugin add workbench@boundless-mind
```

For project-local skills, use [shared installation](#shared-installation).

Refresh the marketplace with `codex plugin marketplace upgrade boundless-mind`. Manage installed plugins through Codex's plugin tools.

### OpenCode

Install with the skills CLI, which requires Node.js and npm.

Install for your user account (all projects):

```sh
npx skills add boundless-mind/agent-skills --skill suspend resume thought --agent opencode --global
```

Or run from the target project's root for project scope:

```sh
npx skills add boundless-mind/agent-skills --skill suspend resume thought --agent opencode
```

To update a user installation:

```sh
npx skills update resume suspend thought --global
```

Use `--project` in place of `--global` for a project installation.

See [OpenCode skill discovery](https://opencode.ai/docs/skills/).

### Shared installation

If you use several tools, the skills CLI can install one shared copy and link it into each tool's skill directory. Select the symlink installation method when prompted:

```sh
npx skills add boundless-mind/agent-skills --skill suspend resume thought --agent claude-code codex opencode --global
```

List only the agents you use after `--agent`. Omit `--global` to install in the current project. Add `--copy` if you prefer separate copies.

This installs standalone skills named `resume`, `suspend`, and `thought`. Update them with the same skills CLI commands shown under OpenCode. Choose one installation method per tool to avoid duplicate entries.

Native Claude Code and Codex plugins are managed separately and updated through their own plugin tools.

## Use

Pause a session with **suspend**, start the next one with **resume**, and use **thought** whenever you want to save an idea for later.

| Tool | Native plugin | Standalone skills |
| --- | --- | --- |
| Claude Code | `/workbench:suspend`, `/workbench:resume`, `/workbench:thought` | `/suspend`, `/resume`, `/thought` |
| Codex | Select the workbench skill from `/skills` | `$suspend`, `$resume`, `$thought` |
| OpenCode | — | Ask the agent to use `suspend`, `resume`, or `thought` |

Claude Code and Codex require you to invoke these skills explicitly. OpenCode may choose to use them automatically.

See [Codex skill invocation](https://learn.chatgpt.com/docs/build-skills#how-chatgpt-and-codex-use-skills).

## Develop the skills

To work on the skills locally, clone this repository and run the installer from the checkout:

```sh
bash scripts/install-skills.sh   # user scope, all three tools
```

This links `dev-resume`, `dev-suspend`, and `dev-thought` to your checkout, so you can use them alongside the public skills. Source edits take effect without reinstalling.

For a single tool or a combination, repeat `--agent`:

```sh
bash scripts/install-skills.sh --agent codex
bash scripts/install-skills.sh --agent claude-code --agent opencode
```

For project-local development, specify an existing project directory:

```sh
bash scripts/install-skills.sh --project /absolute/path/to/project
```

Alternatively, invoke the script by its absolute path from the target project's root with `--scope project`. Both project options can be combined with `--agent`. Run `bash scripts/install-skills.sh --help` for usage.

| Tool | User development links | Project development links |
| --- | --- | --- |
| Claude Code | `~/.claude/skills/dev-*` | `.claude/skills/dev-*` |
| Codex | `~/.agents/skills/dev-*` | `.agents/skills/dev-*` |
| OpenCode | `~/.config/opencode/skills/dev-*` | `.opencode/skills/dev-*` |

The user directories honor `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, and `XDG_CONFIG_HOME`. When `CODEX_HOME` is set, Codex links go into `$CODEX_HOME/skills` instead of `~/.agents/skills`. The installer stores generated entry points in the checkout's ignored `.dev-skills/` directory.

Keep the checkout at its installed location while using the links. Restart your tool if newly installed skills do not appear. Invoke them as `/dev-resume` in Claude Code, `$dev-resume` in Codex, or by asking OpenCode to use `dev-resume`; the same naming applies to the other two skills.

You can rerun the installer safely. It preserves public installations and refuses to replace conflicting `dev-*` entries. OpenCode also searches Claude Code and shared agent skill directories, so it may find development skills linked for another tool.

Development links are specific to your machine; don't commit them to target projects. Use `--project` for project scope rather than changing `CODEX_HOME`, which changes Codex's entire configuration home.

Development skills require explicit invocation in Claude Code and Codex. OpenCode may choose to invoke them automatically.

### Run the checks

Run the installer checks:

```sh
python3 -m unittest discover -s tests -v
```

The tests use temporary directories and cover agent combinations, installation scopes, live source edits, and protection of existing files.
