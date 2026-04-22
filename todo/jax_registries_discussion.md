# JAX/Torch wrapper — registry audit

A registry in this codebase is a `_fact_table_2`-backed predicate
that exposes a `(NAME, VALUE)` lookup table — typically used to
discover library entities (activations, optimisers, layer classes)
or to look one up by name. They're cheap to write and easy to
reach for, so they accumulate.

This doc inventories every existing registry and notes which ones
have a real **name-as-data** use case versus those that exist only
for symmetry. Triggered by the Phase 17 design discussion: the first
draft proposed a `layer/3,/4` constructor backed by a registry, and
recognising that as the wrong shape prompted a wider sweep.

The audit was done at commit `72cc07e` (after the Phase 16 +
pre-Phase-17 `apply_updates` lift).

---

## What makes a registry "necessary"?

Three patterns count as legitimate:

1. **Registry IS the construction surface.** No per-class predicate
   exists or makes sense; users always go through the registry. Most
   distribution wrappers fit this pattern — `pdf("norm", X, OPTS, R)`
   takes the distribution name as data, and there's no
   `pdf_norm/3` alternative.

2. **Name-as-data lookup.** A common use case is *parameterising
   the entity by name*, e.g. reading "adam" from a config file and
   constructing the optimiser from that name. Per-class predicates
   may exist for ergonomics, but the registry serves a separate
   workflow.

3. **Enumeration is the goal.** Users genuinely run
   `findall(N, activation(N, _), NS)` to discover what's available.
   This typically overlaps with (2) — if you need to enumerate, you
   probably also need to look up by name.

A registry that fails all three is **redundant** — a per-class set
of predicates does the work, the call-site cost of the registry form
is *higher* than the per-class form, and nobody actually enumerates
the table.

---

## Inventory (commit `72cc07e`)

| Registry | Module | Per-class alts? | Real use case? | Verdict |
|---|---|---|---|---|
| `distribution/2` | `py.jax_scipy` | No — `pdf`/`cdf` take name as positional arg | Yes (1) | **Necessary** |
| `distribution/2` | `py.torch_distributions` | No | Yes (1) | **Necessary** |
| `layer/2` | `py.torch_nn` | No — torch construction goes through `++()` deliberately | Yes (1) — discovery surface for an imperative library | **Necessary** for that style |
| `initializer/2` | `py.jax_nn` | No — initializers are factory functions consumed by name | Yes (1, 2) | **Necessary** |
| `sampler/2` | `py.jax_random` | Yes (`normal/3`, `uniform/3`, …) | Yes (2) — name-from-config | **Keep** |
| `activation/2` | `py.jax_nn` | Yes (`relu_apply`, `gelu_apply`, …) | Yes (2) — also feeds `init_array` activation lookup | **Keep** |
| `activation/2` | `py.torch_nn` | No — relies on registry + `++()` per torch style | Yes (1, 2) | **Keep** |
| `loss_fn/2` | `py.torch_nn` | No | Yes (1, 2) | **Keep** |
| `optimizer_type/2` | `py.torch_nn` | No | Yes (1, 2) | **Keep** |
| `scheduler_type/2` | `py.torch_nn` | No | Yes (1, 2) | **Keep** |
| `optimizer/2` | `py.jax_optax` | Yes (`sgd/2`, `adam/2`, …) | Yes (2) — fixture exercises name-from-config: `optimizer("sgd", CTOR), OPT is ++(CTOR(0.1))` | **Keep** |
| `schedule/2` | `py.jax_optax` | Yes (`cosine_decay_schedule`, …) | Yes (2) — schedule name from config is plausible | **Keep** |
| `loss_function/2` | `py.jax_optax` | Yes (`softmax_cross_entropy`, …) | Yes (2) — loss name from config is common | **Keep** |
| `gradient_transform/2` | `py.jax_optax` | Yes (`clip`, `scale`, `ema`, `chain`, …) | **No** — gradient transforms are composed in code (`chain([clip(1.0), adam(0.001)])`), not selected by name from config. Fixture only checks names exist; never instantiates from the registry. | **Suspect — exists for symmetry** |

