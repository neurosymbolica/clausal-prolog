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

from clausal.logic.cells import TAGGED_TERMS_FLAG, is_cell
from clausal.logic.variables import Var, deref
from clausal.logic.solve import call

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


# ── Directive ────────────────────────────────────────────────────────────────


def _load_inline(name: str, source: str):
    """Compile *source* as a ``.clausal`` module named *name*."""
    import tempfile
    import os
    from clausal.import_hook import _load_module

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, f"{name}.clausal")
        with open(path, "w") as fh:
            fh.write(source)
        return _load_module(name, path)


class TestDirective:
    def test_bare_directive_sets_module_flag(self):
        m = _load_inline(
            "_tt_bare",
            "-tagged_terms\n-module(_tt_bare, [pt(X, Y), p(A)])\np(pt(1, 2)),\n",
        )
        assert m.__dict__[TAGGED_TERMS_FLAG] is True

    def test_parenthesised_directive_sets_module_flag(self):
        m = _load_inline(
            "_tt_paren",
            "-tagged_terms()\n-module(_tt_paren, [pt(X, Y), p(A)])\np(pt(1, 2)),\n",
        )
        assert m.__dict__[TAGGED_TERMS_FLAG] is True

    def test_directive_rejects_arguments(self):
        with pytest.raises(SyntaxError, match="takes no arguments"):
            _load_inline(
                "_tt_args",
                "-tagged_terms(1)\n-module(_tt_args, [p(A)])\np(1),\n",
            )

    def test_unflagged_module_has_no_flag(self):
        m = _load_inline(
            "_tt_off",
            "-module(_tt_off, [pt(X, Y), p(A)])\np(pt(1, 2)),\n",
        )
        assert TAGGED_TERMS_FLAG not in m.__dict__

    def test_unknown_directive_message_lists_tagged_terms(self):
        with pytest.raises(SyntaxError, match="tagged_terms"):
            _load_inline(
                "_tt_unknown",
                "-no_such_directive(1)\n-module(_tt_unknown, [p(A)])\np(1),\n",
            )


# ── Cell emission ────────────────────────────────────────────────────────────


_PLAIN = "tests.fixtures.tagged_shapes"
_TAGGED = "tests.fixtures.tagged_shapes_tagged"


def _fixture(module_name: str):
    import importlib

    return importlib.import_module(module_name)


def _logic_module(mod):
    return mod.__dict__["$module"]


class TestCellEmission:
    def test_flagged_module_constructs_cells(self):
        """A saturated declared-functor construction lowers to a tuple."""
        src = capture_predicate_codegen(_TAGGED, ["kind"])
        assert "('point', _v2, _v3)" in src
        assert "('seg', _v10, _v11, _v12)" in src
        assert "point(_v" not in src

    def test_unflagged_sibling_constructs_class_terms(self):
        src = capture_predicate_codegen(_PLAIN, ["kind"])
        assert "point(_v2, _v3)" in src
        assert "('point'," not in src

    def test_atoms_stay_class_atoms_in_a_flagged_module(self):
        """Phase 3 does the atom pivot; a 0-arity reference is still a class."""
        src = capture_predicate_codegen(_TAGGED, ["kind"])
        assert "$unify(_v13, nil, trail)" in src
        assert "('nil'" not in src

    def test_keyword_construction_keeps_class_emission(self):
        """A cell is positional and total: no field names, no Var-backfill."""
        m = _load_inline(
            "_tt_kw",
            "-tagged_terms\n"
            "-module(_tt_kw, [pt(X, Y), p(A)])\n"
            "p(pt(X=1)),\n",
        )
        src = capture_predicate_codegen("_tt_kw", ["p"])
        assert "pt(X=1)" in src
        assert "('pt'," not in src

    def test_a_predicate_reference_is_not_a_cell(self):
        """Only DATA functors (no clauses) become cells -- a predicate stays a
        class so ``call/1`` and dispatch keep working on it."""
        m = _load_inline(
            "_tt_pred",
            "-tagged_terms\n"
            "-module(_tt_pred, [q(A), r(A), s(A)])\n"
            "q(1),\n"
            "r(X) <- call(q(X)),\n"
            "s(X) <- r(X),\n",
        )
        src = capture_predicate_codegen("_tt_pred", ["r"])
        assert "('q'," not in src


