"""Diagnosability aid for cross-module declared-atom identity mismatch.

Two modules that each ``-module``/``-private``-*declare* the same atom hold
**distinct** module-local ``PredicateMeta`` classes: unifying a value carrying
one against a value carrying the other fails silently — no error, no solution
(``docs/import.md`` "Same-name declared atoms do not unify across modules";
``GLOBAL_ATOMS_DEFAULT.md``).  The behaviour is *intended* scoping and is NOT
changed here.

Opt-in via ``CLAUSAL_WARN_ATOM_IDENTITY=1``: when unification compares two
zero-arity atom classes with the same ``__name__`` but different identity, a
one-shot ``ClausalAtomIdentityMismatchWarning`` (a ``ClausalAtomShadowingWarning``
subclass) fires naming both owning modules.  With the flag off the diagnostic
``__unify__`` is not installed at all and the hot path is unchanged.

The end-to-end package repro runs in a subprocess because the flag is read at
atom-class-creation time and the one-shot dedup + warnings filters are
process-global.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import warnings

import pytest

from clausal.logic.compiler_v2 import (
    ClausalAtomIdentityMismatchWarning,
    ClausalAtomShadowingWarning,
    _process_declarations,
)
from clausal.logic.predicate import (
    PredicateMeta,
    _atom_identity_warned,
    _make_atom_identity_unify,
    make_atom,
)
from clausal.logic.variables import unify
from clausal.logic.variables._variables import Trail


_SRC_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── Family membership ────────────────────────────────────────────────────────


def test_mismatch_warning_is_in_shadowing_family():
    """The new warning subclasses the existing atom-shadowing family, so
    ``-overwrites``/warning-filter machinery targeting the family covers it."""
    assert issubclass(
        ClausalAtomIdentityMismatchWarning, ClausalAtomShadowingWarning
    )


# ── Unit-level compare-site hook ─────────────────────────────────────────────


def _make_declared_atom(name: str, owner: str):
    """A zero-arity declared atom with a diagnostic __unify__, owned by ``owner``.

    Mirrors what ``_process_declarations`` mints when the flag is on, without
    depending on the process-wide env var (so this test is order-independent).
    """
    atom = make_atom(name)
    atom.__module__ = owner
    atom.__unify__ = _make_atom_identity_unify(atom)
    return atom


def test_cross_module_same_name_atoms_warn_and_still_fail():
    """Same name, different owning modules → warning fires, unify still False."""
    _atom_identity_warned.clear()
    a = _make_declared_atom("approved", "pkg.lib")
    b = _make_declared_atom("approved", "pkg.caller")
    assert a is not b

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = unify(a, b, Trail())

    assert result is False, "intended behaviour: distinct atoms do not unify"
    mismatch = [
        w for w in caught
        if issubclass(w.category, ClausalAtomIdentityMismatchWarning)
    ]
    assert len(mismatch) == 1
    msg = str(mismatch[0].message)
    assert "approved" in msg
    assert "pkg.lib" in msg
    assert "pkg.caller" in msg


def test_warning_is_one_shot_per_pair():
    """Repeated compares of the same atom pair warn only once."""
    _atom_identity_warned.clear()
    a = _make_declared_atom("token", "pkg.a")
    b = _make_declared_atom("token", "pkg.b")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        unify(a, b, Trail())
        unify(a, b, Trail())
        unify(b, a, Trail())  # symmetric compare, same normalised pair
    mismatch = [
        w for w in caught
        if issubclass(w.category, ClausalAtomIdentityMismatchWarning)
    ]
    assert len(mismatch) == 1


def test_same_identity_atoms_do_not_warn():
    """An atom unified with itself succeeds and never warns."""
    _atom_identity_warned.clear()
    a = _make_declared_atom("ok", "pkg.lib")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert unify(a, a, Trail()) is True
    assert not [
        w for w in caught
        if issubclass(w.category, ClausalAtomIdentityMismatchWarning)
    ]


# ── Flag gating at class-creation time ───────────────────────────────────────


def test_flag_off_installs_no_unify_hook(monkeypatch):
    """With the flag unset, a freshly minted atom class carries no __unify__ —
    the hot unify path is byte-for-byte the original identity comparison."""
    monkeypatch.delenv("CLAUSAL_WARN_ATOM_IDENTITY", raising=False)
    atom = PredicateMeta("flag_off_atom", (), {"_fields": ()})
    assert "__unify__" not in atom.__dict__


def test_flag_on_installs_unify_hook(monkeypatch):
    monkeypatch.setenv("CLAUSAL_WARN_ATOM_IDENTITY", "1")
    atom = PredicateMeta("flag_on_atom", (), {"_fields": ()})
    assert "__unify__" in atom.__dict__


def test_declared_atoms_attributed_to_owning_module():
    """``_process_declarations`` stamps a declared atom's ``__module__`` with
    its owning clausal module (not clausal.logic.predicate) so the diagnostic
    can name the real owner."""
    module_dict = {"__name__": "pkg.owner", "__file__": "<pkg.owner>"}
    from clausal.import_hook import EmbedTransformer
    import ast
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tree = ast.parse("-private([owned_atom])\n")
        t = EmbedTransformer()
        t.visit(tree)
    _process_declarations(t._module_items, module_dict)
    assert module_dict["owned_atom"].__module__ == "pkg.owner"


# ── End-to-end two-module package repro (subprocess) ─────────────────────────


_LIB_SRC = textwrap.dedent("""\
    -module(atomlib, [approved, Check(X)])

    Check(approved),
