"""DCG builtins: phrase/2 and phrase/3."""

from __future__ import annotations

from clausal.logic.variables import deref
from clausal.logic.predicate import is_term_instance, term_field_names
from clausal.logic.trampoline import DONE, StepGenerator

from clausal.logic.builtins._registry import _trampoline_builtin


@_trampoline_builtin("phrase", 2)
def _phrase__2(this_generator, parent, rule_body, list_arg, trail):
    """phrase(RuleBody, List) — invoke DCG rule, must consume entire list."""
    rule_val = deref(rule_body)
    list_val = deref(list_arg)

    if isinstance(rule_val, type) and hasattr(rule_val, '_get_dispatch'):
        # Class reference (0 extra args): phrase(greeting, [hello, world])
        dispatch = rule_val._get_dispatch()
        sg = StepGenerator(dispatch, this_generator, list_val, [], trail)
    elif is_term_instance(rule_val):
        # Instance with args: phrase(digit(D_), [3, plus, 4])
        cls = type(rule_val)
        dispatch = cls._get_dispatch()
        fields = term_field_names(rule_val)
        user_args = [deref(getattr(rule_val, f)) for f in fields[:-2]]
        sg = StepGenerator(dispatch, this_generator, *user_args, list_val, [], trail)
    else:
        yield (parent, DONE)
        return

    _st = yield (sg, None)
    while _st is not DONE:
        yield (parent, None)
        _st = yield (sg, None)
    yield (parent, DONE)


@_trampoline_builtin("phrase", 3)
def _phrase__3(this_generator, parent, rule_body, list_arg, rest_arg, trail):
    """phrase(RuleBody, List, Rest) — invoke DCG rule, partial parse."""
    rule_val = deref(rule_body)
    list_val = deref(list_arg)
    rest_val = deref(rest_arg)

    if isinstance(rule_val, type) and hasattr(rule_val, '_get_dispatch'):
        dispatch = rule_val._get_dispatch()
        sg = StepGenerator(dispatch, this_generator, list_val, rest_val, trail)
    elif is_term_instance(rule_val):
        cls = type(rule_val)
        dispatch = cls._get_dispatch()
        fields = term_field_names(rule_val)
        user_args = [deref(getattr(rule_val, f)) for f in fields[:-2]]
        sg = StepGenerator(dispatch, this_generator, *user_args, list_val, rest_val, trail)
    else:
        yield (parent, DONE)
        return

    _st = yield (sg, None)
    while _st is not DONE:
        yield (parent, None)
        _st = yield (sg, None)
    yield (parent, DONE)
