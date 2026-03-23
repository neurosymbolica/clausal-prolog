# List Star Patterns Roadmap

## Completed: Phase 1 — Basic `[HEAD, *TAIL]` head/tail decomposition

**Changes made:**
- `clausal/logic/compiler.py`: Import `StarUnpack`; handle in `_collect_vars`, `_collect_head_types`, `_collect_types_from_term`, `head_to_match_pattern` (→ `MatchStar`), `term_to_ast_expr` (→ `ast.Starred`)
- `tests/clausal_modules/lists.clausal`: Rewritten with `[HEAD, *TAIL]` syntax

**What works now:**
- `[HEAD, *TAIL]` in clause heads — compiles to `case [_v0, *_v1]:`
- `[A, *MID, Z]` in clause heads — compiles to `case [_v0, *_v1, _v2]:`
- `[HEAD, *TAIL]` in body goals — constructs `[_v0, *_v1]` via Python star-unpacking
- Both simple and trampoline compilation modes
- Full `.clausal` module loading pipeline

## Completed: Phase 2 — Repeated Vars in head patterns + bidirectional list unification

**Changes made:**

Two related issues solved together:

1. **Repeated Vars in non-list head positions** (e.g., `append([], B, B)`):
   - `head_to_match_pattern` detects when a Var's `_id` is already in `var_context`
   - Second occurrence generates `MatchAs(name='_v0__dup0')` (unique dup name)
   - `compile_head_to_match_case` wraps body with `if unify(_v0, _v0__dup0, trail):` guards

2. **Bidirectional list pattern unification** (e.g., `[HEAD, *RESULT]` in output position):
   - List patterns in heads now compile as wildcard `MatchAs` captures instead of `MatchSequence`
   - Two runtime helpers: `_head_list_unify_input` (destructures lists) and `_head_list_unify_output` (constructs lists from bound vars)
   - Input check returns `True` (list destructured), `None` (Var, defer to output), or `False` (incompatible)
   - Output construction runs at each yield point via `_wrap_yields_with_output_guards`

3. **Duplicate field name deduplication** in `term_rewriting.py`:
   - `_derive_field_names()` helper ensures unique dataclass field names when the same Var name appears in multiple positional args of a trailing-comma fact

**Files:**
- `clausal/logic/compiler.py` — `head_to_match_pattern`, `compile_head_to_match_case`, `_head_list_unify_input`, `_head_list_unify_output`, `_wrap_yields_with_output_guards`
- `clausal/templating/term_rewriting.py` — `_derive_field_names()` helper
- `tests/clausal_modules/lists.clausal` — append/3, last/2 predicates
- `tests/test_search.py` — `TestRepeatedHeadVars` class (8 tests)

**What works now:**
- `append([], B, B)` — repeated var in non-list positions
- `append([HEAD, *TAIL], B, [HEAD, *RESULT])` — repeated var across list patterns + output-mode construction
- `last([X], X)` — repeated var in list + non-list positions
- Forward mode: `append([1,2], [3,4], RESULT)` → `RESULT=[1,2,3,4]`
- Reverse mode: `append(X, Y, [1,2,3])` → enumerates all splits

## Completed: Phase 3 — Anonymous variable `_`

**Changes made:**

1. **`clausal/templating/term_rewriting.py`** — `TermTransformer.visit_Name`: intercept `_` before the `_is_logic_var_name` check; emit a fresh `Var()` call (not tracked in `seen_vars`). Each `_` gets a distinct Var._id.

2. **`clausal/logic/compiler.py`** — `head_to_match_pattern` list branch: when a Var already in `var_context` appears as a list element, and it was registered as a **direct match capture** (not via list branch), generate a dup name and dup_guard. New `_list_reg_ids` parameter tracks which Vars were registered from list branches vs direct captures. Passed through `_head_arg_patterns` and `compile_head_to_match_case`.

