# `reify_source` crashes on dict literals with bare-atom keys (`unhashable type: 'Goal'`)

STATUS: DONE (2026-07-20). The reifier's `ast.Dict` handler
(`clausal/reflection.py`) now detects `$intern_atom(...)` keys via
`_is_intern_atom_key` and, when any key is a bare atom, reifies the whole
literal to the **same `simple_ast.DictLiteral` node the splat path yields**
(keys stay in a list — the unhashable `Goal("$intern_atom", [...])` never keys a
Python dict) instead of a raw `dict`. Splat and non-splat atom-keyed dicts now
share one representation; string/int-only dicts still reify to a raw `dict`
(F013 preserved). No renderer change was needed — `_dict_literal_ast` /
`_dict_key_ast` already round-trip these back to the bare `{name: value}`
surface. See the RESOLVED design-question section below for why a hashable
`Atom` key was rejected (`Atom.__hash__ is None` by policy).

Pinned by `tests/test_reflection_render.py::TestDictLiteral`
(`test_atom_key_dict_round_trips`, `test_atom_key_dict_shares_splat_representation`).
The corpus round-trip gate's `TypeError`/"unhashable" skip branch was removed —
the previously-skipped files (roughly a fifth of the corpus) now round-trip and are hard
asserted: `test_corpus_clause_round_trips` = 458 passed (was ~332). Full
reflection + dict suites green.

---


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

About a fifth of the files in a downstream rulebase corpus trip this. It raises during
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
  those files round-trip through the renderer — a materially stronger completeness gate.

## Design question — RESOLVED 2026-07-20

**New finding that reframes the fix:** the reflection `Atom` (and every `make_predicate` term) has
`__hash__ = None` by deliberate policy (`clausal/logic/predicate.py:203` — "mutable terms shouldn't
be hashable"). Confirmed: `hash(Atom('foo'))` → `TypeError: unhashable type: 'Atom'`. So the fix
proposed above ("reify the key to a hashable `Atom`") is **not viable** — a plain Python
`dict{Atom: V}` cannot exist, because atom keys are unhashable *by design*, not by accident. Two
non-options fall out:

- **Make `Atom` hashable** — rejected. Violates the mutable-terms-unhashable invariant across the
  whole predicate system; a mutable key whose hash can change is genuinely unsafe.
- **Plain `dict{Atom: V}`** — impossible given the above.

**Decision: reify a non-splat dict that has any bare-atom key to the same `simple_ast.DictLiteral`
node the splat path already produces** (keys in a list, never used as a Python dict key). Concretely:

- The `$intern_atom("name")` key reifies (via the normal `self.term` path) to
  `Goal("$intern_atom", ["name"])` — **byte-identical to the splat path's keys**, so splat and
  non-splat dict literals share one representation. The mutation auditor sees a single
  `DictLiteral` shape for every dict literal regardless of splat.
- **No renderer change needed:** `_dict_literal_ast` / `_dict_key_ast` already round-trip
  `DictLiteral` with `$intern_atom` Goal keys back to the bare `{name: value}` surface.
- **F013 preserved for the common case:** a dict with only string/int (hashable) keys still reifies
  to a raw Python `dict` — "dicts appear as themselves" — unchanged. Only atom-keyed dicts (which
  *cannot* be raw dicts) route to `DictLiteral`.

Tradeoff (for the auditor author to note): the same surface `{...}` maps to two representations —
raw `dict` (hashable keys) vs `DictLiteral` (any atom key). The uniform alternative (all non-splat
dicts → `DictLiteral`) was rejected to avoid regressing the deliberate, recently-landed F013
raw-dict behaviour (commit `080006fe`) and its passing corpus round-trips. Both representations are
walkable; the auditor can normalize "dict literal" over the two if it needs to.
