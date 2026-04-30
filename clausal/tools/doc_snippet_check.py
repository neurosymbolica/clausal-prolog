"""Shared check helpers for doc-snippet integrity and coverage tests.

Both core and each extracted package run the same set of checks against
their own ``docs/`` directory and ``tests/fixtures/docs/`` snippet files.
This module is the single source of truth for those checks; test files
in core (``tests/test_doc_snippet_*.py``) and per-package
(``packages/clausal-<pkg>/tests/test_doc_integrity.py``) call into it.

Each ``check_*`` function returns a list of violation strings — empty
list means the check passed. Test files do the asserting, so they can
compose their own error messages and add per-tree context (such as a
``known_uncompilable`` allowlist).
"""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

# Matches --8<-- "path/to/file" or --8<-- "path/to/file:section".
_SNIPPET_REF_RE = re.compile(r'--8<--\s+"([^"]+)"')

# Section delimiters in source files.
_SECTION_START_RE = re.compile(r"--8<--\s*\[start:([^\]]+)\]")
_SECTION_END_RE = re.compile(r"--8<--\s*\[end:([^\]]+)\]")

# Code-fence pattern for ```clausal blocks.
_CLAUSAL_FENCE_RE = re.compile(r"```clausal\n(.*?)```", re.DOTALL)


@dataclass(frozen=True)
class SnippetRef:
    md_path: Path
    lineno: int
    file_ref: str
    section: str | None


def collect_snippet_refs(docs_dir: Path) -> list[SnippetRef]:
    """Return every --8<-- reference under ``docs_dir`` as a SnippetRef."""
    refs: list[SnippetRef] = []
    for md in sorted(docs_dir.glob("*.md")):
        for i, line in enumerate(md.read_text().splitlines(), 1):
            m = _SNIPPET_REF_RE.search(line)
            if not m:
                continue
            raw = m.group(1)
            if ":" in raw:
                file_part, section = raw.rsplit(":", 1)
            else:
                file_part, section = raw, None
            refs.append(SnippetRef(md, i, file_part, section))
    return refs


def _sections_in_file(path: Path) -> set[str]:
    text = path.read_text()
    starts = set(_SECTION_START_RE.findall(text))
    ends = set(_SECTION_END_RE.findall(text))
    return starts & ends


def _has_test_clause(path: Path) -> bool:
    return bool(re.search(r"Test\s*\(", path.read_text()))


def check_files_exist(
    refs: list[SnippetRef], project_root: Path
) -> list[str]:
    """Every snippet reference must point to an existing file."""
    missing = []
    for ref in refs:
        target = project_root / ref.file_ref
        if not target.exists():
            missing.append(f"  {ref.md_path.name}:{ref.lineno} -> {ref.file_ref}")
    return missing


def check_sections_exist(
    refs: list[SnippetRef], project_root: Path
) -> list[str]:
    """Every section-suffixed reference must name a section in its file."""
    missing = []
    for ref in refs:
        if ref.section is None:
            continue
        target = project_root / ref.file_ref
        if not target.exists():
            continue  # caught by check_files_exist
        sections = _sections_in_file(target)
        if ref.section not in sections:
            missing.append(
                f"  {ref.md_path.name}:{ref.lineno} -> {ref.file_ref}:{ref.section} "
                f"(available: {sorted(sections) or 'none'})"
            )
    return missing


def check_clausal_fixtures_have_tests(
    refs: list[SnippetRef], project_root: Path
) -> list[str]:
    """Every referenced .clausal fixture must contain at least one Test clause."""
    seen: set[str] = set()
    untested = []
    for ref in refs:
        if ref.file_ref in seen or not ref.file_ref.endswith(".clausal"):
            continue
        seen.add(ref.file_ref)
        target = project_root / ref.file_ref
        if target.exists() and not _has_test_clause(target):
            untested.append(f"  {ref.file_ref}")
    return untested


def _is_skip(content: str) -> bool:
    first_line = content.lstrip().split("\n", 1)[0].strip()
    return first_line in ("# skip", "# clausal: skip")


def _is_snippet(content: str) -> bool:
    lines = [line.strip() for line in content.strip().split("\n") if line.strip()]
    return bool(lines) and all(line.startswith("--8<--") for line in lines)


def _has_test(content: str) -> bool:
    return bool(re.search(r"Test\s*\(", content))


def check_no_skip_blocks(docs_dir: Path) -> list[str]:
    """No '# skip' or '# clausal: skip' blocks may exist (ratchet at 0)."""
    violations = []
    for md in sorted(docs_dir.glob("*.md")):
        text = md.read_text()
        for m in _CLAUSAL_FENCE_RE.finditer(text):
            if _is_skip(m.group(1)):
                lineno = text[: m.start()].count("\n") + 1
                violations.append(f"  {md.name}:{lineno}")
    return violations


def check_no_raw_untested_blocks(
    docs_dir: Path,
    *,
    known_uncompilable: set[tuple[str, int]] | None = None,
) -> list[str]:
    """Every ```clausal block must be a --8<-- ref, contain a Test, or compile.

    ``known_uncompilable`` is an allowlist of ``(filename, line_number)`` pairs
    for legacy display fragments that don't compile standalone (partial
    examples, pseudo-code). Used by core docs that predate the snippet pattern.
    """
    from clausal.testing import load_clausal_module

    allowed = known_uncompilable or set()
    violations = []
    for md in sorted(docs_dir.glob("*.md")):
        text = md.read_text()
        for m in _CLAUSAL_FENCE_RE.finditer(text):
            content = m.group(1)
            if _is_skip(content) or _is_snippet(content) or _has_test(content):
                continue
            lineno = text[: m.start()].count("\n") + 1
            if (md.name, lineno) in allowed:
                continue
            # Try to compile — if it works, the block is fine.
            with tempfile.NamedTemporaryFile(
                suffix=".clausal", mode="w", delete=False
            ) as f:
                f.write(content)
                tmp = Path(f.name)
            try:
                load_clausal_module(tmp)
            except Exception:
                first_line = content.strip().split("\n", 1)[0].strip()[:60]
                violations.append(f"  {md.name}:{lineno}  {first_line}")
            finally:
                tmp.unlink(missing_ok=True)
    return violations
