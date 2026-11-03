"""A long ``.pl`` clause body is read and lowered without Python recursion.

todo/done/pl-readers-recursion-limit-on-long-clause-bodies-2026-10-02.md: a
clause body of ~500 goals failed in the native reader (RecursionError in
``prolog_reader``'s term transform) and of ~1000 in the parser
(``prolog_parser._parse_term``) -- a right-nested ``','/2`` chain is as deep
as the body is long, and every walk over it recursed once per goal.

The walks on the way from text to compiled code are now iterative where
they are plain tree walks, and each such walk is held here to the recursive
one it replaced (same terms, spans, variable numbering, messages):

- the parser's operator loop (infix right operands, prefix operands);
- the reader's ``transform_term`` (cells and span trees);
- the lowering: ``Uses``, ``_show``, clause/2's source body, a long ``;``
  chain (a BALANCED ``Or`` tree: disjunction is associative), long data
  chains (``$right_nested`` / ``$left_nested`` over a flat list, so the
  generated AST stays shallow), the DCG body translation;
- the compiler's ``final_yields`` pass;
- the translator's goal collectors and conjunction flattening, and its
  long ``;`` chains (a balanced ``or`` tree).

What still recurses is nesting the TEXT brackets (``f(f(...))``) and an
if-then-else chain; each now fails with a load error that names the clause
and ISO's ``resource_error(stack)``, not a bare RecursionError.

The real limit for a long conjunction is now the engine's code generation:
each goal's continuation runs inside the loop over the previous goal's
answers, so the generated function nests as deep as the body is long, and
``codegen.split_deep_nesting`` outlines it into helpers nested inside each
other.  A 5000-goal body loads (slowly); 10000 goals exceed CPython's own
compiler limit for nested functions (a ``GeneratedCodeError`` naming the
clause).  The tests below stay well under that.

Every expectation marked "Scryer" is the answer of Scryer (the clpq build
in tests/_oracles.py), 2026-11-03.
"""
from __future__ import annotations

import ast
import copy
import itertools
import random
import sys
import textwrap
import warnings

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.codegen import copy_ast, drive, fix_missing_locations
from clausal.import_hook import _load_module
from clausal.logic.cells import left_nested, right_nested
from clausal.logic.solve import call as pcall
from clausal.logic.variables import Var, deref, walk
from clausal.tools import iso_l3
from clausal.tools.iso_l3_directives import Uses, _show
from clausal.tools.prolog_ast import (
    PAtom, PCompound, PCurly, PList, PNumber, PString, PVar)
from clausal.tools.prolog_parser import parse_term
from clausal.tools.prolog_reader import VarRef, transform_term

_names = itertools.count()


def _load(tmp_path, monkeypatch, front_end, src):
    name = f"longpl{next(_names)}"
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", front_end)
    path = tmp_path / f"{name}.pl"
    path.write_text(textwrap.dedent(src).lstrip())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")      # singleton-variable lint
        return _load_module(name, str(path)).__dict__["$module"]


def _answers(m, name, *args, outs):
    return [tuple(walk(deref(o)) for o in outs)
            for _ in pcall(name, *args, module=m)]


def _spine(t, functor, right=True):
    """The operands of a right- (or left-) nested *functor* chain."""
    out = []
    while isinstance(t, PCompound) and t.functor == functor and len(t.args) == 2:
        if right:
            out.append(t.args[0])
            t = t.args[1]
        else:
            out.append(t.args[1])
            t = t.args[0]
    out.append(t)
    return out if right else out[::-1]


# ── the parser ─────────────────────────────────────────────────────────────


def test_a_100k_goal_conjunction_parses_right_nested():
    n = 100_000
    t = parse_term("p :- " + ", ".join(f"q{i}" for i in range(n)))
    assert t.functor == ":-"
    goals = _spine(t.args[1], ",")
    assert [g.name for g in goals] == [f"q{i}" for i in range(n)]


def test_a_long_yfx_chain_parses_left_nested():
    n = 20_000
    t = parse_term(" + ".join(str(i) for i in range(n)))
    assert [x.value for x in _spine(t, "+", right=False)] == list(range(n))


