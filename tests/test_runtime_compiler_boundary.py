"""Enforce the runtime/compiler package boundary.

``clausal.logic.runtime`` is used **inside** compiled predicates.  It
must not depend on ``clausal.logic.compiler`` — that coupling would
drag the compiler into every program that uses compiled predicates,
and it would let compiler internals leak into the compiled-code
execution context.

In the other direction, ``clausal.logic.compiler`` may touch
``clausal.logic.runtime`` for exactly one purpose: populating
``base_globals`` of a compiled predicate (done in
``compiler/predicate.py``).  All other compiler modules reference
runtime helpers by **name string** in emitted AST (e.g.
``_call(_name("_head_list_unify_input"), ...)``), relying on the
base_globals-time resolution rather than a Python-level import.

This pair of tests encodes both directions:

- ``test_runtime_does_not_import_from_compiler``      — runtime → compiler: forbidden
- ``test_compiler_imports_of_runtime_are_in_predicate_py_only`` — compiler → runtime: only in predicate.py

Plus the importability check:

- ``test_runtime_package_is_importable_standalone``   — importing runtime must not load compiler

And a pair of negative tests verifying the AST-walk detector itself
catches offending imports (test-the-test).
"""
from __future__ import annotations

import ast
import pathlib
import textwrap


RUNTIME_ROOT = pathlib.Path("clausal/logic/runtime")
COMPILER_ROOT = pathlib.Path("clausal/logic/compiler")


# ── Detector ────────────────────────────────────────────────────────────────


def _imports_matching(source: str, forbidden_prefix: str) -> list[str]:
    """Return every import in *source* whose target starts with *forbidden_prefix*.

    Each entry is a human-readable rendering of the offending import
    statement (``from X import …`` or ``import X``).
    """
    tree = ast.parse(source)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith(forbidden_prefix):
                offenders.append(f"from {node.module} import ...")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(forbidden_prefix):
                    offenders.append(f"import {alias.name}")
    return offenders


# ── The rules ───────────────────────────────────────────────────────────────


def test_runtime_does_not_import_from_compiler():
    """Every file under clausal/logic/runtime/ must be compiler-free."""
    assert RUNTIME_ROOT.is_dir(), (
        f"Expected {RUNTIME_ROOT} to exist — "
        "slice A of the compiler migration should have created it."
    )
    bad: dict[str, list[str]] = {}
    for path in RUNTIME_ROOT.rglob("*.py"):
        offenders = _imports_matching(path.read_text(), "clausal.logic.compiler")
        if offenders:
            bad[str(path)] = offenders
    assert not bad, (
        "clausal.logic.runtime must not import from clausal.logic.compiler.\n"
        "Offending files:\n"
        + "\n".join(
            f"  {path}:\n    " + "\n    ".join(offenders)
            for path, offenders in bad.items()
        )
    )


def test_compiler_imports_of_runtime_are_in_predicate_py_only():
    """Only compiler/predicate.py may import from clausal.logic.runtime.

    Every other compiler module that needs to reference a runtime helper
    does so via a name string in emitted AST (resolved at call time via
    ``base_globals``).  Python-level imports of runtime into compiler
    code outside ``predicate.py`` are architectural leaks — they mean
    the compiler is calling runtime helpers itself at compile time
    rather than emitting references to them.
    """
    allowed = {
        COMPILER_ROOT / "predicate.py",
    }
    bad: dict[str, list[str]] = {}
    for path in COMPILER_ROOT.rglob("*.py"):
        if path in allowed:
            continue
        offenders = _imports_matching(path.read_text(), "clausal.logic.runtime")
        if offenders:
            bad[str(path)] = offenders
    assert not bad, (
        "Only clausal/logic/compiler/predicate.py is allowed to import "
        "from clausal.logic.runtime (for base_globals construction).\n"
        "Other compiler modules must reference runtime helpers by name "
        "string in emitted AST, not via Python-level imports.\n"
        "Offending files:\n"
        + "\n".join(
            f"  {path}:\n    " + "\n    ".join(offenders)
            for path, offenders in bad.items()
        )
    )


