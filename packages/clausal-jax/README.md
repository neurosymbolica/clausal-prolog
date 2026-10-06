# clausal-jax

[JAX](https://docs.jax.dev) predicates for [Clausal Prolog](https://github.com/neurosymbolica/clausal-prolog).

Wraps JAX as Clausal Prolog predicates: arrays (creation, math, shape
operations, linear algebra, FFT), PRNG and sampling, function transforms,
pytrees, sharding, `jax.scipy`, activations and initializers, and the
optional Optax, Equinox and Flax layers.

## Install

```
pip install clausal-jax
```

`jax` and `jaxlib` are pulled in as dependencies. Optax, Equinox
and Flax are extras: `pip install "clausal-jax[optax,equinox,flax]"`. Requires Python 3.13 or later.

## Use

Import the predicates into a seam (`.seam`) module, as the package's own
tests do. A Clausal Prolog (`.clausal`) module reaches Python only through
the seam: put the imports in a `.seam` module and list it under
`[tool.clausal] python_bridges` in your project's `pyproject.toml` (see
[Importing Prolog](https://github.com/neurosymbolica/clausal-prolog/blob/main/docs/importing_prolog.md)).

This test, from [`tests/fixtures/jax_array_tests.seam`](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-jax/tests/fixtures/jax_array_tests.seam),
shows the shape of a call:

```seam
-import_from(jax, [array, shape])

test("array from list") <- (
    array([1.0, 2.0, 3.0], A),
    shape(A, [3])
)
```

## Documentation

- [jax — JAX Array Operations](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-jax/docs/jax.md)
- [jax_equinox — Equinox Layers, Filter Transforms, Pytree Utilities](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-jax/docs/jax_equinox.md)
- [jax_flax — Flax Linen Models, Init, Apply](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-jax/docs/jax_flax.md)
- [jax_nn — JAX Activations and Initializers](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-jax/docs/jax_nn.md)
- [jax_optax — Optimisers, Schedules, Losses (Optax)](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-jax/docs/jax_optax.md)
- [jax_random — JAX PRNG and Sampling](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-jax/docs/jax_random.md)
- [jax_scipy — JAX Special Functions and Distributions](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-jax/docs/jax_scipy.md)
- [jax_sharding — JAX Device Placement and Sharding](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-jax/docs/jax_sharding.md)
- [jax_transforms — JAX Function Transforms](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-jax/docs/jax_transforms.md)
- [jax_tree — JAX Pytrees](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-jax/docs/jax_tree.md)

## License

MIT
