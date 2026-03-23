#!/usr/bin/env bash
# Unix shorthand — delegates to serve-docs.py (works on macOS, Linux, Windows).
exec python3 "$(dirname "$0")/serve-docs.py" "$@"
