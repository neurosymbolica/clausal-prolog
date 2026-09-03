"""Phase 2 bridge, Task 2 -- the ``-tagged_terms`` module flag.

Spec: ``docs/superpowers/plans/2026-09-03-phase2-bridge.md`` Task 2;
design: ``implementation_plans/tagged-tuple-term-representation.md``.

Three groups of tests, in the order they were written:

1. ``TestDefaultPathGolden`` -- the DEFAULT-PATH INVARIANT.  Modules WITHOUT
   the directive must compile to byte-identical Python.  Written and its
   golden captured BEFORE any compiler change, so a regression in the
   flag-off path shows up as a diff against code that predates the feature.
2. ``TestDirective`` -- ``-tagged_terms`` parsing and threading.
3. ``TestCellEmission`` / ``TestHeadPatterns`` / ``TestParity`` -- what the
   flag actually does.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from tests.tagged_terms_support import (
    capture_predicate_codegen, normalize_term,
)


_GOLDEN_DIR = pathlib.Path(__file__).parent / "golden"

# Unflagged fixtures whose codegen the DEFAULT-PATH golden pins.  Chosen to
# span the branches Task 2 touches: declared-functor construction from source
# (``Call(LoadName)``), recursion, atoms as values, str/int head literals,
# argument indexing with compound buckets, and list/compound head mixing.
_GOLDEN_MODULES = [
    "tests.fixtures.struct_tabling",
    "tests.fixtures.tagged_shapes",
    "tests.fixtures.deep_index",
    "tests.fixtures.head_list_compound",
    "tests.fixtures.edge_graph",
]


def _golden_path(module_name: str) -> pathlib.Path:
    return _GOLDEN_DIR / f"{module_name.rsplit('.', 1)[-1]}.codegen.txt"


class TestDefaultPathGolden:
    """Flag off => byte-identical compilation.

    METHOD.  ``capture_predicate_codegen`` re-drives each predicate's real
    ``_lazy_recompile`` closure (same globals, same strategy, same indexing)
    and ``ast.unparse``\\ s every ``FunctionDef`` the compiler emits --
    the predicate function plus every index bucket, per-position default and
    all-clauses fallback.  The text was captured from the compiler as it
    stood at the commit BEFORE ``-tagged_terms`` existed and committed under
    ``tests/golden/``.  Any change to the flag-OFF emission path -- a
    reordered branch, an extra guard, a renamed local -- produces a diff
    here.

    Regenerate deliberately (never to make a red test green without reading
    the diff) with::

        CLAUSAL_REGEN_GOLDEN=1 pytest tests/test_tagged_terms.py -k golden
    """

    @pytest.mark.parametrize("module_name", _GOLDEN_MODULES)
    def test_unflagged_codegen_unchanged(self, module_name, monkeypatch):
        import os

        actual = capture_predicate_codegen(module_name)
        path = _golden_path(module_name)
        if os.environ.get("CLAUSAL_REGEN_GOLDEN"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(actual)
            pytest.skip(f"regenerated {path}")
        assert path.exists(), (
            f"missing golden {path}; regenerate with CLAUSAL_REGEN_GOLDEN=1"
        )
        expected = path.read_text()
        assert actual == expected, (
            f"{module_name}: flag-off codegen changed -- the DEFAULT-PATH "
            f"INVARIANT is broken (or the change is intended and the golden "
            f"needs regenerating after review)."
        )

    def test_golden_capture_is_deterministic(self):
        """Two captures of the same module agree.

        Guards the golden itself: if compilation were order- or
        id()-dependent the golden would be a flake generator rather than an
        invariant.
        """
        a = capture_predicate_codegen("tests.fixtures.struct_tabling")
        b = capture_predicate_codegen("tests.fixtures.struct_tabling")
        assert a == b

    def test_golden_captures_bucket_functions(self):
        """The golden covers indexed-dispatch codegen, not just the arms."""
        src = capture_predicate_codegen("tests.fixtures.tagged_shapes")
        assert "kind__p0_b0__2" in src
        assert "kind__all__2" in src
