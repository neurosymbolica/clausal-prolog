"""A DIRECT call of an unknown procedure is ISO ``existence_error``, catchable.

Operator ruling 2026-09-25 ("like Scryer"; SWI is not a target).  Scryer::

    ?- catch(nosuch(1), E, true).
    E = error(existence_error(procedure, nosuch/1), nosuch/1).

Before 2026-09-25 Clausal raised ``PredicateNotFoundError`` as a plain
``KeyError``, so ``catch/3`` bound only the transliterated
``PredicateNotFoundError('Predicate nosuch/1 not found ...')`` compound, which
no ISO catcher matches; a module-qualified ``m.nosuch(1)`` died on CPython's
``NameError: name 'm.nosuch' is not defined``; and ``solve.call`` raised a
bare ``KeyError``.  All three now carry
``error(existence_error(procedure, Name/Arity), Why)``.

ADD, not replace: ``PredicateNotFoundError`` is a ``LogicException`` AND a
``KeyError`` (the design ``PredicateArityMismatchError`` got the same day), so
``except KeyError`` / ``except PredicateNotFoundError`` and a ``++KeyError``
catcher keep working, ``++Exception`` still never catches a logic ball, and
the "defines: ... / -> define it or import it" diagnostic is kept, as the
message and as the prose recorded for the term.

Both eras: an UNBOUND name (the class era's only shape for a predicate that
does not exist) and a name bound to a module-qualified HANDLE whose owner
lacks the predicate (the handle era, emulated the way
``tests/test_arity_mismatch_is_iso_existence_error_both_eras.py`` does).
Both drive loops: the C core in-process, the pure-Python twin in a
subprocess with the C extension blocked.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap

import pytest

import clausal
from clausal.logic.atoms import mangle, mint
from clausal import cell_args, cell_functor
from clausal.logic.exceptions import LogicException, error_prose
from clausal.logic.solve import call
from clausal.logic.variables import Var, walk
from clausal.predicate_diagnostics import PredicateNotFoundError
from clausal.terms import Compound


def _load(tmp_path, monkeypatch, name, body):
    from clausal.import_hook import _load_module
    monkeypatch.syspath_prepend(str(tmp_path))
    p = tmp_path / f"{name}.clausal"
    p.write_text(textwrap.dedent(body).lstrip())
    mod = _load_module(name, str(p))
    assert sys.modules[name] is mod
    return mod


def _pi(name, arity):
    return ("/", mint(name), arity)


def _assert_iso(term, name, arity):
    """``error(existence_error(procedure, Name/Arity), Context)``."""
    assert type(term) is tuple and cell_functor(term) == "error", term
    formal = cell_args(term)[0]
    assert type(formal) is tuple, formal
    assert cell_functor(formal) == "existence_error"
    assert cell_args(formal)[0] == mint("procedure")
    assert cell_args(formal)[1] == _pi(name, arity)


def _context_message(term):
    """The engine's diagnostic text, verbatim, for
    ``error(existence_error(procedure, PI), PI)`` -- the second argument is
    the PI itself (Scryer); the text is the prose recorded for the term."""
    assert cell_args(term)[1] == cell_args(cell_args(term)[0])[1], term
    return error_prose(term)


def _uncaught_message(goal, module):
    """The diagnostic of the Python exception *goal* raises.  A term caught
    by ``catch/3`` is Scryer's ``error(existence_error(procedure, PI), PI)``
    and carries no prose; the diagnostic travels on the exception."""
    with pytest.raises(LogicException) as info:
        list(call(goal, module=module))
    return info.value.message


def _answers(goal, module, n=1):
    vs = [Var() for _ in range(n)]
    return [tuple(walk(v) for v in vs) for _ in call(goal, *vs, module=module)]


_OWNER = """
    -module(udc_owner_ERA, [known(X)])
    known(1),
"""

_CALLER = """
    -module(udc_caller_ERA, [])
    -import_module(udc_owner_ERA)
    -private([procedure, caught, wrong, right])
    whole(E) <- catch(ghost(1), E, True)
    pi(PI) <- catch(ghost(1), error(existence_error(procedure, PI), _), True)
    in_findall(L) <- findall(PI, catch(ghost(1), error(existence_error(procedure, PI), _), True), L)
    in_once(PI) <- catch(once(ghost(1)), error(existence_error(procedure, PI), _), True)
    in_forall(PI) <- catch(forall(ghost(1), True), error(existence_error(procedure, PI), _), True)
    by_key_error(E) <- catch(ghost(1), ++KeyError, E is caught)
    not_by_exception(E) <- catch(catch(ghost(1), ++Exception, E is wrong), error(existence_error(procedure, _), _), E is right)
    qualified(PI) <- catch(udc_owner_ERA.nosuch(1), error(existence_error(procedure, PI), _), True)
    qualified_whole(E) <- catch(udc_owner_ERA.nosuch(1, 2), E, True)
    qualified_unloaded(PI) <- catch(udc_never_loaded.nosuch(1), error(existence_error(procedure, PI), _), True)
    uncaught() <- ghost(1)
    qualified_uncaught() <- udc_owner_ERA.nosuch(1)
    qualified_whole_uncaught() <- udc_owner_ERA.nosuch(1, 2)
