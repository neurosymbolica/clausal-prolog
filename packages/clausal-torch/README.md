# clausal-torch

[PyTorch](https://pytorch.org) predicates for [Clausal Prolog](https://github.com/neurosymbolica/clausal-prolog).

Wraps PyTorch as Clausal Prolog predicates: tensors (creation, math,
shape operations, comparisons, conversions), `nn` module structure and
gradient utilities, `nn.functional`, probability distributions and
datasets.

## Install

```
pip install clausal-torch
```

`torch` is pulled in as a dependency. Requires Python 3.13 or later.

## Use

Import the predicates into a seam (`.seam`) module, as the package's own
tests do. A Clausal Prolog (`.clausal`) module reaches Python only through
the seam: put the imports in a `.seam` module and list it under
`[tool.clausal] python_bridges` in your project's `pyproject.toml` (see
[Importing Prolog](https://github.com/neurosymbolica/clausal-prolog/blob/main/docs/importing_prolog.md)).

This test, from [`tests/fixtures/torch_comparison_tests.seam`](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-torch/tests/fixtures/torch_comparison_tests.seam),
shows the shape of a call:

```seam
-import_from(torch, [tensor, eq, tensor_list])

test("eq element-wise") <- (
    tensor([1.0, 2.0, 3.0], A),
    tensor([1.0, 0.0, 3.0], B),
    eq(A, B, C),
    tensor_list(C, [True, False, True])
)
```

## Documentation

- [torch — PyTorch Tensor Operations](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-torch/docs/torch.md)
- [torch_data — Datasets](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-torch/docs/torch_data.md)
- [torch_distributions — Probability Distributions](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-torch/docs/torch_distributions.md)
- [torch_functional — nn.functional](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-torch/docs/torch_functional.md)
- [torch_nn — Module Structure, Registries, and Gradient Utilities](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-torch/docs/torch_nn.md)

## License

MIT
