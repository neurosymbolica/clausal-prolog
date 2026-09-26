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

from clausal.logic.atoms import mint
from clausal.logic.cells import chars
from clausal.logic.variables import Var, Trail, deref, is_var, unify
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


def _own_row(mod, name):
    """The one row the module's Database owns for *name* (W4b-2d: the module
    dict binds a handle, so the row is read from the Database, not a class).
    Exactly one owned arity with clauses is required -- more, or none, is a
    harness failure rather than a guess."""
    db = _logic_module(mod).db
    rows = [db.row(f, a) for (f, a) in sorted(db.owned_keys()) if f == name]
    rows = [r for r in rows if r is not None and r.clauses]
    assert len(rows) == 1, (name, [r.key for r in rows])
    return rows[0]


def _recompile(mod, name):
    """Drop *name*'s memoised dispatch and re-drive it through the row's own
    lazy recompile (the class era's ``_state_row().dispatch_fn = None`` +
    ``_get_dispatch()``)."""
    row = _own_row(mod, name)
    row.invalidate()
    return row.db.get_dispatch(*row.key)




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

    def test_atoms_lower_to_arity_0_cell_constants_not_to_classes(self):
        """THE FLIP (spec §5.1): a 0-arity reference is the ATOM constant --
        stage 2 (atoms as str): the ``str`` literal ``'nil'`` -- not a class
        and not the reserved 1-tuple cell ``('nil',)``.  Inverts the pre-pivot
        pin that atoms "stay class atoms"."""
        src = capture_predicate_codegen(_TAGGED, ["kind"])
        assert "$unify(_v13, 'nil', trail)" in src
        assert "$unify(_v13, nil, trail)" not in src
        assert "$unify(_v13, ('nil',), trail)" not in src

    def test_a_keyword_construction_is_refused_at_load(self):
        """The keyword SPELLING is retired (2026-09-19): a term is built
        positionally.

        This used to pin P3-2 Task 1's signature placement -- ``pt(X=1)``
        placing 1 in ``pt``'s declared X slot and backfilling Y with a fresh
        ``Var()``.  The placement itself is unchanged and still pinned, by
        ``TestSignatureConstruction``'s positional cases and by
        ``test_the_runtime_constructor_places_slots_the_same_way`` (the
        Python caller still reaches ``PredicateMeta.__call__``).  What this
        now pins is that the SOURCE spelling no longer loads.
        """
        with pytest.raises(SyntaxError, match="keyword arguments"):
            _load_inline(
                "_tt_kw",
                "-module(_tt_kw, [pt(X, Y), p(A)])\n"
                "p(pt(X=1)),\n",
            )

    def test_a_dynamic_declaration_is_not_a_data_functor(self):
        """``-dynamic`` leaves a predicate clause-free at compile time.

        Without the ``_dynamic_arities`` gate, "no clauses" would misread the
        ISO declare-then-assertz pattern as a data functor and compile its
        references to cells that the later-asserted clauses could never match.
        """
        m = _load_inline(
            "_tt_dyn",
            "-module(_tt_dyn, [d(A, B), p(X, Y), use(R)])\n"
            "-dynamic(d/2)\n"
            "p(X, d(X, 1)),\n"
            "use(R) <- (d(7, R)),\n",
        )
        # P2: this asks for the BEHAVIOUR now, not for the absence of a
        # string.  A reference to ``d`` DOES compile to a cell since the
        # head flip -- a cell NAMES a predicate and call/N resolves the
        # name (R-P2-2) -- so "compiles to a cell" stopped being the thing
        # that would break the ISO declare-then-assertz pattern.  What
        # would break it is the pattern not answering, so pin that.
        from clausal.logic.solve import call as _call_g, solve as _solve_g
        from clausal.logic.variables import Var as _V, deref as _dr
        list(_call_g("assertz", ("d", 7, 70), module=m))
        R = _V()
        assert [_dr(R) for _ in _solve_g(("use", R), m)] == [70]

    def test_a_predicate_reference_answers_through_call(self):
        """A reference to a predicate WITH clauses, passed to ``call/1``,
        still answers.

        This used to assert ``"('q'," not in`` the codegen -- and was green
        only because ``q(...)`` was quasi-quotation, which stripped
        ``call(q(X))`` to ``call(X)``: the property was never exercised.
        With ``q`` an ordinary name (q() retired 2026-09-25) the reference
        compiles to the cell ``('q', X)``, as it does for every other name
        since the P2 head flip (see the test above): a cell NAMES a
        predicate and call/N resolves it.  So pin the behaviour, not the
        string.
        """
        m = _load_inline(
            "_tt_pred",
            "-module(_tt_pred, [q(A), r(A), s(A)])\n"
            "q(1),\n"
            "r(X) <- call(q(X)),\n"
            "s(X) <- r(X),\n",
        )
        src = capture_predicate_codegen("_tt_pred", ["r"])
        assert "('q', " in src          # not stripped to call(X) any more
        x = Var()
        lm = m.__dict__["$module"]
        assert [deref(x) for _ in call("s", x, module=lm)] == [1]


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

    def test_keyword_args_are_refused_whatever_their_order(self):
        """Was: ``point(y=2, x=1)`` places by NAME and emits
        ``('point', 1, 2)``.  The spelling is retired (2026-09-19); ordering
        by name is no longer a question a source term can ask."""
        with pytest.raises(SyntaxError, match="keyword arguments"):
            self._compile("_tt_sig_kw", "point(y=2, x=1)")

    def test_partial_positional_raises_like_over_arity(self):
        """FLIPPED 2026-09-24 (ruling C): ``point(1)`` used to backfill ``y``
        with a fresh ``Var()``; a short construction of a DATA functor is now
        refused exactly like a long one (no silent padding)."""
        with pytest.raises(SyntaxError, match=r"point/2 was constructed with 1"):
            self._compile("_tt_sig_partial", "point(1)")

    def test_empty_construction_is_refused(self):
        """``point()`` used to backfill both slots with fresh Vars; a
        construction naming no slot of a fielded signature is refused
        (operator ruling 2026-09-25: no padding; it used to fill the rest with fresh Vars)."""
        with pytest.raises(SyntaxError, match=r"point/2"):
            self._compile("_tt_sig_empty", "point()")

    def test_over_arity_raises_naming_the_functor(self):
        with pytest.raises(SyntaxError, match=r"point/2"):
            self._compile("_tt_sig_overarity", "point(1, 2, 3)")

    def test_unknown_keyword_field_raises_naming_the_functor(self):
        """The refusal names the functor at the WRITTEN arity -- ``point/1``
        for ``point(z=1)``, not the declared ``point/2``.  That is the
        keyword lint speaking (the placer's own unknown-field diagnostic is
        unreachable now that no keyword term loads), and the written arity is
        the one a reader can see at the site."""
        with pytest.raises(SyntaxError, match=r"point/1"):
            self._compile("_tt_sig_badfield", "point(z=1)")

    def test_duplicate_slot_raises(self):
        """The same field supplied both positionally and by keyword.  Refused
        by the keyword lint since 2026-09-19 rather than by the duplicate-slot
        check behind it, and at the same functor/arity."""
        with pytest.raises(SyntaxError, match=r"point/2"):
            self._compile("_tt_sig_dup", "point(1, x=2)")

    def test_the_runtime_constructor_places_slots_the_same_way(self):
        """The same constructions through ``PredicateMeta.__call__`` (the
        RUNTIME placer a Python caller still reaches): same field values in
        the same slots.  Signature placement changed what a construction
        lowers TO, never what it means -- the compile-time placer and the
        runtime one must keep agreeing."""
        from tests.predicate_api_support import term_ctor

        # R6: the RUNTIME placer is ``build_term_cell`` -- the one home of
        # construction against a signature (a handle's ``$head`` and, until
        # W4b-3 slice 7, ``PredicateMeta.__call__`` both go through it).
        # ``term_ctor`` calls it directly (``make_predicate`` was retired at
        # W4b-3 slice 6).
        point = term_ctor("point", ["x", "y"])
        assert normalize_term(point(y=2, x=1)) == ("point", 1, 2)
        # keyword-only naming SOME slots: refused, never padded (2026-09-25)
        from clausal.logic.predicate import ClausalTermConstructionError
        with pytest.raises(ClausalTermConstructionError):
            point(x=1)


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

    def test_partial_keyword_head_arg_is_refused(self):
        """A head reference naming only SOME slots used to wildcard the
        rest; the compile-time placer refuses it as the runtime one does
        (operator ruling 2026-09-25: no padding; it used to fill the rest with fresh Vars)."""
        with pytest.raises(SyntaxError, match=r"point/2"):
            self._pattern_for(self._kw_compound("point", 0, ["X"]))
        got = self._pattern_for(self._kw_compound("point", 0, ["X", "Y"]))
        assert got.startswith("case ['point', ")

    def test_over_arity_head_reference_raises_naming_the_functor(self):
        with pytest.raises(SyntaxError, match=r"point/2"):
            self._pattern_for(self._kw_compound("point", 3, []))

    def test_unknown_keyword_field_head_reference_raises(self):
        with pytest.raises(SyntaxError, match=r"point/2"):
            self._pattern_for(self._kw_compound("point", 0, ["z"]))

    def test_duplicate_slot_head_reference_raises(self):
        with pytest.raises(SyntaxError, match=r"point/2"):
            self._pattern_for(self._kw_compound("point", 1, ["X"]))


