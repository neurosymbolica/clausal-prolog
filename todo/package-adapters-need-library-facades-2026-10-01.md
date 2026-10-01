# Package adapters need `library(...)` facades: run the same generator per distribution

**Filed:** 2026-10-01, with the core facades (`clausal/library/*.seam`,
`clausal/tools/gen_library_facades.py`). **Ruled (operator, 2026-10-01):**
Clausal Prolog reaches Python only through `.seam` modules; the engine's
`py/<lib>` bridges are no exception, and neither are the extension
distributions' adapters.

## Population (measured 2026-10-01: `find packages -path '*clausal/modules/py/*.py' -not -name '_*'`)

| distribution | adapters |
|---|---|
| packages/clausal-jax | 10 |
| packages/clausal-opencv | 9 |
| packages/clausal-scipy | 14 |
| packages/clausal-sklearn | 1 |
| packages/clausal-spacy | 1 |
| packages/clausal-sympy | 1 |
| packages/clausal-torch | 5 |
| packages/clausal-yaml | 1 |

Regenerate the count rather than trust it.

## Do, per distribution

1. Install it, then run the generator against its module directory:
   `python -m clausal.tools.gen_library_facades --modules
   packages/clausal-<d>/clausal/modules --out
   packages/clausal-<d>/clausal/library --index ''`.
   Each `py/<lib>` gets `library(<lib>)`, as in core.
2. Make the facades FINDABLE.  `clausal.library` is a regular package in
   core, so a distribution's `clausal/library/<lib>.seam` is not on its
   `__path__` under an editable install -- the same problem `py/` adapters
   have, which `import_hook._ensure_source_modules_on_path` works around.
   Decide: extend that workaround to `clausal.library`, or make
   `clausal.library` a namespace package.
3. Extend `clausal/_py_facades.py` (core lists core facades only), or give
   each distribution its own index; the consumer-facing capability signal
   must not claim a facade that is not installed.
4. A YES/NO test per distribution (facade import works; `py/<lib>` from
   the Clausal Prolog surface is refused naming `library(<lib>)` -- the
   refusal already says "has no library(<lib>) facade" until step 1 lands).

## Blocker

`packages/` are pinned and not gated, and broken on main: see
`todo/packages-are-not-gated-and-are-broken-on-main-2026-09-21.md`.  The
facades cannot be verified green until that is fixed.
