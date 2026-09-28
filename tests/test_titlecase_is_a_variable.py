"""TitleCase is a logic VARIABLE in term position, still an error as a functor.

The ISO reading: a capital-initial identifier standing where a value goes is a
logic variable.  ``p(Foo) <- (bar(Foo))`` loads and ``Foo`` binds, exactly as
``P``/``FOO``/``_foo`` always did.

The asymmetry, deliberately kept: a capital-initial identifier in FUNCTOR
position -- a clause head's functor, or a call in a body -- is still a
load-time ``SyntaxError`` carrying the ``++Name`` remedy.  A variable in
functor position is not ``call/N`` in this language, it is the unit-annotation
sugar, so letting the functor case through would turn a bare Python class in a
clause body from a clear load error into a units expression that dies much
later with a message about SI prefixes.  See the comment on
``_lint_titlecase``'s walk.
"""
import ast
import textwrap
import warnings

import pytest

from clausal.import_hook import _load_module
from clausal.logic.atoms import spelling as atom_spelling
from clausal.logic.cells import chars
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.templating.term_rewriting import ClausalSingletonWarning


def _load(tmp_path, name, text):
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(text).lstrip())
    return _load_module(f"ttiav_{name}", str(path))


def _module(mod):
    return mod.__dict__["$module"]


def _answers(mod, functor, arity=1):
    """Every solution's argument values, snapshotted INSIDE the iteration.

    A binding is undone when the solver backtracks past it, so reading the
    ``Var`` after the generator is exhausted always shows it unbound -- the
    value has to be copied out while the solution is current.
    """
    args = [Var() for _ in range(arity)]
    out = []
    for _ in call(functor, *args, module=_module(mod)):
        out.append(tuple(deref(a) for a in args))
    return out


# ── TERM position: a capital-initial name is a logic variable ───────────────

def test_titlecase_in_term_position_loads_and_binds(tmp_path):
    """The point of the change: not merely "it loads" -- ``Foo`` must be a
    VARIABLE, so the solution carries the fact's argument back out."""
    mod = _load(tmp_path, "bind", """
        -module(ttiav_bind, [p(X)])
        bar(1),
        p(Foo) <- (bar(Foo))
    """)
    assert _answers(mod, "p") == [(1,)]


def test_titlecase_and_allcaps_are_the_same_variable_when_spelled_alike(tmp_path):
    """Two occurrences of one TitleCase name in a clause are one variable --
    the join, which is what distinguishes a variable from a fresh ``_``."""
    mod = _load(tmp_path, "join", """
        -module(ttiav_join, [q(X)])
        edge(1, 1),
        edge(1, 2),
        q(N) <- (edge(Same, Same), N == Same)
    """)
    assert _answers(mod, "q") == [(1,)]


def test_titlecase_singleton_gets_the_singleton_warning(tmp_path):
    """A TitleCase name is a variable like any other, so the singleton lint
    reaches it -- the lint is keyed on the variable classifier, so this is the
    check that the classifier really did widen (rather than the name merely
    slipping past the TitleCase lint)."""
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        _load(tmp_path, "single", """
            -module(ttiav_single, [p(X, Y)])
            p(X, Once) <- (X == 1)
        """)
    msgs = [str(w.message) for w in rec
            if issubclass(w.category, ClausalSingletonWarning)]
    assert any("Once" in m for m in msgs), msgs


# ── FUNCTOR position: still a load-time error ──────────────────────────────

def test_titlecase_clause_head_functor_is_still_a_load_error(tmp_path):
    with pytest.raises(SyntaxError) as exc_info:
        _load(tmp_path, "head", """
            bar(1),
            Foo(X) <- (bar(X))
        """)
    message = str(exc_info.value)
    assert "Foo" in message
    assert "TitleCase" in message


def test_python_class_called_in_a_body_is_still_a_load_error(tmp_path):
    """The shape the functor rule exists for.  Were ``Fraction`` read as a
    variable here it would become the unit-annotation sugar and fail at
    RUNTIME complaining about SI prefixes; it must stay a load error that
    names the ``++`` escape."""
    with pytest.raises(SyntaxError) as exc_info:
        _load(tmp_path, "pyclass", """
            bar(1),
            p(X) <- (bar(Fraction(1, 3)))
        """)
    message = str(exc_info.value)
    assert "Fraction" in message
    assert "++Fraction" in message


def test_the_functor_error_survives_a_titlecase_variable_in_the_same_clause(tmp_path):
    """Narrowing the lint to functor position must not narrow it to "the first
    name in the clause": the head argument ``Arg`` is a variable now, and the
    body call ``Helper`` must still be refused."""
    with pytest.raises(SyntaxError) as exc_info:
        _load(tmp_path, "mixed", """
            p(Arg) <- (Helper(Arg))
        """)
    assert "Helper" in str(exc_info.value)


# ── The shapes that must not have moved ────────────────────────────────────

def test_all_caps_term_position_unchanged(tmp_path):
    mod = _load(tmp_path, "allcaps", """
        -module(ttiav_allcaps, [p(X)])
        bar(1),
        p(FOO) <- (bar(FOO))
    """)
    assert _answers(mod, "p") == [(1,)]


def test_leading_underscore_term_position_unchanged(tmp_path):
    mod = _load(tmp_path, "under", """
        -module(ttiav_under, [p(X)])
        bar(1),
        p(_foo) <- (bar(_foo))
    """)
    assert _answers(mod, "p") == [(1,)]