class TestPartialHeadReferenceIndexing:
    """P3-2 whole-branch final review, F2 -- RETIRED 2026-09-24 by ruling C.

    This class recorded that a clause head referencing a declared data
    functor at LESS than its declared arity (``pt(1)`` for ``pt(x, y)``) was
    padded to ``('pt', 1, _)`` as a pattern but filed under the WRITTEN-arity
    bucket, so above ``_INDEX_THRESHOLD`` no caller could reach it
    (``xfail(strict=True)``).  Ruling C refuses the short construction at
    load instead of padding it, so the unreachable clause cannot be written;
    the saturated reference still dispatches.
    """

    _SRC = (
        "-module(_tt_partial_head_idx, [\n"
        "    pt(x, y),\n"
        "    probe_sat(S, K),\n"
        "])\n"
        "\n"
        'probe_sat(pt(1, 2), "hit"),\n'
        'probe_sat(901, "n1"),\n'
        'probe_sat(902, "n2"),\n'
        'probe_sat(903, "n3"),\n'
        'probe_sat(904, "n4"),\n'
        'probe_sat(905, "n5"),\n'
    )

    @pytest.fixture(scope="class")
    def lm(self):
        mod = _load_inline("_tt_partial_head_idx", self._SRC)
        return _logic_module(mod)

    def _probe(self, lm, name, cell):
        K = Var()
        return [deref(K) for _t in call(name, cell, K, module=lm)]

    def test_saturated_reference_above_threshold_dispatches(self, lm):
        """Full declared arity written in the head: correct today."""
        assert self._probe(lm, "probe_sat", ("pt", 1, 2)) == [mint("hit")]

    def test_a_partial_head_reference_is_refused_at_load(self):
        with pytest.raises(SyntaxError, match=r"pt/2 was constructed with 1"):
            _load_inline("_tt_partial_head_idx_short", (
                "-module(_tt_partial_head_idx_short, [pt(x, y), probe(S, K)])\n"
                'probe(pt(1), "hit"),\n'))


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
            (lambda m: ("point", 1, 2), [mint("pt")]),
            (lambda m: ("circle", 0, 5), [mint("circ")]),
            (lambda m: ("seg", 1, 2, 3), [mint("seg3")]),
            (lambda m: m.nil, [mint("empty")]),
            (lambda m: 42, [mint("num")]),
            # THE FLIP: the fixture's ``kind("s", "str")`` head literal is the
            # ATOM ``("s",)`` under the default ``-double_quotes(atom)``, so
            # the caller passes the atom; a Python ``str`` is a STRING and
            # selects no clause.
            (lambda m: mint("s"), [mint("str")]),
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
        assert mod.point == mint("point")          # the binding IS the spelling
        with pytest.raises(TypeError):
            mod.point(1, 2)
        # ... and the cell of that shape selects its clause.
        assert self._kind_of(_TAGGED, lambda m: ("point", 1, 2)) == [mint("pt")]


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

    def test_partial_construction_is_refused_like_over_arity(self):
        """FLIPPED 2026-09-24 (ruling C): the matching half of the
        construction rule.  A partial head reference ``point(V)`` used to get
        a wildcard for the omitted slot; it is now refused exactly like the
        construction is -- a pattern that builds one shape and matches
        another is the thing the twin placement exists to prevent."""
        with pytest.raises(SyntaxError, match=r"point/2 was constructed with 1"):
            self._pattern(self._source_compound("point", 1))

    def test_a_predicate_reference_matches_as_a_sequence_too(self):
        """P2 INVERTS this, and means to.

        It pinned that ``kind/2``, having clauses, is a PREDICATE and so
        keeps the class pattern.  Since the head flip a SOURCE compound
        lowers to a cell whichever its name binds -- measured: a
        predicate-named head argument is the cell ``('kk', 1, 2)`` at
        runtime, and a cell passed in matches it -- so data-vs-predicate no
        longer decides the PATTERN.  The class pattern is not dead: it is
        what a LIVE INSTANCE still matches as, which
        ``test_live_instance_stays_a_class_pattern`` pins.  The split moved
        from the NAME to the BINDING.
        """
        got = self._pattern(self._source_compound("kind", 2))
        assert got.startswith("case ['kind', ")

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

    def test_the_tuple_data_tag_emits_as_a_plain_literal_value_pattern(self):
        """INVERTED when the tag became the reserved atom ``'()'``.

        The dotted ``$cells.TUPLE_TAG`` pattern existed for one reason: the tag
        was the ``tuple`` TYPE OBJECT, so writing it into a pattern meant
        writing a NAME, and a bare name in a ``match`` pattern CAPTURES rather
        than compares.  Rooting it at ``$cells`` was how that was dodged.

        A string literal cannot capture, so the dodge is no longer needed and
        tuple-data now emits exactly as a str-functor cell does -- one
        ``MatchValue``, no namespace, no injection.  This test pins the
        collapse; ``tests/tuple_tag/`` pins the tag's value.
        """
        from clausal.logic.compiler import head_match

        pattern = head_match._cell_match_pattern("point", [])
        assert isinstance(pattern.patterns[0], ast.MatchValue)
        assert pattern.patterns[0].value.value == "point"
        # The tag is a literal now, so no namespace is supplied and none is
        # needed -- the same shape the "point" cell above produces.
        got = self._pattern((head_match.TUPLE_TAG, 1),
                            globals_=dict(self._module_globals()))
        assert got == "case ['()', _ncap0]:"

    def test_the_cells_namespace_is_injected_from_one_place(self):
        """P3-3 Task 4: ``$cells`` was hand-copied into the trampoline and the
        simple-strategy ``base_globals`` literals.  One entry in
        ``INJECTED_RUNTIME_BUILTINS`` now feeds every compilation path, and it
        needs NO ``STRICTNESS_EXEMPT_RUNTIME_NAMES`` entry: the ``$`` prefix
        is not a legal identifier character, so no module -- strict or not --
        can spell the name as a bare atom and reach the distrust check at all.
        """
        from clausal.logic.compiler.predicate import INJECTED_RUNTIME_BUILTINS
        from clausal.logic.cells import CELLS_NAMESPACE_KEY
        from clausal.import_hook import STRICTNESS_EXEMPT_RUNTIME_NAMES
        from clausal.logic import cells as cells_module

        assert INJECTED_RUNTIME_BUILTINS[CELLS_NAMESPACE_KEY] is cells_module
        assert CELLS_NAMESPACE_KEY not in STRICTNESS_EXEMPT_RUNTIME_NAMES
        assert CELLS_NAMESPACE_KEY.startswith("$")
        source = (pathlib.Path(__file__).resolve().parents[1]
                  / "clausal" / "logic" / "compiler" / "predicate.py").read_text()
        assert source.count("_CELLS_NAMESPACE_KEY: _cells_module") == 1


