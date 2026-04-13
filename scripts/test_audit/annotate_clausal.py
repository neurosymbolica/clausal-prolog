"""Append '  # nv' to each `Test(...)` clause in .clausal test files.

Handles single-line and multi-line Test clauses by tracking paren depth from
the opening `Test(` through the final closing `)`.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TESTS = REPO / "tests"

TEST_START = re.compile(r'^\s*Test\(')


def strip_strings_and_comments(s: str) -> str:
    """Return s with string literals and # comments blanked, so paren counting is safe."""
    out = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == '#':
            break  # rest is comment
        if c in ('"', "'"):
            q = c
            out.append(' ')
            i += 1
            while i < n and s[i] != q:
                if s[i] == '\\' and i + 1 < n:
                    i += 2
                    out.append('  ')
                    continue
                out.append(' ')
                i += 1
            if i < n:
                i += 1
                out.append(' ')
            continue
        out.append(c)
        i += 1
    return ''.join(out)


def has_nv(line: str) -> bool:
    return bool(re.search(r'#\s*(nv|NV|NV!)\b', line))


def annotate(path: Path) -> int:
    lines = path.read_text().splitlines()
    n = len(lines)
    i = 0
    changed = 0
    while i < n:
        line = lines[i]
        if TEST_START.match(line):
            # find closing line by paren depth
            depth = 0
            started = False
            j = i
            while j < n:
                safe = strip_strings_and_comments(lines[j])
                for ch in safe:
                    if ch == '(':
                        depth += 1
                        started = True
                    elif ch == ')':
                        depth -= 1
                if started and depth == 0:
                    break
                j += 1
            if j < n:
                closing = lines[j]
                if not has_nv(closing):
                    # only append if no inline comment already; if comment exists, leave it
                    if '#' in strip_strings_and_comments(closing):
                        pass  # has other comment; skip to avoid confusion
                    else:
                        lines[j] = closing.rstrip() + "  # nv"
                        changed += 1
                i = j + 1
                continue
        i += 1
    if changed:
        text = "\n".join(lines)
        orig = path.read_text()
        if orig.endswith("\n"):
            text += "\n"
        path.write_text(text)
    return changed


def main():
    total = 0
    files = 0
    for cl in sorted(TESTS.rglob("*.clausal")):
        n = annotate(cl)
        if n:
            files += 1
            total += n
    print(f"annotated {total} Test clauses across {files} .clausal files")


if __name__ == "__main__":
    main()