class TestParity:
    """The fixture pair answers the same queries the same way.

    Every comparison runs through ``normalize_term`` -- a cell
    ``("point", 3, nil)`` and a class term ``point(X=3, T=nil)`` canonicalise
    to the same tuple -- so the assertion is about the TERM, not about which
    representation produced it.
    """

    def _answers(self, module_name, goal, n_args, build_args):
        mod = _fixture(module_name)
        out = []
        args = build_args(mod)
        outs = [a for a in args if isinstance(a, Var)]
        for _trail in call(goal, *args, module=_logic_module(mod)):
            out.append(tuple(normalize_term(v) for v in outs))
        return out

    @pytest.mark.parametrize("n", [0, 1, 4])
    def test_mk_builds_the_same_chain(self, n):
        def build(mod):
            return (n, Var())

        plain = self._answers(_PLAIN, "mk", 2, build)
        tagged = self._answers(_TAGGED, "mk", 2, build)
        assert plain == tagged
        assert len(plain) == 1

    def test_depth_round_trips_through_construction(self):
        """Build a chain, then destructure it -- both halves, same answer."""
        for module_name in (_PLAIN, _TAGGED):
            mod = _fixture(module_name)
            lm = _logic_module(mod)
            T, D = Var(), Var()
            got = []
            for _t in call("mk", 5, T, module=lm):
                for _t2 in call("depth", T, D, module=lm):
                    got.append(deref(D))
                break
            assert got == [5], module_name

    def test_open_kind_query_enumerates_the_same_terms(self):
        def build(mod):
            return (Var(), Var())

        assert (self._answers(_PLAIN, "kind", 2, build)
                == self._answers(_TAGGED, "kind", 2, build))

    def test_pair_up_answer_parity(self):
        def build(mod):
            return (1, 2, Var())

        assert (self._answers(_PLAIN, "pair_up", 3, build)
                == self._answers(_TAGGED, "pair_up", 3, build))

    def test_failure_parity(self):
        """A query that must fail fails on both halves."""
        def build(mod):
            return (-1, Var())

        assert self._answers(_PLAIN, "mk", 2, build) == []
        assert self._answers(_TAGGED, "mk", 2, build) == []


class TestCellHeadDispatch:
    """Multi-clause dispatch on cell functor AND arity.

    ``kind/2`` has six clauses discriminating on ``point/2``, ``circle/2``,
    ``seg/3``, the atom ``nil``, an int and a str.  ``point`` and ``circle``
    separate on FUNCTOR at equal arity; ``point`` and ``seg`` separate on
    ARITY.  Passing a cell in must select exactly one clause.
    """

    def _kind_of(self, module_name, shape):
        mod = _fixture(module_name)
        K = Var()
        return [
            deref(K)
            for _t in call("kind", shape(mod), K, module=_logic_module(mod))
        ]

    @pytest.mark.parametrize(
        "shape_tagged, shape_plain, expected",
        [
            (lambda m: ("point", 1, 2), lambda m: m.point(1, 2), ["pt"]),
            (lambda m: ("circle", 0, 5), lambda m: m.circle(0, 5), ["circ"]),
            (lambda m: ("seg", 1, 2, 3), lambda m: m.seg(1, 2, 3), ["seg3"]),
            (lambda m: m.nil, lambda m: m.nil, ["empty"]),
            (lambda m: 42, lambda m: 42, ["num"]),
            (lambda m: "s", lambda m: "s", ["str"]),
        ],
    )
    def test_functor_and_arity_discrimination(
        self, shape_tagged, shape_plain, expected,
    ):
        assert self._kind_of(_TAGGED, shape_tagged) == expected
        assert self._kind_of(_PLAIN, shape_plain) == expected

    def test_wrong_arity_cell_matches_no_clause(self):
        """``point/3`` is not ``point/2``: arity is part of the discriminator."""
        assert self._kind_of(_TAGGED, lambda m: ("point", 1, 2, 3)) == []

    def test_unknown_functor_cell_matches_no_clause(self):
        assert self._kind_of(_TAGGED, lambda m: ("square", 1, 2)) == []


