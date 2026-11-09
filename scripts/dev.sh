#!/usr/bin/env bash
# Development helper for the Linux dev hub, where there is no microphone and
# no Windows to send input to. Everything except `run` works here.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=src

case "${1:-test}" in
  test)     python3 -m pytest tests/ -q "${@:2}" ;;
  check)    python3 -m jarvis doctor ;;
  commands) python3 -m jarvis commands "${@:2}" ;;
  words)    python3 -m jarvis words --all ;;
  try)      python3 -m jarvis test "${@:2}" ;;
  *)        echo "usage: $0 {test|check|commands|words|try} [args]" >&2; exit 2 ;;
esac
