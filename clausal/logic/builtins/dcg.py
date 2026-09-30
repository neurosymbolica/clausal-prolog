"""DCG builtins: phrase/2, phrase/3, sequence//1."""

from __future__ import annotations

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.predicate import (
    is_term_instance, term_field_names, _dispatch_at,
    is_declared_predicate_name, localize_goal,
)
from clausal.logic.trampoline import DONE, StepGenerator

from clausal.logic.builtins._registry import (
    _trampoline_builtin, _DB_BUILTINS, _BUILTIN_FIELDS,
)
from clausal.logic.runtime._seg_helpers import normalize_seg_input, str_chars
from clausal.logic.cells import (
    chars, is_chars, chars_text,           # stage 1: the chars carrier
    compound_cell_shape, CELL_GOAL_CONTROL_FUNCTORS, QUALIFIED_GOAL_FUNCTOR,
)


def _text_out(x):
    """A DCG remainder/expected sequence as a term: a bare str is the chars
    CARRIER (stage 1 of the atoms-as-str flip); anything else is itself."""
    return chars(x) if type(x) is str else x


# ── _DCG_ARITY_NOTE ──────────────────────────────────────────────────────────
#
# ``phrase`` supplies the difference-list pair itself, so the arity it calls a
# nonterminal at is never the arity written in the source: ``greeting//0``
# translates to ``greeting/2`` and ``digit//1`` to ``digit/3``.  Both branches
# below therefore pass ``len(user_args) + 2``, which is literally the number of
# arguments the ``StepGenerator`` on the next line receives.
#
# ``len(fields)`` would look equivalent and is not: ``fields[:-2]`` truncates to
# empty for a class of arity 0 or 1, so a ``phrase(foo, L)`` naming an untranslated
# ``foo/1`` still supplies 2 arguments while ``len(fields)`` says 1.  Counting the
# args actually built keeps the refusal's claim true in that case, which is the
# case worth catching — it is exactly the "you named a plain predicate, not a
# nonterminal" mistake.



def _elements(seq):
    """The list of TERMS *seq* denotes, for a ``str``/``bytes``/list.

    THE FLIP (2026-09-06-atoms-as-cells-strings §6.2): the elements of a
    ``str`` are its CHAR ATOMS, so ``list(s)`` -- which yields 1-char
    ``str`` values, each a one-element STRING -- is no longer the right
    splat.  ``bytes`` keeps the codes model (``list(b)`` yields ints) and a
    list is already elements.
    """
    if is_chars(seq):
        return str_chars(chars_text(seq))   # stage 1
    if type(seq) is str:
        return str_chars(seq)
    if isinstance(seq, bytes):
        return list(seq)
    return seq


def _empty_remainder_like(list_val):
    """Return the type-correct "nothing left" sentinel for *list_val*.

    ``phrase/2``'s contract is "the rule must consume List entirely", i.e.
    the final remaining-state var must unify with the EMPTY sequence.

    THE FLIP (atoms-as-cells/strings §6.2) reinstated the str~char-list
    unification the P3-1 pivot had retired, so ``unify("", [], trail)``
    succeeds again (as ``unify(b"", [], trail)`` always did) and a bare
    ``[]`` would once more DO here.  The type-matched sentinel stays for the
    reason R-S2 gives rather than for a unification failure: the residue
    keeps the input's own REPRESENTATION — a string stays a string, a codes
    sequence stays bytes — instead of swapping spelling halfway through a
    parse and handing the caller a different-looking empty.
    """
    if isinstance(list_val, str) or is_chars(list_val):
        return chars("")               # stage 1: the empty TEXT remainder is the carrier
    if isinstance(list_val, bytes):
        return b""
    return []



#: The control constructs a DCG BODY term may be built from (ISO 7.14 /
#: Scryer's library(dcgs)): conjunction, disjunction (``;`` and ``|``) and
#: negation.  ``->`` stays refused -- Clausal has no committed choice.
_DCG_CONTROL_CELLS = frozenset({",", ";", "|", "\\+"})


