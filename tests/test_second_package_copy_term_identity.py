"""Regression tests: a second copy of the ``clausal`` package in one process
must not silently destroy term identity for the copy that is already running.

Background
----------
``clausal/logic/predicate.py`` hands the C accelerator its ``PredicateMeta`` via
``_register_predicate_meta(PredicateMeta)``.  On the C side that lands in a
single ``static PyObject *PredicateMeta_type``, and ``is_term_instance`` answers
``isinstance(type(obj), PredicateMeta_type)`` against it.

The slot is process-global and the extension uses single-phase init, so its
static state survives ``del sys.modules["clausal..."]``.  A *second* import of
the package therefore builds a second ``PredicateMeta`` class and re-registers
it, overwriting the slot — after which the FIRST copy's ``is_term_instance``
returns ``False`` for the first copy's own term instances, because their
metaclass is no longer the one the C slot holds.  Every caller then treats a
perfectly good functor instance as a non-term.  The reported symptom was
``head_key`` refusing a clause head it was holding::

    TypeError: Cannot extract (functor, arity) from head term:
      decision(PROFILE=AttVar(_1), VALUE='yes')

which is the C fast path disagreeing with its own Python fallback
(``_is_term_instance_py`` still answers ``True`` for the same object).

This is not about two ``.clausal`` modules declaring the same functor name —
that works fine, and no amount of name/arity keying is involved.  It takes two
copies of the *package*, which is what ``sys.modules`` surgery produces.  See
``todo/done/functor-identity-leaks-across-modules-in-one-process.md``.

Both copies must therefore be internally consistent: whoever claimed the C slot
keeps using it, and any later copy falls back to the pure-Python
implementations, which are keyed on that copy's own ``PredicateMeta``.

Driven in a subprocess because the fault requires two package copies in one
interpreter, which cannot be undone inside the test process (prior art:
``tests/test_transitive_py_module_import.py``).
"""

from __future__ import annotations

import collections
import os
import subprocess
import sys
import textwrap

import pytest

from clausal.logic.database import head_key
from clausal.logic.predicate import PredicateMeta

# Source tree root (parent of the ``clausal`` package dir).
_SRC_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The ``sys.modules`` surgery that creates the second copy.  This is exactly the
# shape found in the wild (a test asserting that some module does *not* pull in
# clausal, which drops every ``clausal*`` entry and leaves already-imported
# holders pointing at the now-orphaned first copy).
_WIPE = """
for _k in [_k for _k in list(sys.modules) if _k == "clausal" or _k.startswith("clausal.")]:
    del sys.modules[_k]
"""

_RULEBASE = """-private([decision(PROFILE, VALUE)])
decision(PROFILE, "yes") <- (PROFILE == 1)
"""


def _run(tmp_path, *parts: str) -> subprocess.CompletedProcess:
    """Run the concatenation of *parts* in a subprocess with the source tree on
    ``PYTHONPATH``.

    Each part is dedented separately: the fragments are spliced together from
    differently-indented literals, and dedenting the concatenation would find a
    common prefix of ``""`` and silently do nothing.

    cwd is a throwaway directory so the source root arrives via ``PYTHONPATH``
    alone and cannot be shadowed by a same-named tree next to the test.
    """
    script = tmp_path / "prog.py"
    script.write_text("import sys\n" + "".join(textwrap.dedent(p) for p in parts))
    env = dict(os.environ)
    env["PYTHONPATH"] = _SRC_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-u", str(script)],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


def test_two_package_copies_really_are_distinct(tmp_path):
    """Guard on the premise: the wipe genuinely mints a second PredicateMeta.

    If a future change made the package import idempotent across a
    ``sys.modules`` wipe, the two tests below would pass for a reason that has
    nothing to do with the fix, so pin the precondition explicitly.
    """
    r = _run(
        tmp_path,
        """
        import clausal.logic.predicate as first
        """,
        _WIPE,
        """
        import clausal.logic.predicate as second
        assert first is not second, "expected a genuinely re-executed module"
        assert first.PredicateMeta is not second.PredicateMeta, (
            "expected a second, distinct PredicateMeta class"
        )
        print("PRECONDITION-OK")
        """,
    )
    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert "PRECONDITION-OK" in r.stdout


def test_first_copy_keeps_term_identity_after_second_copy_is_imported(tmp_path):
    """The C fast path must not start disagreeing with its Python fallback.

    This is the fault in its smallest form: one term instance, built and checked
    by the first copy, before and after a second copy appears.
    """
    r = _run(
        tmp_path,
        """
        import clausal.logic.predicate as first

        class demo(metaclass=first.PredicateMeta):
            _fields = ("a", "b")

        inst = demo(1, 2)
        assert first.is_term_instance(inst) is True, "broken before the wipe"
        """,
        _WIPE,
        """
        import clausal.logic.predicate as second   # noqa: F401  — second copy

        # The accelerated check and the reference implementation must agree, and
        # both must still recognise the first copy's own term instance.
        assert first._is_term_instance_py(inst) is True, "reference impl regressed"
        assert first.is_term_instance(inst) is True, (
            "first copy's is_term_instance lost its own term instance after a "
            "second package copy was imported"
        )
        assert first.term_field_names(inst) == ("a", "b"), (
            f"first copy's term_field_names regressed: "
            f"{first.term_field_names(inst)!r}"
        )

        # ...and the second copy must be self-consistent too, on its own terms.
        class demo2(metaclass=second.PredicateMeta):
            _fields = ("x",)

        inst2 = demo2(3)
        assert second.is_term_instance(inst2) is True, (
            "second copy cannot recognise its own term instance"
        )
        assert second.term_field_names(inst2) == ("x",)
        print("IDENTITY-OK")
        """,
    )
    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert "IDENTITY-OK" in r.stdout