def test_a_long_prefix_chain_parses():
    n = 20_000
    t = parse_term("\\+ " * n + "a")
    for _ in range(n):
        assert t.functor == "\\+"
        t = t.args[0]
    assert t == PAtom("a")


@pytest.mark.parametrize("src, spans", [
    # Each operator node spans its left operand's start to its right
    # operand's end, as the recursive parser built them.
    ("a , b , c", [(0, 9), (4, 9)]),
    ("a ; b ; c", [(0, 9), (4, 9)]),
    ("- - a", [(0, 5), (2, 5)]),
])
def test_operator_spans_are_the_recursive_parsers(src, spans):
    t = parse_term(src)
    got = []
    while isinstance(t, PCompound):
        got.append(t.span)
        t = t.args[-1]
    assert got == spans


def test_priority_clashes_still_raise():
    from clausal.tools.prolog_parser import ParseError
    for src in ("a = b = c", "2 ** 3 ** 2", "- - -"):
        with pytest.raises(ParseError):
            parse_term(src)


# ── the reader's transform, against the recursive one it replaced ──────────


class _RecursiveTransform:
    """``prolog_reader._Transform`` as it was (2026-11-03): the reference."""

    def __init__(self):
        self._index_by_name = {}
        self.var_names = {}

    def var_index(self, name):
        if name != "_" and name in self._index_by_name:
            return self._index_by_name[name]
        i = len(self.var_names)
        self.var_names[i] = name
        if name != "_":
            self._index_by_name[name] = i
        return i

    def cell(self, node):
        if isinstance(node, PAtom):
            return [] if node.name == "[]" else sys.intern(node.name)
        if isinstance(node, PNumber):
            return node.value
        if isinstance(node, PString):
            return ("$chars", node.value)
        if isinstance(node, PVar):
            return VarRef(self.var_index(node.name))
        if isinstance(node, PCompound):
            return (node.functor, *(self.cell(a) for a in node.args))
        if isinstance(node, PCurly):
            return ("{}", self.cell(node.body))
        if isinstance(node, PList):
            if node.tail is None:
                return [self.cell(e) for e in node.elements]
            return self._cons_cell(node.elements, node.tail)
        raise TypeError(node)

    def _cons_cell(self, elements, tail):
        if not elements:
            return self.cell(tail)
        head, *rest = elements
        return (".", self.cell(head), self._cons_cell(rest, tail))

    @staticmethod
    def _span_of(node):
        s = getattr(node, "span", None)
        return (-1, -1) if s is None else s

    def span(self, node):
        if isinstance(node, (PAtom, PNumber, PVar, PString)):
            return self._span_of(node)
        if isinstance(node, PCompound):
            return (self._span_of(node), *(self.span(a) for a in node.args))
        if isinstance(node, PCurly):
            return (self._span_of(node), self.span(node.body))
        if isinstance(node, PList):
            if node.tail is None:
                return (self._span_of(node), [self.span(e) for e in node.elements])
            return self._cons_span(node.elements, node.tail,
                                   self._span_of(node), outermost=True)
        raise TypeError(node)

    def _cons_span(self, elements, tail, remaining_span, outermost=False):
        if not elements:
            return self.span(tail)
        head, *rest = elements
        head_start, _ = self._span_of(head)
        _, remaining_end = remaining_span
        this_span = remaining_span if outermost else (head_start, remaining_end)
        return (this_span, self.span(head), self._cons_span(rest, tail, this_span))


def _random_pterm(rng, depth):
    def sp():
        if rng.random() < 0.1:
            return None
        a = rng.randrange(1000)
        return (a, a + rng.randrange(1, 50))
    if depth <= 0 or rng.random() < 0.3:
        k = rng.randrange(5)
        if k == 0:
            return PAtom(rng.choice(["a", "b", "[]", "foo"]), span=sp())
        if k == 1:
            return PNumber(rng.randrange(100), span=sp())
        if k == 2:
            return PString(rng.choice(["", "ab"]), span=sp())
        return PVar(rng.choice(["X", "Y", "_", "Z", "_"]), span=sp())
    k = rng.randrange(4)
    kids = [_random_pterm(rng, depth - 1) for _ in range(rng.randrange(0, 4))]
    if k == 0 and kids:
        return PCompound(rng.choice(["f", ",", "-"]), tuple(kids), span=sp())
    if k == 1:
        return PCurly(_random_pterm(rng, depth - 1), span=sp())
    tail = _random_pterm(rng, depth - 1) if rng.random() < 0.5 else None
    return PList(tuple(kids), tail, span=sp())