def _is_dcg_control_body(rule_val) -> bool:
    """True for a DCG body term phrase must translate rather than call: an
    ISO control cell, a conjunction tuple, or an ``and``/``or``/``not``
    node."""
    from clausal.logic.builtins.call_body import is_conjunction_tuple  # noqa: PLC0415
    from clausal.pythonic_ast import nodes  # noqa: PLC0415
    if isinstance(rule_val, (nodes.And, nodes.Or, nodes.Not)):
        return True
    if is_conjunction_tuple(rule_val):
        return True
    is_cell, functor = compound_cell_shape(rule_val)
    return (is_cell and functor in _DCG_CONTROL_CELLS
            and len(rule_val) == (2 if functor == "\\+" else 3))


def _is_dcg_terminal_body(rule_val) -> bool:
    """True for a DCG body that is its own TERMINALS: a list (``[]``
    included), a string (the chars carrier) or a code list.  ISO DCG and
    Scryer's phrase/2,3 accept any grammar body, so ``phrase([a], L)`` is
    ``L = [a]`` and ``phrase("ab", L)`` is ``L = [a, b]``; both used to fail
    silently here."""
    return isinstance(rule_val, (list, bytes)) or is_chars(rule_val)


def _dcg_body_goal(body, s0, s):
    """The GOAL a DCG body term means between the states *s0* and *s* -- the
    ISO translation (7.14.2), built at run time as a term ``call/1`` runs:
    conjunction threads a fresh state, disjunction shares both, negation
    consumes nothing, a list or string is its terminals, ``true`` is the
    empty body, and any other callable is the nonterminal with S0/S
    appended.  A variable body is ``phrase(B, S0, S)`` at run time."""
    from clausal.logic.builtins.call_body import is_conjunction_tuple  # noqa: PLC0415
    from clausal.pythonic_ast import nodes  # noqa: PLC0415
    b = deref(body)
    if is_var(b):
        return ("phrase", b, s0, s)
    if b is True:
        return ("=", s0, s)
    if isinstance(b, nodes.And):
        b = (",", b.left, b.right)
    elif isinstance(b, nodes.Or):
        b = (";", b.left, b.right)
    elif isinstance(b, nodes.Not):
        b = ("\\+", b.operand)
    elif is_conjunction_tuple(b):
        # ``(A, B, C)`` is ``','(A, ','(B, C))`` -- built from explicit ``,``
        # cells: a leftover bare tuple whose first element is an atom would
        # read as a CELL (``(ws, eol)`` is ``ws(eol)``), not a conjunction.
        acc = b[-1]
        for g in reversed(b[:-1]):
            acc = (",", g, acc)
        b = acc
    is_cell, functor = compound_cell_shape(b)
    if is_cell and functor == "," and len(b) == 3:
        mid = Var()
        return (",", _dcg_body_goal(b[1], s0, mid), _dcg_body_goal(b[2], mid, s))
    if is_cell and functor in (";", "|") and len(b) == 3:
        return (";", _dcg_body_goal(b[1], s0, s), _dcg_body_goal(b[2], s0, s))
    if is_cell and functor == "\\+" and len(b) == 2:
        return (",", ("\\+", _dcg_body_goal(b[1], s0, Var())), ("=", s0, s))
    if isinstance(b, list) or is_chars(b) or isinstance(b, bytes):
        items = list(_elements(b))
        if not items:
            return ("=", s0, s)
        return ("append", items, s, s0)
    if is_cell:
        return (functor, *b[1:], s0, s)
    return (b, s0, s)


