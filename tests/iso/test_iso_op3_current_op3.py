"""``op/3`` and ``current_op/3`` as goals, and op/3's permission checks
(ISO 8.14.3, 8.14.4), pinned against Scryer.

Rows from Ulrich Neumerkel's ISO conformity table
(complang.tuwien.ac.at/ulrich/iso-prolog/conformity_testing):

* ``op(100,yfy,op)``          -> ``domain_error(operator_specifier,yfy)``
* ``op(0,xfy,',')``           -> ``permission_error(modify,operator,',')``
* ``op(699,xf,>)``            -> ``permission_error(create,operator,>)``
* ``current_op(200,fy,+)``    -> succeeds
* ``current_op(P,xfy,.)``     -> fails
* ``op(0,xfy,:-)``, then ``current_op(P,xfx,:-)`` -> fails

Both predicates used to exist only as the load-time directive, so each of
these goals raised ``existence_error(procedure, op/3)``; and the directive
made none of 8.14.3.3's permission checks (``op(0,xfy,',')`` removed the
comma, ``op(699,xf,>)`` gave ``>`` a postfix class beside its infix one).

ISO 8.14.3.3 (with Cor.2): ``,`` can never be modified
(``permission_error(modify, operator, ',')``); a name cannot be both infix
and postfix (6.3.4.3), ``|`` can only be an infix operator of priority 1001
or more (or 0), and ``[]`` and ``{}`` cannot be operators -- each of these is
``permission_error(create, operator, Name)``.

The same program runs in the engine (the native ``.pl`` front end) and in
Scryer.  Every row uses its own operator names, so the rows are independent
of one another (Scryer runs them in ONE process; the engine resets its
runtime operator table around each test).  The row that removes ``:-`` is
last for that reason.
"""

from __future__ import annotations

import importlib
import sys

import pytest

from .test_iso_answers_scryer import _engine_answers, _scryer_answers


def _err(goal: str) -> str:
    return f"catch(({goal}), error(F, _), R = F)"


def _yes(goal: str) -> str:
    return f"catch(({goal}, R = yes), error(F, _), R = F)"