def test_lowercase_name_in_term_position_is_an_atom_not_a_variable(tmp_path):
    """The ordinary case, asserted on a LOWERCASE name.

    This used to spell its clause ``p(Y) <- (bar(Y))`` -- an ALL_CAPS
    variable -- so it duplicated the test above and would still have passed
    if the rule had started reading lowercase names as variables, which is
    the one thing its docstring claimed to check.  ``red`` here is an atom:
    the fact matches only the atom, and the answer comes back as the atom
    rather than as a fresh binding."""
    mod = _load(tmp_path, "lower", """
        -module(ttiav_lower, [p(X), red])
        bar(red),
        p(X) <- (bar(X))
    """)
    [(answer,)] = _answers(mod, "p")
    assert answer == "red", answer


# ── Python-by-definition contexts keep the Python reading ──────────────────

def test_fstring_interpolation_of_a_python_class_still_evaluates(tmp_path):
    """An f-string body is Python, exactly like a ``++`` operand.

    Both compile to a lambda whose PARAMETERS are the clause variables the
    body mentions, so classifying a capital-initial Python name there as a
    variable binds a fresh ``Var`` over the module global and the
    interpolation dies at query time with ``'AttVar' object is not
    callable``.  This is WORKING CODE, not a diagnostic: it evaluates on
    main, and `_lint_titlecase` returns early on ``JoinedStr``, so there is
    no load-time complaint to fall back on either."""
    mod = _load(tmp_path, "fstr", """
        from fractions import Fraction
        -module(ttiav_fstr, [p(S)])
        p(S) <- (S is f"{Fraction(1, 3)}")
    """)
    assert _answers(mod, "p") == [(chars("1/3"),)]  # an f-string is a string (R2)


def test_plus_plus_operand_of_a_python_class_still_evaluates(tmp_path):
    """The ``++`` TWIN of the test above, and the negative control for the
    OTHER skip.

    Two different skips keep a thunk body's names out of the clause-variable
    evidence: ``_clause_variable_names`` refuses ``JoinedStr`` and it refuses
    an adjacent ``++``.  The f-string test exercises the first only.  Delete
    the ``++`` arm and ``Fraction`` is collected as a clause variable, which
    subtracts it from the Python-scope exclusions, which captures it as an
    unbound lambda parameter -- and ``++Fraction(1, 3)`` dies at QUERY time
    with ``'AttVar' object is not callable``, with no load diagnostic
    (``_lint_titlecase`` does not read a ``++`` subtree either).

    Asserted through ``str`` so the answer is the same ``"1/3"`` the
    f-string twin asserts, which is what makes the pair readable as a pair.
    """
    mod = _load(tmp_path, "ppclass", """
        from fractions import Fraction
        -module(ttiav_ppclass, [p(S)])
        p(S) <- (S is ++str(Fraction(1, 3)))
    """)
    # (a ``++`` result stays the Python str -- an atom; the f-string twin is
    # a string since ruling R2, so the pair now differs in exactly that)
    assert _answers(mod, "p") == [("1/3",)]


def test_fstring_still_captures_an_ordinary_clause_variable(tmp_path):
    """The other half: excluding TitleCase from the capture must not stop an
    ordinary variable being captured."""
    mod = _load(tmp_path, "fstrvar", """
        -double_quotes(atom)
        -module(ttiav_fstrvar, [p(N, S)])
        p(N, S) <- (S is f"n={N}")
    """)
    out = []
    for _ in call("p", 7, (v := Var()), module=_module(mod)):
        out.append(deref(v))
    assert out == ["n=7"]


# ── Zero-arity heads are functor positions too ────────────────────────────

def test_zero_arity_rule_head_is_still_a_load_error(tmp_path):
    """``Foo <- (...)`` defines a predicate named ``Foo``: a functor
    position, and a bare ``Name`` rather than a ``Call``, so the walk needs
    telling.  Without it the clause loaded and registered the predicate with
    no lint at all -- the functor invariant silently escaped."""
    with pytest.raises(SyntaxError) as exc_info:
        _load(tmp_path, "zerorule", """
            bar(1),
            Foo <- (bar(X))
        """)
    assert "Foo" in str(exc_info.value)
    assert "TitleCase" in str(exc_info.value)


def test_zero_arity_dcg_head_is_still_a_load_error(tmp_path):
    with pytest.raises(SyntaxError) as exc_info:
        _load(tmp_path, "zerodcg", """
            bar(1),
            Foo >> (bar(X))
        """)
    assert "Foo" in str(exc_info.value)
    assert "TitleCase" in str(exc_info.value)


def test_lowercase_zero_arity_rule_head_still_loads(tmp_path):
    """The control: narrowing must not refuse the ordinary spelling."""
    mod = _load(tmp_path, "zerook", """
        -module(ttiav_zerook, [foo()])
        bar(1),
        foo <- (bar(1))
    """)
    assert len(list(call("foo", module=_module(mod)))) == 1


# ── A name the file's HOSTED PYTHON binds is still a term-position variable ─