def _resolve_nonterminal(db, rule_val, extra_args, context):
    """A CELL nonterminal -> ``(dispatch, call_args)``, else ``None``.

    P2: a cell names a predicate and carries no class, so the name has to be
    looked up, and the only correct place to look it up is the CALLING module
    (R-P2-2, module locality) -- which is why phrase/2,3 became db-receiving,
    exactly as the call/N family did in P3-3 Task 5.

    THE ARITY FALLS OUT.  ``_resolve_named_goal``'s ISO argument fold IS the
    ``_DCG_ARITY_NOTE`` convention: the cell's own arguments come first and the
    caller's extras follow, so ``phrase(digit(D), L, R)`` folds to ``digit/3``
    with S0/S as the extras.  Reusing that resolver keeps ONE name-resolution
    rule (the db's dispatch table, then the module namespace) rather than a
    second copy of it here.

    NARROWED to the shapes phrase already accepted.  A DCG body is not a goal
    tree: call/N RUNS a control-construct cell as a body (operator ruling
    2026-09-25) and raises for a string, ``[]`` and any non-callable, but
    ``phrase((a, b), L)`` never named a nonterminal here, so control
    functors are turned away before the resolver sees them and keep failing.
    A list or string body is its TERMINALS and is translated like a control
    body (``_is_dcg_terminal_body``): ``phrase([a], L)`` gives ``L = [a]``,
    as in Scryer -- it used to fail silently.  A module-qualified
    nonterminal ``M:NT`` (what a ``-meta_predicate`` argument arrives as,
    operator ruling 2026-09-25) resolves NT in M.  The one non-cell that
    RAISES is a non-callable term (a number, tuple data ...):
    ``phrase(42, L)`` is type_error(callable, 42), as in Scryer (operator
    ruling 2026-09-25) -- it used to fail.

    One resolver raise is deliberately NOT narrowed away: a dangling
    predicate HANDLE (a mangled functor whose module never loaded, or whose
    loaded module lacks the nonterminal) RAISES
    ``existence_error(procedure, Name/Arity)`` in phrase/2,3 exactly as in
    ``call/N`` (ruling 2 extended, 2026-09-24).  Nor is the other-arity
    refusal: a nonterminal name the caller binds only at another arity --
    ``phrase(b, L)`` against ``b/1`` asks for ``b/2`` -- raises
    ``PredicateArityMismatchError`` (ISO ``existence_error(procedure, b/2)``,
    catchable; ruling Q3, 2026-09-25).  Nor, since ruling 2 (2026-09-25),
    the UNKNOWN nonterminal: ``phrase(nosuch, L)`` raises
    ``existence_error(procedure, nosuch/2)`` -- N//A is N/(A+2) -- as Scryer.
    """
    from clausal.logic.builtins.higher_order import _resolve_named_goal  # noqa: PLC0415
    if len(extra_args) == 2 and (_is_dcg_control_body(rule_val)
                                 or _is_dcg_terminal_body(rule_val)):
        # A control-construct BODY -- ``phrase((a, b), L)`` -- is translated,
        # not named: it used to be refused (``(",", ...)`` failed; a
        # conjunction tuple reached the resolver as a call of its first
        # element).  Triage B3b, Scryer's phrase/2,3.
        s0, s = extra_args
        return _resolve_named_goal(db, _dcg_body_goal(rule_val, s0, s), [],
                                   context)
    is_cell, functor = compound_cell_shape(rule_val)
    from clausal.logic.builtins.call_body import (  # noqa: PLC0415
        is_non_callable_term, non_callable_goal_error,
    )
    if not is_cell and is_non_callable_term(rule_val, lists=False):
        from clausal.logic.exceptions import LogicException  # noqa: PLC0415
        raise LogicException(non_callable_goal_error(rule_val, context))
    if not is_cell:
        if type(rule_val) is str and rule_val:
            # A bare ATOM names the nonterminal: ruling S (2026-09-24) makes
            # ``phrase(greeting, L)`` pass the plain atom ``greeting``, not the
            # class, so this is the atom's arm the old pin
            # (``test_phrase_bare_str_rule_reference_fails_cleanly``, now
            # flipped) said P4 would need.  It contributes no arguments of its
            # own: S0/S are the whole call, ``greeting/2``.  A mangled handle
            # takes the same route (a dangling one raises, as in call/N).
            return _resolve_named_goal(db, rule_val, list(extra_args), context)
        return None
    if functor == QUALIFIED_GOAL_FUNCTOR and len(rule_val) == 3:
        # ``M:NT`` -- a -meta_predicate qualification (operator ruling
        # 2026-09-25) puts a nonterminal argument in this shape: resolve the
        # module, then the nonterminal in IT, with the same S0/S extras.
        from clausal.logic.cells import resolve_qualified_goal_cell  # noqa: PLC0415
        from clausal.logic.builtins.higher_order import _calling_module  # noqa: PLC0415
        # A module that does not exist is the missing procedure NT/(A+2),
        # as call/N reports it (operator ruling 2026-09-30).
        target, inner = resolve_qualified_goal_cell(
            rule_val, context, _calling_module(db),
            call_extra=len(extra_args))
        inner = deref(inner)
        from clausal.logic.meta_predicate import is_goal_object  # noqa: PLC0415
        if is_goal_object(inner):
            # ``M:NT`` whose NT is a nonterminal CLASS (a dotted ``m.nt``
            # reference): it resolves itself; S0/S are the whole call.
            return (_dispatch_at(inner, len(extra_args), target.db),
                    list(extra_args))
        return _resolve_nonterminal(target.db, inner, extra_args, context)
    if functor in CELL_GOAL_CONTROL_FUNCTORS or functor == QUALIFIED_GOAL_FUNCTOR:
        return None
    # Ruling C (2026-09-24), ISO call/N style: a nonterminal cell is built at
    # its WRITTEN arity -- ``tok(T)`` is ``("tok", T)``, never padded to the
    # translated ``tok/3`` -- so phrase APPENDS S0/S to the cell's own
    # arguments.  (It used to drop the last two slots of a padded cell.)
    user_args = [deref(a) for a in rule_val[1:]]
    # Resolve the FUNCTOR with every argument as an extra.  The atom route
    # through the shared resolver contributes no arguments of its own, so the
    # ISO fold lands at exactly ``len(user_args) + 2`` -- the arity the class
    # arm asks ``_dispatch_at`` for.  Handing it the cell itself would fold
    # the cell's own S0/S slots in on top of the pair phrase is supplying, and
    # ask for a nonterminal two arities too wide.
    return _resolve_named_goal(db, functor, user_args + list(extra_args), context)