def test_transform_matches_the_recursive_transform():
    rng = random.Random(20261103)
    for _ in range(3000):
        t = _random_pterm(rng, 6)
        ref = _RecursiveTransform()
        expected = (ref.cell(t), ref.span(t), ref.var_names)
        assert transform_term(t) == expected


def test_transform_of_a_long_partial_list_and_conjunction():
    n = 50_000
    lst = parse_term("[" + ", ".join(str(i) for i in range(n)) + " | T]")
    cell, spans, names = transform_term(lst)
    assert names == {0: "T"}
    for i in range(n):
        assert cell[0] == "." and cell[1] == i
        cell = cell[2]
    assert cell == VarRef(0)
    body = parse_term(", ".join(f"q(X{i % 7})" for i in range(n)))
    cell, _, names = transform_term(body)
    assert names == {i: f"X{i}" for i in range(7)}


# ── the lowering's walks ───────────────────────────────────────────────────


def _recursive_show(t):
    """``iso_l3_directives._show`` as it was (2026-11-03): the reference."""
    if type(t) is VarRef:
        return "_"
    if type(t) is str:
        return t
    if type(t) is list:
        return "[" + ", ".join(_recursive_show(x) for x in t) + "]"
    if type(t) is tuple and t and type(t[0]) is str:
        if t[0] == "$chars" and len(t) == 2:
            return '"' + str(t[1]) + '"'
        if len(t) == 3 and t[0] in ("/", "//", ":"):
            return f"{_recursive_show(t[1])}{t[0]}{_recursive_show(t[2])}"
        return f"{t[0]}(" + ", ".join(_recursive_show(a) for a in t[1:]) + ")"
    return repr(t)


def test_show_matches_the_recursive_show():
    rng = random.Random(7)
    for _ in range(3000):
        cell, _, _ = transform_term(_random_pterm(rng, 6))
        for t in (cell, ("/", cell, 2), (":", "m", cell), ("$chars", "x"), 1.5):
            assert _show(t) == _recursive_show(t)


def test_show_and_uses_take_a_100k_goal_body():
    n = 100_000
    body = right_nested(",", [("q", "a", i) for i in range(n)] + [r"\+"])
    assert _show(body).count("q(a, ") == n
    u = Uses()
    u.clause((":-", ("p", VarRef(0)), (";", body, (r"\+", ("once", "r")))))
    assert {"q", "r", "once"} <= u.goal_names
    assert u.transition["\\+/1"] == 1 and u.transition["once/1"] == 1
    assert ("p", 1) in u.heads


def test_right_and_left_nested():
    assert right_nested(",", ["a", "b", "c"]) == (",", "a", (",", "b", "c"))
    assert left_nested("+", [1, 2, 3]) == ("+", ("+", 1, 2), 3)
    assert right_nested(";", ["a", "b"]) == (";", "a", "b")


def _ast_depth(node):
    depth, stack = 0, [(node, 1)]
    while stack:
        n, d = stack.pop()
        depth = max(depth, d)
        stack.extend((c, d + 1) for c in ast.iter_child_nodes(n))
    return depth


@pytest.mark.parametrize("sep", [", ", " ; "])
def test_a_20k_goal_body_lowers_to_a_shallow_module(sep):
    n = 20_000
    src = "p(X) :- " + sep.join(f"q(X, {i})" for i in range(n)) + ".\n"
    low = iso_l3.lower_source(src, "long.pl")
    # The body is a flat list of goals (a conjunction) or a balanced Or
    # tree (a disjunction), and clause/2's source term one $right_nested
    # call over a flat list: depth independent of n.
    assert _ast_depth(low.tree) < 80
    compile(low.tree, "long.pl", "exec")


