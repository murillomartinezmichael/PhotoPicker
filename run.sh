#!/usr/bin/env bash
# One-liner operator entry point. Supports:
#   ./run.sh cull <folder> [--top N] [--prompt "..."]  → cull + open web UI
#   ./run.sh pick <folder> --profile <name>            → themed pick (legacy)
#   ./run.sh                                            → usage
set -euo pipefail

PY="${PYTHON:-.venv/bin/python}"
if [ ! -x "$PY" ]; then
  PY=python3
fi

cmd="${1:-}"
shift || true

case "$cmd" in
  cull)
    exec "$PY" -c "from photopicker.cli import cull_main; cull_main()" "$@"
    ;;
  pick)
    exec "$PY" -c "from photopicker.cli import main; main()" --folder "$@"
    ;;
  "")
    cat <<EOF
PhotoPicker — cull a shoot to the best N in a local web UI.

  ./run.sh cull <folder> [--top 30] [--prompt "..."] [--output DIR]
      Point at a shoot folder, get the top N in the browser.
      K keep · X reject · U undo · ←/→ nav · Enter focus · E export · ? help

  ./run.sh pick <folder> --profile <aries|big7|default|aries-gallery>
      Themed pick (categorized) for portfolio galleries.

Examples:
  ./run.sh cull ~/photos/aries_shoot_2026-07-05 --top 30
  ./run.sh cull ~/photos/shoot --top 30 --prompt "best portfolio deck photos"
  ./run.sh pick ~/photos/aries_shoot --profile aries-gallery --output ~/site/img
EOF
    exit 0
    ;;
  *)
    echo "Unknown subcommand: $cmd"
    echo "Use: ./run.sh {cull|pick}"
    exit 1
    ;;
esac
