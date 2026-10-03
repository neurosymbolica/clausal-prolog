# clausal-torch: package-suite failures triaged (2026-10-04)

Box run on 1c5ee5a0: **27 failed**. After feat/package-followups-2026-10-04:
**0 failed** locally (CPU torch); confirm on the box (CUDA torch).

| Group | Class | Count | Representative node id | Status |
|---|---|---|---|---|
| `-import_module(torch)` names py.torch (bare `torch` -> `py.torch` alias), so `MODEL is torch.nn.Linear(10, 5)` raised NameError | ENGINE-SEMANTICS DRIFT | 25 | `packages/clausal-torch/tests/fixtures/torch_nn_tests.seam::named_child names` | fixed: py.torch's module `__getattr__` falls back to PyTorch for a public name it does not define |
| `T is torch.tensor([...])` names the adapter's `tensor/2` predicate and binds a COMPOUND, so save/load round-tripped a term, not a tensor | TEST BUG | 2 | `packages/clausal-torch/tests/fixtures/torch_io_tests.seam::save and load preserves values` | fixed: the fixture calls `tensor/2` |

Remaining failures: none.

Needs a ruling (not done): `X is mod.pred(Args)` where `mod.pred` is a
predicate adapter silently builds the compound `('mod.pred', Args)`. Should
it raise instead (it is almost always a mistake for a Python call)?