# ── the compiler's final_yields helpers ────────────────────────────────────


def test_copy_ast_is_deepcopy():
    tree = ast.parse(open(iso_l3.__file__, encoding="utf-8").read())
    tree.body[0]._marker = "kept"
    assert (ast.dump(copy_ast(tree), include_attributes=True)
            == ast.dump(copy.deepcopy(tree), include_attributes=True))
    assert copy_ast(tree).body[0]._marker == "kept"
    shared = ast.Name(id="x", ctx=ast.Load())
    pair = ast.Tuple(elts=[shared, shared], ctx=ast.Load())
    c = copy_ast(pair)
    assert c.elts[0] is c.elts[1] and c.elts[0] is not shared


def test_fix_missing_locations_is_the_stdlib_rule():
    src = open(iso_l3.__file__, encoding="utf-8").read()
    a, b = ast.parse(src), ast.parse(src)
    for t in (a, b):
        for i, n in enumerate(ast.walk(t)):
            if i % 3 == 0:
                for attr in ("lineno", "col_offset", "end_lineno", "end_col_offset"):
                    if hasattr(n, attr):
                        delattr(n, attr)
    ast.fix_missing_locations(a)
    fix_missing_locations(b)
    assert ast.dump(a, include_attributes=True) == ast.dump(b, include_attributes=True)


def test_drive_keeps_order_values_and_exceptions():
    log = []

    def count(n):
        log.append(n)
        if n == 0:
            return 0
        if n == 3:
            try:
                yield boom()
            except KeyError:
                log.append("caught")
        return 1 + (yield count(n - 1))

    def boom():
        raise KeyError("x")
        yield

    assert drive(count(100_000)) == 100_000
    assert log[:5] == [100_000, 99_999, 99_998, 99_997, 99_996]
    assert "caught" in log
    with pytest.raises(KeyError):
        drive(boom())


# ── loading: native and translator ─────────────────────────────────────────


@pytest.mark.parametrize("front_end", ["native", "translator"])
def test_a_long_conjunction_loads_and_answers(tmp_path, monkeypatch, front_end):
    # Past both old limits (~500 goals native, ~1000 translator).
    n = 1200
    body = ", ".join(f"q(V{i}, V{i + 1})" for i in range(n))
    m = _load(tmp_path, monkeypatch, front_end, f"""
        q(X, Y) :- Y is X + 1.
        p(V0, V{n}) :- {body}.
        """)
    out = Var()
    assert _answers(m, "p", 0, out, outs=[out]) == [(n,)]


@pytest.mark.parametrize("front_end", ["native", "translator"])
def test_a_long_disjunction_answers_in_order(tmp_path, monkeypatch, front_end):
    n = 3000
    body = " ; ".join(f"X = {i}" for i in range(n))
    m = _load(tmp_path, monkeypatch, front_end, f"p(X) :- ({body}).\n")
    x = Var()
    assert _answers(m, "p", x, outs=[x]) == [(i,) for i in range(n)]


def test_clause_2_reads_a_long_body_back_as_written(tmp_path, monkeypatch):
    n = 2000
    m = _load(tmp_path, monkeypatch, "native",
              ":- dynamic(b/0).\nb :- " + ", ".join(f"t({i})" for i in range(n))
              + ".\nd :- " + " ; ".join(f"t({i})" for i in range(n)) + ".\n"
              + ":- dynamic(d/0).\n")
    body = Var()
    [(got,)] = _answers(m, "clause", "b", body, outs=[body])
    assert got == right_nested(",", [("t", i) for i in range(n)])
    [(got,)] = _answers(m, "clause", "d", body, outs=[body])
    assert got == right_nested(";", [("t", i) for i in range(n)])


