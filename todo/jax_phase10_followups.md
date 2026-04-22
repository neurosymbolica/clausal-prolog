# JAX Phase 10 — follow-ups

Deferred items from Phase 10 review (2026-04-21). None block
Phases 11+.

---

## 1. Applied-activation tests rely on exact float equality

**Affects:** `tanh at 0 is 0`, `silu at 0 is 0`, `relu leaves positives
unchanged`, `leaky_relu custom slope`, similar integer-valued spot-checks
in `tests/fixtures/jax_nn_tests.clausal`.

**What's OK:** the tests pass today because each checked value is an
algebraic identity or an integer-arithmetic result (e.g. tanh(0) = 0
exactly; `leaky_relu(x, 0.5)` of `[-10.0, 0.0, 5.0]` is `[-5.0, 0.0,
5.0]` bit-exact). JAX itself is deterministic given the same input and
key, so `array_list(R, EXACT_LIST)` matches.

**The risk:** if a future JAX release inlines one of these activations
into a fused kernel with slightly different ordering, last-ULP drift
could break the tests in a hard-to-diagnose way. The Phase 5 / Phase 7
bijection tests already hit this (see
`todo/jax_wrapper_followups.md#1`).

**Fix when it matters:** switch exact `array_list/2` compares to
`allclose(R, EXPECTED, 1e-6, 0.0)` as a reflex for any value derived
from floating-point math, even if the "clean" value is a small
integer. Integer-dtype tests (e.g. `one_hot`) can keep exact equality.

---

## 2. PyTorch-to-JAX default-parameter drift

**Affects:** `leaky_relu_apply`, `gelu_apply`, `elu_apply`,
`softmax_apply`, `log_softmax_apply`.

**What's OK:** defaults in `jax.nn` happen to match PyTorch's in all
cases we exercise (e.g. `leaky_relu` slope is 0.01 on both sides).

**The risk:** a migrator coming from PyTorch might *assume* defaults
match without checking. Example: `gelu_apply(A, R)` uses
`approximate=False` (exact), while `torch.nn.functional.gelu(x)` also
defaults to exact since PyTorch 1.10 — same default, but the
`approximate=` kwarg is a string in torch (`"none"`, `"tanh"`) and a
bool in JAX.

**Fix when it matters:** add a "Defaults cheatsheet" section to
`docs/jax_nn.md` listing each activation's default alongside the
PyTorch equivalent. Small, stable reference — worth writing before the
first migrator files an issue.

---

## 3. No integration test for `jax_tree` + `jax_nn` composition

**Affects:** `docs/jax_nn.md` describes "initialise a parameter
pytree" as the payoff of combining Phase 9 + Phase 10, but nothing
actually exercises that combination.

**What's OK:** the individual phases are independently tested, and
the composition is straightforward Python wrapped in Clausal
predicates — unlikely to silently break.

**The risk:** documentation rot. If a future phase adjusts pytree or
initializer semantics, the "it's just composition" assumption might
stop holding, and there's no test to catch it.

**Fix when it matters:** add `tests/fixtures/jax_nn_tree_integration.clausal`
with one or two end-to-end tests:

```clausal
Test("init a two-layer param pytree") <- (
    initializer("glorot_uniform", F),
    key(0, K),
    split_key(K, 2, [K1, K2]),
    init_array(F, K1, [10, 5], W1),
    init_array(F, K2, [5, 3], W2),
    PARAMS is ++({"layer1": {"w": W1}, "layer2": {"w": W2}}),
    findall(L, leaf(PARAMS, L), LEAVES),
    length(LEAVES, 2)
)
```

Add the class in `tests/test_jax_infra.py`. Lightweight; runs in
milliseconds; catches cross-phase regressions.

---

## Status

- Phase 10 shipped without these items (they are polish, not
  correctness).
- Re-check before Phase 11 if a user reports confusion or a test
  flake; otherwise revisit when a nearby phase touches the same
  surface.
