"""Shared dispatch helpers for Clausal Python-library wrappers.

Extracted from ``torch.py`` so that all wrappers (torch, scipy, etc.) share
the same implementations — in particular ``to_python`` (historically
``_deep_deref``, still exported under that name) which recursively unwraps
``Var`` / ``DictTerm`` / atom objects inside lists, tuples and dicts.  Its
body now lives in ``clausal.logic.to_python`` — the compiler binds the same
function as ``$to_python`` for the ``++``/f-string thunk path, and
``clausal.logic`` must not import ``clausal.modules.py`` — and is re-exported
here under both names.
"""

from __future__ import annotations

from typing import Callable

from clausal.logic.to_python import to_python, to_python_text  # noqa: F401  (re-exported)
from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py import ModulePredicate, text_result, unify_result


# ── Core helpers ────────────────────────────────────────────────────────────

def _pred(name: str, *arity_fns) -> ModulePredicate:
    p = ModulePredicate(name)
    for arity, fn in arity_fns:
        p._register(arity, fn)
    return p


def _any_unbound(val):
    """True if `val` is an unbound Var, or a list/tuple/dict containing any.

    `is_var` only sees the top level — `[Var, Var]` and `(Var, Var)` both
    return False, which is wrong for bidirectional predicates that want
    to recognise a list-of-unbound-vars as the backward-mode signal.
    """
    if is_var(val):
        return True
    if isinstance(val, (list, tuple)):
        return any(_any_unbound(e) for e in val)
    if isinstance(val, dict):
        return any(_any_unbound(v) for v in val.values())
    return False


#: The ONE outbound term → Python conversion (spec §9.1), re-exported from
#: ``clausal.logic.to_python`` — see that module for the semantics and for why
#: the body lives on the ``clausal.logic`` side.  ``_deep_deref`` is the
#: historical name, kept as an alias: the in-file callers below and the
#: out-of-tree wrapper distributions (clausal-torch, clausal-jax, …) import it
#: by that name.
_deep_deref = to_python


def _pure(fn: Callable) -> Callable:
    """Wrap a pure function: deep-deref all inputs, call fn(*inputs), unify RESULT."""
    def dispatch(this_generator, _proceed, _fail, _catcher, *args):
        trail = args[-1]
        result_var = args[-2]
        inputs = [_deep_deref(x) for x in args[:-2]]
        try:
            out = fn(*inputs)
        except Exception:
            yield (_fail, DONE)
            return
        if unify_result(result_var, out, trail):
            yield (_proceed, None)
        yield (_fail, DONE)
    return dispatch


def _property_2(getter):
    """Multi-mode property predicate: query (+X,-V) or check (+X,+V).

    ``getter(x)`` returns the property value. In query mode (V is a var),
    unify V with the value. In check mode (V is bound), succeed iff
    ``getter(x) == V``.
    """
    def dispatch(this_generator, _proceed, _fail, _catcher, x_var, value_var, trail):
        x = deref(x_var)
        v = deref(value_var)
        try:
            actual = getter(x)
        except Exception:
            yield (_fail, DONE)
            return
        if is_var(v):
            if unify(value_var, text_result(actual), trail):
                yield (_proceed, None)
        else:
            # Check mode accepts what query mode binds (a str property is
            # TEXT, so ``p(X, V), p(X, V)`` holds) as well as the bare str
            # spelling (the atom) it has always accepted.
            if actual == v or (isinstance(actual, str)
                               and _as_text(actual) == v):
                yield (_proceed, None)
        yield (_fail, DONE)
    return dispatch


def _as_text(s: str):
    """*s* (a plain str or a ``symbol``) as TEXT, the chars carrier."""
    from clausal.logic.cells import chars  # noqa: PLC0415
    return chars(str.__str__(s))