"""


@pytest.fixture(params=["class", "handle"])
def pair(request, tmp_path, monkeypatch):
    """*era* ``class``: ``ghost`` is simply unbound.  *era* ``handle``:
    ``ghost`` is bound to ``udc_owner_handle<US>ghost``, a predicate handle
    whose owner has no ``ghost/1`` -- the binding a W4 import would leave."""
    era = request.param
    ow = _load(tmp_path, monkeypatch, f"udc_owner_{era}",
               _OWNER.replace("ERA", era))
    O = ow.__dict__["$module"]
    seen = []
    if era == "handle":
        import clausal.logic.compiler_v2 as cv
        orig = cv._process_imports

        def flipped(items, module_dict, db=None):
            orig(items, module_dict, db)
            # the owner is already loaded: the only module processed from
            # here on is the caller
            module_dict["ghost"] = mangle(O.name, "ghost")
            seen.append("ghost")

        monkeypatch.setattr(cv, "_process_imports", flipped)
    im = _load(tmp_path, monkeypatch, f"udc_caller_{era}",
               _CALLER.replace("ERA", era))
    I = im.__dict__["$module"]
    if era == "handle":
        assert seen, "the handle era must really be exercised"
        assert I.module_dict["ghost"] == mangle(O.name, "ghost")
    else:
        assert "ghost" not in I.module_dict
    return era, O, I


def test_catch_3_binds_the_exact_iso_term(pair):
    _era, _O, I = pair
    [(e,)] = _answers("whole", I)
    _assert_iso(e, "ghost", 1)


def test_an_iso_catcher_matches_it(pair):
    _era, _O, I = pair
    assert _answers("pi", I) == [(_pi("ghost", 1),)]


@pytest.mark.parametrize("goal", ["in_once", "in_forall"])
def test_inside_once_and_forall(pair, goal):
    _era, _O, I = pair
    assert _answers(goal, I) == [(_pi("ghost", 1),)]


def test_inside_findall(pair):
    _era, _O, I = pair
    [(lst,)] = _answers("in_findall", I)
    assert list(lst) == [_pi("ghost", 1)]


def test_a_plus_plus_key_error_catcher_still_catches_it(pair):
    """ADD, not replace: ``exceptions._dual_typed_match``.  Both eras: the
    dangling handle raised a plain ``LogicException`` until round 2 of
    2026-09-25 and is a ``PredicateNotFoundError`` now, the unqualified
    miss's own type."""
    _era, _O, I = pair
    assert _answers("by_key_error", I) == [(mint("caught"),)]


def test_plus_plus_exception_never_catches_a_logic_ball(pair):
    _era, _O, I = pair
    assert _answers("not_by_exception", I) == [(mint("right"),)]


def test_python_except_still_catches_it(pair):
    era, _O, I = pair
    with pytest.raises(KeyError) as info:
        list(call("uncaught", module=I))
    exc = info.value
    # one condition, one Python type, in both eras
    assert isinstance(exc, PredicateNotFoundError)
    assert isinstance(exc, LogicException)
    _assert_iso(exc.term, "ghost", 1)
    text = str(exc)
    assert "Uncaught logic exception" not in text
    assert exc.args == (text,)
    assert cell_args(exc.term)[1] == _pi("ghost", 1)
    assert _context_message(exc.term) == text
    if era == "class":
        # the diagnostic survives verbatim: as str(), and as the prose
        assert text.startswith("Predicate ghost/1 not found")
        assert "udc_caller_class defines:" in text
        assert "-> define ghost/1 in udc_caller_class" in text
    else:
        assert text == ("ghost/1 is not defined in module 'udc_owner_handle' "
                        "(reached through a module-qualified handle)")


def test_the_class_era_message_is_the_exception_message(pair):
    era, _O, I = pair
    [(e,)] = _answers("whole", I)
    assert cell_args(e)[1] == _pi("ghost", 1)
    message = _uncaught_message("uncaught", I)
    if era == "class":
        assert "-> define ghost/1 in udc_caller_class" in message
    else:
        assert "is not defined in module 'udc_owner_handle'" in message


