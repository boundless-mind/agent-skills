#!/usr/bin/env bash
# Install development entry points backed by this checkout, not a public release.
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: install-skills.sh [--scope user|project] [--project PATH] [--agent NAME ...]

Link dev-resume, dev-suspend, and dev-thought to this checkout's current skills.
Defaults to user scope and all three agents. Repeat --agent to select a subset.

  --agent NAME     claude-code, codex, or opencode
  --scope SCOPE    user (default), or project (current directory)
  --project PATH   install in an existing project directory; implies project scope
  --help           show this help without installing

User directories honor CLAUDE_CONFIG_DIR, CODEX_HOME, and XDG_CONFIG_HOME.
Public skills and plugin installations are left in place. Conflicts are rejected.
USAGE
}

die() {
  echo "error: $*" >&2
  exit 1
}

scope=user
project=""
agents=()
while (($#)); do
  case "$1" in
    --scope)
      (($# >= 2)) || die "--scope needs a value"
      scope="$2"
      case "$scope" in user|project) ;; *) die "unknown scope: $scope" ;; esac
      shift 2
      ;;
    --project)
      (($# >= 2)) || die "--project needs a path"
      project="$2"
      scope=project
      shift 2
      ;;
    --agent)
      (($# >= 2)) || die "--agent needs a name"
      case "$2" in claude-code|codex|opencode) ;; *) die "unknown agent: $2" ;; esac
      agents+=("$2")
      shift 2
      ;;
    --help|-h) usage; exit 0 ;;
    *) die "unknown argument: $1 (use --help)" ;;
  esac
done

[[ -z "$project" || "$scope" == project ]] || die "--project requires project scope"
if [[ "$scope" == project ]]; then
  project="${project:-$PWD}"
  [[ -d "$project" ]] || die "project directory does not exist: $project"
  project="$(cd "$project" && pwd -P)"
fi
if ((${#agents[@]} == 0)); then
  agents=(claude-code codex opencode)
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
dev_root="$repo_root/.dev-skills"
targets=()
for agent in "${agents[@]}"; do
  if [[ "$scope" == user ]]; then
    case "$agent" in
      claude-code) target="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills" ;;
      codex)
        target="$HOME/.agents/skills"
        [[ -z "${CODEX_HOME:-}" ]] || target="$CODEX_HOME/skills"
        ;;
      opencode) target="${XDG_CONFIG_HOME:-$HOME/.config}/opencode/skills" ;;
    esac
  else
    case "$agent" in
      claude-code) target="$project/.claude/skills" ;;
      codex) target="$project/.agents/skills" ;;
      opencode) target="$project/.opencode/skills" ;;
    esac
  fi
  case "$target" in /*) ;; *) target="$PWD/$target" ;; esac
  # A repeated --agent must not try to create the same link twice.
  duplicate=false
  for existing in "${targets[@]+${targets[@]}}"; do
    [[ "$existing" != "$target" ]] || duplicate=true
  done
  [[ "$duplicate" == true ]] || targets+=("$target")
done

skills=()
for source in "$repo_root"/plugins/workbench/skills/*; do
  [[ -f "$source/SKILL.md" ]] || continue
  name="${source##*/}"
  [[ "$name" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || die "invalid skill name: $name"
  skills+=("$name")
done
((${#skills[@]})) || die "no workbench skills found"

# Check every destination before generating or linking anything. In particular,
# ln -sfn can descend into real directories, so never use it to replace conflicts.
for target in "${targets[@]}"; do
  ancestor="$target"
  while [[ ! -e "$ancestor" && ! -L "$ancestor" ]]; do
    ancestor="${ancestor%/*}"
    [[ -n "$ancestor" ]] || ancestor=/
  done
  [[ -d "$ancestor" ]] || die "not a directory: $ancestor"
  for name in "${skills[@]}"; do
    link="$target/dev-$name"
    expected="$dev_root/dev-$name"
    if [[ -L "$link" ]]; then
      [[ "$(readlink "$link")" == "$expected" ]] || die "conflicting symlink: $link"
    elif [[ -e "$link" ]]; then
      die "refusing to replace existing skill: $link"
    fi
  done
done

marker="$dev_root/.managed-by-install-skills"
if [[ -e "$dev_root" || -L "$dev_root" ]]; then
  [[ -d "$dev_root" && ! -L "$dev_root" && -f "$marker" && ! -L "$marker" ]] \
    || die "refusing to replace unmanaged development directory: $dev_root"
fi
for name in "${skills[@]}"; do
  entry="$dev_root/dev-$name"
  [[ ! -L "$entry" && (! -e "$entry" || -d "$entry") ]] || die "conflicting development entry: $entry"
  [[ ! -L "$entry/SKILL.md" && ! -L "$entry/agents" && ! -L "$entry/agents/openai.yaml" ]] \
    || die "unexpected symlink in generated metadata: $entry"
done

mkdir -p "$dev_root"
touch "$marker"
for name in "${skills[@]}"; do
  entry="$dev_root/dev-$name"
  source="$repo_root/plugins/workbench/skills/$name"
  mkdir -p "$entry/agents"
  cat > "$entry/SKILL.md" <<SKILL
---
name: dev-$name
description: Use when the user invokes dev-$name to test the checkout's $name workflow on the current project.
disable-model-invocation: true
---

# Development $name

Read \`$source/SKILL.md\` and follow its current instructions with the user's supplied arguments. Apply the workflow to the current working project; the checkout above only supplies the instructions. Resolve the source skill's supporting files relative to \`$source/\`.

Keep this entry point's identity \`dev-$name\`; the source file's frontmatter describes the public skill. When that workflow refers to the workbench resume, suspend, or thought skills, use dev-resume, dev-suspend, or dev-thought respectively during this development invocation.
SKILL
  cat > "$entry/agents/openai.yaml" <<'POLICY'
policy:
  allow_implicit_invocation: false
POLICY
done

for target in "${targets[@]}"; do
  mkdir -p "$target"
  for name in "${skills[@]}"; do
    link="$target/dev-$name"
    [[ -L "$link" ]] || ln -s "$dev_root/dev-$name" "$link"
    echo "linked dev-$name -> $link"
  done
done
