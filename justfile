set shell := ["bash", "-euo", "pipefail", "-c"]

# Backend API recipes (also usable standalone: cd backend && just)
mod backend

# Evaluation tooling recipes (cd eval && just)
mod eval

# Frontend recipes (cd frontend && just)
mod frontend

pre_commit_version := "4.0.1"

# List the available recipes
default:
    @just --list --unsorted

# Install every project's dependencies and the git hooks
[group('setup')]
setup: backend::setup eval::setup frontend::setup hooks

# Install the pre-commit git hooks
[group('setup')]
hooks:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! git rev-parse --git-dir >/dev/null 2>&1; then
        echo "Not a git repository: skipping hooks"
        exit 0
    fi
    command -v pre-commit >/dev/null || uv tool install --quiet "pre-commit=={{ pre_commit_version }}"
    pre-commit install

# Sort imports and format every project
[group('quality')]
fmt: backend::fmt eval::fmt frontend::fmt scripts-fmt

# Apply every automatic fix in every project
[group('quality')]
fix: backend::fix eval::fix frontend::fix scripts-fmt

# Every quality gate of every project
[group('quality')]
check: backend::check eval::check scripts-check frontend::check

# Format the repository scripts (backend toolchain)
[group('scripts')]
scripts-fmt:
    uv run --project backend ruff check --config backend/pyproject.toml --fix scripts
    uv run --project backend ruff format --config backend/pyproject.toml scripts

# Check the repository scripts (backend toolchain)
[group('scripts')]
scripts-check:
    uv run --project backend ruff format --config backend/pyproject.toml --check scripts
    uv run --project backend ruff check --config backend/pyproject.toml scripts
    uv run --project backend mypy --config-file backend/pyproject.toml scripts

# Fix and check one edited file with its project's tools
[group('quality')]
check-file path:
    #!/usr/bin/env bash
    set -uo pipefail
    file="$(realpath "{{ path }}")"
    rel="$(realpath --relative-to="{{ justfile_directory() }}" "$file")"
    case "$rel" in
        backend/*) exec "{{ just_executable() }}" backend::check-file "$file" ;;
        eval/*) exec "{{ just_executable() }}" eval::check-file "$file" ;;
        frontend/*) exec "{{ just_executable() }}" frontend::check-file "$file" ;;
        scripts/*.py)
            status=0
            step() { "$@" || status=1; }
            step uv run --frozen --project backend ruff check --config backend/pyproject.toml --fix "$file"
            step uv run --frozen --project backend ruff format --config backend/pyproject.toml "$file"
            step uv run --frozen --project backend mypy --config-file backend/pyproject.toml scripts
            exit "$status"
            ;;
    esac

# Fail on deprecated, yanked or vulnerable dependencies in every project
[group('dependencies')]
audit: backend::audit eval::audit frontend::audit

# Report available upgrades in every project
[group('dependencies')]
outdated: backend::outdated eval::outdated frontend::outdated

# Build and start the full stack with docker compose on http://localhost:8000
[group('run')]
up:
    docker compose up --build

# Stop the docker compose stack
[group('run')]
down:
    docker compose down
