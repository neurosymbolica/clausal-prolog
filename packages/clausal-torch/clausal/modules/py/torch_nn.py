"""clausal.modules.py.torch_nn — nn.Module predicates for Clausal.

Provides nondeterministic enumeration of PyTorch nn.Module structure and
registry fact tables for layers, activations, losses, optimizers, and
LR schedulers::

    -import_from(torch_nn, [parameter, named_parameter, module,
                                named_module, child, named_child,
                                layer, activation, loss_fn, optimizer_type,
                                scheduler_type, current_lr,
                                clip_grad_norm, clip_grad_value])

Module enumeration
------------------
parameter(MODEL, PARAM)            Enumerate all parameter tensors.
named_parameter(MODEL, NAME, PARAM) Parameters with names.
module(MODEL, SUBMODULE)            All submodules (recursive).
named_module(MODEL, NAME, SUBMOD)   Submodules with names.
child(MODEL, CHILD)                 Direct children only.
named_child(MODEL, NAME, CHILD)     Direct children with names.

Registries (fact tables)
------------------------
layer(NAME, CLASS)                  Available nn.Module layer types.
activation(NAME, CLASS)             Activation modules (nn.ReLU, etc.).
loss_fn(NAME, CLASS)                Loss functions (nn.CrossEntropyLoss, etc.).
optimizer_type(NAME, CLASS)         Optimizer types (Adam, SGD, etc.).
scheduler_type(NAME, CLASS)         LR scheduler types (StepLR, etc.).

Scheduler queries
-----------------
current_lr(SCHEDULER, LRs)         Get current learning rate(s).

Gradient utilities (impure)
----------------------------
clip_grad_norm(PARAMS, MAX_NORM, NORM_TYPE, TOTAL_NORM)
                                    Clip gradient norms in-place.
clip_grad_value(PARAMS, CLIP_VALUE) Clip gradient values in-place.

Names use the original PyTorch class names (e.g. "Linear", "ReLU",
"CrossEntropyLoss", "Adam", "StepLR").
"""

from __future__ import annotations

import threading as _threading

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py._helpers import (
    _pred, _deep_deref, _pure, _fact_table_2, _text_arg,
)
from clausal.modules.py.torch import _ensure_torch, _th


# ── Helpers ──────────────────────────────────────────────────────────────


def _enumerate_2(iter_fn):
    """Nondeterministic enumeration: yield each element from iter_fn(model)."""
    def dispatch(this_generator, _proceed, _fail, _catcher, model_var, elem_var, trail):
        model = deref(model_var)
        try:
            items = iter_fn(model)
        except Exception:
            yield (_fail, DONE)
            return
        for item in items:
            mark = trail.mark()
            if unify(elem_var, item, trail):
                yield (_proceed, None)
            trail.undo(mark)
        yield (_fail, DONE)
    return dispatch


_UNBOUND = object()


def _enumerate_3(iter_fn):
    """Nondeterministic enumeration: yield (name, value) pairs from iter_fn(model).

    A NAME is an atom on the way out (a module path such as ``'0.weight'``
    is a symbolic name), but a bound name may be given as an atom OR a
    string (spec §9.4, "text in"): :func:`_text_arg` reads the chars
    carrier ``('$chars', s)`` as ``s``, so ``named_parameter(M, "0.weight",
    P)`` selects the same entry as ``named_parameter(M, '0.weight', P)``.
    Only a bound TEXT name is compared by its text; anything else (an
    unbound variable, a number, a compound) still goes through ``unify``.

    A bound VALUE is matched by IDENTITY: a parameter or a submodule is an
    object, and ``unify`` would compare two tensors with ``==``, whose
    elementwise answer raises ("Boolean value of Tensor with more than one
    value is ambiguous") instead of failing.  So ``named_parameter(M, N,
    P)`` with ``P`` bound answers the name of that very parameter.
    """
    def dispatch(this_generator, _proceed, _fail, _catcher, model_var, name_var, value_var, trail):
        model = deref(model_var)
        try:
            items = iter_fn(model)
        except Exception:
            yield (_fail, DONE)
            return
        want = _text_arg(name_var)
        if type(want) is not str:
            want = None
        bound = deref(value_var)
        if is_var(bound):
            bound = _UNBOUND
        for name, value in items:
            if want is not None and name != want:
                continue
            if bound is not _UNBOUND and bound is not value:
                continue
            mark = trail.mark()
            if ((want is not None or unify(name_var, name, trail))
                    and (bound is not _UNBOUND
                         or unify(value_var, value, trail))):
                yield (_proceed, None)
            trail.undo(mark)
        yield (_fail, DONE)
    return dispatch


# ``_fact_table_2`` is the engine's (imported above); it reads a string
# name as its text, so ``"Linear"`` and ``Linear`` both match.


# ── Registry builders ────────────────────────────────────────────────────

_ACTIVATION_NAMES = frozenset([
    "CELU", "ELU", "GELU", "GLU", "Hardshrink", "Hardsigmoid", "Hardswish",
    "Hardtanh", "LeakyReLU", "LogSoftmax", "Mish", "PReLU", "ReLU", "ReLU6",
    "SELU", "SiLU", "Sigmoid", "Softmax", "Softmax2d", "Softplus",
    "Softshrink", "Softsign", "Tanh", "Tanhshrink", "Threshold",
])


