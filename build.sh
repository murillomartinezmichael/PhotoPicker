#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# build.sh — clean-clone → running, one command.
#
# WHY THIS EXISTS
#   A new contributor (or future-you on a fresh machine) clones the repo and
#   types ./build.sh. When this script finishes successfully, the project is
#   ready to run locally. If it doesn't work that way, the script is broken
#   and must be fixed — not the docs.
#
# WHAT IT DOES
#   1. Verifies prerequisites (runtimes, tools)
#   2. Installs language packages / restores deps
#   3. Builds any compiled artifacts (DLLs, binaries)
#   4. Generates .env from .env.example if missing
#   5. Runs DB migrations if applicable
#   6. Prints READY when done
#
# HOW TO CUSTOMIZE
#   - Edit the STACK variable below to match your project
#   - Fill in the per-stack functions (python_setup, dotnet_setup, etc.)
#   - Delete any function you don't use
#
# CONVENTIONS
#   - Fail fast (set -euo pipefail)
#   - One concern per function
#   - Print what you're doing before doing it
# -----------------------------------------------------------------------------

set -euo pipefail

# ---- configure -------------------------------------------------------------
STACK="${STACK:-python}"
PROJECT_NAME="$(basename "$(pwd)")"
# ----------------------------------------------------------------------------

log()  { printf '\033[36m[build]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[warn]\033[0m %s\n' "$*"; }
die()  { printf '\033[31m[fail]\033[0m %s\n' "$*" >&2; exit 1; }

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1. Install before running build.sh."
}

ensure_env_file() {
  if [[ ! -f .env ]]; then
    if [[ -f .env.example ]]; then
      cp .env.example .env
      warn ".env was missing — generated from .env.example. EDIT IT with real values before running the service."
    else
      warn "No .env or .env.example found. Skipping env setup."
    fi
  fi
}

python_setup() {
  require_command python3
  require_command pip3

  log "Creating virtualenv (.venv)"
  if [[ ! -d .venv ]]; then
    python3 -m venv .venv
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate

  log "Upgrading pip"
  pip install --quiet --upgrade pip

  if [[ -f requirements.txt ]]; then
    log "Installing requirements.txt"
    pip install --quiet -r requirements.txt
  fi
  if [[ -f requirements-dev.txt ]]; then
    log "Installing requirements-dev.txt"
    pip install --quiet -r requirements-dev.txt
  fi
  if [[ -f pyproject.toml ]]; then
    log "Installing project (editable) from pyproject.toml"
    pip install --quiet -e .
  fi
}

dotnet_setup() {
  require_command dotnet
  log "Restoring NuGet packages"
  dotnet restore
  log "Building solution (Release)"
  dotnet build --configuration Release --nologo --verbosity quiet
}

node_setup() {
  require_command node
  if [[ -f pnpm-lock.yaml ]]; then
    require_command pnpm
    log "Installing with pnpm"
    pnpm install --frozen-lockfile
  elif [[ -f yarn.lock ]]; then
    require_command yarn
    log "Installing with yarn"
    yarn install --frozen-lockfile
  else
    require_command npm
    log "Installing with npm"
    npm ci
  fi
}

go_setup() {
  require_command go
  log "Downloading Go modules"
  go mod download
  log "Building"
  go build ./...
}

static_setup() {
  log "Static site — no build deps. Skipping install."
}

run_migrations() {
  if [[ -x ./scripts/migrate.sh ]]; then
    log "Running database migrations"
    ./scripts/migrate.sh up
  fi
}

main() {
  log "Building $PROJECT_NAME (stack: $STACK)"
  ensure_env_file

  case "$STACK" in
    python)  python_setup ;;
    dotnet)  dotnet_setup ;;
    node)    node_setup ;;
    go)      go_setup ;;
    static)  static_setup ;;
    *)       die "Unknown STACK: $STACK. Set STACK=python|dotnet|node|go|static" ;;
  esac

  run_migrations

  log "READY. See RUNBOOK.md § 1.4 for how to run."
}

main "$@"