class TestBucketPatternIntegration:
    """Cell-headed clauses through the REAL bucket-compilation path.

    Five clauses whose head arg is a CELL, compiled against a real module's
    namespace: index partitioning, the argument-index lift, and head-pattern
    emission together.

    P3-2 Task 2, controller ruling: instance-side cell emission is removed,
    so a live term instance -- the shape this used to build its clauses from,
    because it is the shape ``_lift_clause_at_pos`` lifts -- now yields a
    CLASS pattern.  The clauses are built from cells instead, which is what
    the compiler produces for source-written data.

    P3-2 Task 3 closed the gap this class used to record: a cell head arg now
    has its own branch in ``head_to_match_pattern`` and matches as a sequence.
    Note the clauses here are asserted straight into a ``Database`` with a
    ``Compound`` head, which is the ONE route that runs no hoist at all --
    neither ``Module.define_predicate`` nor ``database_ops``' fact
    normalisation -- so the cell sits in the head from the start and there is
    nothing for the bucket lift to lift.  The lift's own reach is covered by
    ``TestCellHeadReachability``.
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

    def test_a_cell_head_arg_reaches_a_sequence_pattern(self):
        """P3-2 Task 3.  Inverts ``test_the_lift_does_not_yet_reach_a_cell
        _pattern``, which recorded the Task-2 state: a cell head arg had no
        branch in ``head_to_match_pattern``, so a GROUND one was captured and
        unified against a ``$headlit`` global (correct, unindexed) and a
        NON-GROUND one fell to the accept-all wildcard (wrong -- Task 2 report
        section 12).

        The live-cell branch decides both, structurally: a cell is matched the
        way its ``Compound`` analog is matched.
        """
        _db, src = self._compile_cell_headed_kind()
        assert "case [['point', _ncap0, _ncap1]," in src
        assert "case [['seg', " in src
        assert "case [point(" not in src
        # ... and no cell is left riding the opaque-literal capture.
        assert "$headlit_" not in src

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

    def test_asserted_cell_and_compile_time_compound_share_a_bucket(self):
        """P3-2 Task 4: bucket-sharing across producers, end to end.

        Mixes clauses from BOTH producers in one predicate: five asserted
        with a live cell head arg (Python's shape, ``assertz``-style) plus
        one whose head arg is ``Call(LoadName('point'), (7, 8))`` -- the
        shape a compound reference written in ``.clausal`` SOURCE actually
        has (``_lift_clause_at_pos``'s own docstring: "the shape every
        compound written in .clausal source has"), reached via the Var +
        body ``Unify`` a structural head arg is hoisted to
        (``_normalize_structural_head_args``). Both key ``("point", 2)``
        (``_arg_to_index_key``'s ``Call(LoadName)`` branch matches its
        ``Compound``/live-cell branches' key shape exactly), so
        ``_build_arg_index`` puts them in ONE bucket, and a live-cell
        caller reaches clauses from both origins through that single
        compiled bucket function.
        """
        from clausal.logic.compiler import predicate as predicate_mod
        from clausal.logic.database import Clause, Database, Module
        from clausal.terms import Compound, Call, LoadName, Unify

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
        # The sixth clause: a source-shaped compound reference -- Var head
        # arg + body Unify(Var, Call(LoadName('point'), (7, 8))) -- exactly
        # what ``_normalize_structural_head_args`` hoists a written
        # ``kind_probe(point(7, 8), "f")`` fact to.
        v = Var()
        db.assertz(Clause(
            head=Compound(self.PROBE, (v, "f")),
            body=[Unify(left=v, right=Call(
                func=LoadName(name="point"), args=[7, 8], kwargs=[]))],
        ))

        calls = {"bucket": 0, "fallback": 0}
        original = predicate_mod.functiondef_to_function
        bucket_name = f"{self.PROBE}__p0_b0"  # 'point' is the first-seen key

        def _counting(name, fn):
            def wrapped(*a, **kw):
                calls[name] += 1
                yield from fn(*a, **kw)
            wrapped.__name__ = fn.__name__
            wrapped.__qualname__ = fn.__qualname__
            return wrapped

        def _spy(func_def, globals_=None, **kwargs):
            fn = original(func_def, globals_=globals_, **kwargs)
            if func_def.name.startswith(bucket_name):
                return _counting("bucket", fn)
            if func_def.name == f"{self.PROBE}__all":
                return _counting("fallback", fn)
            return fn

        predicate_mod.functiondef_to_function = _spy
        try:
            predicate_mod.compile_predicate_trampoline(
                self.PROBE, 2, db.clauses_for(self.PROBE, 2), db,
                globals_=mod.__dict__,
            )
            lm = Module("_tt_bucket_probe_mixed")
            lm.db = db
            for shape, expected in [
                (("point", 1, 2), ["a"]),
                (("point", 7, 8), ["f"]),   # the Compound-producer clause
                (("point", 3, 4), ["b"]),
            ]:
                K = Var()
                got = [deref(K) for _t in call(self.PROBE, shape, K, module=lm)]
                assert got == expected, shape
        finally:
            predicate_mod.functiondef_to_function = original

        # Every one of the three calls above keyed "point" and reached the
        # single 'point' bucket -- never the all-clauses fallback.
        assert calls == {"bucket": 3, "fallback": 0}, calls


class TestHeadPatternReachability:
    """Where cell head patterns are, and are not, reached in this stage.

    Recorded as executable findings rather than prose so a later stage that
    changes any of it gets a failing test rather than a stale comment.
    """

    def test_source_written_compounds_reach_a_head_pattern(self):
        """P3-2 Task 3 (the crux).  Inverts
        ``test_source_written_compounds_never_reach_a_head_pattern``, which
        pinned the Task-2 state: ``_lift_clause_at_pos`` refused every
        ``Call(LoadName)`` because the pattern emitter needed the functor
        CLASS in the bucket's globals, so a module compiled from source
        emitted its compounds ONLY as cell literals in body ``Unify`` goals.

        A cell pattern is a sequence LITERAL -- it resolves nothing at match
        time -- so that refusal had nothing left to protect.  The lift asks
        the one question that remains, at LIFT time, of the full module
        namespace: is this name a DATA functor?
        """
        src = capture_predicate_codegen(_TAGGED)
        case_lines = [l for l in src.splitlines() if l.lstrip().startswith("case ")]
        assert case_lines, "the capture found no match arms at all"
        assert [l for l in case_lines if "'point'" in l or "'seg'" in l]
        # ... while the UNLIFTED fallback still carries the cell literals in
        # body Unify goals, which is what keeps output mode working.
        assert "('point', " in src and "('seg', " in src

    def test_index_dispatch_routes_a_cell_to_its_bucket(self):
        """``arg_index._runtime_arg_key`` learns cells (P3-2 Task 4): a cell
        argument now keys as ``(functor, arity)`` -- the same shape the
        ``Compound``/class-instance branches already used -- so dispatch
        SELECTS the specific bucket instead of taking the all-clauses
        fallback.

        Inverts ``test_index_dispatch_routes_every_cell_to_the_all_clauses_fallback``,
        whose own docstring named this test as its expected replacement:
        "P3-2 Task 4 is where the cell key lands ... it is expected to be
        inverted there."
        """
        from clausal.logic.compiler import arg_index

        assert arg_index._runtime_arg_key(("point", 3, 4)) == ("point", 2)

        # Demonstrate the SELECTION, not just the key: instrument the
        # compiled bucket and fallback functions of a real, >threshold
        # cell-headed predicate (``kind/2``, 6 clauses -- see
        # tests/fixtures/tagged_shapes_tagged.clausal) and drive it
        # end-to-end through ``call()``.  Before this task both counters
        # would read ``{"bucket": 0, "fallback": 1}`` -- the fallback was
        # the only reachable route for a cell caller.
        import importlib
        from clausal.logic.compiler import predicate as predicate_mod

        module = importlib.import_module(_TAGGED)
        original = predicate_mod.functiondef_to_function
        calls = {"bucket": 0, "fallback": 0}

        def _counting(name, fn):
            def wrapped(*a, **kw):
                calls[name] += 1
                yield from fn(*a, **kw)
            wrapped.__name__ = fn.__name__
            wrapped.__qualname__ = fn.__qualname__
            return wrapped

        def _spy(func_def, globals_=None, **kwargs):
            fn = original(func_def, globals_=globals_, **kwargs)
            if func_def.name == "kind__p0_b0__2":
                return _counting("bucket", fn)
            if func_def.name == "kind__all__2":
                return _counting("fallback", fn)
            return fn

        row = _own_row(module, "kind")
        predicate_mod.functiondef_to_function = _spy
        try:
            row.invalidate()
            lm = _logic_module(module)
            K = Var()
            got = [deref(K) for _t in call("kind", ("point", 1, 2), K, module=lm)]
        finally:
            predicate_mod.functiondef_to_function = original
            row.invalidate()  # don't leak the instrumented closures

        assert got == [mint("pt")]
        assert calls == {"bucket": 1, "fallback": 0}, calls


# ── P3-2 Task 3: head-pattern reachability ───────────────────────────────────


def _named_function(src: str, name: str) -> str:
    """Slice the ``def <name>(...)`` block out of a captured codegen dump."""
    out, keeping = [], False
    for line in src.splitlines():
        if line.startswith(f"def {name}("):
            keeping = True
        elif keeping and line.startswith("def "):
            break
        if keeping:
            out.append(line)
    assert out, f"no function {name} in the capture"
    return "\n".join(out)


def _case_lines(src: str) -> list[str]:
    return [l.strip() for l in src.splitlines() if l.lstrip().startswith("case ")]


#: ``assertz`` of a fact whose CELL head arg carries an opaque literal -- the
#: route on which finding 2 was reported, spelled in ``.clausal`` rather than
#: through the Python API.  ``q/2`` and ``n/2`` are -dynamic, so their heads
#: are predicate instances and ``_normalize_fact_clause`` passes them through
#: unhoisted: the cell sits in the head from the start.
_OPAQUE_ASSERTZ_SRC = """
-allow_singletons
-import_from(date_time, [date])
-module(_tt_opaque_assertz, [pt(X, Y), q(S, K), n(S, K)])
-dynamic(q/2)
-dynamic(n/2)

setup <- (
    D is date(2020, 1, 1),
    assertz(q(pt(1, D), "yes")),
    assertz(q(_Any, "catchall")),
    assertz(n(pt(1, pt(2, D)), "yes")),
    assertz(n(_Any2, "catchall"))
)
"""


#: Six ``kind/2`` clauses -- over ``_INDEX_THRESHOLD`` -- whose position-0
#: buckets the lift reaches, one of them carrying a ``PyThunk`` (the f-string)
#: nested inside the compound reference.  See
#: ``test_a_reference_carrying_a_nested_thunk_is_not_lifted``.
_NESTED_THUNK_SRC = """
-allow_singletons
-module(_tt_nested_thunk, [pt(X, Y), wrap(V), kind(S, K)])

kind(pt(1, _A), "a") <- (true),
kind(pt(2, _B), "b") <- (true),
kind(pt(3, f"x{1}"), "fs") <- (true),
kind(wrap("s"), "w") <- (true),
kind(42, "num") <- (true),
kind(_Other, "fallback") <- (true),
"""


class TestTheBucketLift:
    """``_lift_clause_at_pos`` decides, per clause, whether a hoisted body
    ``Unify`` may go back into the head.

    P3-2 Task 3.  Pre-flip it refused every ``Call(LoadName)`` because the
    pattern emitter needed the functor CLASS in the bucket's globals.  A cell
    pattern is a plain sequence literal -- it resolves nothing at match time
    -- so the only question left is the one asked at LIFT time: is this name
    a DATA functor?  These pin both answers.
    """

    def _clause(self, arg_term):
        from clausal.logic.database import Clause
        from clausal.terms import Compound, Unify

        v = Var()
        return Clause(head=Compound("p", (v, "k")),
                      body=[Unify(left=v, right=arg_term)])

    def _call(self, name, n_args=2, kwargs=None):
        from clausal.terms import Call as TCall, LoadName
        from clausal.pythonic_ast.nodes import Keyword

        return TCall(func=LoadName(name=name),
                     args=[Var() for _ in range(n_args)],
                     kwargs=[Keyword(name=k, value=v)
                             for k, v in (kwargs or {}).items()])

    def _lift(self, term, globals_=None):
        from clausal.logic.compiler.list_dispatch import _lift_clause_at_pos

        g = globals_ if globals_ is not None else _fixture(_TAGGED).__dict__
        return _lift_clause_at_pos(self._clause(term), 0, g)

    def test_a_data_functor_reference_is_lifted_into_the_head(self):
        from clausal.terms import Call as TCall

        out = self._lift(self._call("point", 2))
        assert isinstance(out.head.args[0], TCall)
        assert out.body == [], "the lifted Unify must leave the body"

    def test_a_partial_data_functor_reference_is_lifted_too(self):
        """Signature PLACEMENT backfills the omitted slot with a wildcard on
        the pattern side (Task 1's ruling), so a partial reference is as
        liftable as a saturated one."""
        out = self._lift(self._call("point", 1))
        assert out.body == []

    def test_a_keyword_data_functor_reference_is_lifted_too(self):
        out = self._lift(self._call("point", 0, {"Y": Var()}))
        assert out.body == []

    def test_a_predicate_functor_reference_is_lifted_too(self):
        """P2 INVERTS R6b, and means to.

        R6b refused a ``PredicateMeta``-bound name because a predicate
        reference had no cell pattern to lift into.  It has one now -- the
        head flip gives a source compound a sequence pattern whichever its
        name binds -- so the question this class describes ("is this name a
        DATA functor?") no longer has two answers, and the lift treats both
        alike.  Safe for the reason the class docstring already gives: a
        cell pattern is a plain sequence literal and resolves nothing at
        match time.
        """
        from clausal.terms import Call as TCall

        out = self._lift(self._call("kind", 2))
        assert out.body == [], "the lifted Unify must leave the body"
        assert isinstance(out.head.args[0], TCall)

    def test_an_unresolvable_name_is_still_refused(self):
        out = self._lift(self._call("no_such_functor_anywhere", 2))
        assert len(out.body) == 1

    def test_with_no_namespace_at_all_the_lift_is_refused(self):
        """No namespace, nothing to resolve against, no lift -- the resolver
        answers ``None`` and the old refusal stands."""
        out = self._lift(self._call("point", 2), globals_={})
        assert len(out.body) == 1

    def test_a_loadattr_call_is_still_refused(self):
        """``head_to_match_pattern`` has a ``Call(LoadName)`` branch and no
        ``Call(LoadAttr)`` one, so lifting a LoadAttr chain would emit a
        ``MatchClass(Call, ...)`` no runtime term matches.  Dotted references
        reach the term world as a single dotted ``LoadName`` anyway."""
        from clausal.terms import Call as TCall, LoadName, LoadAttr

        term = TCall(func=LoadAttr(object=LoadName(name="other"), attr="point"),
                     args=[Var(), Var()], kwargs=[])
        out = self._lift(term)
        assert len(out.body) == 1


class TestCellHeadReachability:
    """A compound written in ``.clausal`` source now reaches a head pattern.

    P3-2 Task 3 (the crux).  ``_normalize_structural_head_args`` hoists the
    head arg to ``Var`` + body ``Unify`` at assert time so an unbound caller
    binds in output mode; the argument-index bucket -- where dispatch has
    already guaranteed the argument ground -- lifts it back, and the pattern
    is a cell sequence literal.
    """

    def _kind_src(self):
        return capture_predicate_codegen(_TAGGED, ["kind"])

    def test_the_bucket_arm_is_a_cell_sequence_pattern(self):
        src = self._kind_src()
        arms = _case_lines(_named_function(src, "kind__p0_b0__2"))
        assert any(a.startswith("case [['point', ") for a in arms), arms

    def test_every_source_compound_bucket_gets_its_own_arm(self):
        src = self._kind_src()
        assert "case [['point', " in src
        assert "case [['circle', " in src
        assert "case [['seg', " in src

    def test_the_lifted_positions_body_unify_is_gone(self):
        """The whole point of the lift: one ``trail.mark()`` + ``unify`` +
        ``undo`` triple per clause per invocation, deleted.

        ``ast.unparse`` renders the cell PATTERN with brackets
        (``['point', ...]``) and the cell TERM with parentheses
        (``('point', ...)``), so the absence of the parenthesised form is
        exactly the absence of the body ``Unify``.
        """
        bucket = _named_function(self._kind_src(), "kind__p0_b0__2")
        assert "('point'," not in bucket
        assert "$unify" in bucket, "the second arg still unifies"

    def test_the_all_clauses_fallback_keeps_its_unify(self):
        """Output mode lives in the fallback, which is NOT lifted -- an
        unbound caller reaches it and the body ``Unify`` binds."""
        fallback = _named_function(self._kind_src(), "kind__all__2")
        assert "('point'," in fallback.replace(" ", "")
        assert not [a for a in _case_lines(fallback) if "'point'" in a]

    def test_the_lifted_bucket_function_matches_a_real_cell(self):
        """Drive the compiled bucket directly.

        Runtime dispatch still routes a cell argument to the all-clauses
        fallback (``arg_index._runtime_arg_key`` learns cells in Task 4), so
        the lifted bucket is not yet SELECTED -- but it is compiled, and it
        has to be right when Task 4 turns it on.  Calling it is the evidence.
        """
        fn = _capture_bucket_functions(_TAGGED, "kind")["kind__p0_b0__2"]
        K = Var()
        assert _drive_bucket(fn, ("point", 1, 2), K) == [mint("pt")]
        # ... and it rejects every other shape.
        for other in [("circle", 1, 2), ("point", 1, 2, 3), 42, "point"]:
            assert _drive_bucket(fn, other, Var()) == [], other

    def test_ground_cell_callers_still_get_the_right_answers(self):
        mod = _fixture(_TAGGED)
        lm = _logic_module(mod)
        for shape, expected in [
            (("point", 1, 2), [mint("pt")]),
            (("circle", 1, 2), [mint("circ")]),
            (("seg", 1, 2, 3), [mint("seg3")]),
            (42, [mint("num")]),
            (("square", 1, 2), []),
        ]:
            K = Var()
            assert [deref(K) for _t in call("kind", shape, K, module=lm)] \
                == expected, shape

    def test_an_unbound_caller_still_enumerates_every_clause(self):
        """Output mode is unbroken: the lift only touches bucket functions,
        and an unbound argument never reaches one."""
        mod = _fixture(_TAGGED)
        lm = _logic_module(mod)
        S, K = Var(), Var()
        got = [(normalize_term(deref(S)), deref(K))
               for _t in call("kind", S, K, module=lm)]
        assert [k for _s, k in got] == [mint("pt"), mint("circ"), mint("seg3"),
                                        mint("empty"), mint("num"),
                                        mint("str")]
        assert got[0][0] == ("point", ("$var",), ("$var",))

    def test_a_reference_carrying_a_nested_thunk_is_not_lifted(self):
        """Found by DRIVING a lifted bucket, not by reading it.

        ``_collect_globals_info`` walks the pre-lift clauses, and only its
        HEAD walker records ``$headlit_<id>`` entries.  Lifting a reference
        whose slot holds a ``PyThunk`` (here an f-string) therefore emitted a
        bucket arm naming a global nothing injected -- ``NameError`` the first
        time the bucket was entered -- and the pattern would have been wrong
        anyway, guarding against the thunk OBJECT.  It is the top-level
        ``PyThunk`` skip's own reason, one level down.

        The bucket is entered directly because runtime dispatch still routes
        a cell to the fallback until Task 4 -- which is exactly why reading
        the codegen would not have caught this.
        """
        mod = _load_inline("_tt_nested_thunk", _NESTED_THUNK_SRC)
        fns = _capture_bucket_functions("_tt_nested_thunk", "kind")
        bucket = fns["kind__p0_b0__2"]
        # The bucket also holds the var-headed catch-all, which matches
        # anything -- so "fallback" trails every answer here.
        # ``f"x{1}"`` is a thunk and evaluates to the STRING "x1"; every
        # other literal in the fixture is an atom.
        assert _drive_bucket(bucket, ("pt", 3, "x1"), Var()) \
            == [mint("fs"), mint("fallback")]
        assert _drive_bucket(bucket, ("pt", 1, 9), Var()) \
            == [mint("a"), mint("fallback")]
        # ``wrap`` is not in this (first-argument) bucket at all, so only
        # the var-headed catch-all answers.
        assert _drive_bucket(bucket, ("wrap", mint("s")), Var()) \
            == [mint("fallback")]
        # The two thunk-free clauses ARE lifted; the thunk one keeps its
        # body Unify, which is where the thunk gets evaluated.
        src = capture_predicate_codegen("_tt_nested_thunk", ["kind"])
        bucket_src = _named_function(src, "kind__p0_b0__2")
        assert bucket_src.count("case [['pt', ") == 2
        assert "_pyt_" in bucket_src
        del mod

    def test_an_imported_functor_head_arg_lifts_too(self):
        """R5: compound data crosses module boundaries as cells, so the
        pre-P3-2 refusal reason -- 'the imported functor class is NOT in the
        bucket's globals' -- has nothing left to protect.  A literal pattern
        resolves nothing at match time.
        """
        importer = _load_head_compound_importer()
        src = capture_predicate_codegen(
            "tests.fixtures.head_compound_importer", ["check_indexed"])
        assert "case [['wrap', " in src, src
        assert "case [['item', " in src, src
        del importer

    def test_the_imported_functor_answers_are_unchanged(self):
        importer = _load_head_compound_importer()
        lm = importer.__dict__["$module"]
        R = Var()
        assert [deref(R) for _t in
                call("check_indexed", ("wrap", mint("direct")), R, module=lm)] \
            == [mint("first"), mint("second"), mint("fallback")]
        R2 = Var()
        assert [deref(R2) for _t in
                call("check_indexed", 42, R2, module=lm)] == [mint("fallback")]


class TestLiveCellHeadArg:
    """A live CELL sitting in a clause head -- the ``assertz`` path.

    ``head_to_match_pattern`` had no tuple branch, so a cell head arg fell
    through: a GROUND one to the A02-F003 opaque-literal capture, and a
    NON-GROUND one to the accept-all wildcard, which fired on every caller
    (Task 2 report section 12).  The rule is the one the whole flip is held
    to: answer exactly what the ``Compound`` analog answers.
    """

    def _fact_module(self, arg):
        from clausal.logic.database import Clause, Database, Module
        from tests.predicate_api_support import term_ctor
        from clausal.logic.compiler import predicate as predicate_mod

        Q = term_ctor("qq", ("S", "K"))
        db = Database()
        db.assertz(Clause(head=Q(S=arg, K="yes"), body=[]))
        db.assertz(Clause(head=Q(S=Var(), K="catchall"), body=[]))
        predicate_mod.compile_predicate_trampoline(
            "qq", 2, db.clauses_for("qq", 2), db)
        m = Module("_tt_live_cell")
        m.db = db
        return m

    def _ask(self, m, probe):
        K = Var()
        return [deref(K) for _t in call("qq", probe, K, module=m)]

    def test_a_non_ground_cell_head_arg_no_longer_fires_on_everything(self):
        """The section-12 repro."""
        m = self._fact_module(("pt", 1, Var()))
        assert self._ask(m, 42) == ["catchall"]
        assert self._ask(m, ("other", 1, 2)) == ["catchall"]
        assert self._ask(m, ("pt", 1, 2)) == ["yes", "catchall"]

    def test_a_non_ground_cell_answers_what_its_compound_twin_answers(self):
        from clausal.terms import Compound

        cell = self._fact_module(("pt", 1, Var()))
        comp = self._fact_module(Compound("pt", (1, Var())))
        assert self._ask(cell, 42) == self._ask(comp, 42)
        assert self._ask(cell, ("pt", 1, 2)) == self._ask(
            comp, Compound("pt", (1, 2)))

    def test_the_inner_var_is_fresh_per_invocation(self):
        """A captured literal cannot carry an inner Var -- it would be SHARED
        across invocations.  The sequence pattern captures into per-call
        locals instead, so a first caller binding the slot cannot leak into
        a second."""
        m = self._fact_module(("pt", 1, Var()))
        assert self._ask(m, ("pt", 1, "a")) == ["yes", "catchall"]
        assert self._ask(m, ("pt", 1, "b")) == ["yes", "catchall"]

    def test_a_ground_cell_head_arg_still_selects_correctly(self):
        m = self._fact_module(("pt", 1, 2))
        assert self._ask(m, ("pt", 1, 2)) == ["yes", "catchall"]
        assert self._ask(m, 42) == ["catchall"]
        assert self._ask(m, ("pt", 1, 3)) == ["catchall"]

    def test_the_cell_and_compound_rows_agree_in_every_argument_mode(self):
        """The parity table, asserted rather than argued.

        For each of the four head-arg shapes, what the clause accepts, what it
        rejects, and whether an unbound caller gets an answer.  Cells answer
        what their ``Compound`` analog answers -- including the part nobody
        likes, that a structural head arg asserted through ``assertz`` has no
        output mode (the hoist that provides one runs on the ``.clausal``
        loading path, not here, and it has never run for ``Compound`` either).
        """
        from clausal.terms import Compound

        def row(arg, self_shaped):
            m = self._fact_module(arg)
            S, K = Var(), Var()
            return (
                self._ask(m, 42),
                self._ask(m, self_shaped),
                [deref(K) for _t in call("qq", S, K, module=m)],
            )

        comp_ground = row(Compound("pt", (1, 2)), Compound("pt", (1, 2)))
        comp_open = row(Compound("pt", (1, Var())), Compound("pt", (1, 2)))
        cell_ground = row(("pt", 1, 2), ("pt", 1, 2))
        cell_open = row(("pt", 1, Var()), ("pt", 1, 2))

        assert cell_ground == comp_ground
        assert cell_open == comp_open
        assert comp_ground == (["catchall"], ["yes", "catchall"], ["catchall"])

    def test_a_var_functor_cell_head_arg_stays_a_wildcard(self):
        """Nothing can be decided statically about ``(X, 1, 2)`` -- the same
        answer the ``Compound`` branch gives a var-functor Compound.

        The SINK has to come back empty too.  Recursing into the slots before
        deciding the tag left their guards behind in ``list_guards`` while the
        pattern that would have bound their captures was discarded, so the
        arm ran ``_ncap1 == 2`` against a name no pattern binds (fix round 1,
        finding 1).  Asserting only the pattern is what let that through.
        """
        from clausal.logic.compiler.head_match import head_to_match_pattern

        vc, lg = {}, []
        got = _unparse_pattern(head_to_match_pattern(
            (Var(), 1, 2), vc, [], lg, None, globals_={}))
        assert got == "case _:"
        assert lg == [], f"guards leaked for a pattern that was discarded: {lg}"

    def test_a_tuple_data_cell_head_arg_matches_on_the_dotted_tag(self):
        """Spec section 4: ``(tuple, e1, ...)`` tags slot 0 with the ``tuple``
        TYPE OBJECT, so the pattern needs a DOTTED value pattern -- a bare
        ``tuple`` in a pattern is a capture."""
        from clausal.logic.cells import make_tuple_cell

        m = self._fact_module(make_tuple_cell(1, Var()))
        assert self._ask(m, make_tuple_cell(1, 2)) == ["yes", "catchall"]
        assert self._ask(m, make_tuple_cell(9, 9)) == ["catchall"]
        # ... and it is NOT confused with plain tuple data, nor with a
        # str-functor cell of the same length.
        assert self._ask(m, (1, 2)) == ["catchall"]
        assert self._ask(m, ("pt", 1, 2)) == ["catchall"]

    def test_the_tuple_data_tag_needs_no_namespace_at_all(self):
        """The rooting question is gone with the type-object tag.

        It used to matter which namespace the tag was reached through -- never
        a bare ``tuple`` (a capture), never ``builtins`` (rebindable), never
        ``__builtins__`` (a dict).  A reserved-atom tag is a literal, so there
        is no name to root and an EMPTY globals dict produces the same pattern
        an injected one did."""
        from clausal.logic.cells import make_tuple_cell
        from clausal.logic.compiler.head_match import head_to_match_pattern

        got = _unparse_pattern(head_to_match_pattern(
            make_tuple_cell(1, 2), {}, [], [], None, globals_={}))
        assert got == "case ['()', _ncap0, _ncap1]:"

    def test_the_tag_no_longer_degrades_without_a_namespace(self):
        """INVERTED: the failure this guarded cannot occur any more.

        A compilation path that did not inject ``$cells`` had to throw the
        pattern away, because emitting it would ``NameError`` at MATCH time --
        so a non-ground tuple-data cell fell back to ``case _:`` and lost its
        indexing. A literal tag resolves nothing at match time, so the same
        call with an EMPTY globals dict now keeps its pattern."""
        from clausal.logic.cells import make_tuple_cell
        from clausal.logic.compiler.head_match import head_to_match_pattern

        sink = []
        got = _unparse_pattern(head_to_match_pattern(
            make_tuple_cell(1, Var()), {}, [], sink, None, globals_={}))
        assert got != "case _:", "the tag still degrades without $cells"
        assert got.startswith("case ['()', "), got


class TestCellHeadGuardLeaks:
    """Fix round 1, finding 1: a discarded cell pattern must discard its
    guards with it.

    ``head_to_match_pattern``'s slot recursion appends to the ``list_guards``
    sink as a side effect.  The live-cell branch used to recurse BEFORE
    testing the tag, so when the tag test failed the pattern was thrown away
    and the guards were not -- the compiled arm then ran a guard against a
    capture name no pattern binds.  These drive the two shapes end to end;
    the sink-level assertions live on the two degradation tests above.
    """

    def _module(self, arg):
        from clausal.logic.database import Clause, Database, Module
        from tests.predicate_api_support import term_ctor
        from clausal.logic.compiler import predicate as predicate_mod

        Q = term_ctor("gg", ("S", "K"))
        db = Database()
        db.assertz(Clause(head=Q(S=arg, K="yes"), body=[]))
        db.assertz(Clause(head=Q(S=Var(), K="catchall"), body=[]))
        predicate_mod.compile_predicate_trampoline(
            "gg", 2, db.clauses_for("gg", 2), db)
        m = Module("_tt_guard_leak")
        m.db = db
        return m

    def _ask(self, m, probe):
        K = Var()
        return [deref(K) for _t in call("gg", probe, K, module=m)]

    def test_an_unbound_var_functor_cell_head_arg_does_not_crash(self):
        """`NameError: name '_ncap1' is not defined` before the fix."""
        m = self._module((Var(), 1, 2))
        # A var-functor cell decides nothing statically, so the clause is a
        # wildcard and fires -- the same answer a var-functor Compound gets
        # (A01-D004).  What matters here is that it ANSWERS.
        assert self._ask(m, 42) == ["yes", "catchall"]
        assert self._ask(m, ("pt", 1, 2)) == ["yes", "catchall"]

    def test_a_bound_var_functor_cell_head_arg_does_not_crash(self):
        """The T3-to-T5 window shape the pre-flight scan predicted would
        reach the capture-and-unify guard.  It does -- and before the fix it
        crashed there, because the leaked scalar guards ran right after the
        headlit guard passed, so only a MATCHING caller reached them.

        WINDOW CLOSED (P3-2 Task 5, §1b): this test's END-TO-END ANSWER is
        UNCHANGED by Task 5 -- ``head_to_match_pattern`` already read slot 0
        RAW (never dereferenced), so a bound-Var-functor cell already fell
        to this same opaque-literal capture-and-unify guard pre-Task-5. What
        WAS a "window" is that ``is_cell``/the funnel accessors disagreed
        with the compiler here: pre-Task-5 they answered True (after a
        deref) for this exact tuple, even though the compiler could never
        structurally decide it. Task 5 retires the Var-functor cell outright
        -- ``is_cell`` now also reads slot 0 raw, so it answers False here
        too, closing the window: EVERY recognition site (compiler and
        funnel alike) now agrees this shape was never a cell. The runtime
        answer below is the same answer it was before -- what changed is
        that it is no longer an accident of two disagreeing definitions.
        """
        from clausal.logic.cells import is_cell
        from clausal.logic.variables import Trail, unify

        bound = Var()
        unify(bound, "pt", Trail())
        assert is_cell((bound, 1, 2)) is False  # closes the T3-to-T5 window
        m = self._module((bound, 1, 2))
        assert self._ask(m, ("pt", 1, 2)) == ["yes", "catchall"]
        assert self._ask(m, 42) == ["catchall"]


class TestCellHeadArgOpaqueSlots:
    """Fix round 1, finding 2: the head-walker and the head-pattern branch
    have to agree about what a cell IS.

    ``_collect_globals_info._walk_head`` treated a ground cell as a LEAF and
    injected one ``$headlit_<id(whole cell)>``; the live-cell branch matches
    structurally and asks for ``$headlit_<id(inner value)>`` per opaque slot.
    Nothing injected those, so the arm raised ``NameError`` on its first
    caller -- while the ``Compound`` twin, which the walker has always
    recursed into, answered correctly.  That asymmetry is the bug, and the
    parity assertion below is the test for it.
    """

    #: One representative per opaque-head-literal class the walker can meet
    #: inside a cell slot.  ``nested cell`` is the recursive case.
    def _opaque_values(self):
        import datetime
        from decimal import Decimal

        return {
            "date": datetime.date(2020, 1, 1),
            "Decimal": Decimal("1.25"),
            "frozenset": frozenset({1, 2}),
            "nested cell": ("inner", datetime.date(2021, 2, 3)),
        }

    def _module(self, functor, arg):
        from clausal.logic.database import Clause, Database, Module
        from tests.predicate_api_support import term_ctor
        from clausal.logic.compiler import predicate as predicate_mod

        Q = term_ctor(functor, ("S", "K"))
        db = Database()
        db.assertz(Clause(head=Q(S=arg, K=mint("yes")), body=[]))
        db.assertz(Clause(head=Q(S=Var(), K=mint("catchall")), body=[]))
        predicate_mod.compile_predicate_trampoline(
            functor, 2, db.clauses_for(functor, 2), db)
        m = Module("_tt_opaque_slot")
        m.db = db
        return m

    def _ask(self, m, functor, probe):
        K = Var()
        return [deref(K) for _t in call(functor, probe, K, module=m)]

    @pytest.mark.parametrize("kind", ["date", "Decimal", "frozenset",
                                      "nested cell"])
    def test_an_opaque_value_in_a_cell_slot_answers_like_its_compound_twin(
            self, kind):
        from clausal.terms import Compound

        value = self._opaque_values()[kind]
        cell_mod = self._module("oc", ("pt", 1, value))
        comp_mod = self._module("od", Compound("pt", (1, value)))

        assert self._ask(cell_mod, "oc", ("pt", 1, value)) == \
            self._ask(comp_mod, "od", Compound("pt", (1, value))) == \
            [mint("yes"), mint("catchall")]
        assert self._ask(cell_mod, "oc", 42) == \
            self._ask(comp_mod, "od", 42) == [mint("catchall")]
        # ... and a DIFFERENT value in the slot is rejected, so the guard is
        # really testing the value rather than accepting anything.
        assert self._ask(cell_mod, "oc", ("pt", 1, "other")) == [mint("catchall")]

    def test_the_clausal_assertz_repro(self):
        """The reviewer's repro, from source rather than from the Python API:
        ``assertz`` of a fact whose cell head arg carries a date.

        The fixture's ``D is date(2020, 1, 1)`` binds the TERM since the
        2026-09-15 ruling, so the query passes the same term. A date is no
        longer the OPAQUE case this class is named for -- its siblings keep
        that coverage with a plain ``"other"`` -- but the head-arg shape being
        exercised, a value nested inside a cell, is unchanged.
        """
        mod = _load_inline("_tt_opaque_assertz", _OPAQUE_ASSERTZ_SRC)
        lm = mod.__dict__["$module"]
        list(call("setup", module=lm))
        d = ("date", 2020, 1, 1)
        K = Var()
        assert [deref(K) for _t in call("q", ("pt", 1, d), K, module=lm)] \
            == [mint("yes"), mint("catchall")]
        K2 = Var()
        assert [deref(K2) for _t in call("q", 42, K2, module=lm)] == [mint("catchall")]
        # the nested-cell variant of the same shape
        K3 = Var()
        assert [deref(K3) for _t in
                call("n", ("pt", 1, ("pt", 2, d)), K3, module=lm)] \
            == [mint("yes"), mint("catchall")]

    def test_the_walker_records_a_cells_inner_literals(self):
        """Directly, at the seam that was inconsistent: the head walker must
        report a global for the value INSIDE the cell, not only for the cell.
        """
        import datetime

        from clausal.logic.compiler.globals_env import _collect_globals_info
        from clausal.logic.compiler.terms_to_ast import headlit_global_key
        from clausal.logic.database import Clause
        from tests.predicate_api_support import term_ctor

        d = datetime.date(2020, 1, 1)
        cell = ("pt", 1, d)          # keyed by id(), so hold the ONE object
        Q = term_ctor("ww", ("S", "K"))
        types, _thunks, _targets = _collect_globals_info(
            [Clause(head=Q(S=cell, K=mint("yes")), body=[])])
        assert headlit_global_key(d) in types, sorted(types)
        # The whole-cell entry stays too -- a TUPLE_TAG cell compiled without
        # $cells, and a bound-Var-functor cell, still reach the capture.
        assert headlit_global_key(cell) in types


class TestStructuralHeadValue:
    """``database._is_structural_head_value`` -- the hoist's admission test.

    A cell containing a Var is exactly the shape whose inner vars have to
    couple to the clause's body, which is the reason ``Compound`` is on the
    list.  Cells join it.
    """

    def test_a_cell_is_structural(self):
        from clausal.logic.database import _is_structural_head_value

        assert _is_structural_head_value(("pt", 1, Var()))
        assert _is_structural_head_value(("pt", 1, 2))

    def test_a_plain_data_tuple_is_not_structural(self):
        from clausal.logic.database import _is_structural_head_value

        assert not _is_structural_head_value((1, 2))

    def test_a_cell_nested_in_a_head_list_is_found(self):
        from clausal.logic.database import _contains_structural_head_value

        assert _contains_structural_head_value([("pt", 1, Var())])

    def test_the_hoist_moves_a_cell_head_arg_into_the_body(self):
        from clausal.logic.database import _normalize_structural_head_args
        from tests.predicate_api_support import term_ctor
        from clausal.terms import Unify

        from clausal.logic.cells import cell_args

        Q = term_ctor("qq", ("S", "K"))
        head, body = _normalize_structural_head_args(
            Q(S=("pt", 1, Var()), K="yes"), [True])
        # P2: the normalised head is a CELL, so S is read at the position
        # the class declares it, not as an attribute.
        assert is_var(deref(cell_args(head)[Q._fields.index("S")]))
        assert isinstance(body[0], Unify)
        assert body[0].right == ("pt", 1, body[0].right[2])


def _capture_bucket_functions(module_name: str, pred_name: str) -> dict:
    """Compile *pred_name* and return every emitted function by name."""
    import importlib
    from clausal.logic.compiler import predicate as predicate_mod

    module = importlib.import_module(module_name)
    out: dict = {}
    original = predicate_mod.functiondef_to_function

    def _spy(func_def, globals_=None, **kwargs):
        fn = original(func_def, globals_=globals_, **kwargs)
        out[func_def.name] = fn
        return fn

    predicate_mod.functiondef_to_function = _spy
    try:
        _recompile(module, pred_name)
    finally:
        predicate_mod.functiondef_to_function = original
    return out


def _drive_bucket(bucket_fn, *args) -> list:
    """Drive an index-BUCKET function directly and collect its answers.

    A bucket is compiled with ``emit_done=False`` -- its outer dispatch
    wrapper emits the terminal ``yield (parent, DONE)`` -- so it cannot be
    handed to ``_drive_trampoline`` unwrapped.  This supplies the missing
    final yield, nothing else.  The last argument is the answer Var.
    """
    from clausal.logic.solve import _drive_trampoline
    from clausal.logic.trampoline import DONE
    from clausal.logic.variables import Trail

    def _wrapped(this_generator, _proceed, _fail, _catcher, *rest):
        trail = rest[-1]
        yield from bucket_fn(this_generator, _proceed, _fail, _catcher, *rest)
        yield (_fail, DONE)
        del trail

    out_var = args[-1]
    return [deref(out_var) for _t in _drive_trampoline(_wrapped, Trail(), *args)]


def _load_head_compound_importer():
    """The imported-compound fixture pair (R5), loaded owner-first."""
    import os
    from clausal.import_hook import _load_module

    here = os.path.join(os.path.dirname(__file__), "fixtures")
    _load_module("tests.fixtures.head_compound_owner",
                 os.path.join(here, "head_compound_owner.clausal"))
    return _load_module("tests.fixtures.head_compound_importer",
                        os.path.join(here, "head_compound_importer.clausal"))


class TestNormalizer:
    """The representation normalizer the parity corpus imports.

    Its whole job is to make one assertion possible: that two runs produced
    the SAME TERM, without the assertion caring which representation carried
    it.  Still load-bearing after the flip -- it is what lets the recorded
    class-era answers stay the regression anchor for cell-era results.
    """

    def test_nesting_is_canonicalised_all_the_way_down(self):
        """P3-1 atom pivot (§1b): ``plain.nil`` is the interned str "nil",
        not a 0-arity class, so it canonicalises to itself -- no ("nil",)
        wrapping (phase3-decomposition-and-p31-atom-pivot Task 7 work item
        1)."""
        plain = _fixture(_PLAIN)
        assert normalize_term(("point", 3, ("point", 2, plain.nil))) \
            == ("point", 3, ("point", 2, mint("nil")))

    def test_different_functors_stay_different(self):
        assert (normalize_term(("point", 1, 2))
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
        assert normalize_term([1, "a", plain.nil]) == [1, "a", mint("nil")]
        assert normalize_term(42) == 42

    def test_normalize_answers_handles_binding_dicts_and_bare_terms(self):
        """P3-1 atom pivot (§1b): no ("nil",) wrapping -- see Task 7 work
        item 1."""
        plain = _fixture(_PLAIN)
        rows = [{"T": ("point", 1, plain.nil)},
                ("point", 1, plain.nil)]
        assert normalize_answers(rows) == [
            {"T": ("point", 1, mint("nil"))},
            ("point", 1, mint("nil")),
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
        assert mod.rec == mint("rec")
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
        from clausal.logic.predicate import resolve_predicate_row

        tagged = _fixture(_TAGGED)
        assert tagged.point == mint("point")                    # the premise ...
        kind_row = resolve_predicate_row(                  # ... both halves
            tagged.kind, arity=2, db=_logic_module(tagged).db)
        assert kind_row is not None and kind_row.clauses, tagged.kind
        term = self._source_compound_for("point", 2)
        with lowering_scope(tagged.__dict__):
            got = _unparse_pattern(head_to_match_pattern(
                term, {}, [], [], None,
                globals_={"__name__": tagged.__name__, "point": tagged.kind},
            ))
        # P2 re-casts the DISCRIMINATOR, and the new one is sharper.  Since
        # the head flip a source compound lowers to a cell whether its name
        # binds a data functor or a predicate, so data-vs-predicate no
        # longer separates the two resolutions.  The TAG does: ``globals_``
        # binds the written name ``point`` to the ``kind`` class, and the
        # pattern comes back tagged ``'kind'``.  Resolving in the open
        # compile scope -- where ``point`` is the data functor ``point`` --
        # could only have produced ``'point'``.  So this still pins exactly
        # what it always pinned, that the cell branch resolves a name in
        # ``globals_`` and not in the open scope, and it now reads the
        # answer off the pattern instead of off the class/cell split.
        assert got.startswith("case ['kind', "), got
        assert "'point'" not in got

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


class TestCellsAtTheBuiltinSurface:
    """Fix-round-1 regressions: builtins and writers that were blind to cells.

    Each of these asked a question about a term and answered differently for
    a cell than for the class term it replaced -- which is an ANSWER
    difference, not a representation one, and so forbidden by this phase's
    own invariant.  The class-twin half of each comparison went with W4a
    (2026-09-22): a PredicateMeta INSTANCE can no longer be minted at all,
    so the cell is the only shape left to ask about.
    """

    def _module(self):
        from clausal.logic.database import Module

        return Module("_tt_builtin_surface")

    def _nsol(self, goal, *args):
        return len(list(call(goal, *args, module=self._module())))

    def test_ground_1_sees_a_free_var_inside_a_cell(self):
        """``ground(pt(1, Y))`` with Y free said TRUE -- ``_is_ground`` had
        no tuple branch, so the cell fell through its "unknown shape ->
        ground" tail."""
        assert self._nsol("ground", ("pt", 1, 2)) == 1
        assert self._nsol("ground", ("pt", 1, Var())) == 0

    def test_ground_1_reaches_a_cell_nested_in_a_list(self):
        assert self._nsol("ground", [1, ("pt", Var())]) == 0

    def test_compound_1_answers_for_a_cell(self):
        """The one type check that did not route through the funnel."""
        assert self._nsol("compound", ("pt", 1, 2)) == 1
        # An atom and a 0-arity shape are still not compound.
        assert self._nsol("compound", mint("pt")) == 0
        # Task 15 item 2 (ISO alignment): the STRING ``"pt"`` is the list of
        # its characters, i.e. the ``'.'/2`` compound, so it IS compound --
        # a different question from whether the CELL of that name is.
        assert self._nsol("compound", chars("pt")) == 1

    def test_write_1_renders_the_term_not_the_tuple(self, capsys):
        """``write(pt(1, 2))`` printed ``('pt', 1, 2)``: ``io._format_term_iso``
        fell to ``str()``, which on a cell is the Python tuple repr."""
        list(call("write", ("pt", 1, 2), module=self._module()))
        assert capsys.readouterr().out == "pt(1,2)"

    def test_term_str_renders_a_nested_cell(self):
        from clausal.terms import term_str

        assert term_str(("pt", 1, ("q", 2))) == "pt(1, q(2))"
        # Tuple DATA and an unbound functor slot are NOT compounds: they keep
        # the ordinary tuple rendering rather than inventing a functor.
        assert term_str((1, 2)).startswith("(")


class TestCellWriterSurfaceFixRound(TestCellsAtTheBuiltinSurface):
    """P3-2 Task 7 fix-round additions: ``io._format_term_iso`` also gets a
    ``TUPLE_TAG`` branch and the deref-removal Task 5/Task 7 review ruled in
    (slot 0 read RAW, no ``deref`` -- a bound-Var-functor tuple is not a
    legal cell any more, see ``clausal/logic/cells.py``'s module docstring).
    Subclasses the builtin-surface fixture class for its ``_module``/
    ``_nsol`` helpers."""

    def test_write_1_renders_a_tuple_data_cell_as_a_plain_tuple(self, capsys):
        from clausal.logic.cells import TUPLE_TAG

        list(call("write", (TUPLE_TAG, 1, 2), module=self._module()))
        assert capsys.readouterr().out == "(1,2)"

    def test_write_1_does_not_treat_a_bound_var_functor_tuple_as_a_cell(self, capsys):
        """BEFORE this fix ``io._format_term_iso`` tested
        ``isinstance(deref(val[0]), str)``, so a tuple whose slot 0 was a
        Var bound to a str routed through ``term_str`` and printed as a
        compound.  AFTER: slot 0 read raw, so it keeps ordinary ``str()``
        rendering (the Python tuple repr, since a Var has no cell-shaped
        display of its own)."""
        v = Var()
        trail = Trail()
        assert unify(v, "pt", trail)
        list(call("write", (v, 1, 2), module=self._module()))
        out = capsys.readouterr().out
        assert "pt(1, 2)" not in out


class TestCallableAndTheTupleDataEdge:
    """``callable_/1`` (ISO ``callable``) — fix round 2.

    The second type check in ``type_checks.py`` found blind to cells, and the
    one my own sweep MISSED: the probe called it ``callable``, the ISO name,
    while it is REGISTERED as ``callable_``, so both halves of the comparison
    raised the same ``KeyError`` and compared equal.  Every probe in this
    class therefore asserts the predicate is registered first, and asserts the
    cell and its twin SIDE BY SIDE rather than against a hard-coded expected
    value — a divergence is the failure, whichever way it points.
    """

    def _module(self):
        from clausal.logic.database import Module

        return Module("_tt_callable_edge")

    def _nsol(self, goal, arg):
        from clausal.logic.builtins._registry import _BUILTINS, _DB_BUILTINS

        assert (goal, 1) in _BUILTINS or (goal, 1) in _DB_BUILTINS, (
            f"{goal}/1 is not registered — a probe against it would compare "
            f"two identical KeyErrors and call that agreement"
        )
        return len(list(call(goal, arg, module=self._module())))

    def test_a_str_functor_cell_is_callable_like_its_compound_twin(self):
        from clausal.terms import Compound

        assert self._nsol("callable_", ("pt", 1, 2)) == 1
        assert (self._nsol("callable_", ("pt", 1, 2))
                == self._nsol("callable_", Compound("pt", (1, 2))))

    def test_a_var_functor_tuple_is_no_longer_callable_unlike_its_compound_twin(self):
        """INVERTED (P3-2 Task 5, §1b): the bridge's higher-order
        Var-functor CELL is DEPRECATED — a slot-0-Var tuple is no longer
        cell-shaped at all (``_is_compound`` no longer counts it), so it is
        not ``callable_``. ``Compound`` is a wholly separate representation
        untouched by this narrowing — a ``Compound`` with a Var functor is
        still compound/callable via its own (unrelated) branch, same as
        before. The two representations DIVERGE here now, which is the
        point: §1b routes higher-order metaprogramming over CELLS through
        ``functor/3``/``=../2``/``call/N`` instead, not through a
        Var-functor cell reaching this callable check.

        (Formerly ``test_a_var_functor_cell_is_callable_like_its_compound_
        twin``, asserting both answered 1.)
        """
        from clausal.terms import Compound

        v = Var()
        assert self._nsol("callable_", (v, 1, 2)) == 0
        assert self._nsol("callable_", Compound(v, (1, 2))) == 1

    def test_a_zero_arity_cell_is_callable_like_its_compound_twin(self):
        """``callable_`` yields for a 0-arity Compound, so its cell branch
        carries no arity gate — unlike ``compound/1``'s, whose Compound branch
        does gate.  Each cell branch mirrors the branch it is the twin OF."""
        from clausal.terms import Compound

        assert (self._nsol("callable_", ("f",))
                == self._nsol("callable_", Compound("f", ())) == 1)

    def test_tuple_data_matches_a_plain_tuple_not_a_tagged_compound(self):
        """The tuple-DATA tag's analog is a plain Python tuple, and both
        answers are pinned side by side.

        ``(tuple, 1, 2)`` means "the Python tuple (1, 2) as term data" —
        ``cells.py`` is explicit that it is NOT a compound — so its class-world
        analog is ``(1, 2)``, not ``Compound(TUPLE_TAG, (1, 2))``, which
        nothing constructs.  Under the plain-tuple analog every predicate
        agrees; under the tagged-Compound one, three disagree — INCLUDING
        ``ground/1``, whose cell branch was reviewed and accepted as correct.
        The ORIGINAL evidence was a ground/1 divergence, which came from the
        tag being a type object -- ``Compound`` treats any non-str functor as
        non-ground (``_is_ground_py`` tests ``isinstance(term.functor, str)``),
        predating cells entirely. Under the reserved-atom tag that divergence
        is gone and the point is made more directly: ``Compound('()', (1, 2))``
        is the compound ``'()'/2``, and tuple DATA is not a compound at all.
        """
        from clausal.logic.cells import TUPLE_TAG
        from clausal.terms import Compound

        data = (TUPLE_TAG, 1, 2)
        plain = (1, 2)
        tagged_compound = Compound(TUPLE_TAG, (1, 2))

        # The real analog: tuple data behaves as the tuple it denotes.
        for name in ("callable_", "compound", "ground"):
            assert self._nsol(name, data) == self._nsol(name, plain), name

        # The tagged Compound, pinned side by side so the divergence is on
        # record rather than silent -- and so a future change to either side
        # shows up here.
        assert self._nsol("callable_", tagged_compound) == 1
        assert self._nsol("compound", tagged_compound) == 1
        # MOVED when the tag became the reserved atom ``'()'``: the ground/1
        # quirk used to fall on ``Compound(TUPLE_TAG, ...)`` too, because a
        # type object is not a str and ``_is_ground_py``'s Compound branch
        # tests ``isinstance(term.functor, str)``. With a str tag the tagged
        # Compound is now ordinarily ground -- it is simply the compound
        # ``'()'/2``, which is precisely what tuple DATA is not. The quirk
        # itself is unchanged and still lives on any non-str functor.
        assert self._nsol("ground", tagged_compound) == 1
        assert self._nsol("ground", Compound(123, (1, 2))) == 0  # the quirk

    def test_compound_1_still_gates_on_arity_and_diverges_at_zero(self):
        """A pre-existing wart, pinned rather than copied.

        ``compound(Compound("f", ()))`` answers TRUE — not through the
        Compound branch (which requires ``len(args) > 0``) but through the
        ``is_term_instance`` branch, since ``Compound`` is itself a dataclass
        with two fields.  ISO says a 0-arity term is an atom, not a compound,
        so the cell branch deliberately does NOT reproduce that: it gates on
        arity, as its own Compound branch means to.  Recorded here so the
        difference is a decision on record, not an oversight.
        """
        from clausal.terms import Compound

        assert self._nsol("compound", ("f",)) == 0
        assert self._nsol("compound", Compound("f", ())) == 1
