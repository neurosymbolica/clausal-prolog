# `clausal fmt` — Black-based Clausal formatter via a `<-` operator patch

**Requested:** 2026-07-22 (implements `todo/one-goal-per-line-style-standard.md`).
**Status:** DESIGN DONE, first implementation (SHIM) ABANDONED — see "Why the shim failed".
The correct, reusable pieces are salvageable from tag `wip/clausal-fmt-shim-abandoned`
(branch `feat/clausal-fmt` was deleted; the 13 commits live under that tag).

## Goal — house style (user's Black-like preference; see memory clausal-formatting-style)

A behaviour-preserving formatter for `.clausal` source that produces:
1. **One goal per line** — every multi-goal parenthesised goal-group (`<-` body, and `(…)`
   goal-groups inside `findall`/`not`/`once`) lists one goal per line; single-goal stays inline.
2. **Exploded long heads/calls** — a head/call over the line width splits one-arg-per-line.
3. **Nested goal-conjunctions** get their own `( … )` block, one goal per line.
4. **Trailing commas kept** on exploded goal-groups (Black magic-trailing-comma style — the
   user chose this: reduces diff deltas, avoids missing commas on insertion).
Out of scope: `in_(X,Y)`→`X in Y` (a linter job); corpus-wide reflow (separate opt-in run).

Full design + rationale: the abandoned branch's
`docs/superpowers/specs/2026-07-22-clausal-fmt-design.md` (read via
`git show wip/clausal-fmt-shim-abandoned:docs/superpowers/specs/2026-07-22-clausal-fmt-design.md`).

## Why the shim failed (the CRITICAL finding — the reason to do the operator patch)

The first attempt wrapped **stock Black** behind a text shim: `<-`→`@`, `$x`→`__dollar_x__`
(code-only), inject magic commas, `black.format_str`, restore. A final whole-branch review
found it **silently corrupts embedded-Python `@`**: Clausal embeds arbitrary Python (the user:
"expect any Python inside Clausal and vice-versa"), and Python uses `@` for matmul/decorators.
The restore `@`→`<-` turns real code into garbage:
```
packages/clausal-jax/tests/fixtures/jax_transforms_tests.clausal
  IN : ... F is ++(lambda x: x @ x.T ...
  OUT: ... F is ++(lambda x: x <- x.T ...      # SILENT corruption, no error, tests green
```
`jax_linalg_tests.clausal` and ~24 lambda-bearing fixtures are exposed. **No sentinel operator
is collision-free** — any Python infix op we shim `<-` to (`@`,`|`,`&`,`<<`,`//`,…) can appear
in embedded Python. The clean fix is to make `<-` a **real, distinct token in Black's grammar**
so it never aliases another operator. (This was the user's original instinct; the shim was
chosen on an INCOMPLETE corpus check — only a downstream rulebase corpus was scanned, which
happens to be code-`@`-free; the engine's own fixtures were missed.)

## The operator patch (Black 24.10.0 / blib2to3) — spike results

Make `<-` its own operator so Black parses and re-emits it natively, `@`/`<-` never collide.

- **Tokenizer (VERIFIED working in the spike):** add `r"<-"` to the `Operator` alternation in
  `blib2to3/pgen2/tokenize.py:147` (beside `<>`), then rebuild `Funny`, `PseudoToken`, and
  recompile `pseudoprog`. Result: `<-` tokenises as one `('OP','<-')` (contiguous only — `a < -b`
  stays two tokens, matching the engine's `_is_arrow_adjacent`).
- **Grammar (the UNSOLVED part):** `blib2to3` has no left-arrow token (only `-> RARROW`, see
  `pgen2/grammar.py` `opmap_raw`). Need: a new token type (`token.LARROW`), `grammar.opmap['<-']
  = LARROW`, add the literal `'<-'` to `comp_op` in `blib2to3/Grammar.txt:152`, regenerate the
  grammar via `driver.load_grammar(force=True)`, and INSTALL it into
  `pygram.python_grammar{,_async_keywords,_soft_keywords}` (black.parsing.get_grammars reads
  those dynamically). The driver classifies OP tokens via `grammar.opmap[value]`
  (`pgen2/driver.py:147`), and pgen resolves the `'<-'` literal via `opmap` at build time, so
  `opmap['<-']` must be set BEFORE `load_grammar`. In the spike the regenerated grammar did not
  take effect (Black kept parsing with the original grammar → "Cannot parse" at `<-`); the
  install/opmap wiring is the piece to crack. **Fallback if intractable:** vendor a small fork of
  `blib2to3` with the patched `Grammar.txt` precompiled, imported in place of the stock one.
- With the operator patch, the `<-`⇄`@` shim is **DELETED**. `@` is left alone (Black formats it
  as normal matmul). Pipeline becomes: `$`-shim (still needed — Black can't parse `$`) → magic-
  comma injection → `black.format_str(magic_trailing_comma=True)` → `$`-restore.

## Reusable, CORRECT components (salvage from tag wip/clausal-fmt-shim-abandoned)

Only the shim mechanism was wrong; these are sound and tested — cherry-pick / reuse:
- `clausal/tools/fmt.py`:
  - `_protected_spans` / `_code_spans` — **tokenize-based**, handles EVERY Python string kind
    (single/double/**triple**/f/r/b) + `#` comments + f-string interpolations. (commit `960d935c`,
    after the user corrected "Clausal is full Python, all string types".)
  - `_inject_group_commas` — magic comma into bare-paren goal-groups only (calls/lists/compounds
    untouched); skips nested `<-` lambda param-groups and bodies; comment-safe backward scan;
    idempotent. (commits `1e9bf871`, `e8a116e0`, `372cb577`.)
  - `format_str` orchestration, `format_file`, `main`/CLI (`--check`, `--line-length`, DIR).
- `clausal/tests/test_fmt.py` — 22 tests: house-style-matches-peppol, idempotence, **reify
  structural round-trip** (compare `Clause.head`+`goals`, NOT `repr` — `Clause` has `position`,
  `Goal` doesn't), all-string-kinds, shim-safety, injector edge cases.
- Design spec + plan: on the tag under `docs/superpowers/`.

## Outstanding findings to carry into the operator-patch impl

- **I1 (`$`-restore collision):** `_restore_dollars` maps `__dollar_(\w+)__`→`$\1` unconditionally,
  so a literal `__dollar_x__` in source becomes `$x`. Same injectivity flaw class as the `@` bug.
  The `$`-shim is STILL needed under the operator patch → guard it (tag markers with a
  session-unique nonce, restore only those) or prove `__dollar_\w+__` never occurs in real source;
  add a test.
- **I2 (CLI robustness):** `main()` has no per-file try/except — one unparseable file aborts a
  directory run mid-way (some files already written). Catch per file, print "skipped N".
- **M:** add `dist/` to `.gitignore` (a stray `clausal-0.4.0.tar.gz` was left untracked); add
  regression tests for the code-`@` and literal-`__dollar__` paths and the CLI error path; the
  design spec's "restore" section wrongly claims the corpus is `@`-free — fix if the spec is reused.

## Behaviour-preservation bar (the acceptance gate — unchanged)

Whitespace + trailing-comma only; idempotent (`fmt(fmt(x))==fmt(x)`); reify structural round-trip
(`head`+`goals`); corpus dry-run over a downstream rulebase corpus = 0 errors; one-domain
oracle+mutation green (peppol: `refutations=0`, all mutants killed). The shim impl passed ALL of
these — but only on `@`-free inputs. **The operator-patch impl MUST also test the code-`@`
fixtures** (`packages/clausal-jax/tests/fixtures/*.clausal`) to prove no corruption.
