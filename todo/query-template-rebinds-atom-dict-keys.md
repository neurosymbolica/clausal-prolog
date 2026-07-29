# Query template re-resolves atom dict keys by name — silently wrong key when the name is bound

**Filed:** 2026-07-29. **Severity:** high — produces **silently wrong answers**, no error raised.
**Relationship to existing work:** this is Phenomenon B of
`implementation_plans/dict-atom-keys-vs-predicates.md`, but a *worse* manifestation than that
document records. Phenomenon B as filed describes a loud `NameError`. This is the quiet variant.

## The bug

When a `DictTerm` built outside a module (in Python, or in another Clausal module) is passed to
`solve(m.pred(profile, ...))`, the query compiler inlines the dict's atom keys into the compiled
query template as bare `Name(id='<atom>')`, resolved in the **called predicate's** module namespace.

- If the name is **unbound** there → `NameError: name '<atom>' is not defined` (documented, loud).
- If the name is **bound to something else** there → the template silently substitutes **that other
  object** as the dict key. No error. Reads then miss.

The second case is not hypothetical: under the snake_case convention, profile keys and predicates
are spelled identically (`query_date` the key, `query_date/2` the predicate), so "bound to something
else" is the *common* case, not a corner one.

## Reproduction (verified 2026-07-29, @ `79294be4`)

```clausal
# qd_atom.clausal — owns the key atom
-module(qd_atom, [mk_atom(P), query_date])
mk_atom(P) <- ( P is {query_date: 5} )

# qd_soft.clausal — defines a predicate with the SAME NAME as the key
-module(qd_soft, [query_date(P, X), eligible(P)])
-import_module(qd_atom)
query_date(P, X) <- ( X is 99 )
eligible(P) <- ( get(P, qd_atom.query_date, V), V > 3 )   # qualified key — correct by construction
```

```python
a = _load_module("qd_atom", ...); s = _load_module("qd_soft", ...)
d = <run a.mk_atom(P)>                      # DictTerm({query_date: 5})
list(solve(s.eligible(d)))                  # => []   *** WRONG: should be 1 solution ***
```

The read is written with a **qualified** key (`qd_atom.query_date`), so the rule itself is
unambiguous and correct. It still fails, because the *dict handed to the goal* no longer has the
atom as its key — the template rebound it to `qd_soft`'s `query_date/2` predicate object.

Direct confirmation:

```
p2's bare `query_date` is: <Predicate query_date/2, 1 clause(s), compiled, locked>
  is the atom? False | == atom? False
```

And the same read works when the dict never crosses the boundary:

```clausal
rd_inline(X) <- ( qd_atom.mk_atom(P), X is P[qd_atom.query_date] )   # => [5]
```

## Why it matters here

Failure mode depends on the read, and the common one is the silent one:

| Read | Symptom |
|---|---|
| `P[key]` / `P.key` (strict) | bogus `existence_error(dict_key, key)` — misleading, but loud |
| `get/3` (soft) | **clause fails silently** — a wrong legal determination, no error |
| `get/4` (defaulted) | **silently returns the default** — arguably worst |

`clausify` harnesses build `DictTerm` profiles in Python and call `solve()`; 40 of 54 domains now use
atom keys. The mechanism is verified; **corpus incidence is not** — a sweep is needed for domains
where a profile-key atom name is also bound in the module owning the harness-called predicate.
`au/firb`'s `profile_keys.yaml` header shows the collision being hand-managed already.

## Related sharp edge (same root)

In a module that *defines* `query_date/2`, a bare `query_date` in key position resolves to the
predicate class and the compiler dies with a raw, unhelpful error:

```
NotImplementedError: term_to_ast_expr: unsupported term type PredicateMeta:
  <Predicate query_date/2, 1 clause(s), compiled>
```

This is at least loud and at load time, but it should be a Clausal-level diagnostic naming the
predicate/atom clash and suggesting the qualified form or an import.

## Fix direction

Option 2 of `implementation_plans/dict-atom-keys-vs-predicates.md` — **compile atom `DictTerm` keys
by identity, not by name.** Keys that are already interned atoms should be embedded as constants /
by-identity rather than re-looked-up as `Name`s in the query namespace. That removes both the loud
and the quiet variant at once, and makes atom keys as safe as string keys (which compile as
`Constant` and were never affected).

Suspects: `_compile_as_query`, `_templatize_query_goal`, the query trampoline.

## Acceptance

- The reproduction above yields 1 solution.
- A dict key that is an interned atom survives the Python→`solve()` boundary with identity intact,
  regardless of what the callee module binds that name to.
- The `PredicateMeta`-as-key crash becomes a named Clausal error.
- Corpus sweep for live incidence, then re-run affected domains' gold suites.

## Pointers
- `implementation_plans/dict-atom-keys-vs-predicates.md` (Phenomenon A + B, design options)
- `docs/superpowers/specs/2026-07-29-dot-attribute-access-design.md` (the convention that routes
  around this by keeping keys private to the type module)