def test_hosted_python_binding_does_not_carve_a_name_out_of_the_rule(
        tmp_path):
    """The line this change draws, pinned so it cannot move unnoticed.

    A CLAUSAL binding -- an ``-import_from`` list -- carves its names out of
    the variable rule, because that directive binds into the Clausal
    namespace and the units deprecation window depends on it.  A HOSTED
    PYTHON binding (``from fractions import Fraction`` at the top of the
    file) does not: Clausal code reaches Python through ``++``, so
    ``P is Fraction`` reads ``Fraction`` as an ordinary logic variable.

    It used to be a load error naming ``++Fraction``.  It is now a fresh
    unbound variable, which is the same shape the operator ruled acceptable
    for ``catch(G, ValueError, R)``: a user error with the correct spelling
    (``++Fraction``) one character away.  Pinned, not special-cased."""
    mod = _load(tmp_path, "hosted", """
        from fractions import Fraction
        -module(ttiav_hosted, [q(P)])
        q(P) <- (P is Fraction)
    """)
    [(answer,)] = _answers(mod, "q")
    assert isinstance(answer, Var) or "Var" in type(answer).__name__, answer
    # And the ``++`` spelling -- the one the lint names -- does work.
    mod2 = _load(tmp_path, "hosted_ok", """
        from fractions import Fraction
        -module(ttiav_hosted_ok, [q(P)])
        q(P) <- (P is ++Fraction(1, 3))
    """)
    from fractions import Fraction as _F
    assert _answers(mod2, "q") == [(_F(1, 3),)]


# ── A genuine TitleCase CLAUSE VARIABLE works in ++ and f-strings ──────────
#
# The two spellings of one clause must give the same answers.  Excluding
# every capital-initial name from thunk capture (rather than only the ones
# the file's hosted Python binds) left the lambda with no parameter for the
# variable, so the name resolved in module globals instead: the f-string
# formatted an unbound variable's repr -- a WRONG VALUE, silently -- and the
# ``++`` arithmetic raised on an AttVar.  Neither is reachable by the lint,
# which returns early on both ``JoinedStr`` and ``++``.

def _pair(tmp_path, tag, body_titlecase, body_allcaps):
    """Load the same clause under both spellings and return both answers."""
    out = []
    for suffix, body in (("tc", body_titlecase), ("uc", body_allcaps)):
        mod = _load(tmp_path, f"{tag}_{suffix}", f"""
            -module(ttiav_{tag}_{suffix}, [p(S)])
            bar(7),
            p(S) <- ({body})
        """)
        out.append(_answers(mod, "p"))
    return out


def test_fstring_captures_a_titlecase_clause_variable(tmp_path):
    titlecase, allcaps = _pair(
        tmp_path, "fscap",
        'bar(Total), S is f"{Total}"',
        'bar(TOTAL), S is f"{TOTAL}"')
    assert titlecase == allcaps == [(chars("7"),)]  # an f-string is a string (R2)


def test_python_escape_captures_a_titlecase_clause_variable(tmp_path):
    titlecase, allcaps = _pair(
        tmp_path, "escap",
        "bar(Total), S is ++(Total + 1)",
        "bar(TOTAL), S is ++(TOTAL + 1)")
    assert titlecase == allcaps == [(8,)]


def test_a_captured_titlecase_variable_is_not_reported_as_a_singleton(
        tmp_path):
    """``_build_py_thunk_ast`` bumps the occurrence counter only for names it
    CAPTURES, so failing to capture also produced a bogus singleton warning
    for a variable used twice."""
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        _load(tmp_path, "nosingle", """
            -double_quotes(atom)
            -module(ttiav_nosingle, [p(S)])
            bar(7),
            p(S) <- (bar(Total), S is f"{Total}")
        """)
    named = [str(w.message) for w in rec
             if issubclass(w.category, ClausalSingletonWarning)
             and "`Total`" in str(w.message)]
    assert named == [], named


def test_hosted_python_name_is_still_excluded_from_capture(tmp_path):
    """The round-2 fix must survive: a name the file's hosted Python BINDS is
    still resolved as Python inside a thunk, not captured as a variable."""
    mod = _load(tmp_path, "stillpy", """
        from fractions import Fraction
        -module(ttiav_stillpy, [p(S)])
        p(S) <- (S is f"{Fraction(1, 3)}")
    """)
    assert _answers(mod, "p") == [(chars("1/3"),)]  # an f-string is a string (R2)


def test_hosted_python_name_and_clause_variable_in_one_thunk(tmp_path):
    """Both rules at once, which is the case a per-name test cannot reach:
    ``Fraction`` resolves as Python and ``Total`` is captured, in the SAME
    interpolation."""
    mod = _load(tmp_path, "mixed_thunk", """
        from fractions import Fraction
        -module(ttiav_mixed_thunk, [p(S)])
        bar(3),
        p(S) <- (bar(Total), S is f"{Fraction(1, Total)}")
    """)
    assert _answers(mod, "p") == [(chars("1/3"),)]  # an f-string is a string (R2)


# ── The seam must bind exactly what visit_Name reads as a variable ─────────

def test_seam_does_not_bind_an_exempt_or_imported_name_as_a_variable():
    """``--f(Undefined)`` must not emit ``(Undefined := $Var())``.

    The seam's ``fresh`` list drives ``_var_bind``, which writes those names
    into the HOST PYTHON scope.  Collecting a name ``visit_Name`` refuses to
    read as a variable clobbers the injected binding for the rest of that
    scope while the term side compiles it as the bound name -- the two sides
    of one seam disagreeing about the same spelling.
    """
    import ast as _ast
    from clausal.templating.term_rewriting import _collect_logic_var_names
    clause_ctx = frozenset({"Undefined", "Metre"})
    node = _ast.parse("f(Undefined, Metre, Total, TOTAL)", mode="eval").body
    assert _collect_logic_var_names(node, clause_ctx) == ["Total", "TOTAL"]


