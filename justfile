set shell := ["bash", "-euo", "pipefail", "-c"]

# Backend API recipes (also usable standalone: cd backend && just)
mod backend

# Evaluation tooling recipes (cd eval && just)
mod eval

# Frontend recipes (cd frontend && just)
mod frontend

pre_commit_version := "4.0.1"

# Production on Google Cloud (see guia/despliegue.md). Override with env vars for another project.
# The backend URL is the stable https://<service>-<project number>.<region>.run.app, the one
# allowed by the CSP in frontend/firebase.json.
gcp_project := env("GCP_PROJECT", "giunti-514722")
gcp_region := env("GCP_REGION", "us-central1")
backend_service := env("BACKEND_SERVICE", "giunti-backend")
firebase_site := env("FIREBASE_SITE", gcp_project)
backend_image := gcp_region + "-docker.pkg.dev/" + gcp_project + "/giunti/backend"
gcloud := env("GCLOUD", home_directory() / "google-cloud-sdk/bin/gcloud")

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

# Deploy the backend and then the frontend from the current commit
[group('deploy')]
deploy: deploy-backend deploy-frontend

# Build the backend in Cloud Build from the current commit and roll it out on Cloud Run
[group('deploy')]
deploy-backend: _deploy-ready
    #!/usr/bin/env bash
    set -euo pipefail
    image="{{ backend_image }}:$(git rev-parse --short HEAD)"
    echo "==> Building $image in Cloud Build"
    "{{ gcloud }}" builds submit backend --tag "$image" --region "{{ gcp_region }}" --project "{{ gcp_project }}" --quiet
    echo "==> Rolling out on Cloud Run ({{ backend_service }})"
    "{{ gcloud }}" run deploy "{{ backend_service }}" --image "$image" --region "{{ gcp_region }}" --project "{{ gcp_project }}" --quiet
    url="https://{{ backend_service }}-$("{{ gcloud }}" projects describe "{{ gcp_project }}" --format 'value(projectNumber)').{{ gcp_region }}.run.app"
    echo "==> Health: $(curl -fsS "$url/health")"
    echo "==> Keeping only the deployed image (older ones cost storage and are not used)"
    "{{ gcloud }}" artifacts docker images list "{{ backend_image }}" --include-tags --project "{{ gcp_project }}" --format 'value(version,tags)' \
      | while read -r digest tags; do
          case ",$tags," in *",${image##*:},"*) continue ;; esac
          "{{ gcloud }}" artifacts docker images delete "{{ backend_image }}@$digest" --delete-tags --quiet --project "{{ gcp_project }}"
        done

# Build the frontend against the deployed backend and publish it on Firebase Hosting
[group('deploy')]
deploy-frontend: _deploy-ready
    #!/usr/bin/env bash
    set -euo pipefail
    url="https://{{ backend_service }}-$("{{ gcloud }}" projects describe "{{ gcp_project }}" --format 'value(projectNumber)').{{ gcp_region }}.run.app"
    echo "==> Building the frontend for $url"
    (cd frontend && VITE_API_URL="$url" npm run build --silent)
    echo "==> Publishing on Firebase Hosting ({{ firebase_site }})"
    GCLOUD="{{ gcloud }}" python3 scripts/deploy_hosting.py "{{ firebase_site }}" "{{ gcp_project }}"

# What is running in production: backend revision and image, and the public addresses
[group('deploy')]
deploy-status:
    "{{ gcloud }}" run services describe "{{ backend_service }}" --region "{{ gcp_region }}" --project "{{ gcp_project }}" --format 'table(status.latestReadyRevisionName:label=REVISION,spec.template.spec.containers[0].image.basename():label=IMAGE,metadata.annotations."serving.knative.dev/lastModifier":label=DEPLOYED_BY)'
    @echo "API: https://{{ backend_service }}-$("{{ gcloud }}" projects describe "{{ gcp_project }}" --format 'value(projectNumber)').{{ gcp_region }}.run.app"
    @echo "Web: https://{{ firebase_site }}.web.app"

# Deploys must match a commit that is already on GitHub, so production is always traceable
_deploy-ready:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -n "$(git status --porcelain -- backend frontend scripts)" ]; then
        echo "Uncommitted changes in backend/, frontend/ or scripts/: commit them before deploying." >&2
        exit 1
    fi
    git fetch --quiet origin
    if ! git merge-base --is-ancestor HEAD "@{upstream}"; then
        echo "This commit is not on GitHub yet: run 'git push' before deploying." >&2
        exit 1
    fi
    test -x "{{ gcloud }}" || { echo "gcloud not found: see guia/despliegue.md" >&2; exit 1; }
