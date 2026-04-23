# Reflection — clause/2, current_predicate/1, predicate_property/2

Implementation plan for reflective access to the logic database: enumerate
predicates, inspect their clauses, and query their declared properties.

---

## Motivation

Clausal already tracks everything needed — `PredicateMeta` holds
`_clauses`, `_signature`, `_locked`, `_lazy_recompile`, and the database
carries `_dispatch`. What's missing is a *logic-level* interface to this
information so user code (meta-interpreters, tooling, linters, explanation
systems) can walk it under unification and backtracking.

This is a pure logic-programming feature: the equivalent Python (`inspect`,
`__subclasses__`, direct attribute reads) works but doesn't thread through
unification, doesn't backtrack, and doesn't compose with `findall`/`bagof`.

---

## Target API

Three predicates, modeled on ISO/SWI but adapted to Clausal naming (CamelCase,
expanded abbreviations, trailing-underscore logic vars):

### `Clause/2` — `Clause(Head_, Body_)`

Unifies `Head_` with a clause head in the database and `Body_` with its body.
Backtracks over all matching clauses. Pure builtin, no side effects.

```clausal
# enumerate all clauses of fib/2
FindAll(Head_ :- Body_, Clause(fib(_, _), Body_), Clauses_)

# check if a specific fact exists
Clause(edge(a, b), True)
```

Semantics:
- `Head_` must be nonvar or have a bound functor (we need to know which
  predicate to look up). `current_predicate/1` covers the fully-open case.
- `Body_` is unified with the clause body as a term. Facts produce `True`
  (the Clausal truth literal).
- Only visible on predicates not marked `-static`. For `-dynamic` predicates
  it sees live state (including post-`assertz` additions) under backtracking.
- Static predicates: either (a) expose clauses read-only, or (b) throw a
  `permission_error`. SWI allows read-only access; we do the same for
  debuggability.

### `CurrentPredicate/1` — `CurrentPredicate(Name_/Arity_)`

Backtracks over defined predicates in the current module.

```clausal
FindAll(F_/A_, CurrentPredicate(F_/A_), Preds_)
```

- Enumerates both user-defined and builtin predicates.
- `Name_` and `Arity_` may be var or ground; partial specification constrains
  the search.
- Scope: current module by default; `CurrentPredicate(Mod_:Name_/Arity_)` to
  cross modules (uses the existing `-import_module` machinery).

### `PredicateProperty/2` — `PredicateProperty(Head_, Property_)`

Backtracks over properties of a predicate:

| Property                  | Meaning                                         |
|---------------------------|-------------------------------------------------|
| `dynamic`                 | declared `-dynamic`                             |
| `static`                  | not dynamic (default)                           |
| `tabled`                  | declared `-table`                               |
| `discontiguous`           | declared `-discontiguous`                       |
| `builtin`                 | implemented in Python builtins, not Clausal    |
| `imported_from(Module_)`  | brought in via `-import_from`                   |
| `number_of_clauses(N_)`   | size of `_clauses` list                         |
| `defined_in(File_, Line_)`| source location (if import hook recorded it)    |
| `exported`                | reachable from outside the module               |
| `meta_predicate(Spec_)`   | if/when we add meta_predicate declarations      |

```clausal
# find all tabled predicates
FindAll(P_, PredicateProperty(P_, tabled), Tabled_)
```

---

## Implementation

### Data sources

Everything needed already lives on `PredicateMeta` or `Database`:

| Source                          | Where                                  |
|---------------------------------|----------------------------------------|
| Clauses                         | `pred_cls._clauses` (list[Clause])     |
| Signature                       | `pred_cls._signature`                  |
| Dynamic flag                    | `pred_cls._locked is False`            |
| Tabled flag                     | `pred_cls._tabled` (V2-D metadata)     |
| Discontiguous flag              | `pred_cls._discontiguous`              |
| Number of clauses               | `len(pred_cls._clauses)`               |
| Module membership               | `db.module_dict` scan                  |
| Builtin                         | name in `_BUILTINS` registry           |
| Imported                        | import hook records `_imported_from`   |
| Source location                 | import hook records `_source` (new)    |

One small piece of plumbing needed: the import hook currently does not record
`(filename, lineno)` for each clause. Add this in `LogicModule._define_predicate`
and `_assert_fact` by passing the AST node's `lineno` / `col_offset` through
to each `Clause` as a `source=` field.

### New files / changes

```
clausal/logic/builtins/reflection.py     # new: Clause, CurrentPredicate, PredicateProperty
clausal/logic/builtins/__init__.py       # register new builtins
clausal/logic/database.py                # add Clause.source field (lineno)
clausal/logic/import_hook.py             # populate Clause.source
tests/test_reflection.py                 # new
docs/reflection.md                       # new
```

