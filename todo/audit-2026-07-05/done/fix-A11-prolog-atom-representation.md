# fix(A11-F025/F035): non-identifier atoms emitted bare; PAtom.quoted never set

- `_emit_atom` (prolog_to_clausal.py:521-551) emits every atom name verbatim
  and registers it in `-private`: `p('hello world').` → `P(hello world)`
  (SyntaxError downstream); `p(class).` → Python keyword (SyntaxError);
  `p('Foo').` → `P(Foo)` — parses cleanly and SILENTLY becomes a predicate
  reference. `docs/importing_prolog.md:168` promises quoted atoms → Python
  strings.
- F035: the tokenizer/parser never set `PAtom.quoted` (prolog_ast.py:22), so
  the promised distinction is unimplementable downstream.
- Also (PT23): bare atoms in arithmetic (`X is pi`) bypass `_emit_atom`
  entirely (`_emit_expr`:641-642) — no registration, no mapping of ISO
  evaluable constants (pi, e, inf) → NameError at runtime.

**Fix** (A11-D007): set `quoted=True` in the tokenizer/parser; emit repr()
Python strings for quoted and any non-lowercase-identifier or
keyword-colliding atom; map ISO evaluable constants to math.* in _emit_expr.

**Tests**: test_F025_atom_emission_fidelity, test_F035_quoted_flag_set (xfail).
