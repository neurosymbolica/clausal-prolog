# -meta_predicate follow-ups: the exporter, and dotted calls (2026-09-25)

The `-meta_predicate` directive landed on `fix/small-todos-batch-2026-09-24`
(8eafed79, operator ruling 1 of 2026-09-25, "follow Scryer"). Two follow-ups are
parked here. Neither one blocks anything.

## 1. The ISO exporter could read Clausal's own `-meta_predicate`

The translator infers `:- meta_predicate` modes from goal evidence in the module
body, plus the exporter's cross-module fixpoint (`meta_modes`). It does not read a
declaration the author wrote. `clausal/tools/clausal_to_prolog.py`:

```python
    def _meta_predicate_directives(self, seen_order, defined):
        ...
        local = collect_local_meta_modes(PModule(tuple(self._items)))
        supplied = (self.meta_modes or {}).get(self.module_path or "", {})
        merged = {key: dict(positions) for key, positions in local.items()}
        for key, modes in supplied.items():
            ...
```

The directive is now recorded on the owner's Database
(`clausal/logic/database.py`):

```python
    def meta_predicate_specs(self, functor, arity) -> "tuple | None":
        row = self.row(functor, arity)
        if row is not None and row.db is not self:
            return row.db._meta_specs.get(row.key)
        return self._meta_specs.get((functor, arity))
```

It is also a `Directive(name="meta_predicate", specs=[(f, a, specs)])` module
item (`term_rewriting._parse_meta_predicate_args`), so the translator can see it
without loading the module.

**Proposal:** treat a declared `-meta_predicate` as authoritative. Emit it
verbatim, and use inference only for predicates with no declaration. Consider
refusing, or warning, when inference finds goal evidence at a position the
declaration marks `?`/`+`/`-`.

The pins to extend are in `tests/test_prolog_meta_predicate.py`
(`collect_local_meta_modes`, `TestScryerCallThrough`).

**Question for the operator:** declared-wins, or declared-and-inferred-merged
(the `MODE_MODULE_SENSITIVE` union the merge above uses)?

## 2. Explicit dotted `m.p(G)` qualifies G with the CALLER; Scryer uses `m`

`-import_from` rewrites every call to an imported predicate into the
exporter's dotted spelling. The compiler cannot tell that from a dotted call
the author wrote. `clausal/logic/meta_predicate.py`:

```python
def meta_specs_for_call(db, fname, arity):
    ...
    specs = lookup(fname, arity)
    if specs is not None or "." not in fname:
        return specs
    md = getattr(db, "module_dict", None)
    ...
    row = resolve_predicate_row(md[fname], arity=arity, db=db)
    ...
    return row.db._meta_specs.get(row.key)
```

and `terms_to_goalop.py` wraps every qualifying position the same way:

```python
                meta_specs = meta_specs_for_call(db, fname, arity)
                if meta_specs:
                    ordered_args = [
                        MetaArg(a) if is_qualifying_spec(spec) else a
                        for spec, a in zip(meta_specs, ordered_args)]
```

So `hutil.apply_all(my_pred, L)` written in `hmain` qualifies `my_pred` as
`hmain:my_pred`. Scryer's `expand_module_names` qualifies a written
`hutil:apply_all(my_pred, L)` with `hutil`:

```prolog
expand_module_names(Goals, MetaSpecs, Module, ExpandedGoals, HeadVars, TGs) :-
    Goals =.. [GoalFunctor | SubGoals],
    (  GoalFunctor == (:), SubGoals = [M, SubGoal] ->
       expand_module_names(SubGoal, MetaSpecs, M, ExpandedSubGoal, HeadVars, TGs), ...
```

The RUNTIME qualified path already follows Scryer: `call(hutil:apply_all(G, L))`
is resolved in hutil's db and qualifies G with hutil (`_meta_qualified(target.db,
...)`). Only the compiled dotted body call differs.

**To fix:** mark import-rewritten names during the rewrite (term_rewriting's
`-import_from` handling) so the compiler can tell the two apart. The dotted
call the author wrote would then qualify with the named module.

**Question for the operator:** is an explicit `m.p(G)` Clausal's spelling of
`m:p(G)` for this purpose? The same question arises for any other place that
treats the dotted spelling as a qualification.
