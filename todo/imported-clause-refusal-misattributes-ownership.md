# The imported-clause refusal blames the exporter for clauses the importer minted

**Severity:** high for the branch that introduces it — blocks
`fix/imported-functor-clause-destruction` from merging. Not reachable on `main`,
which has no such refusal.

## Symptom

On branch `fix/imported-functor-clause-destruction` (`ec6bf7bf`), loading the
same module a second time in one process refuses, with a message asserting
something untrue:

```
load 1: OK
load 2: SyntaxError
  _probe_atp_2 defines a clause for impord_qd/2, which it -import_from's from
  tests.fixtures.impord_atomvocab.
  tests.fixtures.impord_atomvocab already defines impord_qd with 2 clauses. An
  -import_from binds the EXPORTER's predicate, so this clause would not add to
  those 2 clauses — it would replace all of them ...
```

Reproduction (branch worktree, PYTHONPATH at the worktree):

```python
from clausal.import_hook import _load_module
f = 'tests/fixtures/impord_atom_then_pred.clausal'
_load_module('_probe_atp_1', f)   # OK
_load_module('_probe_atp_2', f)   # SyntaxError
```

## Why it is wrong

`tests/fixtures/impord_atomvocab.clausal` exports `impord_qd` as a **0-arity
vocabulary atom with no clauses**. The "2 clauses" the message attributes to it
were put on the shared class by **load 1** — by the Phenomenon A re-mint that
two corpus modules — the shape `tests/fixtures/impord_atom_then_pred.clausal`
pins — both rely on (import a 0-arity atom, then define a same-named predicate;
the clauses
land on the imported class without `_arity` moving).

So the refusal reads its own earlier work as the exporter's declaration. Two
consequences:

1. **Order- and process-state-dependent.** Identical source loads or refuses
   depending on whether it was already loaded in that process.
2. **The diagnostic misattributes ownership**, naming a module that declared
   nothing and pointing the author at `impord_atomvocab.clausal:2`, which is
   just the atom declaration.

## Why the domain suites do not catch it

The investment-screening domain (123 tests + 4 negative controls) and the
tax-credit domain (41 tests) are green against the branch. They load each
module once per process, so the second
load never happens. Green domain suites are not evidence here.

It does fail the engine suite:
`tests/test_predicate_arity_mismatch_diagnostic.py::TestTermConstructionUnaffected::test_atom_vocabulary_then_predicate`
passes alone and fails in the full run (branch: 2 failed / 10519 passed, versus
1 / 10514 on `main` at the time).

## The fix this needs

Distinguish clauses the exporter actually declared from clauses a re-mint
deposited on the shared class. The refusal is only sound when the exporter is
the true owner. Options worth weighing: record the declaring module on the
clause (or on the class at declaration time) and compare against the module
being loaded; or make the guard consider only clauses present at export time.

Note the open design question this sits inside: whether Clausal should instead
grow a `-multifile` opt-in. A `-multifile` declaration would **not** fix this
case — the module is not asking to share ownership, it is being told it already
owns clauses it does not.

## See also

- `todo/done/imported-functor-clause-list-replaced-not-extended.md` (the branch's
  own todo, for the fault it was built to fix — which is real)
- `todo/same-name-two-arities-silently-merge.md` (the other place clause lists
  merge in a way the docs do not describe)