#: (row name, body binding R, what both print)
ROWS = [
    # Ulrich's rows
    ("u op yfy", _err("op(100, yfy, op)"),
     ["domain_error(operator_specifier,yfy)"]),
    ("u op 0 comma", _err("op(0, xfy, ',')"),
     ["permission_error(modify,operator,',')"]),
    ("u op xf >", _err("op(699, xf, >)"),
     ["permission_error(create,operator,>)"]),
    ("u current_op fy +", _yes("current_op(200, fy, +)"), ["yes"]),
    ("u current_op xfy dot", "findall(P, current_op(P, xfy, '.'), R)",
     ["[]"]),
    # op/3: the comma
    ("comma at its own priority", _err("op(1000, xfy, ',')"),
     ["permission_error(modify,operator,',')"]),
    ("comma in a list", _err("op(1, xfx, [c_a, ','])"),
     ["permission_error(modify,operator,',')"]),
    ("comma before a bad specifier", _err("op(1000, yfy, ',')"),
     ["permission_error(modify,operator,',')"]),
    # op/3: infix and postfix exclude each other
    ("postfix over infix", _err("op(200, xfx, o_a), op(200, xf, o_a)"),
     ["permission_error(create,operator,o_a)"]),
    ("infix over postfix", _err("op(200, xf, o_b), op(200, xfx, o_b)"),
     ["permission_error(create,operator,o_b)"]),
    ("removed infix frees postfix",
     _yes("op(200, xfx, o_c), op(0, xfx, o_c), op(200, xf, o_c)"), ["yes"]),
    ("removing postfix of an infix", _yes("op(0, xf, >)"), ["yes"]),
    ("prefix beside infix",
     "op(200, xfx, o_d), op(300, fy, o_d), "
     "findall(P-T, current_op(P, T, o_d), L), sort(L, R)",
     ["[200-xfx,300-fy]"]),
    ("same class replaces",
     "op(200, xf, o_e), op(300, yf, o_e), findall(P-T, current_op(P, T, o_e), R)",
     ["[300-yf]"]),
    ("a list declares each",
     "op(200, xf, [o_f, o_g]), findall(P-T, current_op(P, T, o_g), R)",
     ["[200-xf]"]),
    ("a refused list declares none",
     "catch(op(200, xfx, [o_h, ',']), _, true), "
     "findall(P-T, current_op(P, T, o_h), R)", ["[]"]),
    # op/3: | [] {}
    ("bar below 1001", _err("op(1000, xfy, '|')"),
     ["permission_error(create,operator,'|')"]),
    ("bar prefix", _err("op(1100, fy, '|')"),
     ["permission_error(create,operator,'|')"]),
    ("bar removal", _yes("op(0, xfy, '|')"), ["yes"]),
    ("empty list", _err("op(700, xfx, [])"),
     ["permission_error(create,operator,[])"]),
    ("curly", _err("op(700, xfx, {})"),
     ["permission_error(create,operator,{})"]),
    ("curly removal", _err("op(0, xfx, {})"),
     ["permission_error(create,operator,{})"]),
    # op/3: instantiation, type and domain errors
    ("unbound priority", _err("op(_, xfx, o_i)"), ["instantiation_error"]),
    ("unbound specifier", _err("op(1, _, o_i)"), ["instantiation_error"]),
    ("unbound operator", _err("op(1, xfx, _)"), ["instantiation_error"]),
    ("partial list", _err("op(1, xfx, [o_i|_])"), ["instantiation_error"]),
    ("unbound element", _err("op(1, xfx, [o_i, _])"), ["instantiation_error"]),
    ("atom priority", _err("op(a, xfx, o_i)"), ["type_error(integer,a)"]),
    ("integer specifier", _err("op(1, 1, o_i)"), ["type_error(atom,1)"]),
    ("integer operator", _err("op(1, xfx, 1)"), ["type_error(list,1)"]),
    ("improper list", _err("op(1, xfx, [o_i|b])"),
     ["type_error(list,[o_i|b])"]),
    ("integer element", _err("op(1, xfx, [o_i, 1])"), ["type_error(atom,1)"]),
    ("priority 1201", _err("op(1201, xfx, o_i)"),
     ["domain_error(operator_priority,1201)"]),
    ("priority -1", _err("op(-1, xfx, o_i)"),
     ["domain_error(operator_priority,-1)"]),
    # current_op/3
    ("current_op both minus",
     "findall(P-T, current_op(P, T, -), L), sort(L, R)",
     ["[200-fy,500-yfx]"]),
    ("current_op comma", "findall(P-T, current_op(P, T, ','), R)",
     ["[1000-xfy]"]),
    ("current_op priority 0", "findall(T-O, current_op(0, T, O), R)", ["[]"]),
    ("current_op sees op/3",
     "op(700, xfx, o_j), findall(P-T, current_op(P, T, o_j), R)",
     ["[700-xfx]"]),
    ("current_op 1201", _err("current_op(1201, _, _)"),
     ["domain_error(operator_priority,1201)"]),
    ("current_op bad specifier", _err("current_op(_, yfy, _)"),
     ["domain_error(operator_specifier,yfy)"]),
    ("current_op integer operator", _err("current_op(_, _, 1)"),
     ["type_error(atom,1)"]),
    # LAST: removes infix :- for the rest of a Scryer session
    ("u op 0 :- then current_op",
     "op(0, xfy, :-), findall(P, current_op(P, xfx, :-), R)", ["[]"]),
]

#: ISO 8.14.4.3 a/b, where Scryer answers type_error instead
#: (``type_error(integer, a)``, ``type_error(atom, 1)``): engine only.
ISO_ONLY_ROWS = [
    ("current_op atom priority", _err("current_op(a, _, _)"),
     ["domain_error(operator_priority,a)"]),
    ("current_op integer specifier", _err("current_op(_, 1, _)"),
     ["domain_error(operator_specifier,1)"]),
]

#: Engine-only judgment calls.  A refused list is atomic here (Scryer applies
#: it element by element and leaves ``z_4``); and the table current_op/3
#: walks is a snapshot, so an op/3 run between two answers is not seen by the
#: enumeration in progress.
ISO_ONLY_ROWS += [
    ("a refused list is atomic",
     "op(200, xf, z_3a), op(200, xfx, z_3), "
     "catch(op(200, xf, [z_4, z_3]), _, true), "
     "findall(P-T, current_op(P, T, z_4), R)", ["[]"]),
    ("op between current_op answers is not seen",
     "findall(O, (current_op(_, _, O), op(700, xfx, mid_x)), L), "
     "findall(x, memberchk(mid_x, L), M), "
     "length(M, N), R = N",
     ["0"]),
]

