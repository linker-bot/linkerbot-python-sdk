[group('python')]
update:
    uv run uv-bump
    uv lock --upgrade
    uv sync --all-groups --all-extras
    dprint config update -y

[group('lint')]
lint:
    autocorrect --lint .
    dprint check
    uv sync --all-groups --all-extras
    uv run ruff check .
    uv run ruff format --check --diff .
    uv run ty check .

[group('lint')]
fix-lint:
    uv sync --all-groups --all-extras
    autocorrect --fix .
    dprint fmt
    uv run ruff check --fix --unsafe-fixes .
    uv run ruff format .

[group('test')]
test:
    uv sync --all-groups --all-extras
    uv run pytest

[group('test')]
check: lint test

[group('git')]
switch:
    #!/usr/bin/env bash
    set -euo pipefail
    current_branch="$(git branch --show-current)"
    if [[ -z "$current_branch" ]]; then
      echo "Cannot switch from a detached HEAD." >&2
      exit 1
    fi
    if [[ -n "$(git status --porcelain)" ]]; then
      echo "Working tree is not clean; commit or stash changes first." >&2
      exit 1
    fi
    git fetch origin --prune
    if [[ "$current_branch" != "main" ]]; then
      git switch main
    fi
    git merge --ff-only origin/main
    if [[ "$current_branch" != "main" ]]; then
      if git merge-base --is-ancestor "$current_branch" main; then
        git branch --delete -- "$current_branch"
      else
        echo "Preserved unmerged branch: $current_branch" >&2
      fi
    fi

[group('git')]
sync-oss:
    git push oss main
    git tag | grep -v a | xargs -r git push oss

[group('docs')]
preview:
    mdbook serve docs/zh

[group('docs')]
build-docs:
    mdbook build docs/zh
