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

## Phase 3: Anonymous variable `_`

**Problem:** Bare `_` in `.clausal` files becomes `LoadName(name='_')` instead of a don't-care Var. The `TermTransformer.visit_Name` explicitly excludes `_` from logic variable treatment.

**Options:**
1. Make `_` a fresh anonymous Var in predicate context (different from Python's `_`)
2. Keep it as `LoadName` but handle in the compiler as a wildcard
3. Require users to use a named throwaway like `ANY`

**Recommendation:** Option 1 — `_` as anonymous Var in `.clausal` files only. Each occurrence generates a fresh `Var()` (no reuse like named vars).

## Phase 4: Multiple stars — `[*AS, *BS]` (combinatorial backtracking)

**Semantics:** `[*AS, *BS]` matched against `[1, 2, 3]` should enumerate all splits on backtracking:
- `AS=[], BS=[1,2,3]`
- `AS=[1], BS=[2,3]`
- `AS=[1,2], BS=[3]`
- `AS=[1,2,3], BS=[]`

**Challenge:** Python's `match` allows only ONE `MatchStar` per `MatchSequence`. Multiple stars need a different compilation strategy.

**Approach A — Desugar to loops:**
```python
# [*AS, *BS] in head against arg0
for _i in range(len(arg0) + 1):
    _v0 = arg0[:_i]   # AS
    _v1 = arg0[_i:]   # BS
    <body>
```

**Approach B — Desugar to `append`:**
Rewrite `pred([*AS, *BS])` head as `pred(LIST)` with body-prepended `append(AS, BS, LIST)`.

**N-way splits:** `[*A, *B, *C]` → nested loops over two split points. Combinatorial but finite for ground lists.

**Restrictions:** Multiple stars only meaningful when the list is ground (known length). Matching against an unbound Var is an error.

## Phase 5: Star in body unification (deconstruction)

When `[HEAD, *TAIL]` appears as a goal argument that receives a ground list, it must destructure:
- Construction (HEAD and TAIL bound): already works via Python's `[val, *rest]`
- Deconstruction (HEAD and TAIL unbound, receiving a list): needs the compiler to emit splitting code + trail-based unification

Currently body-position `[HEAD, *TAIL]` only works for **construction** (when the starred var is already bound to an iterable). Deconstruction would require detecting the direction and generating appropriate code.

**Note:** Head-position matching handles deconstruction naturally via `MatchStar`. Body deconstruction is only needed when `[HEAD, *TAIL]` appears in an `is` goal's right-hand side or as an argument to a predicate call where the Var is to be bound.

## Phase 6: `[H | T]` syntax (optional)

**Question:** Should `[H | T]` be supported as a Prolog-compat alias?

Python parses `|` as `BitOr`, so `[H | T]` becomes `[BitOr(left=H, right=T)]` — a single-element list with a BitOr node. Could intercept in `visit_List` or `visit_BinOp` to rewrite to `[H, StarUnpack(value=T)]`.

**Recommendation:** Drop it. `[HEAD, *TAIL]` is Pythonic and more powerful. The `|` syntax is confusing because it looks like a 1-element list.

## Priority order

1. **Phase 2** (repeated Vars) — blocks useful patterns like `append`
2. **Phase 3** (anonymous `_`) — quality of life
3. **Phase 4** (multiple stars) — powerful but complex
4. **Phase 5** (body deconstruction) — niche, construction already works
5. **Phase 6** (`|` alias) — optional, probably skip
