# Predicate identity is keyed on spelling, and every spelling is a different bug

**Filed:** 2026-08-26, from the imported-functor fix (`eb566ffb`) and its review
follow-up (`adf95a31`). **Status: OPEN — one live instance fixed, the class is
not.** Severity: the failures in this class are silent wrong answers.

## Three bugs, one shape

A predicate is a `PredicateMeta` **class object**. Code that needs to know
"which predicate is this, and whose is it" keeps asking a *name* instead, and
every distinct name-vs-object mismatch has produced its own defect:

1. **Module name vs source path.** The first attempt at the clause-clobber
   refusal (`fix/imported-functor-clause-destruction`, abandoned) keyed
   ownership on the module NAME. One file legitimately compiles under two names
   in one process — a dotted `-import_from` and
   `clausal.testing.load_clausal_module`'s `_clausal_test_*` — so a file refused
   to load beside itself. Fixed by keying on the canonical source path.
2. **Local name vs class functor.** `-import_from(m, [alias(f, G)])` binds the
   class under `G` while the class keeps functor `f`. `head_key` hands the
   compiler `f`; the origins map held only `G`; the refusal never fired and the
   exporter was destroyed anyway. Fixed by indexing both spellings and carrying
   the bound class.
3. **`module_dict.get(functor)` returning nothing.** Under an alias the class is
   NOT in `module_dict` under its own functor, so `compile_module` step 4's
   `pred_cls = module_dict.get(functor)` is `None` and its clause-sync is
   skipped — while step 5 still replaces the shared dispatch. See
   [[a-shared-predicate-has-no-single-mutation-gate]].

Each was fixed where it was found. Nothing stops the fourth.

## The underlying question

There is no single answer to "given a clause head, which predicate class does
it belong to, and which module owns it?" — callers reconstruct it from whatever
names are in reach: `head_key`, `module_dict`, the `-import_from` list,
`__name__`, `_clauses_source`. The dotted-key workaround in `_process_imports`
(`module_dict[f"{item.module}.{orig}"] = value`) is another patch on the same
seam.

## Proposal

Resolve a head to its CLASS once, in one place, and key everything downstream
on that object (`id()` / identity), with names used only for messages. Concretely:

- a resolver that maps `(pred_node, module_dict, module_items)` → the class
  plus its provenance, used by compiler_v2 steps 3c/4/5 and by import_hook's
  two deferred paths;
- `_import_from_origins` folded into it;
- an explicit rule for what a name means when the class's own functor differs.

## Acceptance

- One resolver; no second `module_dict.get(functor)` in the pipeline.
- A test matrix over plain / aliased / re-exported / twice-loaded imports, each
  asserting the same ownership answer.

Related: [[a-shared-predicate-has-no-single-mutation-gate]]