def _build_layer_facts():
    """Build (name, class) pairs for all nn.Module subclasses."""
    _ensure_torch()
    nn = _th().nn
    facts = []
    for name in sorted(dir(nn)):
        if name.startswith("_"):
            continue
        cls = getattr(nn, name, None)
        if isinstance(cls, type) and issubclass(cls, nn.Module):
            facts.append((name, cls))
    return facts


def _build_activation_facts():
    """Build (name, class) pairs for activation modules."""
    _ensure_torch()
    nn = _th().nn
    return [(name, getattr(nn, name)) for name in sorted(_ACTIVATION_NAMES)
            if hasattr(nn, name)]


def _build_loss_facts():
    """Build (name, class) pairs for loss modules."""
    _ensure_torch()
    nn = _th().nn
    return [(name, getattr(nn, name)) for name in sorted(dir(nn))
            if not name.startswith("_")
            and isinstance(getattr(nn, name, None), type)
            and issubclass(getattr(nn, name), nn.Module)
            and "Loss" in name]


def _build_optimizer_facts():
    """Build (name, class) pairs for optimizer types."""
    _ensure_torch()
    optim = _th().optim
    return [(name, getattr(optim, name)) for name in sorted(dir(optim))
            if not name.startswith("_")
            and isinstance(getattr(optim, name, None), type)
            and issubclass(getattr(optim, name), optim.Optimizer)
            and name != "Optimizer"]


# ═══════════════════════════════════════════════════════════════════════════
# Module enumeration predicates
# ═══════════════════════════════════════════════════════════════════════════

parameter = _pred("parameter",
    (2, _enumerate_2(lambda m: m.parameters())),
)

named_parameter = _pred("named_parameter",
    (3, _enumerate_3(lambda m: m.named_parameters())),
)

module = _pred("module",
    (2, _enumerate_2(lambda m: m.modules())),
)

named_module = _pred("named_module",
    (3, _enumerate_3(lambda m: m.named_modules())),
)

child = _pred("child",
    (2, _enumerate_2(lambda m: m.children())),
)

named_child = _pred("named_child",
    (3, _enumerate_3(lambda m: m.named_children())),
)


# ═══════════════════════════════════════════════════════════════════════════
# Registry fact tables
# ═══════════════════════════════════════════════════════════════════════════

layer = _pred("layer",
    (2, _fact_table_2(_build_layer_facts)),
)

activation = _pred("activation",
    (2, _fact_table_2(_build_activation_facts)),
)

loss_fn = _pred("loss_fn",
    (2, _fact_table_2(_build_loss_facts)),
)

optimizer_type = _pred("optimizer_type",
    (2, _fact_table_2(_build_optimizer_facts)),
)


# ═══════════════════════════════════════════════════════════════════════════
# LR Scheduler registry and queries (Phase 12)
# ═══════════════════════════════════════════════════════════════════════════

def _build_scheduler_facts():
    """Build (name, class) pairs for LR scheduler types."""
    _ensure_torch()
    sched = _th().optim.lr_scheduler
    base = sched.LRScheduler
    return [(name, getattr(sched, name)) for name in sorted(dir(sched))
            if not name.startswith("_")
            and isinstance(getattr(sched, name, None), type)
            and issubclass(getattr(sched, name), base)
            and name != "LRScheduler"]


scheduler_type = _pred("scheduler_type",
    (2, _fact_table_2(_build_scheduler_facts)),
)


def _property_2(getter):
    """Property predicate: (+obj, -value) or (+obj, +value) check."""
    def dispatch(this_generator, _proceed, _fail, _catcher, obj_var, value_var, trail):
        obj = deref(obj_var)
        v = deref(value_var)
        try:
            actual = getter(obj)
        except Exception:
            yield (_fail, DONE)
            return
        if is_var(v):
            if unify(value_var, actual, trail):
                yield (_proceed, None)
        else:
            if actual == v:
                yield (_proceed, None)
        yield (_fail, DONE)
    return dispatch


current_lr = _pred("current_lr",
    (2, _property_2(lambda s: s.get_last_lr())),
)


# ═══════════════════════════════════════════════════════════════════════════
# Gradient utilities (impure — Phase 12)
# ═══════════════════════════════════════════════════════════════════════════

clip_grad_norm = _pred("clip_grad_norm",
    (3, _pure(lambda params, max_norm:
              _th().nn.utils.clip_grad_norm_(list(params), max_norm))),
)


def _clip_grad_value_dispatch(this_generator, _proceed, _fail, _catcher, params_var, clip_var, trail):
    """Impure: clip gradient values in-place, always succeeds."""
    params = _deep_deref(params_var)
    clip_value = deref(clip_var)
    try:
        _th().nn.utils.clip_grad_value_(list(params), clip_value)
    except Exception:
        yield (_fail, DONE)
        return
    yield (_proceed, None)
    yield (_fail, DONE)


clip_grad_value = _pred("clip_grad_value",
    (2, _clip_grad_value_dispatch),
)


# ── Module-level exports ──────────────────────────────────────────────────

__all__ = [
    "parameter", "named_parameter",
    "module", "named_module",
    "child", "named_child",
    "layer", "activation", "loss_fn", "optimizer_type",
    "scheduler_type", "current_lr",
    "clip_grad_norm", "clip_grad_value",
]