def _make_phrase_factory(impl):
    """Bind the caller's database into a ``phrase/N`` dispatch.

    Registered straight into ``_DB_BUILTINS`` rather than through the
    ``@_db_builtin`` decorator, because that decorator wraps its product with
    ``_simple_to_trampoline`` and phrase is already trampoline-native -- the
    same reason ``_make_call_goal_factory`` registers itself by hand.

    ``_db_optional``: everything phrase did before this -- dispatching a
    nonterminal CLASS -- needs no database at all, so ``factory(None)`` is the
    pre-P2 phrase exactly, minus the name resolution it has no db to do.  That
    keeps the db-less paths (the builtin CLASS table, a ``BuiltinPredicate``
    built without a db) answering as they always have.
    """
    def factory(db):
        def _phrase_dispatch(*args):
            return impl(db, *args)
        _phrase_dispatch.__name__ = impl.__name__
        return _phrase_dispatch
    factory._db_optional = True
    return factory


def _phrase__2(db, this_generator, _proceed, _fail, _catcher, rule_body, list_arg, trail):
    """phrase(RuleBody, List) — invoke DCG rule, must consume entire list.

    Strings are accepted natively (per the Liskov "strings-as-lists" rule):
    the head/body star-unify helpers destructure str and SegString directly,
    so no eager char-list conversion is needed. SegList / SegString inputs
    are walked to their ground form (str / list) where possible so the
    dispatch path receives a uniform shape.
    """
    rule_val = deref(rule_body)
    list_val = deref(list_arg)
    # F069 (C10): walk SegList / SegString to plain str / list so the
    # dispatch path sees a uniform container. Strings are *not* converted
    # to lists — `_head_list_unify_input` / `_body_star_unify` handle
    # both str and list uniformly.
    list_val = normalize_seg_input(list_val)
    # P3-1 Task 5 (§1b): the "must consume entirely" sentinel must match
    # list_val's own type — see _empty_remainder_like.
    empty = _empty_remainder_like(list_val)
    # a bare str is TRANSIENT (the funnel's contract); the rule body receives
    # its input state as the carrier again (stage 1), so sequence//1 and
    # phrase/3 downstream see text and not a bare str
    list_val = _text_out(list_val)

    if (isinstance(rule_val, type) and hasattr(rule_val, '_get_dispatch')) \
            or is_declared_predicate_name(rule_val, db=db):
        # Class reference (0 extra args): phrase(greeting, [hello, world]),
        # or (W4b-3) the module-qualified HANDLE the name is bound to after
        # the flip -- which ``_resolve_nonterminal`` below would refuse.
        # A nonterminal's translated arity is its written arity plus S0 and S,
        # so a bare name here is called at 2 — see _DCG_ARITY_NOTE.
        dispatch = _dispatch_at(localize_goal(db, rule_val), 2, db)
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, list_val, empty, trail)
    elif is_term_instance(rule_val):
        # Instance with args: phrase(digit(D_), [3, plus, 4])
        cls = type(rule_val)
        fields = term_field_names(rule_val)
        user_args = [deref(getattr(rule_val, f)) for f in fields[:-2]]
        dispatch = _dispatch_at(cls, len(user_args) + 2)
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, *user_args, list_val, empty, trail)
    else:
        # A CELL names the nonterminal and brings no class with it --
        # resolve the name against the calling module.
        resolved = _resolve_nonterminal(db, rule_val, (list_val, empty), "phrase/2")
        if resolved is None:
            yield (_fail, DONE)
            return
        dispatch, call_args = resolved
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, *call_args, trail)

    _st = yield (sg, None)
    while _st is not DONE:
        yield (_proceed, None)
        _st = yield (sg, None)
    yield (_fail, DONE)