""")

_CALLER_SRC = textwrap.dedent("""\
    -import_from(atomid_pkg.atomlib, [Check])
    -private([approved])

    Ask() <- Check(approved)
""")

_DRIVER = textwrap.dedent("""\
    import sys, warnings
    import clausal  # noqa: F401  (installs the .clausal import hook)
    from clausal.logic.compiler_v2 import ClausalAtomIdentityMismatchWarning
    from clausal.logic.solve import call

    warnings.simplefilter("always")
    import atomid_pkg.caller as caller

    records = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        lm = caller.__dict__["$module"]
        # Ask/0 calls Check(approved) where `approved` is the CALLER's local
        # declaration but Check comes from atomlib whose clause head carries
        # atomlib's `approved` — distinct classes, so no solution.
        solutions = list(call("Ask", module=lm))
        records = [
            w for w in caught
            if issubclass(w.category, ClausalAtomIdentityMismatchWarning)
        ]

    assert solutions == [], f"expected no solution, got {solutions!r}"
    print("MISMATCH_WARNINGS", len(records))
""")


def _write_package(tmp_path):
    pkg = tmp_path / "atomid_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "atomlib.clausal").write_text(_LIB_SRC)
    (pkg / "caller.clausal").write_text(_CALLER_SRC)
    return tmp_path


def _run_driver(tmp_path, *, flag_on: bool):
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(tmp_path), _SRC_ROOT])
    env.pop("CLAUSAL_WARN_ATOM_IDENTITY", None)
    if flag_on:
        env["CLAUSAL_WARN_ATOM_IDENTITY"] = "1"
    proc = subprocess.run(
        [sys.executable, "-c", _DRIVER],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"driver failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    for line in proc.stdout.splitlines():
        if line.startswith("MISMATCH_WARNINGS"):
            return int(line.split()[1])
    raise AssertionError(f"no MISMATCH_WARNINGS line:\n{proc.stdout}")


def test_package_repro_warns_once_under_flag(tmp_path):
    """Two-module package, duplicate declared atom: exactly one warning."""
    root = _write_package(tmp_path)
    assert _run_driver(root, flag_on=True) == 1


def test_package_repro_silent_without_flag(tmp_path):
    """Same package, flag off: no warning (behaviour still silently fails)."""
    root = _write_package(tmp_path)
    assert _run_driver(root, flag_on=False) == 0
