# `reify_source` crashes on dict literals with bare-atom keys (`unhashable type: 'Goal'`)

**Discovered:** 2026-07-20 during Task 8 (renderer corpus round-trip gate). **Pre-existing** —
in the reflection *reifier* (`clausal/reflection.py`), independent of the compiler-side
`dict-atom-key-literal-parser-gap.md` (that one, DONE 2026-07-14, fixed the *runtime/exec* path
in `term_rewriting.py`/`import_hook.py`; this is the *static reflection* path).

## Symptom

`reify_source` raises `TypeError: unhashable type: 'Goal'` on any file containing a **non-splat**
dict literal with a bare-atom key in term position, e.g.:

```clausal
k(B) <- (X is {foo: B, bar: 2})
```

126 of 571 corpus files under `/workspace/clausify-domains` trip this (22%). It raises during
`reify_source` of the whole file — before any clause reaches the renderer — so it is **out of
scope for the renderer completeness gate**. The Task 8 corpus test
(`tests/test_reflection_render.py::test_corpus_clause_round_trips`) skips exactly these files with
reason `reifier defect (dict-literal atom key unhashable)`; every *reifiable* clause (4171 across
331 files) round-trips cleanly.

## Root cause

`EmbedTransformer.visit_Dict` rewrites a non-splat dict literal `{foo: V}` to
`DictTerm({$intern_atom('foo'): V})`. The reflection reifier's `_call` `DictTerm` branch
(`clausal/reflection.py`, ~line 282) does `self.term(node.args[0])`, hitting the `ast.Dict`
handler (~line 218):

```python
return {self.term(key): self.term(value) for key, value in zip(node.keys, node.values) ...}
```

`self.term($intern_atom('foo'))` reifies to `Goal('$intern_atom', ['foo'], [])` (a Goal is not
hashable), and using it as a Python dict key raises `TypeError: unhashable type: 'Goal'`.

Note the **splat** case `{**B, foo: V}` does NOT crash: splat forces the `DictLiteral` node path,
whose keys stay in a list (never used as a Python dict key). Only the plain `DictTerm({...})` path
crashes.

## Proposed fix (reifier scope — separate task)

In the reifier's `ast.Dict` / `DictTerm` handling, detect a `$intern_atom("name")` key and reify
it to a hashable `Atom("name")` (mirroring the design decision in
`dict-atom-key-literal-parser-gap.md`: atom keys are distinct from string keys). Then:

- The renderer must render an `Atom`-keyed dict back to the bare `{name: value}` surface
  (currently the renderer only reaches `$intern_atom` keys inside the `DictLiteral` splat node,
  handled by `_dict_key_ast`). A plain `dict` with `Atom` keys would need the same key handling in
  the renderer's `ast.Dict` branch.
- Once reifiable, drop the `except TypeError` skip in `test_corpus_clause_round_trips` and confirm
  the 126 files round-trip through the renderer — a materially stronger completeness gate.

## Design question to confirm

Should a reified atom-keyed dict be a plain Python `dict{Atom: V}` (matches F013 "dicts appear as
themselves") or a `DictLiteral` node? The splat path already produces `DictLiteral` with
`$intern_atom` Goal keys; the non-splat path (once fixed) should be consistent with whichever
representation the mutation auditor expects.