def _values_equal(a, b):
    """Equality check that tolerates array-like operands.

    Python `==` on numpy / JAX / torch arrays returns an element-wise
    bool array rather than a scalar, and `bool(array)` of a multi-
    element array raises. This helper:

    - returns True on object identity;
    - returns the result directly if `==` yields a plain bool;
    - otherwise reduces via `.all()` (numpy / JAX / torch share this).

    Any exception during comparison is treated as inequality — this
    covers unhashable or type-mismatched operands without surprises.
    """
    if a is b:
        return True
    try:
        r = (a == b)
    except Exception:
        return False
    if isinstance(r, bool):
        return r
    try:
        return bool(r.all())
    except (AttributeError, TypeError):
        try:
            return bool(r)
        except Exception:
            return False


def _bidir_2(forward, backward):
    """Bidirectional predicate: (+X,-Y) forward, (-X,+Y) backward, (+X,+Y) check.

    In check mode `unify` is tried first so structured Y terms with
    embedded Vars (e.g. ``tensor_list(X, [V1, V2])``) still work.
    ``unify`` can raise on array-typed operands (JAX / numpy /
    multi-element torch tensors — `==` yields element-wise bool), in
    which case `_values_equal` is used as a fallback.

    Uses `_deep_deref` so that list / tuple arguments with bound Vars
    inside (e.g. `stacked([A, B], 0, C)` where A and B are bound
    elsewhere) are resolved before reaching forward/backward.
    """
    def dispatch(this_generator, _proceed, _fail, _catcher, x_raw, y_raw, trail):
        x = _deep_deref(x_raw)
        y = _deep_deref(y_raw)

        if not _any_unbound(x) and _any_unbound(y):
            try:
                out = forward(x)
            except Exception:
                yield (_fail, DONE)
                return
            if unify_result(y_raw, out, trail):
                yield (_proceed, None)

        elif _any_unbound(x) and not _any_unbound(y):
            try:
                out = backward(y)
            except Exception:
                yield (_fail, DONE)
                return
            if unify_result(x_raw, out, trail):
                yield (_proceed, None)

        elif not _any_unbound(x) and not _any_unbound(y):
            try:
                out = forward(x)
            except Exception:
                yield (_fail, DONE)
                return
            mark = trail.mark()
            unified = False
            try:
                unified = unify(y_raw, text_result(out), trail)
            except Exception:
                trail.undo(mark)
                unified = _values_equal(out, y)
            if unified:
                yield (_proceed, None)

        yield (_fail, DONE)
    return dispatch


def _bidir_3_mid(forward, backward):
    """Bidirectional with a middle arg: (+X,+M,-Y) forward, (-X,+M,+Y) backward.

    Uses `_deep_deref` on X and Y so list / tuple arguments with bound
    Vars inside are resolved before reaching forward/backward.
    """
    def dispatch(this_generator, _proceed, _fail, _catcher, x_raw, mid_raw, y_raw, trail):
        x = _deep_deref(x_raw)
        m = _deep_deref(mid_raw)
        y = _deep_deref(y_raw)

        if not _any_unbound(x) and _any_unbound(y):
            try:
                out = forward(x, m)
            except Exception:
                yield (_fail, DONE)
                return
            if unify_result(y_raw, out, trail):
                yield (_proceed, None)

        elif _any_unbound(x) and not _any_unbound(y):
            try:
                out = backward(y, m)
            except Exception:
                yield (_fail, DONE)
                return
            if unify_result(x_raw, out, trail):
                yield (_proceed, None)

        elif not _any_unbound(x) and not _any_unbound(y):
            try:
                out = forward(x, m)
            except Exception:
                yield (_fail, DONE)
                return
            mark = trail.mark()
            unified = False
            try:
                unified = unify(y_raw, text_result(out), trail)
            except Exception:
                trail.undo(mark)
                unified = _values_equal(out, y)
            if unified:
                yield (_proceed, None)

        yield (_fail, DONE)
    return dispatch


