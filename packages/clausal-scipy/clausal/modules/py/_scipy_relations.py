"""Shared bidirectional dispatch infrastructure for scipy relation predicates."""

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE


def _bidir_dispatch(fwd_call, bwd_call, n_fixed=0):
    """Trampoline dispatch for a bidirectional predicate.

    args layout: (fixed_0, ..., fixed_{n_fixed-1}, x_raw, result_var, trail)

    n_fixed args are leading and always ground (e.g. 'a' in gamma_inc(A,X,Y)).
    x_raw and result_var are the variable pair.
    """
    def dispatch(this_generator, _proceed, _fail, _catcher, *args):
        trail   = args[-1]
        fixed   = [deref(args[i]) for i in range(n_fixed)]
        x_raw   = args[n_fixed]           # forward input / backward output
        y_raw   = args[n_fixed + 1]       # result var (forward output / backward input)
        x       = deref(x_raw)
        y       = deref(y_raw)

        if not is_var(x) and is_var(y):
            out = fwd_call(*fixed, x)
            if unify(y_raw, out, trail):
                yield (_proceed, None)

        elif is_var(x) and not is_var(y):
            out = bwd_call(*fixed, y)
            if unify(x_raw, out, trail):
                yield (_proceed, None)

        elif not is_var(x) and not is_var(y):
            # both ground: consistency check via forward
            # unify may raise ValueError/TypeError for numpy arrays — treat as failure
            out = fwd_call(*fixed, x)
            try:
                ok = bool(unify(y_raw, out, trail))
            except (ValueError, TypeError):
                ok = False
            if ok:
                yield (_proceed, None)

        # both unbound: fail silently
        yield (_fail, DONE)
    return dispatch


def _fft_bidir_n(fwd_fn, bwd_fn):
    """Bidirectional dispatch for arity-3 FFT forms: (X, N, RESULT).

    N sits between the two variable args, so n_fixed cannot be used.
    N must always be ground; X and RESULT are the variable pair.
    """
    def dispatch(this_generator, _proceed, _fail, _catcher, x_raw, n_raw, result_var, trail):
        n = deref(n_raw)
        x = deref(x_raw)
        y = deref(result_var)

        if not is_var(x) and is_var(y):
            out = fwd_fn(x, n)
            if unify(result_var, out, trail):
                yield (_proceed, None)

        elif is_var(x) and not is_var(y):
            out = bwd_fn(y, n)
            if unify(x_raw, out, trail):
                yield (_proceed, None)

        elif not is_var(x) and not is_var(y):
            # both ground: consistency check via forward
            # unify may raise ValueError/TypeError for numpy arrays — treat as failure
            out = fwd_fn(x, n)
            try:
                ok = bool(unify(result_var, out, trail))
            except (ValueError, TypeError):
                ok = False
            if ok:
                yield (_proceed, None)

        yield (_fail, DONE)
    return dispatch