### Clause/2 implementation

```python
class Clause(BuiltinPredicate):
    _fields = ('head', 'body')

    def _resolve(self, head, body, db, trail):
        # Must know the functor. Otherwise delegate to CurrentPredicate.
        cls = _functor_class_of(head, db)
        if cls is None:
            raise InstantiationError("Clause/2 needs head with bound functor")
        for clause in list(cls._clauses):   # snapshot — dynamic may mutate
            mark = trail.mark()
            stored_head, stored_body = _rebuild_clause(clause)
            if unify(head, stored_head, trail) and \
               unify(body, stored_body, trail):
                yield
            trail.undo_to(mark)
```

`_rebuild_clause` reconstructs the stored `Clause` object as two terms
(`Head`, `Body`) using fresh variables for each quantified variable — same
semantics as SWI `clause/2`. Reuses `copy_term` infrastructure from V2-13.

### CurrentPredicate/1

Walk `db.module_dict.values()`, filter for `PredicateMeta` instances, yield
`F_/A_` for each. For cross-module, consult `sys.modules` and `LogicModule`
registry.

### PredicateProperty/2

Flat generator over the property list for a given head's class. Accepts
unbound `Property_` (enumerates all) or ground (tests one).

---

## Interaction with existing features

### Dynamic predicates

`Clause/2` on a `-dynamic` predicate must see the live list, and must behave
correctly under concurrent `Assertz` / `Retract` during backtracking:
- snapshot the list at entry (shallow copy),
- iterate the snapshot,
- skip snapshot entries whose `alive` flag was cleared by `Retract` between
  `Clause/2` entry and this iteration.

This matches SWI's "logical update view" for dynamic predicates and avoids
the famous cursor-invalidation bugs.

### Static predicates

`Clause/2` works read-only. Any attempt to `Retract` a static clause still
throws `permission_error` (existing behavior).

### Builtins

`CurrentPredicate/1` lists them; `Clause/2` on a builtin throws
`permission_error(access, private_procedure, Name/Arity)` — SWI-compatible.

### Tabling

For tabled predicates, `Clause/2` returns the *source* clauses, not the
answer table. Answer tables get their own debug API (future work).

### Modules

`CurrentPredicate(Module_:Name_/Arity_)` requires module-qualified call
machinery already present in V3-1. Unqualified form defaults to current
module — implementation checks the calling module via the compiler's
existing module-tracking (compiler_v2 tags clauses with their defining
module).

---

## Testing

Targets (~40 tests):

- `Clause/2` on facts, rules, multi-clause predicates
- `Clause/2` variable-sharing (each call returns fresh vars)
- `Clause/2` backtracks in source order
- `Clause/2` under `Assertz`/`Retract` in the same transaction
- `Clause/2` rejects builtin access
- `Clause/2` raises on fully-unbound head
- `CurrentPredicate/1` enumerates user, builtin, imported
- `CurrentPredicate/1` with partial `Name_/Arity_` binding
- `PredicateProperty` for each flag (dynamic/static/tabled/discontiguous/
  builtin/imported/number_of_clauses/defined_in)
- cross-module enumeration
- interaction with `FindAll`, `BagOf`, `SetOf`

Plus a `tests/fixtures/reflection_target.clausal` fixture with a mix of
predicate kinds.

---

## Phases

### Phase 1 — read-only reflection (1 week)
- [ ] `Clause.source` field plumbed through import hook
- [ ] `Clause/2` builtin
- [ ] `CurrentPredicate/1` builtin
- [ ] `PredicateProperty/2` builtin with 7 core properties
- [ ] 40+ tests
- [ ] Docs page

### Phase 2 — meta-interpreter examples (0.5 week)
- [ ] Vanilla meta-interpreter in `examples/meta_interp.clausal`
- [ ] Tracing meta-interpreter (proof-tree builder)
- [ ] Use in an explanation-system tutorial page

### Phase 3 — tooling hooks (optional)
- [ ] `clausal.tools.visualize` grows a "list all predicates" command using
      `CurrentPredicate`.
- [ ] Linter using reflection to find unused predicates.

---

## Open questions

- **Naming.** `Clause` is already used in `database.py` as the internal
  dataclass. Name the builtin `Clause` (the class) or `ClauseOf`? SWI uses
  `clause/2` and we've generally stuck close to Prolog names. Recommend
  reusing `Clause` as the builtin name; internal type renamed to
  `_ClauseRecord`.
- **Source locations on asserted clauses.** Runtime `Assertz(X :- Y)` has no
  file/line. Store `None` or `'<asserted>'`? SWI uses `'<assert>'` — match.
- **Guarding access to internal metadata.** `PredicateProperty` could leak
  `_locked`, `_dispatch_fn`, etc. Whitelist the exposed properties, never
  expose raw attrs.
