# DCG `{...}` embedded goals: multi-goal silent drop + broken Prolog import

## STATUS: DONE (2026-07-19)
Fixed all three bugs. Multi-element `{g1, g2}` sets in DCG/EDCG body position now
lower to a conjunction (`And(g1, g2, ...)`, source order preserved by Python's AST)
at all four sites (`_rewrite_dcg_body`, both `_rewrite_dcg_sequence` fast paths via
a new `_dcg_set_goals` helper, `_rewrite_edcg_body`, `_rewrite_edcg_sequence`). Empty
`{}` (a Dict) now raises "empty {} block in DCG/EDCG body"; bare goals in body
position get a "wrap it in braces: {...}" hint. `prolog_to_clausal._emit_dcg_goal`
emits `{Goal}` / `{(A, B, ...)}` so imports round-trip (`bounded` rejects 12). Added
6 tests to tests/test_dcg.py (75 pass, was 69); documented multi-goal blocks + the
body-vs-data position rule in docs/dcg.md. Golden updated:
tests/fixtures/prolog_golden/dcg_grammar.clausal now pins the braced emission (the
old golden encoded the unbraced bug). Full suite: no new failures.

## Verdict on the design question first
KEEP `{}` as the embedded-goal syntax. Do NOT switch to `()`:
- `()` is already the DCG sequence/grouping syntax (`Tuple` → `_rewrite_dcg_sequence`),
  and `(helper(X))` would be irresolvably ambiguous between non-terminal and goal —
  the DCG rewrite is purely syntactic and cannot know.
- Fatal: Python's parser erases single-element parens — `(G)` parses identically to
  `G`, so single-goal `()` blocks are literally undetectable at the AST level.
- The set-literal conflict is narrow and positional: in DCG *body* position a bare
  set literal has no grammar meaning (terminals are lists), so claiming braces for
  goals shadows nothing. Set DATA still works fine where data belongs — verified:
  `tok >> ([{1, 2}])` consumes a set token; sets in non-terminal args untouched.
- `{}` is standard Prolog DCG syntax; keeping it preserves imports + muscle memory.

## What works today (probed)
- `{G}` single inline goal — works, documented (docs/dcg.md), 47 tests in
  tests/test_dcg.py (each brace holds ONE goal).
- `{(G1, G2)}` — parenthesized conjunction inside one brace pair works (the single
  Set element is a Tuple; the goal compiler flattens it). Undocumented.
- Sets as data inside terminals / args — work (braces only claim body position).

## Bug 1: `{G1, G2}` silently drops every goal after the first
`bounded(_d) >> ([_d], {_d > 0, _d < 10})` loads fine and ACCEPTS 50:
`_d < 10` is discarded. Root cause: both sequence rewriters take only `elts[0]`:
- clausal/templating/term_rewriting.py:1811 and :1836 (`_rewrite_dcg_sequence`)
- same pattern in `_rewrite_edcg_sequence` (~:2283-2285) — EDCG path identical
- inconsistently, a bare multi-element-set body (`r >> ({a, b})`) hits
  `_rewrite_dcg_body`'s `case Set(elts=[goal])` miss → SyntaxError instead.
Note `_is_dcg_passthrough` (:1648) treats ANY `Set` as passthrough, arity-blind.

FIX: treat `Set(elts=[g1, g2, ...])` in DCG/EDCG body position as a CONJUNCTION of
inline goals (Python's AST preserves source order in set displays, so order is
deterministic at rewrite time; the set is never materialized). This matches Prolog's
`{A, B}` exactly. Cover: `_rewrite_dcg_body` case, both sequence fast paths, EDCG.
Empty `{}` parses as a Dict — keep it an error but give it a real message
("empty {} block in DCG body") instead of `Unsupported DCG body element: Dict()`.

## Bug 2: prolog_to_clausal emits `{Goal}` WITHOUT braces
clausal/tools/prolog_to_clausal.py `_emit_dcg_goal` (~:475-477): `PCurly` →
`self._emit_goal(goal.body)` bare. Probed end-to-end:
- `count(N) --> [x], {N is 1}.` → `Count(N) >> ([x], eval_(1, N))` — the bare Call
  is rewritten as a NON-TERMINAL (2 hidden state args appended): silent semantic
  corruption, no load error.
- `bounded(D) --> [D], {D >= 0, D =< 9}.` → `... ([D], (D >= 0, D <= 9))` →
  load-time `SyntaxError: Unsupported DCG body element: Compare(...)`.

FIX: emit `{...}` for a PCurly with a single goal and `{(A, B, ...)}` for a
conjunction body (the verified-working forms). After Bug 1's fix, `{A, B}` would
also be acceptable output, but `{(...)}` works against both old and new engines.

## Bug 3 (polish): bare-goal error message
A bare goal in body position (`bare(_d) >> ([_d], _d > 0)`) correctly errors but
with an AST dump. Add a hint: "wrap embedded goals in braces: {_d > 0}".

## Acceptance
- `{_d > 0, _d < 10}` enforces BOTH goals ([50] fails); same for EDCG bodies.
- `r >> ({a, b})` (whole-body multi-goal block) behaves identically to the
  in-sequence form, not SyntaxError.
- Round-trip: the two Prolog rules above import, load, and parse correctly
  (`bounded` rejects 12).
- Existing 47 tests in tests/test_dcg.py unchanged; new tests for each bullet.
- docs/dcg.md documents multi-goal `{G1, G2}` and the set-literal position rule.
