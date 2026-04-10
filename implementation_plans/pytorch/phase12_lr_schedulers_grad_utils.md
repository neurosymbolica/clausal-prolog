# Phase 12 — Learning Rate Schedulers and Gradient Utilities

Thin wrappers for queryable aspects of LR schedulers and gradient
utilities. The mutation-heavy parts (`.step()`, `clip_grad_norm_`) stay
as `++()` — this phase wraps only the relational/queryable surface.

**Depends on:** Phase 3 — `clausal/modules/py/torch_nn.py` for
`_fact_table_2()` registry pattern.

**File to modify:** `clausal/modules/py/torch_nn.py`

---

## Predicates

### Scheduler registry

| Name | Arity | Modes | Nondet? | Description |
|---|---|---|---|---|
| `scheduler_type` | `/2` | `(+name, -class)`, `(-name, -class)` | yes | Available scheduler types |

### Scheduler queries (read-only)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `current_lr` | `/2` | `(+scheduler, -LRs)` | Get current learning rate(s) |

### Gradient utilities (impure — documented as such)

| Name | Arity | Modes | Purity | Description |
|---|---|---|---|---|
| `clip_grad_norm` | `/4` | `(+params, +max_norm, -total_norm)` | impure | Clip gradient norms in-place |
| `clip_grad_value` | `/3` | `(+params, +clip_value)` | impure | Clip gradient values in-place |

---

## Context and Reference Patterns

`scheduler_type/2` follows the `_fact_table_2()` pattern from Phase 3.
Introspect `torch.optim.lr_scheduler`:

```python
def _build_scheduler_facts():
    sched = _ensure_torch().optim.lr_scheduler
    facts = []
    for name in dir(sched):
        cls = getattr(sched, name)
        if isinstance(cls, type) and issubclass(cls, sched.LRScheduler):
            facts.append((name, cls))
    return facts
```

`current_lr/2` is a pure query on a scheduler object:

```python
current_lr = _pred("current_lr",
    (2, _property_2(lambda s: s.get_last_lr())),
)
```

Gradient utilities are impure (they modify tensors in-place) but are
commonly needed at the boundary of training loops. Document as impure.

---

## Example Usage

```clausal
-import_from(py.torch_nn, [scheduler_type])

Test("enumerate schedulers") <- (
    findall(N, scheduler_type(N, _), NS),
    in_("StepLR", NS),
    in_("CosineAnnealingLR", NS)
)
```

---

## Tests

**`.clausal` integration tests** (`tests/fixtures/torch_schedulers_tests.clausal`):
- Scheduler registry enumeration
- Known scheduler types present (StepLR, CosineAnnealingLR, etc.)

---

## Docs

Update `docs/torch_nn.md` with scheduler registry.
Note gradient utilities as impure.

---

## Issues

_To be populated during implementation._