# ── Two shapes that must not diverge from their lowercase twins ────────────

def test_qualified_name_on_an_exempt_base_is_not_dict_sugar(tmp_path):
    """``Undefined.k`` is a qualified name, not a dict read.

    ``is_dict_attr_access`` asks whether the BASE is a logic variable.  On
    the lexical rule every capital-initial base qualifies, including the
    names ``visit_Name`` refuses to read as variables, so ``Undefined.k``
    flipped from a qualified reference to dict-subscript sugar and started
    demanding that ``k`` be a declared atom."""
    mod = _load(tmp_path, "qualbase", """
        -module(ttiav_qualbase, [p(X)])
        p(X) <- (X is Undefined.k)
    """)
    assert mod is not None


def test_comma_less_bare_titlecase_statement_matches_its_lowercase_twin(
        tmp_path, monkeypatch):
    """``Foo`` with no trailing comma, for a name already seen as a functor.

    The trailing-comma arm got a TitleCase disjunct so the lint could still
    refuse it; the comma-LESS arm did not, so the statement fell through to
    hosted Python -- the exact silent-fallthrough the sibling fix cites as
    its reason.  With the lint demoted, both spellings must reach the same
    arity-conflict diagnosis."""
    from clausal.templating import term_rewriting
    monkeypatch.setattr(
        term_rewriting, "TITLECASE_IDENTIFIER_SEVERITY", "warn")
    with pytest.raises(SyntaxError, match="conflicts with"):
        _load(tmp_path, "commaless_lc", """
            -module(ttiav_commaless_lc, [])
            foo(1),
            foo
        """)
    with pytest.raises(SyntaxError, match="conflicts with"):
        _load(tmp_path, "commaless_tc", """
            -module(ttiav_commaless_tc, [])
            Foo(1),
            Foo
        """)


def test_a_thunk_inside_a_lambda_body_uses_the_same_exclusions(tmp_path):
    """A sub-transformer must inherit the hosted-Python binding set.

    A lambda body gets its own ``TermTransformer``; it already inherited
    ``_import_remap`` and now inherits the hosted-Python names too, because a
    ``++`` or f-string inside it resolves free names in the SAME module
    namespace.  Without that, one spelling would mean two different things
    depending only on whether it sits inside a lambda.

    (Interpolating the lambda's own PARAMETER is a separate, pre-existing
    limitation -- ``f"{_x}"`` in a lambda body raises ``NameError`` on main
    too -- so this stays to the part the exclusion set decides.)
    """
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        _load(tmp_path, "lamthunk", """
            from fractions import Fraction
            -module(ttiav_lamthunk, [p(L)])
            p(L) <- (L is (_x <- (f"{Fraction(1, 3)}")))
        """)
    # Captured names get an occurrence bump, so capturing ``Fraction`` here
    # would have silently suppressed nothing and bound an unbound Var into
    # the interpolation.  It must not be treated as a variable at all.
    assert not [w for w in rec
                if issubclass(w.category, ClausalSingletonWarning)
                and "`Fraction`" in str(w.message)]


# ── A clause variable wins over a same-spelled module-namespace class ──────
#
# The Python-scope exclusion holds every TitleCase name in the module
# namespace -- all of ``pythonic_ast.nodes.__all__`` (``Node``, ``Branch``,
# ``Match``, ``Call``, ``Return``, ``Slice`` …) plus the TitleCase builtins.
# Excluding by SPELLING alone means an ordinary clause variable that happens
# to share one of those spellings is not captured, and the thunk formats the
# CLASS.  Silently, because the lint returns early on both ``JoinedStr`` and
# ``++``.  The names are short, ordinary and domain-plausible, so the
# collision is not exotic.

def test_a_clause_variable_named_like_an_ast_node_is_still_captured(tmp_path):
    """``Node`` is bound by ``tree/1`` here, so the f-string must format the
    BINDING (7), not ``<class '...nodes.Node'>``."""
    mod = _load(tmp_path, "nodevar", """
        -double_quotes(atom)
        -module(ttiav_nodevar, [p(S)])
        tree(7),
        p(S) <- (tree(Node), S is f"{Node}")
    """)
    # -double_quotes(atom): an f-string follows the module's mode (R2)
    assert _answers(mod, "p") == [("7",)]


def test_a_clause_variable_named_like_a_builtin_is_still_captured(tmp_path):
    mod = _load(tmp_path, "matchvar", """
        -module(ttiav_matchvar, [p(S)])
        tree(7),
        p(S) <- (tree(Match), S is ++(Match + 1))
    """)
    assert _answers(mod, "p") == [(8,)]


def test_the_namespace_name_still_wins_when_the_clause_never_binds_it(
        tmp_path):
    """The other side of the rule, and the reason it is "unless the clause
    binds it" rather than "never exclude": a name appearing ONLY inside the
    thunk is the module-namespace class, which is what ``++Name`` is for."""
    mod = _load(tmp_path, "nsonly", """
        from fractions import Fraction
        -module(ttiav_nsonly, [p(S)])
        p(S) <- (S is f"{Fraction(1, 3)}")
    """)
    assert _answers(mod, "p") == [(chars("1/3"),)]  # an f-string is a string (R2)