def _phrase__3(db, this_generator, _proceed, _fail, _catcher, rule_body, list_arg, rest_arg, trail):
    """phrase(RuleBody, List, Rest) — invoke DCG rule, partial parse.

    Strings are accepted natively (per the Liskov "strings-as-lists" rule):
    when ``List`` is a str, the residue ``Rest`` is bound to a str slice
    rather than a Python list — preserving the input type end-to-end
    (closes F067). SegList / SegString inputs are walked to their ground
    form (closes F069).
    """
    rule_val = deref(rule_body)
    list_val = deref(list_arg)
    # F069 (C10): walk SegList / SegString to plain str / list so the
    # dispatch path sees a uniform container. F067 (C10): strings are *not*
    # converted to lists — `_head_list_unify_input` / `_body_star_unify`
    # destructure str natively and bind Rest to a str slice when the
    # input is str.
    list_val = normalize_seg_input(list_val)
    list_val = _text_out(list_val)   # stage 1: the rule body receives the carrier, not the transient bare str
    rest_val = deref(rest_arg)

    if (isinstance(rule_val, type) and hasattr(rule_val, '_get_dispatch')) \
            or is_declared_predicate_name(rule_val, db=db):   # W4b-3: see phrase/2
        dispatch = _dispatch_at(localize_goal(db, rule_val), 2, db)  # see _DCG_ARITY_NOTE
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, list_val, rest_val, trail)
    elif is_term_instance(rule_val):
        cls = type(rule_val)
        fields = term_field_names(rule_val)
        user_args = [deref(getattr(rule_val, f)) for f in fields[:-2]]
        dispatch = _dispatch_at(cls, len(user_args) + 2)
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, *user_args, list_val, rest_val, trail)
    else:
        # A CELL names the nonterminal and brings no class with it --
        # resolve the name against the calling module.
        resolved = _resolve_nonterminal(db, rule_val, (list_val, rest_val), "phrase/3")
        if resolved is None:
            yield (_fail, DONE)
            return
        dispatch, call_args = resolved
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, *call_args, trail)

    _st = yield (sg, None)
    while _st is not DONE:
        yield (_proceed, None)
        _st = yield (sg, None)
    yield (_fail, DONE)


_DB_BUILTINS[("phrase", 2)] = _make_phrase_factory(_phrase__2)
_BUILTIN_FIELDS[("phrase", 2)] = ("rule_body", "list_arg")
_DB_BUILTINS[("phrase", 3)] = _make_phrase_factory(_phrase__3)
_BUILTIN_FIELDS[("phrase", 3)] = ("rule_body", "list_arg", "rest_arg")


