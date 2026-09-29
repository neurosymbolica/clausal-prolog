# phrase/2,3 of a list or string should parse it as a terminal

Parked 2026-09-25 (call-runs-body-terms round 5) as a feature.

ISO DCG (WG17 DCG draft; Scryer's library(dcgs)) makes a list in a grammar
body a TERMINAL, and `phrase/2,3` accepts any grammar body, so:

```
?- phrase([a], L).        % Scryer: L = [a]
?- phrase("ab", L).       % Scryer: L = [a, b]  (double_quotes = chars)
```

Clausal fails both today -- `dcg._resolve_nonterminal` accepts only a CELL
nonterminal, and every other shape falls to `return None`:

```python
# clausal/logic/builtins/dcg.py, _resolve_nonterminal
if not is_cell:
    ...
    return None            # phrase([a], L) / phrase("ab", L): no answers
```

Pinned as-is by
`tests/test_call_runs_body_terms.py::test_phrase_of_a_list_or_string_keeps_failing`
(with a note that Scryer answers).  To do: in `_phrase__2/3`, a non-empty
list or chars rule unifies `List` with `Rule ++ Rest` (Rest = [] for
phrase/2); the empty list is the empty terminal (`phrase([], L)` gives
`L = []`).  Control-construct rule bodies (`phrase((a, b), L)`) are the
larger half of the same feature -- a DCG body interpreter, the grammar
analogue of `call_body`.

## Closed 2026-09-30

Fixed on fix/todo-batch-2-2026-09-30: `_resolve_nonterminal` translates a
list/string/code-list body through `_dcg_body_goal` (which already turned a
terminal list into `append(Items, S, S0)` for a control body), exactly as it
does a control-construct body. Scryer-verified rows (phrase/2 and /3, `[]`,
chars, a failing match) pinned in tests/test_call_runs_body_terms.py; the old
"keeps failing" pin is flipped. Control-construct bodies had already landed
(triage B3b).