def test_capture_does_not_depend_on_where_the_thunk_sits_in_the_clause(
        tmp_path):
    """The CAPTURE decision is made over the whole clause, not from what the
    walk has seen so far -- otherwise one clause would mean two different
    things depending on goal order.

    Here the thunk runs BEFORE the goal that binds the name, so an unbound
    variable is the right answer; what matters is that both spellings give
    the SAME right answer.  Were the namespace collision still deciding it,
    the TitleCase arm would render the class instead -- which is why this
    asserts what the two arms produce rather than merely that they load.
    """
    rendered = []
    for spelling in ("Node", "NODE"):
        mod = _load(tmp_path, f"orderindep_{spelling}", f"""
            -double_quotes(atom)
            -module(ttiav_orderindep_{spelling}, [p(S)])
            tree(7),
            p(S) <- (S is f"{{{spelling}}}", tree({spelling}))
        """)
        [(answer,)] = _answers(mod, "p")
        rendered.append(answer)
    # An unbound variable renders as ``_N``; the class would render as
    # ``<class '...'>``.  Both arms must be the former.
    assert all(atom_spelling(r).startswith("_") for r in rendered), rendered
    assert not any("class" in atom_spelling(r) for r in rendered), rendered


def test_a_captured_namespace_named_variable_is_not_a_singleton(tmp_path):
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        _load(tmp_path, "nodesingle", """
            -double_quotes(atom)
            -module(ttiav_nodesingle, [p(S)])
            tree(7),
            p(S) <- (tree(Node), S is f"{Node}")
        """)
    assert not [w for w in rec
                if issubclass(w.category, ClausalSingletonWarning)
                and "`Node`" in str(w.message)]


# ── The arrow-lambda reading of a bare TitleCase head ─────────────────────

def test_a_bare_titlecase_arrow_head_inside_a_term_is_a_lambda(tmp_path):
    """``Foo <- Body`` in TERM position is an arrow LAMBDA, not a clause.

    ``_extract_arrow_lambda_params`` asks whether the head is a list of logic
    variables, so a bare capital-initial head now matches and lowers to a
    closure.  That mirrors what ``FOO <- Body`` has always done, and it is
    the consistent reading -- a capital initial in term position is a
    variable, and a lambda head is a parameter list.  Pinned so the reading
    is deliberate rather than incidental: the shape LOADS, its head lowers
    to a closure, and ``assertz`` then refuses that closure at query time --
    loudly, naming it -- exactly as its ALL_CAPS twin does.
    """
    outcomes = []
    for spelling in ("Foo", "FOO"):
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("ignore")
            mod = _load(tmp_path, f"arrowlam_{spelling}", f"""
                -module(ttiav_arrowlam_{spelling}, [p(X)])
                bar(1),
                p(X) <- (assertz({spelling} <- bar(X)))
            """)
        # It LOADS, and the head lowers to a closure, so ``assertz`` refuses
        # it at query time -- loudly, naming the lambda.  Recorded rather
        # than merely tolerated: if this ever starts asserting a clause, or
        # starts refusing at load, the change is deliberate.
        try:
            list(call("p", Var(), module=_module(mod)))
            outcomes.append("succeeded")
        except TypeError as exc:
            outcomes.append(("TypeError", "functor, arity" in str(exc)))
    # The CONCRETE outcome, not merely that the two arms match: both arms
    # succeeding, or the message losing "functor, arity", would still agree
    # and would still have passed.
    assert outcomes == [("TypeError", True), ("TypeError", True)], outcomes
    # And they agree -- linting only the TitleCase arm would make one clause
    # mean two things depending on how its head is spelled, the very
    # divergence this change removes.
    assert outcomes[0] == outcomes[1], outcomes


# ── The clause scope reaches every thunk position ─────────────────────────
#
# ``_clause_var_names`` decides whether a thunk captures a name or leaves it
# to the module namespace.  It is only correct if EVERY thunk position sees
# the whole clause -- otherwise position decides the reading, which is the
# fault the mechanism exists to remove.  The head cases are asserted on the
# DECISION rather than on a rendered value: a head thunk is forced while the
# body has not run, so the value is an unbound variable either way, and a
# same-named Python local in the clause function makes an uncaptured name
# close over that variable too.  Both mask the defect end-to-end; neither
# masks it here.

def _excluded_at_thunks(monkeypatch, tmp_path, name, source):
    """Whether *name* was excluded from capture, at each thunk lowered."""
    from clausal.templating import term_rewriting
    decisions = []
    real = term_rewriting.TermTransformer._python_scope_exclusions

    def spy(transformer):
        result = real(transformer)
        decisions.append(name in result)
        return result

    monkeypatch.setattr(
        term_rewriting.TermTransformer, "_python_scope_exclusions", spy)
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("ignore")
        _load(tmp_path, f"excl_{abs(hash(source))}", source)
    return decisions


def test_a_thunk_in_the_HEAD_sees_the_variables_the_body_binds(
        tmp_path, monkeypatch):
    """``q(f"{Node}") <- (tree(Node))``: ``Node`` is a clause variable, so
    the head thunk must capture it, not leave it to the AST node class."""
    decisions = _excluded_at_thunks(monkeypatch, tmp_path, "Node", """
        -double_quotes(atom)
        -module(ttiav_headscope, [q(S)])
        tree(7),
        q(f"{Node}") <- (tree(Node))
    """)
    assert decisions and not any(decisions), decisions


