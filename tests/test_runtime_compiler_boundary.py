"""Enforce the runtime/compiler package boundary.

``clausal.logic.runtime`` is used **inside** compiled predicates.  It
must not depend on ``clausal.logic.compiler`` — that coupling would
drag the compiler into every program that uses compiled predicates,
and it would let compiler internals leak into the compiled-code
execution context.

This test walks every Python file under ``clausal/logic/runtime/``
and asserts none of them contain ``from clausal.logic.compiler`` or
``import clausal.logic.compiler``.
"""
from __future__ import annotations

import ast
import pathlib


RUNTIME_ROOT = pathlib.Path("clausal/logic/runtime")


def _iter_runtime_python_files():
    yield from RUNTIME_ROOT.rglob("*.py")


def _imports_from_compiler(source: str) -> list[str]:
    """Return the offending import statements (source lines) in *source*."""
    tree = ast.parse(source)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("clausal.logic.compiler"):
                offenders.append(f"from {node.module} import ...")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("clausal.logic.compiler"):
                    offenders.append(f"import {alias.name}")
    return offenders


def test_runtime_does_not_import_from_compiler():
    """Every file in clausal.logic.runtime must be compiler-free."""
    assert RUNTIME_ROOT.is_dir(), (
        f"Expected {RUNTIME_ROOT} to exist — "
        "slice A of the compiler migration should have created it."
    )
    bad: dict[str, list[str]] = {}
    for path in _iter_runtime_python_files():
        source = path.read_text()
        offenders = _imports_from_compiler(source)
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


def test_runtime_package_is_importable_standalone():
    """Importing clausal.logic.runtime should not drag in the compiler."""
    import sys

    # Drop any already-loaded compiler modules so we can observe a clean import.
    before = {k for k in sys.modules if k.startswith("clausal.logic.compiler")}
    for key in list(sys.modules):
        if key.startswith("clausal.logic.compiler"):
            del sys.modules[key]
    try:
        import clausal.logic.runtime  # noqa: F401
        import clausal.logic.runtime.list_unify  # noqa: F401
        import clausal.logic.runtime.body_star_unify  # noqa: F401
        import clausal.logic.runtime.tramp_call  # noqa: F401
        loaded_compiler_modules = {
            k for k in sys.modules if k.startswith("clausal.logic.compiler")
        } - before
        assert not loaded_compiler_modules, (
            "Importing clausal.logic.runtime.* should not have loaded any "
            f"clausal.logic.compiler.* modules, but loaded: "
            f"{sorted(loaded_compiler_modules)}"
        )
    finally:
        # Don't leave the module table scrubbed for other tests.
        import clausal.logic.compiler  # noqa: F401