_ALL = ROWS + ISO_ONLY_ROWS

PROGRAM = "".join(f"r{i}(R) :- {body}.\n" for i, (_, body, _) in enumerate(_ALL))


def _reset():
    from clausal.tools import prolog_operators  # noqa: PLC0415
    reset = getattr(prolog_operators, "reset_runtime_op_table", None)
    if reset is not None:
        reset()


@pytest.fixture(autouse=True)
def _fresh_runtime_ops():
    _reset()
    yield
    _reset()


def _import_pl(d, name: str, text: str, mp):
    mp.setenv("CLAUSAL_PL_FRONTEND", "native")
    mp.syspath_prepend(str(d))
    (d / f"{name}.pl").write_text(text)
    sys.modules.pop(name, None)
    importlib.invalidate_caches()
    return importlib.import_module(name)


@pytest.fixture(scope="module")
def pl_mod(tmp_path_factory):
    d = tmp_path_factory.mktemp("iso_op3")
    mp = pytest.MonkeyPatch()
    name = "_iso_op3_1014"
    try:
        yield _import_pl(d, name, PROGRAM, mp)
    finally:
        sys.modules.pop(name, None)
        mp.undo()


@pytest.mark.parametrize("i", range(len(_ALL)), ids=[r[0] for r in _ALL])
def test_engine(pl_mod, i):
    assert _engine_answers(pl_mod, f"r{i}", 5) == _ALL[i][2]


def test_oracle(scryer):
    del scryer   # the fixture only asserts the binary is there
    got = _scryer_answers(PROGRAM, [(f"r{i}(R)", 5) for i in range(len(ROWS))])
    assert got == [r[2] for r in ROWS]


# ── the directive form ───────────────────────────────────────────────────────

#: (row name, directive, what the refusal names)
DIRECTIVE_REFUSALS = [
    ("u op yfy", ["op(100, yfy, op)"], "domain_error(operator_specifier"),
    ("u op 0 comma", ["op(0, xfy, ',')"], "permission_error(modify, operator"),
    ("u op xf >", ["op(699, xf, >)"], "permission_error(create, operator, >)"),
    ("infix over postfix", ["op(200, xf, d_a)", "op(200, xfx, d_a)"],
     "permission_error(create, operator, d_a)"),
    ("bar below 1001", ["op(1000, xfy, '|')"],
     "permission_error(create, operator"),
    ("curly", ["op(700, xfx, {})"], "permission_error(create, operator"),
    ("empty list", ["op(700, xfx, [])"], "permission_error(create, operator"),
]


@pytest.mark.parametrize("i", range(len(DIRECTIVE_REFUSALS)),
                         ids=[r[0] for r in DIRECTIVE_REFUSALS])
def test_directive_refused(tmp_path, monkeypatch, i):
    _, directives, names = DIRECTIVE_REFUSALS[i]
    text = "".join(f":- {d}.\n" for d in directives) + "p(1).\n"
    name = f"_iso_op3_dir_{i}"
    try:
        with pytest.raises(SyntaxError) as exc:
            _import_pl(tmp_path, name, text, monkeypatch)
        assert names in str(exc.value), str(exc.value)
    finally:
        sys.modules.pop(name, None)


def test_directive_declares_for_current_op(tmp_path, monkeypatch):
    """A file's ``:- op`` directive governs the file's own reading AND is in
    the table ``current_op/3`` reads once the file is loaded."""
    name = "_iso_op3_dir_ok"
    text = (":- op(700, xfx, ===).\n"
            "t(R) :- X = (a === b), X =.. R.\n"
            "c(R) :- findall(P-T, current_op(P, T, ===), R).\n")
    try:
        mod = _import_pl(tmp_path, name, text, monkeypatch)
        assert _engine_answers(mod, "t", 5) == ["[===,a,b]"]
        assert _engine_answers(mod, "c", 5) == ["[700-xfx]"]
    finally:
        sys.modules.pop(name, None)


# ── which load-time op/3 reaches the run-time table (Scryer's rule) ─────────

