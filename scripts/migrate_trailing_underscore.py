#!/usr/bin/env python3
"""Migrate .clausal files from trailing-underscore to leading-underscore variable convention.

Converts logic variable names like ``foo_`` → ``_foo``, ``HEAD_`` → ``_head``.
ALLCAPS variables (``X``, ``FOO``) and the anonymous ``_`` are left unchanged.

Uses Python's ast module to find Name nodes accurately, then applies
source-level replacements to preserve formatting and comments.

Also handles regex group names in string literals: (?P<word_>...) → (?P<_word>...)
"""

import ast
import re
import sys
from pathlib import Path


def _is_trailing_underscore_var(name: str) -> bool:
    """True if name uses the old trailing-underscore convention."""
    if name == "_":
        return False
    if name.endswith("__"):
        return False
    if name.endswith("_"):
        return True
    return False


def _convert_name(name: str) -> str:
    """Convert trailing-underscore name to leading-underscore.

    foo_  → _foo
    HEAD_ → _head
    X_    → _x
    """
    base = name[:-1]  # strip trailing _
    return "_" + base.lower()


# Regex to find named groups like (?P<word_>...) where the group name
# uses trailing underscore convention
_GROUP_RE = re.compile(r'\(\?P<([A-Za-z_]\w*)>')


def _migrate_regex_groups(source: str) -> str:
    """Replace trailing-underscore named groups in regex patterns within strings."""
    def _replace_group(m):
        group_name = m.group(1)
        if _is_trailing_underscore_var(group_name):
            new_name = _convert_name(group_name)
            return f"(?P<{new_name}>"
        return m.group(0)
    return _GROUP_RE.sub(_replace_group, source)


def migrate_file(filepath: Path, *, dry_run: bool = False) -> list[tuple[str, str]]:
    """Migrate a single .clausal file. Returns list of (old, new) replacements made."""
    try:
        source = filepath.read_text()
    except (OSError, UnicodeDecodeError):
        print(f"  SKIP (unreadable): {filepath}", file=sys.stderr)
        return []

    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        print(f"  SKIP (syntax error): {filepath}", file=sys.stderr)
        return []

    # Collect all Name nodes that use trailing underscore convention
    replacements: dict[str, str] = {}  # old_name -> new_name
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and _is_trailing_underscore_var(node.id):
            if node.id not in replacements:
                replacements[node.id] = _convert_name(node.id)

    if not replacements:
        # Still check for regex group names in strings
        new_source = _migrate_regex_groups(source)
        if new_source != source and not dry_run:
            filepath.write_text(new_source)
            return [("(regex groups)", "(updated)")]
        return []

    # Apply replacements using word-boundary regex to avoid partial matches.
    # Process longest names first to avoid substring issues.
    new_source = source
    for old_name in sorted(replacements, key=len, reverse=True):
        new_name = replacements[old_name]
        # Match the old name at word boundaries.
        # Use negative lookbehind/lookahead to avoid matching inside longer identifiers.
        pattern = re.compile(r'(?<![A-Za-z0-9_])' + re.escape(old_name) + r'(?![A-Za-z0-9])')
        new_source = pattern.sub(new_name, new_source)

    # Also migrate regex group names in strings
    new_source = _migrate_regex_groups(new_source)

    if new_source != source:
        if not dry_run:
            filepath.write_text(new_source)
        return list(replacements.items())
    return []


def main():
    dry_run = "--dry-run" in sys.argv
    root = Path(__file__).resolve().parent.parent

    clausal_files = sorted(root.rglob("*.clausal"))
    total_changes = 0

    for fp in clausal_files:
        changes = migrate_file(fp, dry_run=dry_run)
        if changes:
            total_changes += len(changes)
            label = "[DRY RUN] " if dry_run else ""
            print(f"{label}{fp.relative_to(root)}: {len(changes)} variable(s) renamed")
            for old, new in changes[:10]:
                print(f"    {old} → {new}")
            if len(changes) > 10:
                print(f"    ... and {len(changes) - 10} more")

    print(f"\nTotal: {total_changes} variable(s) across {len(clausal_files)} files")
    if dry_run:
        print("(dry run — no files were modified)")


if __name__ == "__main__":
    main()