def test_a_thunk_in_one_head_argument_sees_another_argument(
        tmp_path, monkeypatch):
    """Within a head, argument order must not decide it either."""
    for source in (
        '-double_quotes(atom)\n-module(ttiav_ha, [r(S, N)])\ntree(7),\nr(f"{Node}", Node) <- (tree(Node))\n',
        '-double_quotes(atom)\n-module(ttiav_hb, [r(N, S)])\ntree(7),\nr(Node, f"{Node}") <- (tree(Node))\n',
    ):
        decisions = _excluded_at_thunks(monkeypatch, tmp_path, "Node", source)
        assert decisions and not any(decisions), (source, decisions)


def test_a_thunk_in_a_DCG_head_sees_the_body(tmp_path, monkeypatch):
    decisions = _excluded_at_thunks(monkeypatch, tmp_path, "Node", """
        -double_quotes(atom)
        -module(ttiav_dcgscope, [])
        tree(7),
        d(f"{Node}") >> (tree(Node))
    """)
    assert decisions and not any(decisions), decisions


def test_a_thunk_in_a_FACT_argument_sees_the_other_arguments(
        tmp_path, monkeypatch):
    """A fact has no body, but its arguments are still one scope."""
    decisions = _excluded_at_thunks(monkeypatch, tmp_path, "Node", """
        -double_quotes(atom)
        -module(ttiav_factscope, [])
        f(Node, f"{Node}"),
    """)
    assert decisions and not any(decisions), decisions


def test_a_thunk_in_a_LAMBDA_body_sees_the_enclosing_clause(
        tmp_path, monkeypatch):
    """The sub-transformer must SHARE the set, not start a fresh one --
    otherwise one spelling means two things depending only on whether it
    sits inside a lambda, which is the divergence the sibling test names."""
    decisions = _excluded_at_thunks(monkeypatch, tmp_path, "Node", """
        -double_quotes(atom)
        -module(ttiav_lamscope, [p(S)])
        tree(7),
        p(S) <- (tree(Node), S is (_x <- (f"{Node}")))
    """)
    assert decisions and not any(decisions), decisions


def test_the_namespace_name_is_still_excluded_when_no_clause_binds_it(
        tmp_path, monkeypatch):
    """The negative control on the same instrument: without this, deleting
    the exclusion entirely would pass every test above."""
    decisions = _excluded_at_thunks(monkeypatch, tmp_path, "Node", """
        -double_quotes(atom)
        -module(ttiav_nsexcl, [p(S)])
        p(S) <- (S is f"{Node}")
    """)
    assert decisions and all(decisions), decisions


def test_head_and_body_thunks_agree_across_all_three_spellings(tmp_path):
    """The user-visible half: whatever a head thunk renders, it must render
    the same for a colliding name, an ordinary one and an ALL_CAPS one."""
    rendered = {}
    for spelling in ("Node", "Nodex", "NODE"):
        mod = _load(tmp_path, f"agree_{spelling}", f"""
            -double_quotes(atom)
            -module(ttiav_agree_{spelling}, [q(S)])
            tree(7),
            q(f"{{{spelling}}}") <- (tree({spelling}))
        """)
        [(answer,)] = _answers(mod, "q")
        rendered[spelling] = answer
    # A head thunk is forced before the body binds, so an unbound variable is
    # the right answer -- for all three.  What must never appear is a class.
    assert all(atom_spelling(r).startswith("_") for r in rendered.values()), rendered
    assert not any("class" in atom_spelling(r) for r in rendered.values()), rendered


# ── The escape predicate is one predicate, adjacency included ──────────────

def test_a_spaced_plus_plus_is_not_an_escape_for_the_collector():
    """The same adjacency rule, on the ``++`` side and from the COLLECTOR's
    end — one shared predicate, so the two cannot disagree.

    ``+ +Node`` is NOT a Python escape: ``visit_UnaryOp`` requires the two
    operators to be adjacent, so the transform compiles it as arithmetic on
    the logic variable ``Node``.  The clause therefore DOES use ``Node`` as a
    variable, and a collector that skipped ``+ +`` as an escape threw away
    the only evidence of it — after which a thunk in the same clause resolves
    ``Node`` in the module namespace instead.

    Asserted on the collector directly rather than end-to-end, because
    end-to-end the fault is MASKED: the arithmetic reading emits
    ``(Node := $Var())``, whose walrus leaks a same-named binding into the
    module globals that the uncaptured thunk then finds.  A test through the
    front door would have passed either way."""
    from clausal.templating.term_rewriting import _clause_variable_names
    adjacent = ast.parse("maybe(++Node)", mode="eval").body
    spaced = ast.parse("maybe(+ +Node)", mode="eval").body
    assert _clause_variable_names(adjacent, frozenset()) == set()
    assert _clause_variable_names(spaced, frozenset()) == {"Node"}


def test_a_spaced_plus_plus_is_not_an_escape_for_the_lint_either(tmp_path):
    """The third copy of the predicate.  The TitleCase lint skips a ``++``
    subtree because the name there is Python — its own docstring says
    "adjacent double ``UAdd``" — but the code omitted the adjacency test, so
    it also skipped ``+ +Foo(1)``, which the transform compiles as Clausal.
    The functor refusal the lint exists for therefore never fired."""
    with pytest.raises(SyntaxError) as excinfo:
        _load(tmp_path, "lint_spaced", """
            -module(cvmit_lint_spaced, [p(X)])
            bar(Y),
            p(X) <- (bar(+ +Foo(1)))
        """)
    assert "Foo" in str(excinfo.value)