def _bidir_3_split(forward, backward):
    """Bidirectional predicate that splits one value into two.

    (+X,-A,-B) forward: A, B = forward(X)
    (-X,+A,+B) backward: X = backward(A, B)
    (+X,+A,+B) check: compute forward(X), unify/value-equal vs (A, B)

    Mirror of `_bidir_2`'s check-mode fallback: `unify` can raise on
    array-typed operands; `_values_equal` is used as the fallback.
    """
    def dispatch(this_generator, _proceed, _fail, _catcher, x_raw, a_raw, b_raw, trail):
        x = _deep_deref(x_raw)
        a = _deep_deref(a_raw)
        b = _deep_deref(b_raw)

        x_unbound = _any_unbound(x)
        a_unbound = _any_unbound(a)
        b_unbound = _any_unbound(b)

        if not x_unbound and (a_unbound or b_unbound):
            try:
                out_a, out_b = forward(x)
            except Exception:
                yield (_fail, DONE)
                return
            if unify(a_raw, text_result(out_a), trail) and unify(b_raw, text_result(out_b), trail):
                yield (_proceed, None)

        elif x_unbound and not a_unbound and not b_unbound:
            try:
                out_x = backward(a, b)
            except Exception:
                yield (_fail, DONE)
                return
            if unify(x_raw, text_result(out_x), trail):
                yield (_proceed, None)

        elif not x_unbound and not a_unbound and not b_unbound:
            try:
                out_a, out_b = forward(x)
            except Exception:
                yield (_fail, DONE)
                return
            mark = trail.mark()
            unified = False
            try:
                unified = (unify(a_raw, text_result(out_a), trail)
                           and unify(b_raw, text_result(out_b), trail))
            except Exception:
                trail.undo(mark)
                unified = (_values_equal(out_a, a)
                           and _values_equal(out_b, b))
            if unified:
                yield (_proceed, None)

        yield (_fail, DONE)
    return dispatch


def _bidir_4_mid2(forward, backward):
    """Bidirectional with two middle args: (+X,+M1,+M2,-Y) forward, (-X,+M1,+M2,+Y) backward.

    Uses `_deep_deref` on X and Y and `_any_unbound` for boundness checks
    so list/tuple arguments with inner Vars route correctly.
    """
    def dispatch(this_generator, _proceed, _fail, _catcher, x_raw, m1_raw, m2_raw, y_raw, trail):
        x = _deep_deref(x_raw)
        m1 = _deep_deref(m1_raw)
        m2 = _deep_deref(m2_raw)
        y = _deep_deref(y_raw)

        if not _any_unbound(x) and _any_unbound(y):
            try:
                out = forward(x, m1, m2)
            except Exception:
                yield (_fail, DONE)
                return
            if unify_result(y_raw, out, trail):
                yield (_proceed, None)

        elif _any_unbound(x) and not _any_unbound(y):
            try:
                out = backward(y, m1, m2)
            except Exception:
                yield (_fail, DONE)
                return
            if unify_result(x_raw, out, trail):
                yield (_proceed, None)

        elif not _any_unbound(x) and not _any_unbound(y):
            try:
                out = forward(x, m1, m2)
            except Exception:
                yield (_fail, DONE)
                return
            mark = trail.mark()
            unified = False
            try:
                unified = unify(y_raw, text_result(out), trail)
            except Exception:
                trail.undo(mark)
                unified = _values_equal(out, y)
            if unified:
                yield (_proceed, None)

        yield (_fail, DONE)
    return dispatch


def _check_1(predicate_fn):
    """Check predicate on one value: succeed if predicate_fn(x) is truthy."""
    def dispatch(this_generator, _proceed, _fail, _catcher, x_var, trail):
        x = _deep_deref(deref(x_var))
        try:
            if predicate_fn(x):
                yield (_proceed, None)
        except Exception:
            pass
        yield (_fail, DONE)
    return dispatch


def _check_2(predicate_fn):
    """Check predicate on two values: succeed if predicate_fn(a, b) is truthy."""
    def dispatch(this_generator, _proceed, _fail, _catcher, a_var, b_var, trail):
        a = _deep_deref(deref(a_var))
        b = _deep_deref(deref(b_var))
        try:
            if predicate_fn(a, b):
                yield (_proceed, None)
        except Exception:
            pass
        yield (_fail, DONE)
    return dispatch


