"""Round-trip tests for clausal.reflection render_ast/render_source — the
inverse of reify_ast. Invariant: reify(render_source(clause)) is structurally
identical to clause (positions ignored)."""

import dataclasses
import glob
import os

import pytest

from clausal.reflection import (
    Clause,
    ReifyError,
    RenderError,
    reify_source,
    render_ast,
    render_source,
)


def strip_positions(term):
    """Recursively null every ``position`` field so structural == ignores
    source location. Reified terms carry ``_fields``; simple_ast operator
    nodes are dataclasses (their position is compare=False, but we normalise
    anyway to reach nested position-bearing terms)."""
    if isinstance(term, list):
        return [strip_positions(x) for x in term]
    if isinstance(term, tuple):
        return tuple(strip_positions(x) for x in term)
    if isinstance(term, dict):
        return {k: strip_positions(v) for k, v in term.items()}
    if dataclasses.is_dataclass(term) and not isinstance(term, type):
        return dataclasses.replace(term, **{
            f.name: (None if f.name == "position" else strip_positions(getattr(term, f.name)))
            for f in dataclasses.fields(term)
        })
    fields = getattr(type(term), "_fields", None)
    if fields is not None:
        return type(term)(*[
            None if name == "position" else strip_positions(getattr(term, name))
            for name in fields
        ])
    return term


def only_clause(src):
    clauses = [i for i in reify_source(src) if isinstance(i, Clause)]
    assert len(clauses) == 1, f"expected one clause, got {len(clauses)}"
    return clauses[0]


def assert_round_trips(src):
    """render_source then re-reify equals the original clause (ignoring positions)."""
    original = only_clause(src)
    rendered_text = render_source(original)
    reparsed = only_clause(rendered_text + "\n")
    assert strip_positions(reparsed) == strip_positions(original), (
        f"round-trip mismatch for {src!r}\n  rendered: {rendered_text!r}"
    )


class TestFacts:
    @pytest.mark.parametrize("src", [
        "Edge(1, 2),\n",
        "Item('widget', 2.5),\n",
        "Status(ok, 1),\n",
        "Temp(-40),\n",
        "Rule(X, Y),\n",
    ])
    def test_fact_round_trips(self, src):
        assert_round_trips(src)


class TestRules:
    @pytest.mark.parametrize("src", [
        "Connected(X, Y) <- Edge(X, Y)\n",
        "Grandparent(X, Z) <- (Parent(X, Y), Parent(Y, Z))\n",
        "Reachable(X) <- Edge(_, _)\n",
        "Three(A) <- (Pa(A), Qa(A), Ra(A))\n",
    ])
    def test_rule_round_trips(self, src):
        assert_round_trips(src)


class TestOperators:
    @pytest.mark.parametrize("src", [
        "Positive(N) <- (N > 0)\n",
        "AtLeast(N) <- (N >= 10)\n",
        "Eq(N) <- (N == 0)\n",
        "Neq(N) <- (N != 0)\n",
        "Sum(X, Y, Z) <- (Z is X + Y)\n",
        "Prod(X, Y, Z) <- (Z is X * Y)\n",
        "Diff(X, Y, Z) <- (Z is X - Y)\n",
        "Unify2(X, Y) <- (X is Y)\n",
        "Dif2(X, Y) <- (X is not Y)\n",
        "Free(A) <- (not Busy(A))\n",
        "Either(A) <- (Pa(A) or Qa(A))\n",
        "Both(A) <- (Pa(A) and Qa(A))\n",
        "Neg(X, Y) <- (Y is -X)\n",
        "ConsTail(T) <- Head([a, b | T])\n",
        "StarTail(T) <- Head([a, b, *T])\n",
    ])
    def test_operator_round_trips(self, src):
        assert_round_trips(src)


class TestCompoundAndKwargs:
    @pytest.mark.parametrize("src", [
        "Holds(State(A)) <- Check(A)\n",
        "Deep(Pp(Qq(Rr(X)))) <- Base(X)\n",
        "WithList(Pp([1, 2, 3])),\n",
        "Nested([Pp(X), Qq(Y)]),\n",
    ])
    def test_compound_round_trips(self, src):
        assert_round_trips(src)


class TestIfThenElse:
    @pytest.mark.parametrize("src", [
        "Pick(X, Y) <- (Y is If(X > 0, 1, 2))\n",
    ])
    def test_ite_round_trips(self, src):
        assert_round_trips(src)


class TestEscapes:
    @pytest.mark.parametrize("src", [
        "Calc(X, Y) <- (Y is ++(X + 1))\n",
        "Calc2(X, Y, Z) <- (Z is ++(X * Y + 1))\n",
    ])
    def test_escape_round_trips(self, src):
        assert_round_trips(src)


