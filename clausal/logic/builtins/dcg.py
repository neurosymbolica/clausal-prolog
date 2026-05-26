"""DCG builtins: phrase/2, phrase/3, sequence//1."""

from __future__ import annotations

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.predicate import is_term_instance, term_field_names
from clausal.logic.trampoline import DONE, StepGenerator

from clausal.logic.builtins._registry import _trampoline_builtin
from clausal.logic.runtime._seg_helpers import normalize_seg_input


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

    if isinstance(rule_val, type) and hasattr(rule_val, '_get_dispatch'):
        # Class reference (0 extra args): phrase(greeting, [hello, world])
        dispatch = rule_val._get_dispatch()
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, list_val, [], trail)
    elif is_term_instance(rule_val):
        # Instance with args: phrase(digit(D_), [3, plus, 4])
        cls = type(rule_val)
        dispatch = cls._get_dispatch()
        fields = term_field_names(rule_val)
        user_args = [deref(getattr(rule_val, f)) for f in fields[:-2]]
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, *user_args, list_val, [], trail)
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
        dispatch = rule_val._get_dispatch()
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, list_val, rest_val, trail)
    elif is_term_instance(rule_val):
        cls = type(rule_val)
        dispatch = cls._get_dispatch()
        fields = term_field_names(rule_val)
        user_args = [deref(getattr(rule_val, f)) for f in fields[:-2]]
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
    from clausal.terms import SegList, SegString, ConcreteSeg, VarSeg

    # F070 (C10): walk ground SegList / SegString inputs so the existing
    # str / list arms fire. A non-ground Seg* is treated as a structural
    # var-like value and falls through to the build branch below.
    lst_val = normalize_seg_input(deref(lst))
    if is_var(lst_val) or not isinstance(lst_val, (list, str)):
        yield (_fail, DONE)
        return
    s_val = normalize_seg_input(deref(s))
    s0_val = normalize_seg_input(deref(s0))
    if isinstance(s0_val, (list, str)):
        # S0 is bound — check prefix and bind S to remainder.
        # F070 Mode A: when S0 and lst are both str, ``s0_val[n:]`` is a
        # str slice and ``s0_val[:n] == lst_val`` works across (list, str)
        # because list[c, …] == "ab" returns True only when elements are
        # 1-char strs equal to chars — which is exactly the contract.
        n = len(lst_val)
        # str.startswith equivalent across mixed types: normalize both
        # sides to list for the comparison so we accept either input
        # type. (str == list of 1-char strs evaluates False even when
        # the contents match, so we have to be explicit.)
        s0_pref = s0_val[:n]
        lst_pref = lst_val
        if isinstance(s0_pref, str):
            s0_pref_norm = list(s0_pref)
        else:
            s0_pref_norm = s0_pref
        if isinstance(lst_pref, str):
            lst_pref_norm = list(lst_pref)
        else:
            lst_pref_norm = lst_pref
        if len(s0_val) >= n and s0_pref_norm == lst_pref_norm:
            mark = trail.mark()
            if unify(s, s0_val[n:], trail):
                yield (_proceed, None)
            trail.undo(mark)
    elif isinstance(s_val, (list, str)):
        # S is bound — compute S0 = List ++ S and unify.
        # F070 Mode B: when both lst_val and s_val are str, build a str
        # so the output preserves the input type. Otherwise fall back to
        # list construction.
        if isinstance(lst_val, str) and isinstance(s_val, str):
            expected = lst_val + s_val
        else:
            lst_as_list = list(lst_val) if isinstance(lst_val, str) else lst_val
            s_as_list = list(s_val) if isinstance(s_val, str) else s_val
            expected = lst_as_list + s_as_list
        mark = trail.mark()
        if unify(s0, expected, trail):
            yield (_proceed, None)
        trail.undo(mark)
    else:
        # Both S0 and S are unbound — build a partial list: S0 = List ++ S.
        # F070 Mode C: when lst is str, build a SegString so the str shape
        # carries through; otherwise build a SegList as before.
        if isinstance(lst_val, str):
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
