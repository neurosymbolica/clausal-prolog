#!/usr/bin/env bash
# Rebuild docs and (re)start the local server on port 8080.
# Usage: ./serve-docs.sh

PORT=8080
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Kill any existing server on this port
pid=$(lsof -ti :$PORT 2>/dev/null)
if [ -n "$pid" ]; then
    kill "$pid" 2>/dev/null
    sleep 1
fi

# Sync nav with docs/*.md
python3 -c "
import os, yaml, sys

docs = sorted(f for f in os.listdir('docs') if f.endswith('.md'))
with open('mkdocs.yml') as fh:
    cfg = yaml.safe_load(fh)

def extract_files(nav):
    files = set()
    for item in nav:
        if isinstance(item, str):
            files.add(item)
        elif isinstance(item, dict):
            for v in item.values():
                if isinstance(v, str):
                    files.add(v)
                elif isinstance(v, list):
                    files |= extract_files(v)
    return files

nav_files = extract_files(cfg.get('nav', []))
missing = sorted(set(docs) - nav_files)
if missing:
    print('Warning: docs not in nav:', ', '.join(missing), file=sys.stderr)
"

mkdocs build --clean --quiet
echo "Serving docs at http://127.0.0.1:$PORT/"
cd site && python3 -m http.server $PORT --bind 127.0.0.1
