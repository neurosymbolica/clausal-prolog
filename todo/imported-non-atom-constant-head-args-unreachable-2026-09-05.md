# A non-atom value nested inside an indexed cell head-arg is unreachable

Found during design review of the imported-atom index-key hotfix
(fix/imported-atom-index-key, 2026-09-05). PRE-DATES this hotfix — verified
empirically by swapping in the pre-fix `arg_index.py`/`predicate.py` (clone
main `1f86daf4`) and reproducing the identical zero-solutions result. Not a
regression; this hotfix's diff never touches `head_match.py` or the
`Call(LoadName)` cell branch this bug lives in.

## Mechanism (verified, and narrower than first suspected)

A TOP-LEVEL scalar head-arg reference that resolves to a non-atom value
(e.g. a plain int) is **not** affected: `list_dispatch.py::_lift_clause_at_pos`
unconditionally refuses to lift a bare `LoadName`/`LoadAttr` at the position
being indexed (see its "Skip the lift when the lifted term is a bare name
reference" comment), regardless of what the name resolves to. The head arg
stays a `Var`; the body `Unify` is left in place and resolved by the real
runtime `unify()`, which handles any type correctly. Confirmed: a
`compile_predicate_trampoline` clause set with a top-level
`Unify(v, LoadName('c.CONST'))` head arg (`c.CONST` resolving to a plain
int via `globals_`) answers correctly for every query shape, indexed or
not.

The gap is real, but only for a non-atom reference **nested inside** a
data-functor/cell argument that DOES get lifted — e.g. a rule head like
`Foo(Wrap(SOME_IMPORTED_INT))`. `_lift_clause_at_pos`'s `Call(LoadName)`
branch (list_dispatch.py, "A compound reference... Whether it may be
lifted is decided HERE") does not universally refuse a compound reference;
once it decides to lift, `head_to_match_pattern` recurses into the cell's
FIELDS, and for a field that is itself a `LoadName`/`LoadAttr`
(head_match.py:794-800) the pattern is built via `_resolve_loadname`:

```python
if isinstance(term, (LoadName, LoadAttr)):
    dotted = _dotted_name_from_loadattr(term)
    resolved = _resolve_loadname(dotted, globals_) if dotted else None
    if isinstance(resolved, str):
        return ast.MatchValue(value=ast.Constant(value=resolved))
# falls through to the is_term_instance dead-pattern fallback: never
# wrongly matches, but never fires either, for anything but a str.
```

Only a `str` resolution gets a real `MatchValue` pattern. A non-`str`
resolution (int, float, etc.) falls through to the `is_term_instance`
fallback below, which is a dead pattern for a bare name reference (it
requires the runtime value to BE an instance of a user-defined term class,
which a `LoadName` reference never produces) — so the field never matches,
and the clause can never fire through THIS bucket.

### Reproduction (verified both post-fix and pre-fix, identical result)

Direct low-level construction (bypasses `.clausal` source parsing/constant
folding entirely — `-constants` inlines to a literal at parse time and
never reaches this branch, so it cannot be used to build a repro):

```python
clauses = [
    Clause(
        head=Compound("level", (Var(), Var())),  # BOTH positions Var
        body=[
            Unify(left=n_var, right=i),  # N discriminates 1..4
            Unify(left=l_var, right=Call(
                func=LoadName(name="Wrap"),
                args=(LoadName(name=f"c.CONST{i}"),), kwargs=(),
            )),
        ],
    )
    for i in (1, 2, 3, 4)
]
globals_ = {f"c.CONST{i}": v for i, v in zip((1,2,3,4), (100,200,300,400))}
globals_["Wrap"] = "Wrap"
globals_[FUNCTOR_SIGNATURES_KEY] = {"Wrap": ("x",)}
fn = compile_predicate_trampoline("level", 2, clauses, None, globals_=globals_)
```

- `level(1, ('Wrap', 100))` (BOTH args ground) → **1 solution**. Dispatch
  picks the MORE selective position-0 index (4 distinct int keys) over
  position-1's single-key cell bucket, so the broken nested pattern is
  never actually exercised for this query shape.
- `level(V, ('Wrap', 300))` (position 0 unbound, forcing dispatch through
  position 1's `('Wrap', 1)` bucket — the ONLY index available when
  position 0 gives no information) → **0 solutions**. Expected: 1,
  binding `V = 3`.

This is why the bug is easy to miss: it only manifests when the OTHER
indexed position(s) don't discriminate the call, forcing dispatch through
the specific bucket carrying the broken nested field pattern.

## Fix direction

Extend `head_to_match_pattern`'s `LoadName`/`LoadAttr` branch
(head_match.py:794-800) to also emit a `MatchValue` for any resolved value
`ast.Constant` accepts directly as a pattern literal (int, float, bool,
bytes, `None` — the same `_INDEXABLE_TYPES` family `arg_index.py` already
treats as scalar-indexable), not just `str`. Alternatively, if a resolved
non-literal-safe value is reached, refuse the lift entirely for that
clause (mirroring `_lift_clause_at_pos`'s existing top-level bare-name
skip) rather than emitting a pattern that can never match — safe over
fast, exactly the principle this hotfix's own `_INDEX_VAR` fallback
follows.

## Acceptance

The reproduction above (or an equivalent driven through a real
`.clausal` fixture using a `py.`-shim int constant nested in a data-functor
head arg) returns 1 solution for the "other position forced unbound"
query shape, not 0.
