"""A qualified predicate-ADAPTER goal built as a term and run by a meta-call.

``call(torch.tensor([1], X))`` raised ``existence_error(procedure,
'torch.tensor'/2)`` although the clause body ``torch.tensor([1], X)`` runs.
The compiler names the goal cell after the source spelling
(``("torch.tensor", [1], X)``) and the meta-call resolver looked a functor up
only as a plain key -- the namespace, the db's row, the builtins -- none of
which carries a dotted name.  A qualified Clausal PREDICATE was unaffected:
its cell carries the predicate's module-qualified handle.

Fixed in ``higher_order._resolve_named_goal`` (every meta-call: ``call/N``,
``findall``, ``maplist``, a goal variable) and in ``solve.call``'s dotted
walk (Python entry), by walking the dotted name as the compiled call does.

The dialect gate still bites: a Clausal Prolog (``.clausal``) frame reaches
Python only through a ``.seam`` module, so the same term run by
``call/1`` THERE raises ``permission_error(access, python_module, M)``.
"""
from __future__ import annotations

import importlib
import shutil
import sys

import pytest

from clausal import import_hook as ih  # noqa: F401 -- installs the finders
from clausal._suffixes import SEAM_SUFFIX
from clausal.import_hook import _load_module
from clausal.logic.cells import chars
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call, _deref_walk
from clausal.logic.variables import Var


SRC = """\
-import_module(py.re)
-import_module(py.os)
-import_module(adapter_goal_lib)

direct(X) <- py.os.platform(X)
via_call(X) <- call(py.os.platform(X))
via_call_extra(X) <- call(py.os.platform(), X)
via_findall(L) <- findall(X, call(py.os.platform(X)), L)
run_goal(G) <- call(G)
via_goal_var(X) <- run_goal(py.os.platform(X))
via_once() <- once(call(py.re.match("a", "abc")))
fails() <- call(py.re.match("z", "abc"))
via_maplist() <- maplist(py.re.match("a"), ["abc", "abd"])
caught(E) <- catch(call(py.re.match("a", "abc", 0, 1, 2)), error(E, _), True)
body_caught(E) <- catch(py.re.match("a", "abc", 0, 1, 2), error(E, _), True)
seam_pred(X) <- call(adapter_goal_lib.p(X))
"""

LIB = "p(1),\np(2)\n"


@pytest.fixture(scope="module")
def module(tmp_path_factory):
    root = tmp_path_factory.mktemp("adapter_goal")
    (root / f"adapter_goal_lib{SEAM_SUFFIX}").write_text(LIB, encoding="utf-8")
    sys.path.insert(0, str(root))
    try:
        src = root / f"adapter_goal_probe{SEAM_SUFFIX}"
        src.write_text(SRC, encoding="utf-8")
        yield _load_module("adapter_goal_probe", str(src)).__dict__["$module"]
    finally:
        sys.path.remove(str(root))
        sys.modules.pop("adapter_goal_lib", None)


def _answers(module, name, arity=1):
    args = [Var() for _ in range(arity)]
    return [[_deref_walk(a) for a in args]
            for _ in call(name, *args, module=module)]


def _platform():
    import sys as _s
    return _s.platform


@pytest.mark.parametrize("name", ["direct", "via_call", "via_call_extra",
                                  "via_goal_var"])
def test_a_dotted_adapter_goal_term_runs_like_the_body_call(module, name):
    assert _answers(module, name) == [[_platform()]]


def test_findall_over_it(module):
    assert _answers(module, "via_findall") == [[[_platform()]]]


def test_once_and_maplist(module):
    assert _answers(module, "via_once", 0) == [[]]
    assert _answers(module, "via_maplist", 0) == [[]]


def test_a_failing_adapter_goal_fails(module):
    assert _answers(module, "fails", 0) == []


def test_the_adapter_still_answers_for_an_arity_it_lacks(module):
    # The adapter's own arity check, as the body call gets it -- not a
    # silent failure and not the dotted name's existence_error.
    [[err]] = _answers(module, "caught")
    assert err == ("existence_error", "procedure", ("/", "match", 5))
    assert _answers(module, "body_caught") == [[err]]


def test_a_qualified_clausal_predicate_is_unchanged(module):
    assert _answers(module, "seam_pred") == [[1], [2]]


def test_python_entry_resolves_a_dotted_adapter_name(module):
    x = Var()
    got = [_deref_walk(x) for _ in call("py.os.platform", x, module=module)]
    assert got == [_platform()]


def test_a_dotted_name_that_is_no_adapter_is_still_unknown(module):
    with pytest.raises(LogicException) as info:
        list(call("call", ("py.os.nosuch", Var()), module=module))
    assert info.value.term[1] == (
        "existence_error", "procedure", ("/", "py.os.nosuch", 1))


# ── the dialect gate: a Clausal Prolog frame ──

_CP_RUNNER = """:- module({m}, [rc/1]).
rc(G) :- call(G).
:- end_module({m}).
"""
_SEAM_RUNNER = "rc(G) <- call(G)\n"


@pytest.fixture
def runners(tmp_path, monkeypatch):
    from clausal._suffixes import CLAUSAL_PROLOG_SUFFIXES
    monkeypatch.syspath_prepend(str(tmp_path))
    cp_suffix = CLAUSAL_PROLOG_SUFFIXES[0]
    (tmp_path / f"u4_cp_runner{cp_suffix}").write_text(
        _CP_RUNNER.format(m="u4_cp_runner"))
    (tmp_path / f"u4_seam_runner{SEAM_SUFFIX}").write_text(_SEAM_RUNNER)
    importlib.invalidate_caches()
    for p in tmp_path.rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)
    importlib.import_module("py.re")   # the adapter is loaded, as py.re
    mods = {k: importlib.import_module(k)
            for k in ("u4_cp_runner", "u4_seam_runner")}
    yield mods
    for k in mods:
        sys.modules.pop(k, None)


GOAL = ("py.re.match", chars("a"), chars("abc"))


def test_a_clausal_prolog_frame_refuses_the_python_adapter(runners):
    with pytest.raises(LogicException) as info:
        list(call("rc", GOAL, module=runners["u4_cp_runner"]))
    term = info.value.term
    assert term[0] == "error"
    assert term[1][:3] == ("permission_error", "access", "python_module")


def test_a_seam_frame_runs_it(runners):
    assert len(list(call("rc", GOAL, module=runners["u4_seam_runner"]))) == 1
