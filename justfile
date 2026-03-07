current_branch := `git branch --show-current`

[group('python')]
update:
    uv run uv-bump
    uv sync

[group('lint')]
lint:
    autocorrect --lint .
    uv sync --all-groups
    uv run ruff check .
    uv run ruff format --check --diff .
    uv run ty check .

[group('lint')]
fix-lint:
    autocorrect --fix .
    uv run ruff check --fix --unsafe-fixes .
    uv run ruff format .

[group('git')]
switch:
    if [ {{ current_branch }} != "main" ]; then \
      git switch main; \
      git fetch origin -p; \
      git branch -D {{ current_branch }}; \
    fi

[group('git')]
sync-oss:
    git push oss main
    git push oss --tags

[group('docs')]
preview:
    mdbook serve docs/zh

[group('docs')]
build-docs:
    mdbook build docs/zh