# ── Head patterns ────────────────────────────────────────────────────────────


def _unparse_pattern(pattern) -> str:
    """Render a single ``ast.pattern`` as the ``case`` line it produces."""
    node = ast.Module(
        body=[
            ast.Match(
                subject=ast.Name(id="_subject", ctx=ast.Load()),
                cases=[ast.match_case(pattern=pattern, guard=None,
                                      body=[ast.Pass()])],
            )
        ],
        type_ignores=[],
    )
    ast.fix_missing_locations(node)
    return ast.unparse(node).splitlines()[1].strip()


class TestHeadPatterns:
    """A flagged module's compound head args match as SEQUENCE literals.

    ``head_to_match_pattern`` is exercised directly because the compound
    MatchClass sites it feeds are, in this stage, reached only from the
    argument-index bucket path -- see
    ``TestHeadPatternReachability`` below, which records exactly why the
    ``.clausal`` corpus does not reach them and what would be needed to close
    that.  The pattern shapes are pinned here regardless, because they are
    what any such follow-up would rely on.
    """

    def _flagged_globals(self):
        return _fixture(_TAGGED).__dict__

    def _pattern(self, term, flagged, globals_=None):
        from clausal.logic.compiler.head_match import head_to_match_pattern
        from clausal.logic.compiler.terms_to_ast import tagged_terms_lowering

        g = globals_ if globals_ is not None else self._flagged_globals()
        var_context, dup_guards, list_guards = {}, [], []
        if not flagged:
            return _unparse_pattern(head_to_match_pattern(
                term, var_context, dup_guards, list_guards, None, globals_=g,
            ))
        with tagged_terms_lowering(g):
            return _unparse_pattern(head_to_match_pattern(
                term, var_context, dup_guards, list_guards, None, globals_=g,
            ))

    def _source_compound(self, name, n):
        """The term shape a compound written in ``.clausal`` source has."""
        from clausal.terms import Call as TCall, LoadName

        return TCall(func=LoadName(name=name),
                     args=[Var() for _ in range(n)], kwargs=[])

    def test_source_compound_becomes_a_sequence_pattern(self):
        got = self._pattern(self._source_compound("point", 2), flagged=True)
        # ``ast.unparse`` renders every ``MatchSequence`` with brackets; a
        # tuple-literal and a list-literal pattern are the SAME node in
        # Python's grammar, and both match any sequence.  So this IS the
        # ``case ("point", x, y)`` the design calls for -- and it carries that
        # design's consequence, that a LIST ["point", x, y] would match it
        # too.  Flagged modules do not build str-headed list data.
        assert got.startswith("case ['point', ")
        assert "point(" not in got

    def test_source_compound_unflagged_stays_a_class_pattern(self):
        got = self._pattern(self._source_compound("point", 2), flagged=False)
        assert got.startswith("case point(")

    def test_arity_is_part_of_the_pattern(self):
        """``seg/3`` and ``point/2`` differ in sequence LENGTH as well as tag."""
        two = self._pattern(self._source_compound("point", 2), flagged=True)
        three = self._pattern(self._source_compound("seg", 3), flagged=True)
        assert two.count(",") == 2      # tag + 2 args
        assert three.count(",") == 3    # tag + 3 args
        assert three.startswith("case ['seg', ")

    def test_partial_construction_keeps_the_class_pattern(self):
        """Unsaturated: no positional cell can express the missing field."""
        got = self._pattern(self._source_compound("point", 1), flagged=True)
        assert got.startswith("case point(")

    def test_a_predicate_reference_keeps_the_class_pattern(self):
        """``kind/2`` has clauses -- it is a predicate, not a data functor."""
        got = self._pattern(self._source_compound("kind", 2), flagged=True)
        assert got.startswith("case kind(")

    def test_live_instance_becomes_a_sequence_pattern(self):
        mod = _fixture(_TAGGED)
        got = self._pattern(mod.point(1, 2), flagged=True)
        assert got.startswith("case ['point', ")

    def test_live_instance_unflagged_stays_a_class_pattern(self):
        mod = _fixture(_TAGGED)
        got = self._pattern(mod.point(1, 2), flagged=False)
        assert got.startswith("case point(")

    def test_another_modules_functor_keeps_the_class_pattern(self):
        """Compound data does not cross the flag boundary: a functor owned by
        a different module keeps class construction, so it must keep class
        matching too."""
        other = _fixture(_PLAIN)
        got = self._pattern(other.point(1, 2), flagged=True)
        assert got.startswith("case point(")

    def test_no_tuple_data_tag_is_emitted_in_this_stage(self):
        """The ``(tuple, ...)`` tuple-DATA pattern is NOT implemented here.

        Recorded as a test so the absence is deliberate rather than an
        oversight: this stage's corpus reaches no tuple-data head pattern.  If
        one is ever added it must use the dotted ``builtins.tuple`` value
        pattern -- a bare ``tuple`` in a pattern is a capture, and
        ``__builtins__`` is a dict inside an imported module.
        """
        from clausal.logic.compiler import head_match

        # The only cell pattern this stage emits tags slot 0 with a functor
        # STRING; nothing here needs the ``tuple`` type object, so the
        # ``builtins.tuple`` value pattern is not emitted and cannot be
        # mis-spelled as a bare ``tuple`` capture.
        assert not hasattr(head_match, "TUPLE_TAG")
        pattern = head_match._cell_match_pattern("point", [])
        assert isinstance(pattern.patterns[0], ast.MatchValue)
        assert pattern.patterns[0].value.value == "point"