---

## The Phase 17 lesson

The original Phase 17 plan proposed `layer/3,/4` plus
`layer_class/2` as the construction surface for Equinox's 43 `nn.*`
classes. The argument was "per-class would balloon the wrapper to
80+ entries." User counter: 43 classes is no big deal, and the
call-site cost of the registry form is higher (string name +
runtime-validated kwargs dict) than per-class predicates with named
positional args.

That logic generalises. A registry adds value when:

- there's no per-class alternative (distributions, initializers); or
- the name *is* a piece of data the user manipulates (optimiser
  selection from config).

It does not add value just because other registries near it exist.
"Symmetry with neighbouring registries" is the same anti-pattern as
"uniformity of the dispatcher" — both are wrapper-side conveniences
that users don't see.

---

## Candidate for removal: `py.jax_optax.gradient_transform/2`

The only registry in the inventory that fails all three legitimacy
tests:

- **No name-as-data use case.** Gradient transforms compose
  positionally with `chain`. Nobody reads "clip_by_global_norm" from
  a config file and looks it up by name.
- **No enumeration use case.** The fixture's
  `gradient_transform registry has known names` test calls
  `gradient_transform("clip_by_global_norm", _)` for four names —
  it doesn't `findall` over the registry, doesn't `++(CTOR(...))` to
  construct, doesn't do anything beyond verifying presence. That's
  testing a symmetry, not a workflow.
- **Per-class alternatives exist.** Every entry in the registry has
  a corresponding per-class predicate (`clip/2`,
  `clip_by_global_norm/2`, `ema/2`, `scale/2`, etc.).

**Cost of removal:** delete `gradient_transform = _pred(...)` from
`jax_optax.py`, drop it from `__all__`, drop the
`_GRADIENT_TRANSFORM_NAMES` tuple, remove the
`gradient_transform registry has known names` test (and its name
from the test_jax_infra.py parametrize list), update the
`docs/jax_optax.md` registry table. ~20 lines total.

**Cost of keeping it:** ~20 lines of dead code that future
maintainers will pattern-match and copy when adding a new sibling
registry, propagating the anti-pattern.

Lean: remove it as a small follow-up commit, keep the other three
Phase 16 registries (`optimizer`, `schedule`, `loss_function`) since
each has a fixture test exercising the name-from-config pattern.

---

## Borderline: do `optimizer/2`, `schedule/2`, `loss_function/2`
## need separate registries, or one `named_thing/3` lookup?

A future cleanup could collapse them:

```clausal
named(optimizer, "adam", CTOR)    % was: optimizer("adam", CTOR)
named(schedule, "cosine_decay_schedule", CTOR)
named(loss, "softmax_cross_entropy", FN)
```

The collapsed form is more uniform but loses a free
auto-completion / type-safety dimension (you can't get a schedule
when you ask for an optimiser). And it doesn't actually *reduce*
code — there's still one `_FOO_NAMES` tuple per kind.

Verdict: not worth it. The three registries are cheap to keep
separate, and `optimizer/2` reads better than `named(optimizer, ...)`
at the call site. Document this decision so it's not relitigated.

---

## When to add a new registry

Before adding `_fact_table_2(...)` to a new module, ask:

1. Do users construct entries with the name as data, or with the
   per-class predicate?
2. Will anyone `findall` over this table, or test it just for
   symmetry?
3. If a per-class set exists already, what does the registry add
   beyond a runtime kwargs dict?

If the answers are "per-class" / "just symmetry" / "nothing real" —
don't add the registry.

---

## Action items

- [ ] **Remove `gradient_transform/2`** from `py.jax_optax`. Cost
  ~20 lines, no caller depends on it. Suggested as a small standalone
  commit.
- [ ] (Optional, not now) Capture this audit's "when to add a
  registry" checklist somewhere user-facing — maybe in the wrapper
  authoring section of the docs, or in the
  `EXTERNAL_WRAPPER_CHECKLIST.md` if that's the right home.
