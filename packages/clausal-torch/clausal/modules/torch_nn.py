"""clausal.modules.torch_nn — nn.Module predicates for Clausal.

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
from clausal.modules.py._helpers import _pred, _deep_deref, _pure, _fact_table_2
from clausal.modules.torch import _ensure_torch, _th


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


def _enumerate_3(iter_fn):
    """Nondeterministic enumeration: yield (name, value) pairs from iter_fn(model)."""
    def dispatch(this_generator, _proceed, _fail, _catcher, model_var, name_var, value_var, trail):
        model = deref(model_var)
        try:
            items = iter_fn(model)
        except Exception:
            yield (_fail, DONE)
            return
        for name, value in items:
            mark = trail.mark()
            if unify(name_var, name, trail) and unify(value_var, value, trail):
                yield (_proceed, None)
            trail.undo(mark)
        yield (_fail, DONE)
    return dispatch


def _fact_table_2(get_facts):
    """Nondeterministic fact table: enumerate (name, value) pairs.

    Supports modes: (+name, -value), (-name, +value), (-name, -value), (+name, +value).
    get_facts() is called lazily to build the list on first use.
    """
    cache = {}

    def dispatch(this_generator, _proceed, _fail, _catcher, name_var, value_var, trail):
        if not cache:
            facts = get_facts()
            cache["facts"] = facts
            cache["by_name"] = {n: v for n, v in facts}
            cache["by_value"] = {id(v): n for n, v in facts}
        facts = cache["facts"]
        n = deref(name_var)
        v = deref(value_var)

        if not is_var(n) and is_var(v):
            # Lookup by name
            cls = cache["by_name"].get(n)
            if cls is not None and unify(value_var, cls, trail):
                yield (_proceed, None)
        elif is_var(n) and not is_var(v):
            # Reverse lookup by value
            key = cache["by_value"].get(id(v))
            if key is not None and unify(name_var, key, trail):
                yield (_proceed, None)
        elif is_var(n) and is_var(v):
            # Enumerate all
            for name, value in facts:
                mark = trail.mark()
                if unify(name_var, name, trail) and unify(value_var, value, trail):
                    yield (_proceed, None)
                trail.undo(mark)
        else:
            # Both ground: check
            cls = cache["by_name"].get(n)
            if cls is not None and cls is v:
                yield (_proceed, None)
        yield (_fail, DONE)
    return dispatch


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