def test_a_non_variable_spelling_stays_double_negation(tmp_path):
    """The marker names a Clausal VARIABLE, and ``total`` cannot be one, so
    ``--total`` is the arithmetic it always was.  Numeric on purpose: here
    the double negation IS the property under test."""
    mod = _load(tmp_path, "lower", """
        total = 4
        -module(cvmit_lower, [p(S)])
        p(S) <- (S is ++(--total))
    """)
    assert _answers(mod, "p") == [(4,)]


# ── One shared scope across every outermost root ───────────────────────────
#
# ``note_clause_scope``'s auto-note in ``visit`` fires once per outermost
# root and ACCUMULATES, so where one transformer visits several roots that
# share a variable scope, a thunk in root 1 is decided before root 2's names
# are known.  Both sites below are such a shape, and both are order-sensitive
# without an up-front note — silently, since the two readings differ only in
# what the thunk formats.

def _lambda_params(rendered, name):
    """Whether the emitted thunk captured *name* as a lambda parameter."""
    return f"lambda {name}:" in rendered


def test_the_dash_dash_block_form_notes_every_statement_up_front():
    from clausal.templating.term_rewriting import EmbedTransformer, unparse

    def render(src):
        tree = ast.parse(src)
        ast.fix_missing_locations(tree)
        out = EmbedTransformer().visit(tree)
        ast.fix_missing_locations(out)
        return unparse(out)

    thunk_first = render(
        'with --{} as clauses:\n    bar(f"{Node}")\n    tree(Node)\n')
    thunk_last = render(
        'with --{} as clauses:\n    tree(Node)\n    bar(f"{Node}")\n')
    assert _lambda_params(thunk_last, "Node"), thunk_last
    assert _lambda_params(thunk_first, "Node"), thunk_first


def test_the_repl_conjunction_path_notes_every_conjunct_up_front():
    from clausal.import_hook import _StarQueryTransformer
    from clausal.templating.term_rewriting import unparse

    def render(src):
        tree = ast.parse(src)
        out = _StarQueryTransformer().visit(tree)
        ast.fix_missing_locations(out)
        return unparse(out)

    thunk_first = render(
        '_clausal_star_query_(bar(f"{Node}"), tree(Node))')
    thunk_last = render(
        '_clausal_star_query_(tree(Node), bar(f"{Node}"))')
    assert _lambda_params(thunk_last, "Node"), thunk_last
    assert _lambda_params(thunk_first, "Node"), thunk_first


# ── A ``++`` escape inside a seam is Python, so its names are not variables ──
#
# READ THE TRACEBACK WITH CARE.  When this collection goes wrong the failure
# is an ``UnboundLocalError`` reported on an EARLIER, entirely innocent line
# -- the first plain-Python use of the name in the same function.  Python
# decides locality for a whole function at compile time, so the seam's
# ``(Name := $Var())`` further down is what made the earlier read local; the
# line the traceback blames is the victim, not the cause.  The cause is
# always the seam, however far below the reported line it sits.


def test_a_python_escape_in_a_seam_does_not_capture_its_name_as_a_variable(
        tmp_path):
    """``--f(++Var())``: ``Var`` is Python, and must stay Python.

    A ``++`` operand is verbatim Python by definition, so a capital-initial
    name inside one is a module-namespace binding, not a logic variable.
    Collecting it puts ``(Var := $Var())`` into the enclosing function, and
    every plain-Python ``Var()`` in that function -- including ones written
    ABOVE the seam -- then raises ``UnboundLocalError``.

    The ANSWER is asserted, not merely the load: the escaped variable has to
    reach the fact's argument and come back bound.
    """
    mod = _load(tmp_path, "esc_own_api", """
        from clausal import Var
        from clausal.logic.seam import once_bind, export
        -private([h])
        amount(h, 7),
        def probe():
            a = Var()
            t = --amount(++h, ++Var())
            return type(a).__name__, once_bind(t, globals()), export(t[2])
    """)
    assert mod.probe() == ("AttVar", True, 7)


def test_the_escape_rule_is_not_specific_to_one_name(tmp_path):
    """The same shape with a name the engine has never heard of.

    Exempting ``Var`` by spelling would leave the hole open for every other
    capital-initial Python name reachable from a ``++``; the rule is about
    the POSITION, so an arbitrary imported class has to behave identically.
    ``once_bind`` succeeding is the answer -- the escape evaluated to ``7``
    in the module namespace, which it cannot do if the class it names had
    been replaced by an unbound variable.
    """
    mod = _load(tmp_path, "esc_other", """
        from fractions import Fraction
        from clausal.logic.seam import once_bind
        -private([h])
        amount(h, 7),
        def probe():
            a = Fraction(1, 3)
            t = --amount(++h, ++int(Fraction(14, 2)))
            return a, once_bind(t, globals()), t[2]
    """)
    from fractions import Fraction
    assert mod.probe() == (Fraction(1, 3), True, 7)


def test_a_real_seam_variable_beside_an_escape_is_still_bound(tmp_path):
    """The negative half: "collect nothing" must not pass.

    One seam holding both -- a capital-initial name inside a ``++`` (skipped)
    and a genuine seam variable outside one (collected, bound up front, and
    readable as a plain Python local once the goal has run).
    """
    mod = _load(tmp_path, "esc_and_var", """
        from clausal import Var
        from clausal.logic.seam import once_bind, export
        -private([h])
        amount(1, 7),
        def probe():
            a = Var()
            t = --amount(++len([Var]), N)
            bound = once_bind(t, globals())
            return type(a).__name__, bound, export(N)
    """)
    assert mod.probe() == ("AttVar", True, 7)


