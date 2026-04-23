# ~~Fix registry name inconsistency in docs and plans~~ DONE

The PyTorch Phase 3 implementation uses original PyTorch class names as
string atoms: `"Linear"`, `"ReLU"`, `"CrossEntropyLoss"`, `"Adam"`.

But several plan and overview documents still reference lowercase atoms
from the original (pre-implementation) design:

## Places to fix

- `implementation_plans/pytorch/overview.md` — showcase example uses
  `layer(conv2d, CONV_CLASS)` but should be `layer("Conv2d", CONV_CLASS)`
- Any docs that reference `linear`, `conv2d`, `relu` as bare atoms in
  registry predicates

## What to change

All registry predicate examples should use quoted strings matching
PyTorch's class names:
- `layer("Linear", CLASS)` not `layer(linear, CLASS)`
- `activation("ReLU", CLASS)` not `activation(relu, CLASS)`
- `loss_fn("CrossEntropyLoss", CLASS)` not `loss_fn(cross_entropy, CLASS)`
- `optimizer_type("Adam", CLASS)` not `optimizer_type(adam, CLASS)`

The tests (`tests/fixtures/torch_registry_tests.clausal`) already use
the correct string form.
