"""Cells as the compiled representation of compound data.

Spec: ``docs/superpowers/plans/2026-09-03-phase2-bridge.md`` (the bridge
that introduced cells behind the ``-tagged_terms`` flag) and
``.superpowers/sdd/p32-cell-default-flip/`` (P3-2, which DELETED that flag
and made cells unconditional); design:
``implementation_plans/tagged-tuple-term-representation.md``.

Four groups of tests:

1. ``TestDefaultPathGolden`` -- the codegen pin.  Five fixtures' full
   generated Python, captured under ``tests/golden/``, so any change to the
   emission path shows up as a reviewable diff rather than as a behavioural
   surprise.  (Pre-flip this pinned the FLAG-OFF path against code that
   predated cells; post-flip there is only one path, and the golden pins
   it.)
2. ``TestRetiredDirective`` -- ``-tagged_terms`` is gone: writing it is a
   SyntaxError like any other unknown directive (R9).
3. ``TestFunctorSignatureRegistry`` -- the declared-signature registry the
   cell resolvers read.
4. ``TestCellEmission`` / ``TestHeadPatterns`` / ``TestParity`` and friends
   -- what cells actually compile to, and that the answers are unchanged.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from clausal.logic.variables import Var, deref
from clausal.logic.solve import call

from tests.tagged_terms_support import (
    capture_predicate_codegen, normalize_answers, normalize_term,
)


_GOLDEN_DIR = pathlib.Path(__file__).parent / "golden"

# Fixtures whose codegen the golden pins.  Chosen to
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
    """The codegen pin: five fixtures' generated Python, byte for byte.

    METHOD.  ``capture_predicate_codegen`` re-drives each predicate's real
    ``_lazy_recompile`` closure (same globals, same strategy, same indexing)
    and ``ast.unparse``\\ s every ``FunctionDef`` the compiler emits --
    the predicate function plus every index bucket, per-position default and
    all-clauses fallback.  The text lives under ``tests/golden/``.  Any
    change to the emission path -- a reordered branch, an extra guard, a
    renamed local -- produces a diff here.

    P3-2 Task 2 (THE FLIP) regenerated these: compound data that used to
    emit class constructions now emits cell literals.  That was the WHOLE
    point of the commit, and the diff was read before it landed.

    Regenerate deliberately (never to make a red test green without reading
    the diff) with::

        CLAUSAL_REGEN_GOLDEN=1 pytest tests/test_tagged_terms.py -k golden
    """

    @pytest.mark.parametrize("module_name", _GOLDEN_MODULES)
    def test_codegen_unchanged(self, module_name):
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
            f"{module_name}: codegen changed -- either a regression, or the "
            f"change is intended and the golden needs regenerating after "
            f"the diff has been READ."
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


class TestRetiredDirective:
    """``-tagged_terms`` is gone (P3-2 Task 2, R9).

    Cells are how compound data compiles, full stop -- there is no per-file
    opt-in left to spell, so the directive is unknown exactly like any other
    misspelling.  Inverts the four ``TestDirective`` tests that pinned the
    flag's parsing and threading: the SyntaxError IS the behaviour now.
    """

    _MESSAGE = "Unknown directive: -tagged_terms"

    def test_bare_form_is_an_unknown_directive(self):
        # R9: the flag is deleted, so the bare marker form is a plain
        # unknown-directive SyntaxError (inverts
        # ``test_bare_directive_sets_module_flag``).
        with pytest.raises(SyntaxError, match=self._MESSAGE):
            _load_inline(
                "_tt_bare",
                "-tagged_terms\n-module(_tt_bare, [pt(X, Y), p(A)])\np(pt(1, 2)),\n",
            )

    def test_parenthesised_form_is_an_unknown_directive(self):
        # R9 (inverts ``test_parenthesised_directive_sets_module_flag``).
        with pytest.raises(SyntaxError, match=self._MESSAGE):
            _load_inline(
                "_tt_paren",
                "-tagged_terms()\n-module(_tt_paren, [pt(X, Y), p(A)])\np(pt(1, 2)),\n",
            )

    def test_argument_form_is_an_unknown_directive_too(self):
        """Not a "takes no arguments" complaint any more -- the name itself
        is unknown, so the argument form gets the same message as the other
        two."""
        # R9 (inverts ``test_directive_rejects_arguments``, which pinned the
        # marker directive's own arity check).
        with pytest.raises(SyntaxError, match=self._MESSAGE):
            _load_inline(
                "_tt_args",
                "-tagged_terms(1)\n-module(_tt_args, [p(A)])\np(1),\n",
            )

    def test_unknown_directive_message_no_longer_lists_tagged_terms(self):
        """The known-directive list must not advertise a deleted directive."""
        # R9 (inverts ``test_unknown_directive_message_lists_tagged_terms``).
        with pytest.raises(SyntaxError) as excinfo:
            _load_inline(
                "_tt_unknown",
                "-no_such_directive(1)\n-module(_tt_unknown, [p(A)])\np(1),\n",
            )
        message = str(excinfo.value)
        assert "known directives:" in message
        assert "tagged_terms" not in message


class TestFunctorSignatureRegistry:
    """P3-2 Task 1: the ``__clausal_functor_signatures__`` registry the
    ``-module``/``-private`` rewrite emits, and ``-import_from`` copies
    across a module boundary.

    Emitted by every ``-module``/``-private`` directive, and load-bearing
    everywhere since P3-2 Task 2 (THE FLIP): it is where a functor's slot
    layout comes from when its declaration mints no class to read
    ``_fields`` off.
    """

    def test_module_directive_registers_field_carrying_entries(self):
        from clausal.logic.cells import FUNCTOR_SIGNATURES_KEY

        m = _load_inline(
            "_tt_sigreg_mod",
            "-module(_tt_sigreg_mod, [pt(x, y), solo])\n",
        )
        registry = m.__dict__[FUNCTOR_SIGNATURES_KEY]
        assert registry["pt"] == ("x", "y")
        assert "solo" not in registry  # bare atom: no fields to register

    def test_private_directive_registers_field_carrying_entries(self):
        from clausal.logic.cells import FUNCTOR_SIGNATURES_KEY

        m = _load_inline(
            "_tt_sigreg_priv",
            "-private([pt(x, y), solo])\n",
        )
        registry = m.__dict__[FUNCTOR_SIGNATURES_KEY]
        assert registry["pt"] == ("x", "y")
        assert "solo" not in registry

    def test_predicates_are_registered_too(self):
        """A functor WITH clauses (a predicate) still gets a registry entry
        -- the data/predicate split is decided by binding shape, not by
        this registry (see the ``-module`` docstring)."""
        from clausal.logic.cells import FUNCTOR_SIGNATURES_KEY

        m = _load_inline(
            "_tt_sigreg_pred",
            "-module(_tt_sigreg_pred, [q(A)])\nq(1),\n",
        )
        assert m.__dict__[FUNCTOR_SIGNATURES_KEY]["q"] == ("A",)

    def test_multiple_directives_accumulate_rather_than_clobber(self):
        from clausal.logic.cells import FUNCTOR_SIGNATURES_KEY

        m = _load_inline(
            "_tt_sigreg_multi",
            "-module(_tt_sigreg_multi, [pt(x, y)])\n"
            "-private([helper(a, b)])\n",
        )
        registry = m.__dict__[FUNCTOR_SIGNATURES_KEY]
        assert registry["pt"] == ("x", "y")
        assert registry["helper"] == ("a", "b")

    def test_import_from_copies_entries_under_the_local_spelling(self):
        """Cross-module fixture pair: ``sig_registry_owner`` declares
        ``pt(x, y)`` and a bare atom ``ao``; ``sig_registry_importer``
        imports ``pt`` under the alias ``local_pt`` and imports ``ao``
        plain.  Only ``pt``'s entry exists to copy -- ``ao`` has none, and
        that must be silently harmless."""
        from clausal.import_hook import _load_module
        from clausal.logic.cells import FUNCTOR_SIGNATURES_KEY

        fixtures_dir = pathlib.Path(__file__).parent / "fixtures"
        owner = _load_module(
            "tests.fixtures.sig_registry_owner",
            str(fixtures_dir / "sig_registry_owner.clausal"),
        )
        importer = _load_module(
            "tests.fixtures.sig_registry_importer",
            str(fixtures_dir / "sig_registry_importer.clausal"),
        )
        assert owner.__dict__[FUNCTOR_SIGNATURES_KEY]["pt"] == ("x", "y")
        registry = importer.__dict__[FUNCTOR_SIGNATURES_KEY]
        assert registry["local_pt"] == ("x", "y")
        assert "ao" not in registry
        assert "pt" not in registry  # only the LOCAL spelling is copied


# ── Cell emission ────────────────────────────────────────────────────────────


# The fixture PAIR.  Pre-flip these differed by one line (``-tagged_terms``
# on the ``_tagged`` half); post-flip they are the same program under two
# module names, compiled identically.  The pair is kept because its recorded
# ANSWERS are a class-era regression anchor -- two independent module
# universes that must still agree, and still agree with what the class
# representation answered before the flip.
_PLAIN = "tests.fixtures.tagged_shapes"
_TAGGED = "tests.fixtures.tagged_shapes_tagged"


def _fixture(module_name: str):
    import importlib

    return importlib.import_module(module_name)


def _logic_module(mod):
    return mod.__dict__["$module"]


def _python_minted(functor, fields, *values):
    """A live term INSTANCE, minted the way PYTHON producers mint one.

    P3-2 Task 2 (THE FLIP, R6): a ``.clausal`` data functor's name binds its
    interned spelling, so ``mod.point(1, 2)`` is no longer a construction --
    ``mod.point`` is the str.  Instances have not gone away, though: modules
    like ``clausal.reflection`` and ``clausal.logic.clpb`` mint their own
    functor classes with ``make_predicate`` and build instances at runtime,
    and those keep CLASS emission everywhere (controller ruling on the gate
    asymmetry).  Tests that need a live instance mint one the same way.
    """
    from clausal.logic.predicate import make_predicate

    return make_predicate(functor, list(fields))(*values)


class TestCellEmission:
    def test_a_module_constructs_cells(self):
        """A saturated declared-functor construction lowers to a tuple."""
        src = capture_predicate_codegen(_TAGGED, ["kind"])
        assert "('point', _v2, _v3)" in src
        assert "('seg', _v10, _v11, _v12)" in src
        assert "point(_v" not in src

    def test_the_sibling_module_constructs_cells_too(self):
        """P3-2 Task 2 (THE FLIP, R5): no opt-in left.  Inverts
        ``test_unflagged_sibling_constructs_class_terms``, which pinned the
        flag-era rule that a module without the directive kept class
        emission -- the sibling fixture carries no directive (none exists)
        and compiles to the identical cells."""
        src = capture_predicate_codegen(_PLAIN, ["kind"])
        assert "('point', _v2, _v3)" in src
        assert "point(_v" not in src

    def test_atoms_lower_to_str_constants_not_to_cells(self):
        """P3-1 atom pivot (§1b): a 0-arity reference is a Constant str, not a
        class -- cells are how COMPOUND (arity >= 1) data compiles; an atom
        was already a str before the flip and still is. Inverts the pre-pivot
        pin
        that atoms "stay class atoms" (phase3-decomposition-and-p31-atom-pivot
        Task 7 work item 1)."""
        src = capture_predicate_codegen(_TAGGED, ["kind"])
        assert "$unify(_v13, 'nil', trail)" in src
        assert "$unify(_v13, nil, trail)" not in src

    def test_keyword_construction_places_by_field_name(self):
        """P3-2 Task 1: signature placement, not a class fallback.

        ``pt(X=1)`` places ``1`` in ``pt``'s declared ``X`` slot and
        backfills the omitted ``Y`` slot with a fresh ``Var()`` -- see
        ``TestSignatureConstruction`` for the fuller placement coverage.
        Superseded ``test_keyword_construction_keeps_class_emission``,
        which pinned the PRE-Task-1 behaviour this test inverts.
        """
        m = _load_inline(
            "_tt_kw",
            "-module(_tt_kw, [pt(X, Y), p(A)])\n"
            "p(pt(X=1)),\n",
        )
        src = capture_predicate_codegen("_tt_kw", ["p"])
        assert "('pt', 1, Var())" in src
        assert "pt(X=1)" not in src

    def test_a_dynamic_declaration_is_not_a_data_functor(self):
        """``-dynamic`` leaves a predicate clause-free at compile time.

        Without the ``_dynamic_arities`` gate, "no clauses" would misread the
        ISO declare-then-assertz pattern as a data functor and compile its
        references to cells that the later-asserted clauses could never match.
        """
        _load_inline(
            "_tt_dyn",
            "-module(_tt_dyn, [d(A, B), p(X, Y)])\n"
            "-dynamic(d/2)\n"
            "p(X, d(X, 1)),\n",
        )
        src = capture_predicate_codegen("_tt_dyn", ["p"])
        assert "('d'," not in src

    def test_a_predicate_reference_is_not_a_cell(self):
        """Only DATA functors (no clauses) become cells -- a predicate stays a
        class so ``call/1`` and dispatch keep working on it."""
        m = _load_inline(
            "_tt_pred",
            "-module(_tt_pred, [q(A), r(A), s(A)])\n"
            "q(1),\n"
            "r(X) <- call(q(X)),\n"
            "s(X) <- r(X),\n",
        )
        src = capture_predicate_codegen("_tt_pred", ["r"])
        assert "('q'," not in src


class TestSignatureConstruction:
    """P3-2 Task 1 (cell-default-flip bridge): kwarg placement + Var
    backfill for cell CONSTRUCTION.  Unconditional since Task 2's flip.

    Positional args fill leading declared slots, keyword args fill their
    named slots, and every slot neither reaches backfills with a fresh
    ``Var()`` -- the same rule ``PredicateMeta.__call__`` already applies to
    class construction, now applied to cell construction too.
    """

    _MODULE_TEMPLATE = (
        "-module({name}, [point(x, y), p(A)])\n"
        "p({goal}),\n"
    )

    def _compile(self, name, goal):
        return _load_inline(name, self._MODULE_TEMPLATE.format(name=name, goal=goal))

    def test_keyword_args_place_by_field_name_regardless_of_order(self):
        self._compile("_tt_sig_kw", "point(y=2, x=1)")
        src = capture_predicate_codegen("_tt_sig_kw", ["p"])
        assert "('point', 1, 2)" in src

    def test_partial_positional_backfills_the_omitted_slot(self):
        """``point(1)`` supplies ``x`` only; ``y`` backfills with a fresh
        ``Var()`` -- asserted by TEXT (var-ness), not by identity, since a
        fresh Var's id is not a meaningful thing to pin."""
        self._compile("_tt_sig_partial", "point(1)")
        src = capture_predicate_codegen("_tt_sig_partial", ["p"])
        assert "('point', 1, Var())" in src

    def test_empty_construction_backfills_both_slots(self):
        self._compile("_tt_sig_empty", "point()")
        src = capture_predicate_codegen("_tt_sig_empty", ["p"])
        assert "('point', Var(), Var())" in src

    def test_over_arity_raises_naming_the_functor(self):
        with pytest.raises(SyntaxError, match=r"point/2"):
            self._compile("_tt_sig_overarity", "point(1, 2, 3)")

    def test_unknown_keyword_field_raises_naming_the_functor(self):
        with pytest.raises(SyntaxError, match=r"point/2"):
            self._compile("_tt_sig_badfield", "point(z=1)")

    def test_duplicate_slot_raises(self):
        """The same field supplied both positionally and by keyword."""
        with pytest.raises(SyntaxError, match=r"point/2"):
            self._compile("_tt_sig_dup", "point(1, x=2)")

    def test_the_runtime_constructor_places_slots_the_same_way(self):
        """The same constructions through ``PredicateMeta.__call__`` (the
        RUNTIME placer a Python caller still reaches): same field values in
        the same slots.  Signature placement changed what a construction
        lowers TO, never what it means -- the compile-time placer and the
        runtime one must keep agreeing."""
        from clausal.logic.predicate import make_predicate

        # R6: read through a PYTHON-minted class -- a ``.clausal``
        # declaration mints none, but ``PredicateMeta.__call__`` is untouched
        # and is still what every Python-side functor producer constructs
        # through, so it is still the placer that has to agree.
        point = make_predicate("point", ["x", "y"])
        assert normalize_term(point(y=2, x=1)) == ("point", 1, 2)
        kw_only = point(x=1)
        assert normalize_term(kw_only)[:2] == ("point", 1)
        assert normalize_term(kw_only)[2] == ("$var",)