# ── module-qualified calls ───────────────────────────────────────────────────


def test_a_qualified_unknown_call_is_the_same_iso_term(pair):
    """``m.nosuch(1)`` used to die on ``NameError: name 'm.nosuch' is not
    defined``."""
    _era, _O, I = pair
    assert _answers("qualified", I) == [(_pi("nosuch", 1),)]


def test_a_qualified_unknown_call_names_the_module_in_the_message(pair):
    era, _O, I = pair
    [(e,)] = _answers("qualified_whole", I)
    _assert_iso(e, "nosuch", 2)
    assert cell_args(e)[1] == _pi("nosuch", 2)
    assert (f"nosuch/2 is not defined in module 'udc_owner_{era}'"
            in _uncaught_message("qualified_whole_uncaught", I))


def test_a_qualified_call_into_an_unloaded_module_is_the_same_iso_term(pair):
    _era, _O, I = pair
    assert _answers("qualified_unloaded", I) == [(_pi("nosuch", 1),)]


def test_a_qualified_call_resolves_a_predicate_asserted_later(tmp_path, monkeypatch):
    """The refusal re-resolves per call through the owner's handle, so it
    cannot go stale: a clause added to the owner afterwards answers."""
    ow = _load(tmp_path, monkeypatch, "udc_late_owner", """
        -module(udc_late_owner, [known(X)])
        known(1),
    """)
    im = _load(tmp_path, monkeypatch, "udc_late_caller", """
        -module(udc_late_caller, [])
        -import_module(udc_late_owner)
        q(X) <- udc_late_owner.late(X)
    """)
    I = im.__dict__["$module"]
    with pytest.raises(PredicateNotFoundError) as info:
        _answers("q", I)
    _assert_iso(info.value.term, "late", 1)
    O = ow.__dict__["$module"]
    list(call("assertz", Compound("late", (7,)), module=O))
    assert _answers("q", I) == [(7,)]


def test_the_refusal_for_a_base_that_resolves_to_nothing(tmp_path, monkeypatch):
    """The dispatch itself, for a dotted base that names nothing at all: the
    same ISO term, the base named in the message."""
    from clausal.logic.compiler.globals_env import _unresolved_qualified_dispatch
    fn = _unresolved_qualified_dispatch("udc_nomod.p", 1, {}, None)
    with pytest.raises(PredicateNotFoundError) as info:
        fn(None, None, None, None, 1)
    _assert_iso(info.value.term, "p", 1)
    assert "udc_nomod" in info.value.message


def test_a_qualified_unknown_call_raises_the_same_python_type(pair):
    """Round 2 (2026-09-25): the qualified miss is a
    ``PredicateNotFoundError`` too, whichever route raises it."""
    _era, _O, I = pair
    with pytest.raises(PredicateNotFoundError) as info:
        list(call("qualified_uncaught", module=I))
    _assert_iso(info.value.term, "nosuch", 1)
    assert "udc_owner_" in str(info.value)


def test_a_base_module_loaded_after_the_caller_compiled_answers(tmp_path, monkeypatch):
    """roborev round 2: the base is resolved per call, not once at compile
    time -- a module that is not loaded when the caller compiles (a lazy or
    circular import) answers once it has loaded."""
    im = _load(tmp_path, monkeypatch, "udc_lazy_caller", """
        -module(udc_lazy_caller, [])
        q(X) <- udc_lazy_owner.p(X)
    """)
    I = im.__dict__["$module"]
    assert "udc_lazy_owner" not in sys.modules
    with pytest.raises(PredicateNotFoundError) as info:
        _answers("q", I)
    _assert_iso(info.value.term, "p", 1)
    assert "is not loaded" in str(info.value)
    _load(tmp_path, monkeypatch, "udc_lazy_owner", """
        -module(udc_lazy_owner, [p(X)])
        p(5),
    """)
    assert _answers("q", I) == [(5,)]


def test_a_base_that_is_a_python_module_is_the_same_iso_term(tmp_path, monkeypatch):
    """A base that resolves to a loaded NON-Clausal object (the ``math``
    module): same term, the message says it is not a predicate of it."""
    import math  # noqa: F401 -- the base must be loaded
    im = _load(tmp_path, monkeypatch, "udc_pybase", """
        -module(udc_pybase, [])
        q(E) <- catch(math.nosuch(1), E, True)
        q_uncaught() <- math.nosuch(1)
    """)
    I = im.__dict__["$module"]
    [(e,)] = _answers("q", I)
    _assert_iso(e, "nosuch", 1)
    assert cell_args(e)[1] == _pi("nosuch", 1)
    assert _uncaught_message("q_uncaught", I) == ("nosuch/1 is not a predicate of 'math' "
                         "(a module-qualified call math.nosuch/1)")


