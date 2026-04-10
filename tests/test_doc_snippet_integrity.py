"""Verify that all --8<-- snippet references in docs point to valid targets.

Checks:
1. Every --8<-- reference points to an existing file.
2. If the reference includes a :section suffix, that section exists in the file.
3. Every referenced .clausal fixture file contains at least one Test clause.
"""

import re
from pathlib import Path

_DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Matches --8<-- "path/to/file" or --8<-- "path/to/file:section" inside
# ```clausal blocks (or bare in markdown).
_SNIPPET_REF_RE = re.compile(r'--8<--\s+"([^"]+)"')

# Section delimiter pattern used in source files.
_SECTION_START_RE = re.compile(r"--8<--\s*\[start:([^\]]+)\]")
_SECTION_END_RE = re.compile(r"--8<--\s*\[end:([^\]]+)\]")


def _collect_snippet_refs() -> list[tuple[Path, int, str, str | None]]:
    """Return (md_path, line_no, file_ref, section_or_None) for each ref."""
    refs = []
    for md in sorted(_DOCS_DIR.glob("*.md")):
        for i, line in enumerate(md.read_text().splitlines(), 1):
            m = _SNIPPET_REF_RE.search(line)
            if m:
                raw = m.group(1)
                if ":" in raw:
                    file_part, section = raw.rsplit(":", 1)
                else:
                    file_part, section = raw, None
                refs.append((md, i, file_part, section))
    return refs


def _sections_in_file(path: Path) -> set[str]:
    """Return the set of section names defined in a file."""
    text = path.read_text()
    starts = set(_SECTION_START_RE.findall(text))
    ends = set(_SECTION_END_RE.findall(text))
    return starts & ends


def _has_test_clause(path: Path) -> bool:
    """True if a .clausal file contains at least one Test(...) clause."""
    text = path.read_text()
    return bool(re.search(r'Test\s*\(', text))


def test_all_snippet_files_exist():
    refs = _collect_snippet_refs()
    missing = []
    for md, lineno, file_ref, _ in refs:
        target = _PROJECT_ROOT / file_ref
        if not target.exists():
            missing.append(f"  {md.name}:{lineno} -> {file_ref}")
    assert not missing, (
        "Snippet references point to missing files:\n" + "\n".join(missing)
    )


def test_all_snippet_sections_exist():
    refs = _collect_snippet_refs()
    missing = []
    for md, lineno, file_ref, section in refs:
        if section is None:
            continue
        target = _PROJECT_ROOT / file_ref
        if not target.exists():
            continue  # caught by test_all_snippet_files_exist
        sections = _sections_in_file(target)
        if section not in sections:
            missing.append(
                f"  {md.name}:{lineno} -> {file_ref}:{section} "
                f"(available: {sorted(sections) or 'none'})"
            )
    assert not missing, (
        "Snippet references point to missing sections:\n" + "\n".join(missing)
    )


def test_clausal_fixtures_have_tests():
    """Every .clausal file referenced from docs should have Test clauses."""
    refs = _collect_snippet_refs()
    seen: set[str] = set()
    untested = []
    for _, _, file_ref, _ in refs:
        if file_ref in seen or not file_ref.endswith(".clausal"):
            continue
        seen.add(file_ref)
        target = _PROJECT_ROOT / file_ref
        if target.exists() and not _has_test_clause(target):
            untested.append(f"  {file_ref}")
    assert not untested, (
        "Referenced .clausal fixture files have no Test clauses:\n"
        + "\n".join(untested)
    )