class TestBucketPatternIntegration:
    """The cell pattern through the REAL bucket-compilation path.

    Clauses whose head arg is a live term instance are the shape that
    ``_lift_clause_at_pos`` will lift into the head, which is what puts a
    compound in front of ``head_to_match_pattern``.  Compiling five of them
    against a flagged module's namespace therefore exercises index
    partitioning, the lift, and cell pattern emission together.
    """

    #: Head functor for the probe predicate.  A ``Compound`` head under a
    #: name the fixture does not define, so nothing here mutates the shared
    #: module's own predicates (an earlier draft asserted onto ``mod.kind``
    #: and silently polluted every later test in the file).
    PROBE = "kind_probe"

    def _compile_instance_headed_kind(self):
        from clausal.logic.compiler import predicate as predicate_mod
        from clausal.logic.database import Clause, Database
        from clausal.terms import Compound

        mod = _fixture(_TAGGED)
        db = Database()
        for shape, k in [
            (mod.point(1, 2), "a"),
            (mod.point(3, 4), "b"),
            (mod.circle(0, 5), "c"),
            (mod.seg(1, 2, 3), "d"),
            (mod.point(9, 9), "e"),
        ]:
            db.assertz(Clause(head=Compound(self.PROBE, (shape, k)), body=[]))

        captured = []
        original = predicate_mod.functiondef_to_function

        def _spy(func_def, globals_=None, **kwargs):
            captured.append(ast.unparse(func_def))
            return original(func_def, globals_=globals_, **kwargs)

        predicate_mod.functiondef_to_function = _spy
        try:
            predicate_mod.compile_predicate_trampoline(
                self.PROBE, 2, db.clauses_for(self.PROBE, 2), db,
                globals_=mod.__dict__,
            )
        finally:
            predicate_mod.functiondef_to_function = original
        return db, "\n".join(captured)

    def test_buckets_match_cells_by_functor_and_arity(self):
        _db, src = self._compile_instance_headed_kind()
        assert "case [['point', _ncap0, _ncap1]," in src
        assert "case [['circle', _ncap0, _ncap1]," in src
        assert "case [['seg', _ncap0, _ncap1, _ncap2]," in src
        assert "case [point(" not in src

    @pytest.mark.parametrize(
        "shape, expected",
        [
            (("point", 3, 4), ["b"]),
            (("point", 1, 2), ["a"]),
            (("circle", 0, 5), ["c"]),
            (("seg", 1, 2, 3), ["d"]),
            (("point", 1, 2, 3), []),     # wrong arity
            (("square", 1, 2), []),       # unknown functor
        ],
    )
    def test_cell_callers_select_the_right_clause(self, shape, expected):
        from clausal.logic.database import Module

        db, _src = self._compile_instance_headed_kind()
        lm = Module("_tt_bucket_probe")
        lm.db = db
        K = Var()
        got = [deref(K) for _t in call(self.PROBE, shape, K, module=lm)]
        assert got == expected

    def test_a_class_instance_caller_finds_nothing(self):
        """The documented cross-boundary limit, asserted rather than assumed.

        In a flagged module every compound is a cell, so a caller that hands
        in a class INSTANCE simply does not unify -- it is not an error, it
        is no solutions.  This is why the parity corpus keeps fixtures
        self-contained.
        """
        from clausal.logic.database import Module

        mod = _fixture(_TAGGED)
        db, _src = self._compile_instance_headed_kind()
        lm = Module("_tt_bucket_probe")
        lm.db = db
        K = Var()
        assert [
            deref(K)
            for _t in call(self.PROBE, mod.point(3, 4), K, module=lm)
        ] == []