class TestHeadSignaturePlacement:
    """P3-2 Task 1, controller ruling: the MATCHING half of the same
    symmetry.  A cell pattern gets the identical signature placement a cell
    construction gets -- positional args fill leading slots, keyword args
    fill named slots, and every omitted slot becomes a WILDCARD pattern
    (binding nothing), not a fallback to class matching.
    """

    def _module_globals(self):
        return _fixture(_TAGGED).__dict__

    def _pattern_for(self, term):
        # ``head_match`` resolves against the ``globals_`` it is handed, so
        # no compile scope is needed here (nor available: this calls the
        # pattern builder directly, not a compile entrypoint).
        from clausal.logic.compiler.head_match import head_to_match_pattern

        return _unparse_pattern(head_to_match_pattern(
            term, {}, [], [], None, globals_=self._module_globals(),
        ))

    @staticmethod
    def _kw_compound(name, positional_n, kw_names):
        from clausal.terms import Call as TCall, LoadName
        from clausal.pythonic_ast.nodes import Keyword

        return TCall(
            func=LoadName(name=name),
            args=[Var() for _ in range(positional_n)],
            kwargs=[Keyword(name=n, value=Var()) for n in kw_names],
        )

    # ``tagged_shapes_tagged.clausal`` declares ``point(X, Y)`` -- the
    # fixture's field names are uppercase, so kwarg-shaped head references
    # against it must use the same spelling.

    def test_keyword_head_arg_places_by_field_name(self):
        got = self._pattern_for(self._kw_compound("point", 0, ["Y", "X"]))
        assert got.startswith("case ['point', ")
        assert not got.endswith(", _]:")  # both slots filled, neither omitted

    def test_partial_keyword_head_arg_wildcards_the_omitted_slot(self):
        got = self._pattern_for(self._kw_compound("point", 0, ["X"]))
        assert got.startswith("case ['point', ")
        assert got.endswith(", _]:")

    def test_over_arity_head_reference_raises_naming_the_functor(self):
        with pytest.raises(SyntaxError, match=r"point/2"):
            self._pattern_for(self._kw_compound("point", 3, []))

    def test_unknown_keyword_field_head_reference_raises(self):
        with pytest.raises(SyntaxError, match=r"point/2"):
            self._pattern_for(self._kw_compound("point", 0, ["z"]))

    def test_duplicate_slot_head_reference_raises(self):
        with pytest.raises(SyntaxError, match=r"point/2"):
            self._pattern_for(self._kw_compound("point", 1, ["X"]))


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

    # P3-2 Task 2 (THE FLIP, R6): one shape column, not two.  Pre-flip the
    # plain half was queried with CLASS instances (``m.point(1, 2)``) because
    # that is what its clauses built; both halves build cells now, so both
    # are queried with the cell -- the class-instance column would test the
    # no-solutions trap, not dispatch.  (That trap keeps its own test below.)
    @pytest.mark.parametrize(
        "shape, expected",
        [
            (lambda m: ("point", 1, 2), ["pt"]),
            (lambda m: ("circle", 0, 5), ["circ"]),
            (lambda m: ("seg", 1, 2, 3), ["seg3"]),
            (lambda m: m.nil, ["empty"]),
            (lambda m: 42, ["num"]),
            (lambda m: "s", ["str"]),
        ],
    )
    def test_functor_and_arity_discrimination(self, shape, expected):
        assert self._kind_of(_TAGGED, shape) == expected
        assert self._kind_of(_PLAIN, shape) == expected

    def test_wrong_arity_cell_matches_no_clause(self):
        """``point/3`` is not ``point/2``: arity is part of the discriminator."""
        assert self._kind_of(_TAGGED, lambda m: ("point", 1, 2, 3)) == []

    def test_unknown_functor_cell_matches_no_clause(self):
        assert self._kind_of(_TAGGED, lambda m: ("square", 1, 2)) == []

    def test_a_declared_data_functor_binds_its_spelling_not_a_constructor(self):
        """The trap the flip CLOSES, pinned on the real path (R6).

        A declared data functor mints no reachable class any more: the name
        binds its interned spelling, so a Python caller cannot build a
        class term that silently unifies with nothing -- reaching for the
        constructor is a loud ``TypeError`` instead, and the cell is the
        thing that works.  (The bridge era pinned the opposite here: the
        constructor existed, was callable, and matched nothing.)
        """
        mod = _fixture(_TAGGED)
        assert mod.point == "point"          # the binding IS the spelling
        with pytest.raises(TypeError):
            mod.point(1, 2)
        # ... and the cell of that shape selects its clause.
        assert self._kind_of(_TAGGED, lambda m: ("point", 1, 2)) == ["pt"]


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
    """Compound head args match as SEQUENCE literals.

    ``head_to_match_pattern`` is exercised directly because the compound
    MatchClass sites it feeds are, in this stage, reached only from the
    argument-index bucket path -- see
    ``TestHeadPatternReachability`` below, which records exactly why the
    ``.clausal`` corpus does not reach them and what would be needed to close
    that.  The pattern shapes are pinned here regardless, because they are
    what any such follow-up would rely on.
    """

    def _module_globals(self):
        return _fixture(_TAGGED).__dict__

    def _pattern(self, term, globals_=None):
        from clausal.logic.compiler.head_match import head_to_match_pattern

        g = globals_ if globals_ is not None else self._module_globals()
        var_context, dup_guards, list_guards = {}, [], []
        return _unparse_pattern(head_to_match_pattern(
            term, var_context, dup_guards, list_guards, None, globals_=g,
        ))

    def _source_compound(self, name, n):
        """The term shape a compound written in ``.clausal`` source has."""
        from clausal.terms import Call as TCall, LoadName

        return TCall(func=LoadName(name=name),
                     args=[Var() for _ in range(n)], kwargs=[])

    def test_source_compound_becomes_a_sequence_pattern(self):
        got = self._pattern(self._source_compound("point", 2))
        # ``ast.unparse`` renders every ``MatchSequence`` with brackets; a
        # tuple-literal and a list-literal pattern are the SAME node in
        # Python's grammar, and both match any sequence.  So this IS the
        # ``case ("point", x, y)`` the design calls for -- and it carries that
        # design's consequence, that a LIST ["point", x, y] would match it
        # too.  Flagged modules do not build str-headed list data.
        assert got.startswith("case ['point', ")
        assert "point(" not in got

    def test_arity_is_part_of_the_pattern(self):
        """``seg/3`` and ``point/2`` differ in sequence LENGTH as well as tag."""
        two = self._pattern(self._source_compound("point", 2))
        three = self._pattern(self._source_compound("seg", 3))
        assert two.count(",") == 2      # tag + 2 args
        assert three.count(",") == 3    # tag + 3 args
        assert three.startswith("case ['seg', ")

    def test_partial_construction_gets_a_wildcard_for_the_missing_slot(self):
        """P3-2 Task 1 (controller ruling): the matching half of signature
        placement.  A partial reference now builds a cell PATTERN too, with
        a wildcard for the field it omits -- ``point(V)`` matches
        ``('point', <p0>, _)``, not a class pattern.  Supersedes
        ``test_partial_construction_keeps_the_class_pattern``, which pinned
        the PRE-Task-1 behaviour this test inverts."""
        got = self._pattern(self._source_compound("point", 1))
        assert got.startswith("case ['point', ")
        assert got.endswith(", _]:")

    def test_a_predicate_reference_keeps_the_class_pattern(self):
        """``kind/2`` has clauses -- it is a predicate, not a data functor."""
        got = self._pattern(self._source_compound("kind", 2))
        assert got.startswith("case kind(")

    def test_live_instance_stays_a_class_pattern(self):
        """P3-2 Task 2, controller ruling: instance-side cell emission is
        REMOVED.  A live ``PredicateMeta`` instance always matches as a
        class, because it always CONSTRUCTS as one -- cell-vs-class is
        decided on the BINDING, and an instance's producer is by definition
        class-world (``clausal.reflection``, ``clpb``).  Inverts
        ``test_live_instance_becomes_a_sequence_pattern``, which pinned the
        bridge-era instance gate.
        """
        got = self._pattern(_python_minted("point", ("X", "Y"), 1, 2))
        assert got.startswith("case point(")

    def test_another_modules_functor_matches_as_a_cell_too(self):
        """P3-2 Task 2 (THE FLIP, R5): the own-module gate is deleted.

        Inverts ``test_another_modules_functor_keeps_the_class_pattern``,
        which pinned the flag-era rule that compound data did not cross the
        module boundary.  Both modules build cells now, so a reference
        resolved against ANOTHER module's namespace must MATCH as a cell --
        keeping the class pattern here is what would produce a clause that
        can never fire.

        Asked on the NAME side: post-ruling an INSTANCE is always a class
        pattern (see the test above), so a name resolved in the other
        module's namespace is where the cross-module question now lives.
        """
        other = _fixture(_PLAIN)
        got = self._pattern(self._source_compound("point", 2),
                            globals_=other.__dict__)
        assert got.startswith("case ['point', ")

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
    """Cell-headed clauses through the REAL bucket-compilation path.

    Five clauses whose head arg is a CELL, compiled against a real module's
    namespace: index partitioning, the argument-index lift, and head-pattern
    emission together.

    P3-2 Task 2, controller ruling: instance-side cell emission is removed,
    so a live term instance -- the shape this used to build its clauses from,
    because it is the shape ``_lift_clause_at_pos`` lifts -- now yields a
    CLASS pattern.  The clauses are built from cells instead, which is what
    the compiler produces for source-written data.  What that costs is
    recorded in ``test_the_lift_does_not_yet_reach_a_cell_pattern`` below:
    the lift does not recognise a cell, so dispatch stays correct but goes
    through the capture-and-unify path rather than a sequence pattern.  Task
    3 is where the lift learns cells.
    """

    #: Head functor for the probe predicate.  A ``Compound`` head under a
    #: name the fixture does not define, so nothing here mutates the shared
    #: module's own predicates (an earlier draft asserted onto ``mod.kind``
    #: and silently polluted every later test in the file).
    PROBE = "kind_probe"

    def _compile_cell_headed_kind(self):
        from clausal.logic.compiler import predicate as predicate_mod
        from clausal.logic.database import Clause, Database
        from clausal.terms import Compound

        mod = _fixture(_TAGGED)
        db = Database()
        for shape, k in [
            (("point", 1, 2), "a"),
            (("point", 3, 4), "b"),
            (("circle", 0, 5), "c"),
            (("seg", 1, 2, 3), "d"),
            (("point", 9, 9), "e"),
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

    def test_the_lift_does_not_yet_reach_a_cell_pattern(self):
        """Recorded finding, not an endorsement (Task 3 closes it).

        ``list_dispatch._lift_clause_at_pos`` recognises ``Compound`` and
        term-instance head args; a CELL is a plain tuple, so it is not
        lifted into a sequence pattern.  The clause still dispatches
        correctly -- the ground cell is captured and unified against a
        ``$headlit`` global, the value-rejecting path every other opaque
        ground literal takes -- which is why
        ``test_cell_callers_select_the_right_clause`` below passes.  What is
        missing is the INDEXED pattern, not the answer.
        """
        _db, src = self._compile_cell_headed_kind()
        assert "case [['point', _ncap0, _ncap1]," not in src
        assert "case [point(" not in src
        # ... and the ground cells reach the clause bodies as head literals.
        assert "$headlit_" in src

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

        db, _src = self._compile_cell_headed_kind()
        lm = Module("_tt_bucket_probe")
        lm.db = db
        K = Var()
        got = [deref(K) for _t in call(self.PROBE, shape, K, module=lm)]
        assert got == expected

    def test_a_class_instance_caller_finds_nothing(self):
        """The documented representation limit, asserted rather than assumed.

        Every compound compiles to a cell now (P3-2 Task 2, R6), so a caller
        that hands in a class INSTANCE -- which post-R6 only a Python-side
        producer can mint -- simply does not unify.  It is not an error, it
        is no solutions.
        """
        from clausal.logic.database import Module

        db, _src = self._compile_cell_headed_kind()
        lm = Module("_tt_bucket_probe")
        lm.db = db
        K = Var()
        assert [
            deref(K)
            for _t in call(self.PROBE,
                           _python_minted("point", ("X", "Y"), 3, 4),
                           K, module=lm)
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
        module compiled from source emits its compounds ONLY as cell
        literals in body ``Unify`` goals -- the head arms stay plain arg
        captures.  (Closing that is P3-2 Task 3's job, not this one's.)
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

        The key function runs at dispatch time with no module context, so
        teaching it about cells changes routing for every plain data tuple
        too -- a decision this task does not take.  P3-2 Task 4 is where the
        cell key lands; until then this test records that cells are
        UNINDEXED but correct, and it is expected to be inverted there.
        """
        from clausal.logic.compiler import arg_index

        assert arg_index._runtime_arg_key(("point", 3, 4)) is arg_index._INDEX_VAR
        # ... while a class INSTANCE of the same functor keys, and indexes,
        # normally.  Post-flip no ``.clausal`` module produces one (R6: a
        # declared data functor mints no reachable class), but a Python-side
        # producer still does -- so the class branch of the key function is
        # live code, and still tested.
        assert arg_index._runtime_arg_key(
            _python_minted("point", ("X", "Y"), 3, 4)) == ("point", 2)


class TestNormalizer:
    """The representation normalizer the parity corpus imports.

    Its whole job is to make one assertion possible: that two runs produced
    the SAME TERM, without the assertion caring which representation carried
    it.  Still load-bearing after the flip -- it is what lets the recorded
    class-era answers stay the regression anchor for cell-era results.
    """

    def test_cell_and_class_term_canonicalise_alike(self):
        # R6: the class half is Python-minted now -- which is exactly the
        # case the normalizer still has to cover, since those are the only
        # class terms left.
        instance = _python_minted("point", ("X", "Y"), 1, 2)
        assert normalize_term(instance) == normalize_term(("point", 1, 2))
        assert normalize_term(instance) == ("point", 1, 2)

    def test_nesting_is_canonicalised_all_the_way_down(self):
        """P3-1 atom pivot (§1b): ``plain.nil`` is the interned str "nil",
        not a 0-arity class, so it canonicalises to itself -- no ("nil",)
        wrapping (phase3-decomposition-and-p31-atom-pivot Task 7 work item
        1)."""
        plain = _fixture(_PLAIN)
        chain = _python_minted(
            "point", ("X", "Y"), 3,
            _python_minted("point", ("X", "Y"), 2, plain.nil))
        assert normalize_term(chain) == ("point", 3, ("point", 2, "nil"))
        assert normalize_term(("point", 3, ("point", 2, plain.nil))) \
            == ("point", 3, ("point", 2, "nil"))

    def test_different_functors_stay_different(self):
        assert (normalize_term(_python_minted("point", ("X", "Y"), 1, 2))
                != normalize_term(("circle", 1, 2)))

    def test_different_arities_stay_different(self):
        assert normalize_term(("seg", 1, 2, 3)) != normalize_term(("seg", 1, 2))

    def test_unbound_vars_canonicalise_to_one_placeholder(self):
        """Var identity is not comparable across two independent runs."""
        assert normalize_term(Var()) == normalize_term(Var()) == ("$var",)

    def test_lists_and_scalars_pass_through(self):
        """P3-1 atom pivot (§1b): ``plain.nil`` is already the plain str
        "nil" -- it passes through like any other scalar, same as before
        the pivot an atom would have needed ("nil",) wrapping (Task 7 work
        item 1)."""
        plain = _fixture(_PLAIN)
        assert normalize_term([1, "a", plain.nil]) == [1, "a", "nil"]
        assert normalize_term(42) == 42

    def test_normalize_answers_handles_binding_dicts_and_bare_terms(self):
        """P3-1 atom pivot (§1b): no ("nil",) wrapping -- see Task 7 work
        item 1."""
        plain = _fixture(_PLAIN)
        rows = [{"T": _python_minted("point", ("X", "Y"), 1, plain.nil)},
                ("point", 1, plain.nil)]
        assert normalize_answers(rows) == [
            {"T": ("point", 1, "nil")},
            ("point", 1, "nil"),
        ]


class TestGateSymmetry:
    """Construction and matching must agree, functor by functor.

    Any gate that one side applies and the other does not produces a clause
    that can never match: built one shape, matched as another.  These pin the
    two sides against each other on the awkward cases.
    """

    _POS_SRC = (
        "-module(_tt_pos, [rec(position, x), p(A)])\n"
        "p(rec(1, 2)),\n"
    )

    def _pos_module(self):
        import sys

        if "_tt_pos" not in sys.modules:
            _load_inline("_tt_pos", self._POS_SRC)
        return sys.modules["_tt_pos"]

    def test_position_field_functor_constructs_as_a_cell(self):
        """P3-2 Task 2, controller ruling: the ``position`` exclusion is GONE.

        It existed because ``term_to_ast_expr``'s keyword slow path DROPS a
        ``position`` field when it constructs a class instance, so the two
        representations of such a functor were not interchangeable.  A cell
        keeps every declared slot, so there is nothing to exclude: a
        declared ``rec(position, x)`` binds its spelling like any other data
        functor and its references compile to ``('rec', 1, 2)``.  Inverts
        ``test_position_field_functor_constructs_as_a_class``.
        """
        self._pos_module()
        src = capture_predicate_codegen("_tt_pos", ["p"])
        assert "('rec', 1, 2)" in src

    def test_position_field_functor_has_no_instance_half_any_more(self):
        """... and the matching half it had to agree with is gone with it.

        The old twin matched a live ``rec`` INSTANCE as a class.  Post-R6 the
        declaration mints no reachable class, so no such instance exists to
        match -- the name is the interned spelling, and both sides of the
        symmetry now answer the same question about the same binding.
        Inverts ``test_position_field_functor_matches_as_a_class``.
        """
        mod = self._pos_module()
        assert mod.rec == "rec"
        with pytest.raises(TypeError):
            mod.rec(1, 2)

    def test_the_cell_branch_resolves_names_where_its_fallback_does(self):
        """``cell_signature_for_name`` looks the name up in the ``globals_``
        argument -- the same dict ``_resolve_loadname`` just used to pin
        ``fields`` for the MatchClass beside it.  Resolving in the open
        compile SCOPE instead would let the two branches disagree about what
        a name means.

        Constructed so the two answers differ: ``globals_`` binds ``point``
        to a PREDICATE (a class with clauses -> class pattern), while the
        open scope binds the same name to a data functor (-> cell pattern).
        Only globals_-resolution gives the class pattern, which is the one
        that agrees with its own fallback.

        (Pre-flip the discriminator was another MODULE's data functor, which
        the deleted own-module gate refused; R5 removed that gate, so the
        premise is re-cast on the data/predicate split, which is what the
        resolver keys on now.)
        """
        from clausal.logic.compiler.head_match import head_to_match_pattern
        from clausal.logic.compiler.terms_to_ast import lowering_scope
        from clausal.logic.predicate import PredicateMeta

        tagged = _fixture(_TAGGED)
        assert tagged.point == "point"                    # the premise ...
        assert isinstance(tagged.kind, PredicateMeta)     # ... both halves
        term = self._source_compound_for("point", 2)
        with lowering_scope(tagged.__dict__):
            pattern = head_to_match_pattern(
                term, {}, [], [], None,
                globals_={"__name__": tagged.__name__, "point": tagged.kind},
            )
        assert _unparse_pattern(pattern).startswith("case point(")

    @staticmethod
    def _source_compound_for(name, n):
        from clausal.terms import Call as TCall, LoadName

        return TCall(func=LoadName(name=name),
                     args=[Var() for _ in range(n)], kwargs=[])

    def test_a_nested_compile_scope_resolves_against_its_own_namespace(self):
        """The compile scope is a STACK whose top wins, not a global setting.

        Replaces ``test_an_unflagged_compile_inside_a_flagged_scope_emits_no_
        cells``, which pinned the same structural property through the
        deleted flag ("an unflagged compile inside a flagged scope emits no
        cells").  There is no flag to seal against any more, but the reason
        the stack is a stack survives it: an inner compile must resolve
        names against ITS namespace, never against whatever an outer compile
        left open -- and a compile handed no namespace must resolve nothing
        rather than borrow one.
        """
        from clausal.logic.compiler.terms_to_ast import (
            cell_signature_for_name, lowering_globals, lowering_scope,
        )

        tagged = _fixture(_TAGGED)
        empty: dict = {"__name__": "_tt_empty"}
        assert lowering_globals() is None
        with lowering_scope(tagged.__dict__):
            assert cell_signature_for_name("point") == ("point", ("X", "Y"))
            with lowering_scope(empty):
                # Inner namespace knows no ``point``: resolves nothing,
                # rather than inheriting the outer scope's answer.
                assert lowering_globals() is empty
                assert cell_signature_for_name("point") is None
                with lowering_scope(None):
                    assert cell_signature_for_name("point") is None
            assert cell_signature_for_name("point") == ("point", ("X", "Y"))
        assert lowering_globals() is None