def test_an_escape_naming_a_variable_of_the_same_seam_still_resolves(tmp_path):
    """A ``++`` that names a variable the enclosing seam itself binds.

    ``N`` is used OUTSIDE the escape as well, and THAT is what makes the
    spelling a variable here -- so the thunk must capture the seam's own
    ``N``, not look the name up in the module namespace and not mint a
    second variable.  Skipping escape operands during collection must not
    disturb that, which is why the assertion is on IDENTITY: the value the
    escape produced is the very variable standing in the first argument, and
    binding the term binds both.

    (Identity rather than arithmetic on the value: a thunk is evaluated when
    the term is BUILT, before anything has been unified, so ``++(N * 2)``
    would be multiplying an unbound variable -- true on both sides of this
    fix, and not what this test is about.)
    """
    mod = _load(tmp_path, "esc_enclosing", """
        from clausal.logic.seam import once_bind, export
        same(2, 2),
        def probe():
            t = --same(N, ++(N))
            return (t[1] is t[2]), once_bind(t, globals()), export(N)
    """)
    assert mod.probe() == (True, True, 2)


def test_an_fstring_in_a_seam_does_not_capture_its_names_either(tmp_path):
    """The sibling verbatim-Python body, which had the identical defect.

    An interpolation slot is Python exactly as a ``++`` operand is, and the
    clause-scope collector has always skipped both.  Before this fix a seam
    containing ``f"{Fraction(1, 2)}"`` made ``Fraction`` local to the
    enclosing function and the plain-Python use above it died.
    """
    mod = _load(tmp_path, "esc_fstring", """
        from fractions import Fraction
        -private([h])
        amount(h, 7),
        def probe():
            a = Fraction(1, 3)
            t = --amount(++h, f"{Fraction(1, 2)}")
            return a, t[2]
    """)
    from fractions import Fraction
    assert mod.probe() == (Fraction(1, 3), chars("1/2"))  # R2: a string


# ── The sibling paths, pinned either way ───────────────────────────────────

def test_the_goal_position_seam_shares_the_escape_rule(tmp_path):
    """``if``/``while``/a comprehension guard all reach the same collection
    through ``_goal_seam``, so all of them carried the defect and all of them
    are fixed by the one change.  Pinned here so a future divergence between
    goal and term position is a failure rather than a discovery."""
    mod = _load(tmp_path, "esc_goal", """
        from clausal import Var
        -private([h])
        amount(1, 7),
        def by_if():
            a = Var()
            if --amount(++len([Var]), N):
                return type(a).__name__, N
            return None
        def by_while():
            a = Var()
            seen = []
            while --amount(++len([Var]), N):
                seen.append((type(a).__name__, N))
                break
            return seen
        def by_for():
            a = Var()
            out = []
            for N in --amount(++len([Var]), N):
                out.append((type(a).__name__, N))
            return out
    """)
    assert mod.by_if() == ("AttVar", 7)
    assert mod.by_while() == [("AttVar", 7)]
    assert mod.by_for() == [("AttVar", 7)]


def test_the_block_form_never_had_the_defect(tmp_path):
    """``with --{} as terms:`` is the one seam shape that does NOT compute a
    fresh list at all -- it visits each root with a plain term transformer,
    and a name inside a ``++`` never reaches ``visit_Name``.  So it was
    already correct, and the point of pinning it is that it stays correct
    rather than being "fixed" into some new shape."""
    mod = _load(tmp_path, "esc_block", """
        from clausal import Var
        -private([h])
        amount(h, 7),
        def probe():
            a = Var()
            with --{} as terms:
                amount(++h, ++Var())
            return type(a).__name__, terms
    """)
    kind, terms = mod.probe()
    # ``a`` is still a variable object: the block did not turn ``Var`` into a
    # function-local, which is the whole failure mode.
    assert kind == "AttVar"
    # The block yields COMPILE-TIME term nodes, not runtime terms -- both
    # escapes are still unevaluated Python thunks, which is exactly what a
    # ``++`` operand must lower to.
    assert len(terms) == 1
    assert type(terms[0]).__name__ == "Call"
    assert terms[0].func.name == "amount"
    assert [type(a).__name__ for a in terms[0].args] == ["PyThunk", "PyThunk"]


def test_a_nested_seam_inside_an_escape_still_hoists_its_variable(tmp_path):
    """The carve-out the escape rule needs, pinned by ANSWER.

    Inside a seam a ``++`` operand is hosted Python again, and there
    ``--expr`` is a nested SEAM (not the variable marker, which is read only
    where the thunk body is embedded verbatim).  So its operand is Clausal
    text and ``N`` there is a variable -- one the ENCLOSING seam binds, so
    that the inner seam reuses it rather than walrusing a fresh one inside
    the lambda and shadowing the parameter the thunk was handed.

    Skipping Python bodies wholesale breaks exactly this: the term would
    carry a variable nobody outside the lambda can see, so ``N`` would come
    back unbound instead of ``7``.
    """
    mod = _load(tmp_path, "esc_nested_seam", """
        from clausal.logic.seam import once_bind, export
        -private([h])
        amount(h, 7),
        def pick(v):
            return v
        def probe():
            t = --amount(++h, ++pick(--N))
            return once_bind(t, globals()), export(N)
    """)
    assert mod.probe() == (True, 7)
