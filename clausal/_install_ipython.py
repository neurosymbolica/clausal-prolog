"""Install Clausal's IPython startup hook into a user's IPython profile.

Exposed as the ``clausal-install-ipython`` console script.  The hook is a
single Python file dropped into ``$IPYTHONDIR/profile_<name>/startup/`` —
IPython runs every ``.py`` in that directory before the user's first
cell, which is the only timing that lets the AST transformer rewrite
``-import_from(...)`` directives typed at the prompt.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


_STARTUP_SCRIPT = '''\
"""Clausal IPython integration — installed by `clausal-install-ipython`.

Delete this file to disable Clausal's `*(...)` query syntax and
`-import_from(...)` directives in this IPython profile.
"""
try:
    from clausal.import_hook import enable_ipython as _enable_clausal
    _enable_clausal(get_ipython().user_ns)
except ImportError:
    pass
'''

_TARGET_FILENAME = "00-clausal.py"


def _profile_startup_dir(ipython_dir: Path, profile: str) -> Path:
    return ipython_dir / f"profile_{profile}" / "startup"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="clausal-install-ipython",
        description=(
            "Install Clausal's IPython startup hook so that `*(...)` queries "
            "and `-import_from(...)` directives work from the first cell."
        ),
    )
    parser.add_argument(
        "--profile",
        default="default",
        help="IPython profile name (default: 'default')",
    )
    parser.add_argument(
        "--ipython-dir",
        default=os.environ.get("IPYTHONDIR", str(Path.home() / ".ipython")),
        help="IPython directory (default: $IPYTHONDIR or ~/.ipython)",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Overwrite an existing startup file",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove the installed startup file",
    )
    parser.add_argument(
        "--print",
        dest="print_only",
        action="store_true",
        help="Print the script contents to stdout and exit (no file write)",
    )
    args = parser.parse_args(argv)

    if args.print_only:
        sys.stdout.write(_STARTUP_SCRIPT)
        return 0

    ipython_dir = Path(args.ipython_dir).expanduser()
    startup_dir = _profile_startup_dir(ipython_dir, args.profile)
    target = startup_dir / _TARGET_FILENAME

    if args.uninstall:
        if target.exists():
            target.unlink()
            print(f"Removed {target}")
            return 0
        print(f"Nothing to remove: {target} does not exist", file=sys.stderr)
        return 1

    profile_dir = startup_dir.parent
    if not profile_dir.exists():
        print(
            f"IPython profile {args.profile!r} not found at {profile_dir}.\n"
            f"Create it first:  ipython profile create {args.profile}",
            file=sys.stderr,
        )
        return 1

    startup_dir.mkdir(parents=True, exist_ok=True)

    if target.exists() and not args.force:
        print(
            f"{target} already exists. Pass --force to overwrite, "
            f"or --uninstall to remove.",
            file=sys.stderr,
        )
        return 1

    target.write_text(_STARTUP_SCRIPT)
    action = "Overwrote" if args.force and target.exists() else "Installed"
    print(f"{action} Clausal IPython startup hook at {target}")
    print("It will load automatically the next time you start IPython.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