@_trampoline_builtin("sequence", 3, fields=("list", "s0", "s"))
def _sequence__3(this_generator, _proceed, _fail, _catcher, lst, s0, s, trail):
    """sequence//1 — DCG non-terminal that matches a list of terminals.

    sequence(List, S0, S) succeeds when S0 = List ++ S.
    Used as a DCG rule: ``phrase(sequence([a, b, c]), Input)``.

    Under the Liskov "strings-as-lists" rule (F070, C10):

    * Mode A (S0 str, S unbound) — S is bound to a str slice of S0, not a
      Python list of chars.
    * Mode B (S0 unbound, S str/list) — S0 is built as a str when both
      ``lst`` and ``S`` are str, else as a list (input-type-wins).
    * Mode C (both unbound, lst str) — S0 is built as a ``SegString``
      so the str shape of ``lst`` is preserved across the partial list.
    * Mode D (lst is SegList / SegString) — walked to its ground form so
      the same branches fire as for a plain list / str.
    """
    from clausal.terms import SegList, SegString, SegBytes, ConcreteSeg, VarSeg

    # F070 (C10): walk ground SegList / SegString inputs so the existing
    # str / list arms fire. A non-ground Seg* is treated as a structural
    # var-like value and falls through to the build branch below.
    lst_val = normalize_seg_input(deref(lst))
    if is_var(lst_val) or not isinstance(lst_val, (list, str, bytes)):
        yield (_fail, DONE)
        return
    s_val = normalize_seg_input(deref(s))
    s0_val = normalize_seg_input(deref(s0))
    if isinstance(s0_val, (list, str, bytes)):
        # S0 is bound — check prefix and bind S to remainder.
        # F070 Mode A: when S0 and lst are both str, ``s0_val[n:]`` is a
        # str slice; when both are bytes, ``s0_val[n:]`` is a bytes slice.
        # (list, str, bytes) are all handled uniformly by normalising both
        # sides to a list of ELEMENTS for the comparison so we accept either
        # input type.  A ``str`` splats to its CHAR ATOMS (``str_chars``,
        # THE FLIP: ``list("hi")`` would give 1-char STRINGS, which are one
        # ``[("h",)]`` list each and unify with nothing) and ``bytes``
        # splats to ints — they never compare equal across the str/bytes
        # divide, preserving the no-cross-unification guard.
        n = len(lst_val)
        s0_pref = s0_val[:n]
        s0_pref_norm = _elements(s0_pref)
        lst_pref_norm = _elements(lst_val)
        # F009: unify the prefix element-wise rather than comparing with
        # Python ``==`` — a Var terminal (e.g. ``sequence([X], "a", S)``)
        # must bind to the corresponding S0 element, which ``==`` never does.
        # unify preserves the str/bytes divide (1-char str never unifies with
        # the int a bytes element normalises to).
        if len(s0_val) >= n:
            mark = trail.mark()
            if unify(lst_pref_norm, s0_pref_norm, trail) and unify(s, _text_out(s0_val[n:]), trail):
                yield (_proceed, None)
            trail.undo(mark)
    elif isinstance(s_val, (list, str, bytes)):
        # S is bound — compute S0 = List ++ S and unify.
        # F070 Mode B: when both lst_val and s_val are str, build a str;
        # when both are bytes, build bytes; otherwise fall back to a list.
        if isinstance(lst_val, bytes) and isinstance(s_val, bytes):
            expected = lst_val + s_val
        elif isinstance(lst_val, str) and isinstance(s_val, str):
            expected = _text_out(lst_val + s_val)
        else:
            expected = _elements(lst_val) + _elements(s_val)
        mark = trail.mark()
        if unify(s0, expected, trail):
            yield (_proceed, None)
        trail.undo(mark)
    else:
        # Both S0 and S are unbound — build a partial list: S0 = List ++ S.
        # F070 Mode C: when lst is str, build a SegString; when lst is
        # bytes, build a SegBytes so the bytes shape carries through;
        # otherwise build a SegList as before.
        if isinstance(lst_val, bytes):
            ss = SegBytes([lst_val, VarSeg(s_val)])
            mark = trail.mark()
            if unify(s0, ss, trail):
                yield (_proceed, None)
            trail.undo(mark)
        elif isinstance(lst_val, str):
            ss = SegString([lst_val, VarSeg(s_val)])
            mark = trail.mark()
            if unify(s0, ss, trail):
                yield (_proceed, None)
            trail.undo(mark)
        else:
            sl = SegList([ConcreteSeg(lst_val), VarSeg(s_val)])
            mark = trail.mark()
            if unify(s0, sl, trail):
                yield (_proceed, None)
            trail.undo(mark)
    yield (_fail, DONE)