class TestHeadPatternReachability:
    """Where cell head patterns are, and are not, reached in this stage.

    Recorded as executable findings rather than prose so a later stage that
    changes any of it gets a failing test rather than a stale comment.
    """

    def test_source_written_compounds_never_reach_a_head_pattern(self):
        """A compound written in ``.clausal`` source is a ``Call(LoadName)``
        term, and ``list_dispatch._lift_clause_at_pos`` refuses to lift those
        into a head (the class may not be in the bucket's globals).  So a
        flagged module compiled from source emits its compounds ONLY as cell
        literals in body ``Unify`` goals -- the head arms stay plain arg
        captures, exactly as they do without the flag.
        """
        src = capture_predicate_codegen(_TAGGED)
        case_lines = [l for l in src.splitlines() if l.lstrip().startswith("case ")]
        assert case_lines, "the capture found no match arms at all"
        assert not [l for l in case_lines if "'point'" in l or "'seg'" in l]
        # ... while the cell literals themselves are all over the bodies.
        assert "('point', " in src and "('seg', " in src

    def test_index_dispatch_routes_every_cell_to_the_all_clauses_fallback(self):
        """``arg_index._runtime_arg_key`` has no cell branch, so a cell
        argument keys as ``_INDEX_VAR`` and dispatch takes the all-clauses
        fallback (correct, and unindexed).

        Giving it one is NOT a flag-gated change -- the key function runs at
        dispatch time with no module context -- and it would alter routing
        for plain data tuples in UNFLAGGED modules, which the bridge's
        opt-in-only constraint forbids.  Making bucket dispatch cell-aware
        therefore needs the dispatch key function parameterised per
        predicate; that is a restructuring, deliberately left to a later
        stage.
        """
        from clausal.logic.compiler import arg_index

        mod = _fixture(_TAGGED)
        assert arg_index._runtime_arg_key(("point", 3, 4)) is arg_index._INDEX_VAR
        # ... while the equivalent class term keys, and indexes, normally.
        assert arg_index._runtime_arg_key(mod.point(3, 4)) == ("point", 2)