3. **`clausal/logic/database.py`** — `_normalize_dataclass_fact`: added `_is_ground_value()` helper; only normalize field values that are truly ground (no Vars, no StarUnpack). Lists containing Vars or StarUnpack are structural patterns left intact for the compiler's list-guard machinery. Also imports `StarUnpack`.

4. **`tests/clausal_modules/anon.clausal`** — new fixture: `first/2`, `has_pair/1`, `second/2`, `const/2`, `member_of_pair/2`.

5. **`tests/clausal_modules/lists.clausal`** — use `_` for unused `HEAD` in `last/2` recursive clause.

6. **`tests/test_term_rewriting.py`** — three new tests for anonymous var: fresh per occurrence, never reused like named vars.

7. **`tests/test_search.py`** — `TestAnonymousVar` class: 11 integration tests.

**What works now:**
- `_` in clause heads → wildcard (accepts anything, no binding)
- Multiple `_` in the same clause → each is a distinct Var
- `_` in lists → fresh Var per occurrence; `*_` in list head patterns correctly captures the tail
- `_` in body goals → fresh Var (value not used after)
- `member_of_pair(X, [X, _])` — cross-pattern repeated Var + anonymous Var
- `last([_, *TAIL], X)` — anonymous Var in list head

## Completed: Phase 4 — Multiple stars `[*AS, *BS]` (combinatorial backtracking)

**Changes made:**

1. **`clausal/logic/compiler.py`** — `head_to_match_pattern` list branch: refactored to parse lists into segments (`("fixed", [elems])` / `("star", var)`). Counts stars; single-star uses existing `(before, star, after)` format, multi-star stores `(cap_name, segments, guard_vc, "multi")`.

2. **`clausal/logic/compiler.py`** — `_compile_multi_star_guard()`: new function that generates nested `for` loops over split points. For k stars, generates k-1 nested `range()` loops. Innermost body: `trail.mark()` + chained `unify()` calls mapping each segment to its list slice + body stmts + `trail.undo()`. Raises `TypeError` if the target is an unbound Var.

3. **`clausal/logic/compiler.py`** — `_head_multi_star_error()`: runtime error helper for unbound-Var multi-star patterns.

4. **`clausal/logic/compiler.py`** — `compile_head_to_match_case`: list guard processing split into single-star (existing path, untouched) and multi-star branches.

5. **`tests/clausal_modules/multistar.clausal`** — new fixture: `split/3`, `split3/4`, `around/3`, `split3way/4`.

6. **`tests/test_search.py`** — `TestMultiStarPatterns` class: 8 tests.

**What works now:**
- `[*A, *B]` — enumerate all 2-way splits of a ground list
- `[X, *A, *B]` — fixed element + 2-way split of remainder
- `[*A, X, *B]` — element at every position with prefix/suffix
- `[*A, *B, *C]` — all 3-way partitions (nested loops)
- Unbound Var target → `TypeError` (Pythonic error)
- Both simple and trampoline compilation modes
- Single-star path completely untouched (no regressions)

## Phase 5: Star in body unification (deconstruction)

When `[HEAD, *TAIL]` appears as a goal argument that receives a ground list, it must destructure:
- Construction (HEAD and TAIL bound): already works via Python's `[val, *rest]`
- Deconstruction (HEAD and TAIL unbound, receiving a list): needs the compiler to emit splitting code + trail-based unification

Currently body-position `[HEAD, *TAIL]` only works for **construction** (when the starred var is already bound to an iterable). Deconstruction would require detecting the direction and generating appropriate code.

**Note:** Head-position matching handles deconstruction naturally via `MatchStar`. Body deconstruction is only needed when `[HEAD, *TAIL]` appears in an `is` goal's right-hand side or as an argument to a predicate call where the Var is to be bound.

## Priority order

1. **Phase 2** (repeated Vars) — blocks useful patterns like `append`
2. **Phase 3** (anonymous `_`) — quality of life
3. **Phase 4** (multiple stars) — powerful but complex
4. **Phase 5** (body deconstruction) — niche, construction already works