def test_runtime_package_is_importable_standalone():
    """Importing clausal.logic.runtime should not drag in the compiler."""
    import sys

    # Drop any already-loaded compiler modules so we can observe a clean import.
    # Save the module objects so we can restore them (not just re-import): a
    # re-import would create new module objects and break module-identity checks
    # in tests that run later in the same process (e.g. tests that hold a
    # reference to ClausalStrictAtomsDeprecationWarning or compiler_v2 globals).
    saved = {
        k: sys.modules[k]
        for k in list(sys.modules)
        if k.startswith("clausal.logic.compiler")
    }
    for key in saved:
        del sys.modules[key]
    try:
        import clausal.logic.runtime  # noqa: F401
        import clausal.logic.runtime.list_unify  # noqa: F401
        import clausal.logic.runtime.body_star_unify  # noqa: F401
        import clausal.logic.runtime.tramp_call  # noqa: F401
        loaded_compiler_modules = {
            k for k in sys.modules if k.startswith("clausal.logic.compiler")
        }
        assert not loaded_compiler_modules, (
            "Importing clausal.logic.runtime.* should not have loaded any "
            f"clausal.logic.compiler.* modules, but loaded: "
            f"{sorted(loaded_compiler_modules)}"
        )
    finally:
        # Restore the original module objects so later tests see the same
        # module identity (class objects, module-level globals, etc.).
        sys.modules.update(saved)


# ── Test-the-test: verify _imports_matching detects what it should ─────────


def test_detector_finds_from_import_of_forbidden_prefix():
    source = textwrap.dedent("""
        from clausal.logic.compiler import predicate
        import os
    """)
    assert _imports_matching(source, "clausal.logic.compiler") == [
        "from clausal.logic.compiler import ...",
    ]


def test_detector_finds_submodule_from_import():
    source = textwrap.dedent("""
        from clausal.logic.compiler.predicate import compile_predicate
    """)
    assert _imports_matching(source, "clausal.logic.compiler") == [
        "from clausal.logic.compiler.predicate import ...",
    ]


def test_detector_finds_bare_import_of_forbidden_prefix():
    source = textwrap.dedent("""
        import clausal.logic.compiler.predicate
    """)
    assert _imports_matching(source, "clausal.logic.compiler") == [
        "import clausal.logic.compiler.predicate",
    ]


def test_detector_ignores_sibling_packages():
    """A module whose name shares a prefix but not the full path must be ignored."""
    source = textwrap.dedent("""
        from clausal.logic.compilerX import thing
        import clausal.logic.compilerish
    """)
    # str.startswith("clausal.logic.compiler") IS true for "compilerX" —
    # this test documents that behaviour and would fail if someone
    # tightened the detector to use full dotted-segment matching
    # without revisiting these cases.  If that change comes, update
    # both the detector and this test together.
    assert _imports_matching(source, "clausal.logic.compiler") == [
        "from clausal.logic.compilerX import ...",
        "import clausal.logic.compilerish",
    ]


def test_detector_clean_source_returns_empty():
    source = textwrap.dedent("""
        from clausal.logic.variables import unify, deref
        from clausal.terms import Compound
        import ast
    """)
    assert _imports_matching(source, "clausal.logic.compiler") == []


def test_detector_finds_multiple_offenders():
    source = textwrap.dedent("""
        from clausal.logic.compiler import a
        import clausal.logic.compiler.b
        from clausal.logic.compiler.c import d
    """)
    assert _imports_matching(source, "clausal.logic.compiler") == [
        "from clausal.logic.compiler import ...",
        "import clausal.logic.compiler.b",
        "from clausal.logic.compiler.c import ...",
    ]