# ── the Python API ───────────────────────────────────────────────────────────


def test_solve_call_raises_the_dual_typed_error(tmp_path, monkeypatch):
    """``solve.call`` on an unknown name: still a ``KeyError`` with the same
    message, now also the ISO ``LogicException``."""
    im = _load(tmp_path, monkeypatch, "udc_api", """
        -module(udc_api, [known(X)])
        known(1),
    """)
    I = im.__dict__["$module"]
    with pytest.raises(KeyError) as info:
        list(call("nosuch3", 1, module=I))
    exc = info.value
    assert isinstance(exc, PredicateNotFoundError)
    assert isinstance(exc, LogicException)
    _assert_iso(exc.term, "nosuch3", 1)
    assert str(exc) == "Predicate 'nosuch3'/1 is not defined in module 'udc_api'"


def test_a_message_only_construction_keeps_the_old_ball():
    """Out-of-tree code that builds the error from a message alone gets the
    ball ``catch/3`` bound before 2026-09-25, not a malformed ISO term."""
    exc = PredicateNotFoundError("Predicate p/1 not found")
    assert isinstance(exc, KeyError) and isinstance(exc, LogicException)
    assert exc.term == ("PredicateNotFoundError", "Predicate p/1 not found")
    assert str(exc) == "Predicate p/1 not found"


# ── C drive core vs the pure-Python twin ─────────────────────────────────────


_PARITY_SCRIPT = r"""
import json, os, sys, textwrap
sys.path.insert(0, REPO)
if BLOCK_C:
    sys.modules["clausal.logic.runtime._trampoline"] = None
import clausal
assert clausal.__file__.startswith(REPO), clausal.__file__
import clausal.logic.trampoline as t
from clausal.import_hook import _load_module
from clausal import cell_args
from clausal.logic.solve import call
from clausal.logic.variables import Var, walk
sys.path.insert(1, TMP)
_load_module("udcp_owner", os.path.join(TMP, "udcp_owner.clausal"))
m = _load_module("udcp_caller", os.path.join(TMP, "udcp_caller.clausal"))
M = m.__dict__["$module"]
out = {"drive": t._drive_until_yield.__module__}
for g in ["pi", "in_findall", "in_once", "in_forall", "by_key_error",
          "not_by_exception", "qualified"]:
    v = Var()
    out[g] = [repr(walk(v)) for _ in call(g, v, module=M)]
try:
    list(call("uncaught", module=M))
    out["uncaught"] = "no error"
except KeyError as e:
    out["uncaught"] = [type(e).__name__, repr(cell_args(e.term)[0])]
print("RESULT" + json.dumps(out))
"""


def _run_parity(tmp_path, block_c):
    (tmp_path / "udcp_owner.clausal").write_text(
        textwrap.dedent(_OWNER.replace("udc_owner_ERA", "udcp_owner")).lstrip())
    (tmp_path / "udcp_caller.clausal").write_text(textwrap.dedent(
        _CALLER.replace("udc_caller_ERA", "udcp_caller")
        .replace("udc_owner_ERA", "udcp_owner")).lstrip())
    repo = os.path.dirname(os.path.dirname(os.path.abspath(clausal.__file__)))
    code = (f"REPO = {repo!r}\nTMP = {str(tmp_path)!r}\nBLOCK_C = {block_c!r}\n"
            + _PARITY_SCRIPT)
    proc = subprocess.run([sys.executable, "-c", code], cwd=str(tmp_path),
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr[-3000:]
    [line] = [ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT")]
    return json.loads(line[len("RESULT"):])


def test_the_c_core_and_the_python_twin_agree(tmp_path):
    c_side = _run_parity(tmp_path, block_c=False)
    py_side = _run_parity(tmp_path, block_c=True)
    # positive control: the two runs really used different drive loops
    assert c_side.pop("drive") == "clausal.logic.runtime._trampoline"
    assert py_side.pop("drive") == "clausal.logic._trampoline_py"
    assert c_side == py_side
    assert c_side["pi"] == [repr(_pi("ghost", 1))]
    assert c_side["qualified"] == [repr(_pi("nosuch", 1))]
    assert c_side["by_key_error"] == [repr(mint("caught"))]
    assert c_side["not_by_exception"] == [repr(mint("right"))]
    assert c_side["uncaught"][0] == "PredicateNotFoundError"