def _runtime_ops(name: str) -> list:
    from clausal.tools.prolog_operators import runtime_op_table  # noqa: PLC0415
    return sorted((e.precedence, e.specifier)
                  for e in runtime_op_table().entries() if e.name == name)


def test_plain_file_op_is_global(tmp_path, monkeypatch):
    name = "_iso_op3_plain"
    try:
        _import_pl(tmp_path, name, ":- op(700, xfx, g_plain).\np(1).\n",
                   monkeypatch)
        assert _runtime_ops("g_plain") == [(700, "xfx")]
    finally:
        sys.modules.pop(name, None)


def test_module_own_op_stays_local(tmp_path, monkeypatch):
    """A module's unexported op/3 governs its own reading only: not even its
    own code sees it in current_op/3."""
    name = "iso_op3_local_1014"
    text = (f":- module({name}, [t/1, c/1]).\n"
            ":- op(700, xfx, g_local).\n"
            "t(R) :- X = (a g_local b), X =.. R.\n"
            "c(R) :- findall(P-T, current_op(P, T, g_local), R).\n"
            f":- end_module({name}).\n")
    try:
        mod = _import_pl(tmp_path, name, text, monkeypatch)
        assert _engine_answers(mod, "t", 5) == ["[g_local,a,b]"]
        assert _runtime_ops("g_local") == []
        assert _engine_answers(mod, "c", 5) == ["[]"]
    finally:
        sys.modules.pop(name, None)


def test_module_exported_op_is_global(tmp_path, monkeypatch):
    name = "iso_op3_exported_1014"
    text = (f":- module({name}, [t/1, op(700, xfx, g_exported)]).\n"
            "t(R) :- X = (a g_exported b), X =.. R.\n"
            f":- end_module({name}).\n")
    try:
        mod = _import_pl(tmp_path, name, text, monkeypatch)
        assert _engine_answers(mod, "t", 5) == ["[g_exported,a,b]"]
        assert _runtime_ops("g_exported") == [(700, "xfx")]
    finally:
        sys.modules.pop(name, None)


# ── the table API, on a table of its own ────────────────────────────────────

def test_op_error_on_a_local_table():
    from clausal.tools.prolog_operators import OperatorTable, op_error  # noqa: PLC0415
    t = OperatorTable.scryer_builtin_default()
    assert op_error(t, 0, "xfy", [","]) == (
        "permission_error", "modify", "operator", ",")
    assert op_error(t, 100, "yfy", ["op"]) == (
        "domain_error", "operator_specifier", "yfy")
    assert op_error(t, 699, "xf", [">"]) == (
        "permission_error", "create", "operator", ">")
    assert op_error(None, 699, "xf", [">"]) is None   # no table: no conflict
    assert op_error(t, 0, "xf", [">"]) is None
    assert op_error(t, 699, "fy", [">"]) is None
    assert op_error(t, 1100, "xfy", ["|"]) is None
    assert op_error(t, 1201, "xfx", ["a"]) == (
        "domain_error", "operator_priority", 1201)


def test_entries_and_version():
    from clausal.tools.prolog_operators import OperatorTable  # noqa: PLC0415
    t = OperatorTable()
    assert list(t.entries()) == [] and t.version == 0
    t.define(700, "xfx", "a")
    t.define(200, "fy", "a")
    assert t.version == 2
    assert sorted((e.precedence, e.specifier) for e in t.entries()) == [
        (200, "fy"), (700, "xfx")]


def test_runtime_table_reset_and_default():
    from clausal.tools.prolog_operators import (  # noqa: PLC0415
        reset_runtime_op_table, runtime_op_table, runtime_op_table_is_default)
    t = runtime_op_table()
    assert runtime_op_table_is_default()
    v = t.version
    t.define(700, "xfx", "g_reset")
    assert not runtime_op_table_is_default()
    reset_runtime_op_table()
    assert runtime_op_table() is t                  # reset in place
    assert t.version > v + 1                        # a cache keyed on it moves
    assert runtime_op_table_is_default()
    assert t.lookup_infix("g_reset") is None
    assert t.lookup_prefix("+") is not None         # the defaults are back


