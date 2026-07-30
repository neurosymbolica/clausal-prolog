# Functor identity leaks across independently loaded modules in one process

**Found:** 2026-07-29, immediately after the `_lazy_hook` recursion fix.
**Investigated:** 2026-07-30 on `fix/functor-identity-cross-module`.
**Status:** original mechanism REFUTED. One real engine defect found and fixed; the
reported reproduction is a harness fault in `clausify-executor-train` plus three
unrelated pre-existing failures. Remaining engine work is a parked design
question, see [[term-identity-cannot-cross-two-package-copies]].

## The hypothesis, refuted

This todo blamed a process-global, name/arity-keyed functor registry: two
`.clausal` modules declaring the same functor name with different field names
were supposed to collide, and the suggested fix was to intern identity by
`(module, name, arity)`.

That is not what happens. Identity is not keyed by name or arity at all — it is
*nominal on the metaclass*. `is_term_instance(obj)` asks
`isinstance(type(obj), PredicateMeta)`, and nothing about `decision/2`'s spelling
enters into it. Two modules declaring `decision/2` with different field names
load and run fine; this todo's own failed isolation attempt #1 already
demonstrated that, it just drew the wrong conclusion from it. No amount of
`(module, name, arity)` interning would have changed any of the observed
failures, so that redesign is not needed and should not be built.

The prediction that "at 10^4 domains name collisions are certain rather than
likely" is therefore also void: a corpus walker loading many rulebases in one
process is not at risk from name reuse.

## What actually happens

`clausal/logic/predicate.py` hands the C accelerator its `PredicateMeta` via
`_register_predicate_meta(PredicateMeta)`. On the C side that lands in a single

    static PyObject *PredicateMeta_type;          /* _variables.c:1960 */

and `is_term_instance` answers `isinstance(type(obj), PredicateMeta_type)`
against it. The slot is process-global, the extension uses single-phase init
(`PyModule_Create`, `m_size = -1`), so its static state outlives
`del sys.modules["clausal..."]`.

A **second import of the `clausal` package** therefore builds a second,
unrelated `PredicateMeta` class and — before the fix — re-registered it, quietly
stealing the slot. Every term the *first* copy had already minted then stopped
being a term: its metaclass was no longer the registered one. Confirmed
directly:

    copy1 is_term_instance(copy1's own instance)      -> False
    copy1 _is_term_instance_py(same instance)         -> True

i.e. the accelerated path silently disagreed with its own Python reference
implementation. That is the engine defect: a fast path that is not semantically
equivalent to its fallback, failing closed on perfectly good terms.

The symptom recorded above (`head_key` refusing a head it is holding) is one
downstream consequence; every `is_term_instance` caller in the engine was
affected the same way.

The trigger in the reported reproduction is
`auto/tests/test_check_certificate.py::test_checker_does_not_import_clausal`,
which does

    for m in [k for k in sys.modules if k == "clausal" or k.startswith("clausal.")]:
        del sys.modules[m]

to assert that the certificate checker does not pull in clausal. That leaves
`auto/gate/query.py` — which imported `_load_module` once at module import — bound
to the now-orphaned first copy, while every later `import clausal` builds a
second one. Nothing to do with fresh module names: `_fresh_module`'s
`gate_q_0`, `gate_q_1`, … were never the problem, which is why the todo's
isolation attempts could not reproduce it.

The `arg_0`/`arg_2` field names in the second quoted message are a red herring:
that is ordinary placeholder minting for an undeclared `requirement/4`, not a
resurgence of [[done/functor-field-name-mismatch-diagnostic]] or
[[done/same-name-two-arities-silently-merge]].

## Fixed

Both on `fix/functor-identity-cross-module`:

1. **The slot is claimed once and never stolen** (`clausal/logic/predicate.py`).
   Ownership is recorded on `sys` — the only namespace that survives the
   `sys.modules` surgery which creates the second copy. Later copies keep the
   pure-Python implementations, which close over *their own* `PredicateMeta` and
   are therefore self-consistent. Both copies end up internally correct; only
   later ones pay interpreter speed, which is the right way round because the
   first copy is the one already holding live terms.

2. **`head_key`'s error names both classes and where each came from**
   (`describe_term_identity_mismatch`, used at `clausal/logic/database.py:515`).
   It previously said "expected a functor dataclass instance" while holding one,
   naming neither class nor either declaring module.

Gate: `tests/test_second_package_copy_term_identity.py` (subprocess-driven; two
package copies cannot be undone inside one test process).

## Deliberately NOT fixed

A term that genuinely *crosses* between two live copies still raises. Loading a
rulebase through the first copy's captured `_load_module` after a second copy
exists mixes them: the head class is minted by copy 1's `PredicateMeta` (the
captured loader's compiler builds it) while the `Database` it is asserted into
belongs to copy 2 (the generated module body re-resolves `clausal.*` through
`sys.modules`). Neither copy is wrong and no per-copy policy can bridge it —
only giving up nominal term identity engine-wide would, which is a redesign.
Parked as [[term-identity-cannot-cross-two-package-copies]].

## The reported reproduction: accounting for all four failures

    cd /workspace/clausify-executor-train
    python3 -m pytest auto/tests/test_check_certificate.py auto/tests/test_gate_query.py -q -p no:randomly

* **1 failure** (`test_query_headline_returns_count_and_decisions`) is the
  cross-copy case above. It is a **harness fault**: the fix belongs in
  `clausify-executor-train`, whose `test_checker_does_not_import_clausal` should
  assert its property in a subprocess instead of mutating the live `sys.modules`
  of a process that other modules are still using. Deselecting that one test
  makes this failure go away. With the diagnostic above it now says so itself.
* **3 failures** (`test_query_requirements_*`) are unrelated and pre-existing:
  the fixtures in that test file use bare atoms `req_a`, `met`, `art_1`, … which
  strict-atoms-by-default now rejects. They fail identically against canonical
  `/workspace/clausal` and *in isolation*, so this todo's "order matters and
  isolation passes" note is stale — it predates the strict-atoms default landing.
  Filed as [[done/strict-atoms-default-broke-downstream-bare-atom-fixtures]]
  and fixed there on 2026-07-30, along with five more `.clausal` files and two
  further embedded fixture groups that the consumer sweep turned up.
