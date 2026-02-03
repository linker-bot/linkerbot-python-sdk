current_branch := `git branch --show-current`

[group('python')]
update:
    uvx uv-bump
    uv sync

[group('lint')]
lint:
    uv sync --all-groups
    uvx ruff check .
    uvx ruff format --check --diff .
    uvx ty check .

[group('lint')]
fix-lint:
    uvx ruff check --fix --unsafe-fixes .
    uvx ruff format .

[group('git')]
switch:
    if [ {{ current_branch }} != "main" ]; then \
      git switch main; \
      git fetch -p; \
      git branch -D {{ current_branch }}; \
    fi
