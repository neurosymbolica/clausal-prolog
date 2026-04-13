"""Coverage tests for doc code blocks.

1. No # skip blocks allowed (ratchet at 0).
2. Every ```clausal block must be either a --8<-- snippet reference
   or contain at least one Test clause.
"""

import re
from pathlib import Path

_DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
_CLAUSAL_FENCE_RE = re.compile(r"```clausal\n(.*?)```", re.DOTALL)

_HOWTO = (
    "See implementation_plans/DOC_SNIPPET_TESTING.md for the pattern: "
    "create a section in tests/fixtures/docs/<page>_sigs.txt (display) "
    "or tests/fixtures/docs/<page>_examples.clausal (executable), "
    "add companion tests in tests/fixtures/docs/<page>_sig_tests.clausal, "
    'then reference via --8<-- "tests/fixtures/docs/<file>:<section>" '
    "in the markdown."
)


def _is_skip(content: str) -> bool:
    first_line = content.lstrip().split("\n", 1)[0].strip()
    return first_line in ("# skip", "# clausal: skip")


def _is_snippet(content: str) -> bool:
    lines = [line.strip() for line in content.strip().split("\n") if line.strip()]
    return bool(lines) and all(line.startswith("--8<--") for line in lines)


def _has_test(content: str) -> bool:
    return bool(re.search(r"Test\s*\(", content))


def test_no_skip_blocks():
    """No # skip blocks allowed — all doc snippets must be tested."""
    # nv
    violations = []
    for md in sorted(_DOCS_DIR.glob("*.md")):
        text = md.read_text()
        for m in _CLAUSAL_FENCE_RE.finditer(text):
            if _is_skip(m.group(1)):
                lineno = text[: m.start()].count("\n") + 1
                violations.append(f"  {md.name}:{lineno}")
    assert not violations, (
        f"Found {len(violations)} # skip block(s):\n"
        + "\n".join(violations)
        + f"\n\n{_HOWTO}"
    )


def test_no_raw_untested_blocks():
    """New ```clausal blocks must be --8<-- references, contain a Test, or
    compile successfully.  Blocks that fail to compile and have no Test
    are the gap — they silently rot.  This test catches them.

    Inline blocks that compile (imports, predicate defs, working examples)
    are allowed — conftest.py already compile-checks them at collection time.
    """
    # nv
    import tempfile
    from clausal.testing import load_clausal_module

    # Pre-existing display fragments that don't compile standalone.
    # These are partial examples / pseudo-code in guide pages.
    # TODO: migrate these to snippet references.
    _KNOWN_UNCOMPILABLE = {
        ("directives.md", 218),
        ("for_ai_agents.md", 155),
        ("for_ai_agents.md", 206),
        ("for_prolog_programmers.md", 61),
        ("for_prolog_programmers.md", 81),
        ("for_prolog_programmers.md", 98),
        ("for_prolog_programmers.md", 114),
        ("for_python_programmers.md", 272),
        ("for_python_programmers.md", 291),
        ("index.md", 10),
        ("purity.md", 111),
    }

    violations = []
    for md in sorted(_DOCS_DIR.glob("*.md")):
        text = md.read_text()
        for m in _CLAUSAL_FENCE_RE.finditer(text):
            content = m.group(1)
            if _is_skip(content) or _is_snippet(content) or _has_test(content):
                continue
            lineno = text[: m.start()].count("\n") + 1
            if (md.name, lineno) in _KNOWN_UNCOMPILABLE:
                continue
            # Try to compile — if it works, the block is fine
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
    assert not violations, (
        f"Found {len(violations)} ```clausal block(s) that fail to compile "
        f"and have no Test clause or --8<-- reference:\n"
        + "\n".join(violations)
        + "\n\nEither fix the code, add a Test clause, or move to a "
        + f"tested fixture file.\n{_HOWTO}"
    )