def test_long_chains_cut_and_if_then_else_match_scryer(tmp_path, monkeypatch):
    n = 40      # past the 32 at which chains are built flat / balanced
    disj = " ; ".join(f"X = {i}" for i in range(n))
    m = _load(tmp_path, monkeypatch, "native", f"""
        c(X) :- ({disj} ; !, X = cut ; X = after).
        c(X) :- X = clause2.
        i(X, Y) :- ({disj} ; (X == a -> Y = then ; Y = else)).
        t(T) :- T = ({' - '.join(f'a{i}' for i in range(n))}).
        u(T) :- T = ({', '.join(f'a{i}' for i in range(n))}).
        """)
    x, y, t = Var(), Var(), Var()
    # Scryer: [0, ..., 39, cut]
    assert _answers(m, "c", x, outs=[x]) == [(i,) for i in range(n)] + [("cut",)]
    # Scryer: 41 answers, the last _-else
    got = _answers(m, "i", x, y, outs=[x, y])
    assert len(got) == n + 1 and got[-1][1] == "else"
    assert got[:n] == [(i, got[i][1]) for i in range(n)]
    # Scryer: T = (A - a39), A = a0 - ... - a38 (yfx: left-nested)
    [(tt,)] = _answers(m, "t", t, outs=[t])
    assert tt == left_nested("-", [f"a{i}" for i in range(n)])
    [(tt,)] = _answers(m, "u", t, outs=[t])
    assert tt == right_nested(",", [f"a{i}" for i in range(n)])


def test_a_long_grammar_body_and_findall_body_load(tmp_path, monkeypatch):
    n = 1000
    m = _load(tmp_path, monkeypatch, "native", f"""
        s --> {', '.join('[a]' if i % 2 else 't' for i in range(n))}.
        t --> [b].
        q(X, X).
        f(L) :- findall(X, (X = 1, {', '.join(f'q(X, V{i})' for i in range(n))}), L).
        """)
    lst = Var()
    [(got,)] = _answers(m, "phrase", "s", lst, outs=[lst])
    if type(got) is tuple and got[0] == "$chars":    # the chars carrier
        got = list(got[1])
    assert got == ["a" if i % 2 else "b" for i in range(n)]
    [(got,)] = _answers(m, "f", lst, outs=[lst])
    assert got == [1]


# ── what still recurses fails cleanly ──────────────────────────────────────


def test_deep_bracketed_nesting_is_a_resource_error_naming_the_line(
        tmp_path, monkeypatch):
    with pytest.raises(SyntaxError) as e:
        _load(tmp_path, monkeypatch, "native",
              "a(1).\nn(" + "s(" * 3000 + "0" + ")" * 3000 + ").\n")
    msg = str(e.value)
    assert "resource_error(stack)" in msg and ".pl:2:" in msg
    assert "RecursionError" not in msg


def test_a_long_if_then_else_chain_is_a_resource_error_naming_the_clause(
        tmp_path, monkeypatch):
    chain = " ; ".join(f"X =:= {i} -> Y = {i}" for i in range(1000))
    with pytest.raises(SyntaxError) as e:
        _load(tmp_path, monkeypatch, "native",
              f"a(1).\np(X, Y) :- ( {chain} ; Y = none ).\n")
    msg = str(e.value)
    assert "resource_error(stack)" in msg and ":2:" in msg


def test_a_long_conjunction_held_as_data_is_a_resource_error(
        tmp_path, monkeypatch):
    # The engine compiler's walks over a data term still recurse.
    body = ", ".join(f"q(X, V{i})" for i in range(3000))
    with pytest.raises(SyntaxError) as e:
        _load(tmp_path, monkeypatch, "native",
              f":- dynamic(r/1).\nq(X, X).\np :- assertz((r(X) :- {body})).\n")
    msg = str(e.value)
    assert "resource_error(stack)" in msg and "p/0" in msg and ":3:" in msg


def test_a_query_compile_still_raises_recursion_error_itself():
    # Only a MODULE load names the overflow (compiler_v2): a query compile
    # must see the RecursionError, to recompile with the deep argument
    # lifted (tests/test_python_entry_cyclic_deep.py).
    from clausal.logic.compiler import compile_predicate_trampoline
    from clausal.logic.compiler.predicate import too_deep_named
    import inspect
    assert "RecursionError" not in inspect.getsource(compile_predicate_trampoline)
    with pytest.raises(SyntaxError):
        with too_deep_named("p", 1, [], {}):
            raise RecursionError("deep")