def test_clausal_prolog_surface_follows_the_same_rule(tmp_path, monkeypatch):
    """A ``.clausal`` file goes through the same directive lowering, so the
    same rule holds: a non-module file's op/3 and a module's exported op
    are global, a module's own op/3 is not.  (A ``.seam`` file has no op/3
    directive at all.)"""
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / "iso_op3_cl_plain.clausal").write_text(
        ":- op(700, xfx, g_cl_plain).\np(1).\n")
    (tmp_path / "iso_op3_cl_mod.clausal").write_text(
        ":- module(iso_op3_cl_mod, [p/1, op(700, xfx, g_cl_exported)]).\n"
        ":- op(700, xfx, g_cl_local).\n"
        "p(R) :- X = (a g_cl_local b), X =.. R.\n"
        ":- end_module(iso_op3_cl_mod).\n")
    names = ("iso_op3_cl_plain", "iso_op3_cl_mod")
    try:
        importlib.invalidate_caches()
        for n in names:
            sys.modules.pop(n, None)
            importlib.import_module(n)
        assert _runtime_ops("g_cl_plain") == [(700, "xfx")]
        assert _runtime_ops("g_cl_exported") == [(700, "xfx")]
        assert _runtime_ops("g_cl_local") == []
    finally:
        for n in names:
            sys.modules.pop(n, None)


# ── the translator's reader leaves a refused op directive unapplied ─────────

def test_translator_reader_leaves_a_refused_op_unapplied():
    from clausal.tools.prolog_operators import OperatorTable  # noqa: PLC0415
    from clausal.tools.prolog_parser import parse  # noqa: PLC0415
    t = OperatorTable.scryer_builtin_default()
    parse(":- op(0, xfy, ',').\n:- op(699, xf, >).\n:- op(700, xfx, tr_ok).\n",
          op_table=t)
    assert t.lookup_infix(",") is not None          # not removed
    assert t.lookup_postfix(">") is None            # not given a postfix class
    assert t.lookup_infix("tr_ok") is not None      # a legal one still applies


def test_op3_names_a_seglist_with_a_non_list_tail_is_a_type_error():
    """``[o_i|T]`` with T bound to ``b`` is a SegList whose last hole holds a
    non-list: the improper list ``[o_i|b]``, ``type_error(list, ...)``."""
    from clausal.logic.builtins.operators import _op__3  # noqa: PLC0415
    from clausal.logic.exceptions import LogicException  # noqa: PLC0415
    from clausal.logic.variables import Trail, Var, unify  # noqa: PLC0415
    from clausal.terms import ConcreteSeg, SegList, VarSeg  # noqa: PLC0415
    trail, tail = Trail(), Var()
    assert unify(tail, "b", trail)
    names = SegList([ConcreteSeg(["o_i"]), VarSeg(tail)])
    with pytest.raises(LogicException) as exc:
        list(_op__3(1, "xfx", names, trail, None))
    assert "type_error(list,[o_i|b])" in str(exc.value)


# ── thread safety of the run-time table ─────────────────────────────────────

def test_op3_against_current_op3_in_two_threads():
    """op/3 in one thread while another walks the table with current_op/3:
    neither may raise (``dictionary changed size during iteration``), and
    every op/3 must land."""
    import threading  # noqa: PLC0415
    from clausal.logic.builtins.operators import _current_op__3, _op__3  # noqa: PLC0415
    from clausal.terms import Var  # noqa: PLC0415
    from clausal.tools.prolog_operators import runtime_op_table  # noqa: PLC0415

    from clausal.logic.variables import Trail  # noqa: PLC0415

    n = 3000
    errors: list = []
    old_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)          # switch threads as often as possible
    go = threading.Barrier(2)

    def writer():
        try:
            go.wait()
            for i in range(n):
                list(_op__3(700, "xfx", f"thr_{i}", Trail(), None))
        except BaseException as e:      # noqa: BLE001
            errors.append(e)

    def reader():
        try:
            go.wait()
            for _ in range(n):
                # drive the enumeration the way the engine does
                for _ans in _current_op__3(Var(), Var(), Var(), Trail(), None):
                    break
        except BaseException as e:      # noqa: BLE001
            errors.append(e)

    ts = [threading.Thread(target=writer), threading.Thread(target=reader)]
    for t in ts:
        t.start()
    try:
        for t in ts:
            t.join(120)
    finally:
        sys.setswitchinterval(old_interval)
    assert errors == [], errors
    assert runtime_op_table().lookup_infix(f"thr_{n - 1}") is not None