def test_term_crossing_between_copies_is_refused_with_a_precise_message(tmp_path):
    """A term that genuinely crosses the copy boundary must say so.

    Loading a rulebase through the first copy's ``_load_module`` after a second
    copy exists produces a *mixed* term flow that no per-copy policy can rescue:
    the head class is minted by the first copy's ``PredicateMeta`` (the captured
    loader's compiler builds it), while the ``Database`` it is asserted into
    belongs to the second copy (the generated module body re-resolves
    ``clausal.*`` through ``sys.modules``).  Neither copy is wrong; the term
    simply is not a term to its checker.

    That case stays an error — bridging it would mean giving up nominal term
    identity engine-wide, which is a redesign, not a fix (see
    ``todo/term-identity-cannot-cross-two-package-copies.md``).  What must not
    stay is the old message, which said "expected a functor dataclass instance"
    while holding one and named neither class nor either declaring module.
    """
    rb = tmp_path / "rb.clausal"
    rb.write_text(_RULEBASE)
    r = _run(
        tmp_path,
        f"""
        import clausal.import_hook                       # noqa: F401
        from clausal.import_hook import _load_module

        rb = {str(rb)!r}
        first = _load_module("rb_before", rb)
        assert first.decision is not None
        """,
        _WIPE,
        """
        import clausal                                   # noqa: F401  — second copy

        # Same loader object the harness captured before the wipe.
        try:
            _load_module("rb_after", rb)
        except TypeError as exc:
            print("DIAGNOSTIC-START")
            print(exc)
            print("DIAGNOSTIC-END")
        else:
            print("UNEXPECTEDLY-LOADED")
        """,
    )
    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert "UNEXPECTEDLY-LOADED" not in r.stdout
    msg = r.stdout.split("DIAGNOSTIC-START", 1)[-1].split("DIAGNOSTIC-END", 1)[0]

    # Names the offending class, at its real arity, and where it was declared.
    assert "decision/2" in msg, msg
    assert "rb_after" in msg, msg
    # Names both metaclasses, distinguishably, and where each came from.
    assert msg.count("PredicateMeta id=0x") == 2, msg
    ids = [
        chunk.split()[0]
        for chunk in msg.split("PredicateMeta id=0x")[1:]
    ]
    assert ids[0] != ids[1], f"both metaclasses reported with the same id: {msg}"
    assert msg.count("clausal/logic/predicate.py:") == 2, msg
    # And says what the situation actually is, rather than that we wanted a
    # functor instance while holding one.
    assert "two copies of the clausal package" in msg, msg
    assert "sys.modules" in msg, msg


# ── the diagnostic declines when it has nothing to say ───────────────────────
#
# The two-copy case above needs a subprocess, which makes it slow and coarse.
# These pin the guards in-process, because the failure mode they prevent is a
# diagnostic that fires confidently on something else entirely.


def test_a_recognised_term_gets_no_explanation():
    """Nothing foreign about it, so the caller's own wording stands."""
    from clausal.logic.predicate import describe_term_identity_mismatch

    class Thing(metaclass=PredicateMeta):
        _fields = ("a",)

    assert describe_term_identity_mismatch(Thing) == ""


def test_a_plain_object_gets_no_explanation():
    from clausal.logic.predicate import describe_term_identity_mismatch

    assert describe_term_identity_mismatch(object()) == ""
    assert describe_term_identity_mismatch(42) == ""


def test_a_namedtuple_is_not_reported_as_a_second_package_copy():
    """A stdlib namedtuple carries ``_fields``, and that used to be the whole
    test — so passing one as a head produced a confident, entirely wrong
    account of two live clausal copies and advice to fix import surgery that
    never happened.  Its metaclass is plain ``type``, which is the tell.
    """
    from clausal.logic.predicate import describe_term_identity_mismatch

    Point = collections.namedtuple("Point", "x y")
    assert describe_term_identity_mismatch(Point(1, 2)) == ""

    # ...and the error a caller actually raises stays its own.
    with pytest.raises(TypeError) as excinfo:
        head_key(Point(1, 2))
    assert "two copies" not in str(excinfo.value)
    assert "Cannot extract (functor, arity)" in str(excinfo.value)


def test_the_diagnostic_never_raises():
    """It runs on the way into someone else's ``raise``."""
    from clausal.logic.predicate import describe_term_identity_mismatch

    class Exploding:
        @property
        def _fields(self):  # pragma: no cover - accessed via type, not instance
            raise RuntimeError("boom")

    assert describe_term_identity_mismatch(Exploding()) == ""
