"""DCG builtins: phrase/2, phrase/3, sequence//1."""

from __future__ import annotations

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.predicate import (
    is_term_instance, term_field_names, _dispatch_at,
)
from clausal.logic.trampoline import DONE, StepGenerator

from clausal.logic.builtins._registry import _trampoline_builtin
from clausal.logic.runtime._seg_helpers import normalize_seg_input, str_chars
from clausal.logic.cells import chars, is_chars, chars_text  # stage 1: the chars carrier


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


@_trampoline_builtin("phrase", 2)
def _phrase__2(this_generator, _proceed, _fail, _catcher, rule_body, list_arg, trail):
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

    if isinstance(rule_val, type) and hasattr(rule_val, '_get_dispatch'):
        # Class reference (0 extra args): phrase(greeting, [hello, world])
        # A nonterminal's translated arity is its written arity plus S0 and S,
        # so a bare name here is called at 2 — see _DCG_ARITY_NOTE.
        dispatch = _dispatch_at(rule_val, 2)
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, list_val, empty, trail)
    elif is_term_instance(rule_val):
        # Instance with args: phrase(digit(D_), [3, plus, 4])
        cls = type(rule_val)
        fields = term_field_names(rule_val)
        user_args = [deref(getattr(rule_val, f)) for f in fields[:-2]]
        dispatch = _dispatch_at(cls, len(user_args) + 2)
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, *user_args, list_val, empty, trail)
    else:
        yield (_fail, DONE)
        return

    _st = yield (sg, None)
    while _st is not DONE:
        yield (_proceed, None)
        _st = yield (sg, None)
    yield (_fail, DONE)


@_trampoline_builtin("phrase", 3)
def _phrase__3(this_generator, _proceed, _fail, _catcher, rule_body, list_arg, rest_arg, trail):
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
    rest_val = deref(rest_arg)

    if isinstance(rule_val, type) and hasattr(rule_val, '_get_dispatch'):
        dispatch = _dispatch_at(rule_val, 2)  # see _DCG_ARITY_NOTE
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, list_val, rest_val, trail)
    elif is_term_instance(rule_val):
        cls = type(rule_val)
        fields = term_field_names(rule_val)
        user_args = [deref(getattr(rule_val, f)) for f in fields[:-2]]
        dispatch = _dispatch_at(cls, len(user_args) + 2)
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, *user_args, list_val, rest_val, trail)
    else:
        yield (_fail, DONE)
        return

    _st = yield (sg, None)
    while _st is not DONE:
        yield (_proceed, None)
        _st = yield (sg, None)
    yield (_fail, DONE)


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
