# Under `-double_quotes(chars)` a string must BE its char list in `==` and in `[H | T]` unification

Found 2026-09-08 by a downstream exporter on landed canonical 9246f385, reproduced and widened
by the engine lane. ISO chars mode: `"ab"` and `[a, b]` are the SAME term, so every term
operation must agree. Today (clausal.testing, `-double_quotes(chars)`):

| goal | Clausal | ISO/Scryer |
|---|---|---|
| `"ab" is [a, b]` (ground unify) | succeeds | true |
| `"ab" == "ab"`, `length("ab", 2)` | succeed | true |
| `"ab" == [a, b]` | **fails** | true |
| `[a, b] == "ab"` | **fails** | true |
| `"ab" == ['a', 'b']` | **fails** | true |
| `[H \| T] is "ab"` | **fails** | H = a, T = [b] |
| `"ab" is [H \| T]` | **fails** | H = a, T = [b] |

So structural equality (`==`, `clausal/logic/builtins/_registry.py::structural_unify` and the
`==` builtin) and unification of a string against a PARTIAL list (head/tail pattern, both
directions) do not apply the "a complete char list IS a string" rule that ground list
unification and `length/2` already apply (the flip's SegString / `maybe_promote_to_str`
discipline). The corpus suites compare answers with `==` and destructure with `[H | T]`, so
this surfaces the moment step (3) inserts `-double_quotes(chars)`.

Fix: in `==`, compare a `str` against a list by walking the list as chars (and a list of
1-char atoms against a str), and in the unifier, unify a `str` with a partial list by
binding the head to the first char atom and the tail to the remaining SegString/str (empty →
`[]`); mirror in the C twin and the Python twin (parity corpus). Pin all seven rows above.

## DONE 2026-09-08 — landed on canonical as 5ecee8b6

Surface `==` lowers to clpfd fd_eq, whose ground fallback was Python `==` (str vs list is False on sight); fixed by a text/char-list equality consulted in the ground fallback of fd_eq/fd_ne and the C-wrapper fronts, delegating to structural_eq so `==` cannot drift from `is`. Partial-list unification needed no change (rows 6-7 only looked broken through the `==` bug). Left open: `<`/`<=`/`>`/`>=` still diverge for str vs char list; `==` stays Python-equality for other two-spelling pairs (a ruling, not a patch).
