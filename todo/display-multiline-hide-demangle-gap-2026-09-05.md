# `term_pformat`/`term_pformat_html` don't demangle `-hide` functors in wide/multi-line output

Filed at P3-2 Task 7 close-out (ledger: "minor (deferred)"). Task 7
(`clausal/terms.py`) gave the flat `term_str` cell branch mangled-atom
(`-hide`) demangling on the functor — a hidden atom's compiler-renamed
spelling (`module⟨SEP⟩name`) now displays as the human `module.name` form
there, per `docs/directives.md` §"-hide" ("Printing renders the human form").
The WIDE/multi-line cell branch added in the same task
(`term_pformat`, `clausal/terms.py` ~2568) does **not** call
`demangle_for_display`/`is_mangled` on its functor:

```python
if type(t) is tuple and t and type(t[0]) is str:
    ...
    functor_s = _c(t[0], 'atom', style)   # raw t[0], no demangle
```

## Why it's not actually a cell-specific regression

This mirrors a **pre-existing** omission in the `Compound` branch immediately
above it in the same function (`clausal/terms.py` ~2557), which also renders
`functor_s` from the raw functor with no demangle call. Task 7's brief was to
bring cells to parity with `Compound`'s existing behavior in every display
surface — it did that faithfully, including this gap. The content is correct
(a hidden atom in a wide cell renders as its raw compiler-mangled spelling,
containing the `⟨SEP⟩` U+E000 codepoint, rather than the demangled
`module.name` form) — the *format* is what's missing, not the data.

`term_pformat_html`/`term_html`'s cell branches (added in the same task)
inherit the same gap for the same reason wherever they build a functor label
directly rather than delegating to `term_str`.

## Why it's not fixed here

- It is a pure display polish, not a correctness bug (`-hide`'s guarantee is
  uniqueness/analysis-soundness, not runtime security — display fidelity is a
  nice-to-have already flagged as an open gap for the `Compound` case this
  mirrors).
- Fixing it consistently means deciding whether to fix `Compound`'s omission
  at the same time (recommended, to avoid a new cell/Compound display
  asymmetry) or leave the two in their current — matched — state.

## Where to look

- `clausal/terms.py` — `term_pformat`'s `Compound` branch (~2557) and its
  cell-mirror branch (~2568); `term_pformat_html`/`term_html`'s cell branches
  (Task 7, same file).
- `clausal/terms.py` ~2386-2418 — `term_str`'s existing demangle call sites,
  the pattern to mirror (`demangle_for_display(x) if is_mangled(x) else x`).
- `docs/directives.md` §"-hide" — "Printing renders the human form" — the
  contract this gap under-delivers on on the wide-output path only.
- `.superpowers/sdd/p32-cell-default-flip/task-7-report.md` — Task 7's own
  before/after table recording exactly what was and wasn't added per surface.
