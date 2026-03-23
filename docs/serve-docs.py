#!/usr/bin/env python3
"""Rebuild docs and (re)start the local server on port 8080.

Works on macOS, Linux, and Windows.

Usage:
    python docs/serve-docs.py           # any platform
    ./docs/serve-docs.sh                # Unix shorthand
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

PORT = 8080
PROJECT_DIR = Path(__file__).resolve().parent.parent


def _kill_port(port: int) -> None:
    """Kill any process currently listening on *port*."""
    if sys.platform == "win32":
        r = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
        for line in r.stdout.splitlines():
            parts = line.split()
            # netstat line: Proto  Local  Foreign  State  PID
            if len(parts) >= 5 and f":{port}" in parts[1] and parts[3] == "LISTENING":
                subprocess.run(
                    ["taskkill", "/F", "/PID", parts[4]], capture_output=True
                )
        time.sleep(0.5)
    else:
        # lsof: available on macOS and most Linux distros
        r = subprocess.run(
            ["lsof", "-ti", f":{port}"], capture_output=True, text=True
        )
        if r.returncode == 0 and r.stdout.strip():
            for pid_s in r.stdout.strip().split():
                try:
                    os.kill(int(pid_s), signal.SIGKILL)
                except (ProcessLookupError, ValueError):
                    pass
            time.sleep(0.5)
            return
        # fuser: Linux fallback (not available on macOS)
        subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True)
        time.sleep(0.5)


def _check_nav() -> None:
    """Warn about any docs/*.md files missing from mkdocs.yml nav."""
    import yaml  # bundled with mkdocs

    docs = sorted(f for f in os.listdir("docs") if f.endswith(".md"))

    with open("mkdocs.yml") as fh:
        cfg = yaml.safe_load(fh)

    def _extract(nav):
        files: set[str] = set()
        for item in nav:
            if isinstance(item, str):
                files.add(item)
            elif isinstance(item, dict):
                for v in item.values():
                    if isinstance(v, str):
                        files.add(v)
                    elif isinstance(v, list):
                        files |= _extract(v)
        return files

    nav_files = _extract(cfg.get("nav", []))
    missing = sorted(set(docs) - nav_files)
    if missing:
        print(f"Warning: docs not in nav: {', '.join(missing)}", file=sys.stderr)


def main() -> None:
    os.chdir(PROJECT_DIR)
    _kill_port(PORT)
    _check_nav()

    result = subprocess.run(["mkdocs", "build", "--clean", "--quiet"])
    if result.returncode != 0:
        sys.exit(result.returncode)

    print(f"Serving docs at http://127.0.0.1:{PORT}/")
    site_dir = PROJECT_DIR / "site"

    # Replace current process with the HTTP server so Ctrl-C works cleanly.
    # On Windows os.execv uses CreateProcess, which is fine for this purpose.
    os.chdir(site_dir)
    os.execv(
        sys.executable,
        [sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"],
    )


if __name__ == "__main__":
    main()