class TestSubscript:
    @pytest.mark.parametrize("src", [
        "Get(P, I) <- (I is P[flags])\n",
        "GetDotted(P, I) <- (I is P[a.b.c])\n",
    ])
    def test_subscript_round_trips(self, src):
        assert_round_trips(src)


class TestDictLiteral:
    @pytest.mark.parametrize("src", [
        "Merge(A, B) <- (A is {**B, foo: B})\n",
        "Merge2(A, B, C) <- (A is {**B, foo: C, bar: B})\n",
    ])
    def test_dict_literal_round_trips(self, src):
        assert_round_trips(src)


class TestArrowLambda:
    @pytest.mark.parametrize("src", [
        "Run0(C) <- run(( () <- base()), C)\n",
        "Run1(C) <- run((X <- base(X)), C)\n",
        "RunN(C) <- run(((ID, PR) <- req(ID, PR)), C)\n",
        "RunBody(C) <- run((X <- (Y is X + 1)), C)\n",
        "RunTwo(C) <- run((X <- p(X)), (Y <- q(Y)), C)\n",
    ])
    def test_arrow_lambda_round_trips(self, src):
        assert_round_trips(src)

    @pytest.mark.parametrize("src", [
        # A genuine `X < -N` comparison must NOT be tightened into a lambda arrow.
        "Cmp(X) <- (X < -1)\n",
        "CmpVar(X, Y) <- (X < -Y)\n",
    ])
    def test_spaced_comparison_not_arrow(self, src):
        assert_round_trips(src)


class TestFormatString:
    @pytest.mark.parametrize("src", [
        'Greet(Name, M) <- (M is f"hi {Name}")\n',
        'Msg(X, S) <- (S is f"val={X}")\n',
    ])
    def test_format_string_round_trips(self, src):
        assert_round_trips(src)


class TestOutOfScope:
    def test_module_directive_raises(self):
        items = reify_source("-module(m)\n")
        directive = next(i for i in items if type(i).__name__ == "ModuleDirective")
        with pytest.raises(RenderError):
            render_source(directive)

    def test_python_code_raises(self):
        items = reify_source("def helper():\n    return 1\n")
        pycode = next(i for i in items if type(i).__name__ == "PythonCode")
        with pytest.raises(RenderError):
            render_source(pycode)


CORPUS_DIR = "/workspace/clausify-domains"


def _corpus_files():
    if not os.path.isdir(CORPUS_DIR):
        return []
    return sorted(glob.glob(os.path.join(CORPUS_DIR, "**", "*.clausal"), recursive=True))


@pytest.mark.skipif(not _corpus_files(), reason=f"corpus {CORPUS_DIR} absent")
@pytest.mark.parametrize("path", _corpus_files())
def test_corpus_clause_round_trips(path):
    """Every Clause in every corpus file renders and re-reifies identically.

    Only Clause items are exercised: every file opens with -module/-import_from
    which reify to ModuleDirective/PythonCode — node kinds the renderer
    deliberately raises on. A RenderError on a real clause is a hard failure
    (a silently-corrupt mutant would falsely 'survive' in the auditor)."""
    try:
        items = reify_source(open(path, encoding="utf-8").read(), filename=path)
    except ReifyError as exc:
        pytest.skip(f"source not reifiable ({exc})")
    except TypeError as exc:
        # Pre-existing REIFIER defect (not a renderer bug): a non-splat dict
        # literal ``{atom: V}`` in term position is rewritten to
        # ``DictTerm({$intern_atom('atom'): V})``; the reifier's ast.Dict
        # handler reifies the ``$intern_atom(...)`` key into a Goal and then
        # tries to use it as a dict key -> "unhashable type: 'Goal'".  This
        # raises before any clause reaches the renderer, so it is out of scope
        # for the render completeness gate.  Filed as a reifier todo; skip so
        # the gate still asserts every *reifiable* clause round-trips.
        if "unhashable type: 'Goal'" not in str(exc):
            raise
        pytest.skip(f"reifier defect (dict-literal atom key unhashable): {exc}")
    clauses = [i for i in items if isinstance(i, Clause)]
    if not clauses:
        pytest.skip("no clauses in file")
    for clause in clauses:
        rendered = render_source(clause)              # must not raise RenderError
        reparsed = [i for i in reify_source(rendered + "\n") if isinstance(i, Clause)]
        assert len(reparsed) == 1, f"{path}: render produced {len(reparsed)} clauses:\n{rendered}"
        assert strip_positions(reparsed[0]) == strip_positions(clause), (
            f"{path}: round-trip mismatch\n  rendered: {rendered!r}"
        )