def _check_4(predicate_fn):
    """Check predicate on four values: succeed if predicate_fn(a, b, c, d) is truthy."""
    def dispatch(this_generator, _proceed, _fail, _catcher, a_var, b_var, c_var, d_var, trail):
        a = _deep_deref(deref(a_var))
        b = _deep_deref(deref(b_var))
        c = _deep_deref(deref(c_var))
        d = _deep_deref(deref(d_var))
        try:
            if predicate_fn(a, b, c, d):
                yield (_proceed, None)
        except Exception:
            pass
        yield (_fail, DONE)
    return dispatch


def _check_axis_1(fn):
    """Check predicate with an axis/dim int arg: succeed if fn(x, axis) is truthy."""
    def dispatch(this_generator, _proceed, _fail, _catcher, x_var, axis_var, trail):
        x = _deep_deref(deref(x_var))
        try:
            axis = int(deref(axis_var))
        except Exception:
            yield (_fail, DONE)
            return
        try:
            if fn(x, axis):
                yield (_proceed, None)
        except Exception:
            pass
        yield (_fail, DONE)
    return dispatch


def _text_arg(val):
    """*val* dereferenced, with a STRING read as the ``str`` it denotes.

    The input-side shape for an adapter position that takes a name or other
    text but is not routed through :func:`to_python`: an atom is already
    its ``str``, and a string -- the chars carrier ``('$chars', s)`` --
    becomes ``s``, so ``f(foo)`` and ``f("foo")`` reach the library alike
    (spec §9.4).  Anything else (an unbound variable, a number, a list, a
    compound) comes back dereferenced and otherwise untouched, so a
    caller's mode test (``is_var``) and its non-text handling are unchanged.
    """
    from clausal.logic.cells import CHARS_TAG  # noqa: PLC0415
    val = deref(val)
    # Type-check the tag before comparing it: an argument may be a pair of
    # arrays (an LU factorisation), whose ``==`` is elementwise.
    if (type(val) is tuple and len(val) == 2 and type(val[0]) is str
            and val[0] == CHARS_TAG and type(val[1]) is str):
        return val[1]
    return val


def _fact_table_2(get_facts):
    """Nondeterministic fact table: enumerate (name, value) pairs.

    Supports modes: (+name, -value), (-name, +value), (-name, -value), (+name, +value).
    get_facts() is called lazily to build the list on first use.  A bound
    name may be an atom or a string (:func:`_text_arg`); both match the
    fact of that spelling.  A bound VALUE matches an opaque fact value (a
    class, a function) by identity; a TEXT fact value (a string, as a
    path registry holds) matches by its text, so a bound atom or string of
    the same spelling finds it.  ``dispatch.cache`` is the lazily filled
    cache (tests reset it).
    """
    cache = {}

    def _text_of(val):
        t = _text_arg(val)
        return t if type(t) is str else None

    def _value_matches(fact_value, v):
        if fact_value is v:
            return True
        ft = _text_of(fact_value)
        return ft is not None and ft == _text_of(v)

    def dispatch(this_generator, _proceed, _fail, _catcher, name_var, value_var, trail):
        if not cache:
            facts = get_facts()
            cache["facts"] = facts
            cache["by_name"] = {n: v for n, v in facts}
            cache["by_value"] = {id(v): n for n, v in facts}
        n = _text_arg(name_var)
        v = deref(value_var)

        if not is_var(n) and is_var(v):
            cls = cache["by_name"].get(n)
            if cls is not None and unify(value_var, cls, trail):
                yield (_proceed, None)
        elif is_var(n) and not is_var(v):
            key = cache["by_value"].get(id(v))
            if key is None and _text_of(v) is not None:
                key = next((name for name, value in cache["facts"]
                            if _value_matches(value, v)), None)
            if key is not None and unify(name_var, key, trail):
                yield (_proceed, None)
        elif is_var(n) and is_var(v):
            for name, value in cache["facts"]:
                mark = trail.mark()
                if unify(name_var, name, trail) and unify(value_var, value, trail):
                    yield (_proceed, None)
                trail.undo(mark)
        else:
            cls = cache["by_name"].get(n)
            if cls is not None and _value_matches(cls, v):
                yield (_proceed, None)
        yield (_fail, DONE)
    dispatch.cache = cache
    return dispatch
