# Meta-Interpreter Specialization via Partial Deduction

## Background

Meta-interpreters (MIs) are one of the most powerful features of logic
programming: write a small interpreter, extend it with tracing, depth
limiting, proof trees, or constraint propagation, and run any object
program through it.  The cost is interpretation overhead — every goal
resolution in the object program goes through the MI's own clause
matching, `CopyTerm`, list manipulation, and recursive calls.

**Partial deduction** (partial evaluation for logic programs) eliminates
this overhead.  Specializing an MI with respect to a known object program
produces a residual program structurally identical to the object program,
but with the MI's extensions (counting, depth tracking, proof logging)
woven directly into the compiled code.  This is the **first Futamura
projection** applied to logic programming.

The technique is well-established in the literature (Lloyd & Shepherdson
1991, Gallagher 1993, Leuschel et al. 2004) and has been implemented in
systems like LOGEN, ECCE, and Mixtus, demonstrating 10–400× speedups.

### What we already have

The `clausal/examples/metainterpreters.clausal` file contains five MIs
ported from Triska's *acomip*:

| MI | Signature | Extension over vanilla |
|---|---|---|
| `Solve/2` | `(Goals, Program)` | None — vanilla |
| `SolveCount/3` | `(Goals, Program, Count)` | Counts inference steps |
| `SolveLimit/3` | `(Goals, Program, Max)` | Depth-bounded search |
| `SolveIterativeDeepening/2` | `(Goals, Program)` | Complete search via ID |
| `SolveTree/3` | `(Goals, Program, Tree)` | Builds proof trees |

All use the same core loop:

```
Solve([GOAL, *GOALS], PROGRAM) <- (
    MatchClause(GOAL, BODY, PROGRAM),    # In + CopyTerm + unify
    Append(BODY, GOALS, ALL_GOALS),       # list append
    Solve(ALL_GOALS, PROGRAM)             # recursive MI call
)
```

The overhead per resolution step: `In` iterates the program list,
`CopyTerm` deep-copies a clause, `is` unifies the goal with the fresh
head, `Append` concatenates lists.  For a directly compiled predicate,
none of this exists — the compiler generates a match/dispatch function
that jumps straight to the right clause arm.

### What partial deduction would produce

Given the counting MI and a natnum object program:

```
NatnumProgram = [
    [["natnum", 0], []],
    [["natnum", ["s", X]], [["natnum", X]]]
]
```

Specializing `SolveCount([["natnum", GOAL_ARG]], NatnumProgram, COUNT)`
would produce:

```
# Residual — MI overhead removed, counting woven in
SolveCountNatnum(0, 1),
SolveCountNatnum(["s", X], COUNT) <- (
    SolveCountNatnum(X, SUB_COUNT),
    COUNT := SUB_COUNT + 1
)
```

The `In`/`CopyTerm`/`Append` machinery is gone.  The counting extension
remains, compiled directly into the object program's structure.  This
residual program compiles through the normal clausal pipeline and runs at
full speed.

---

## Design

### The user-facing API

Two directives, used together:

```clausal
# 1. Declare that SolveCount is a meta-interpreter.
#    Arg 2 (0-indexed: 1) carries the object program (static).
#    Arg 1 (0-indexed: 0) carries the goal list (dynamic).
-metainterpreter(SolveCount/3, program=1)

# 2. Request specialization for a specific object program.
-specialize(SolveCount, NatnumProgram, as=SolveCountNatnum)
```

The `-metainterpreter` directive declares which argument is the "program"
(static data to specialize on) and which is the "goal" (dynamic query).
Extra arguments (count, depth, tree) are implicitly dynamic.

The `-specialize` directive triggers the transformation.  It names:
- the MI predicate
- a nullary predicate that returns the object program (or a ground list literal)
- the name for the specialized predicate

After specialization, user code calls `SolveCountNatnum` directly — no
program argument, no interpretation overhead.

### Why a two-directive design

Separating declaration from use allows:

1. **One MI, many specializations** — `SolveCount` can be specialized
   for natnum, graph, or any other program independently.
2. **MI defined in a library module** — the `-metainterpreter` directive
   lives with the MI definition; `-specialize` lives in the user module.
3. **Explicit naming** — the user controls what the specialized predicate
   is called, avoiding magic names.

### Alternative: single-directive design

A simpler alternative collapses both into one:

```clausal
-specialize(SolveCount/3, program=1, source=NatnumProgram, as=SolveCountNatnum)
```

This is self-contained but verbose.  Either design works; the two-step
version is more composable.

---

## Architecture

### Where it fits in the pipeline

```
compile_module()
│
├─ Step 0: _process_imports()
├─ Step 1: run_term_expansion()
├─ Step 1b: run_goal_expansion()
├─ ★ Step 1c: run_specialization()     ← NEW
├─ Step 2: _process_directives()
├─ Step 3: _process_declarations()
├─ Step 4: assert clauses
├─ Step 5: compile predicates
├─ Step 6: wrap tabled
└─ Step 7: lock non-dynamic
```

Specialization runs **after** term/goal expansion (so the MI and object
program are in final form) and **before** clause assertion and
compilation (so residual clauses enter the normal pipeline).

`run_specialization()` consumes `-specialize` directives from
`module_items`, reads MI clauses and object program data, performs
partial deduction, and emits new `PredicateItem` nodes into
`predicate_nodes`.

### Core algorithm: offline partial deduction

We use the **offline** (annotation-driven) approach rather than a fully
automatic online specializer.  The `-metainterpreter` directive provides
the binding-time annotation: which argument is static.  This avoids the
complexity of automatic binding-time analysis while covering the
practical MI patterns.

```
SPECIALIZE(mi_clauses, object_program, mi_name, specialized_name):

    1. EVALUATE the object program
       - If it's a nullary predicate like NatnumProgram/1, call it to
         get the ground list of [Head, Body] pairs.
       - The result is a concrete list of clauses: PROGRAM.

    2. ANALYZE the MI
       - Identify the MI's recursive structure:
         * base case: Solve([], _PROGRAM)
         * recursive case: Solve([GOAL, *GOALS], PROGRAM) <- body
       - Identify MatchClause calls (goal ↔ clause matching)
       - Identify extra arguments (count, depth, tree, etc.)
       - Identify the recursive MI call in the body

    3. UNFOLD
       - For each clause [Head_i, Body_i] in PROGRAM:
         * Create fresh variables for Head_i and Body_i (via CopyTerm)
         * Substitute into the MI's recursive case:
           - MatchClause(GOAL, BODY, PROGRAM)  →  GOAL unifies with Head_i,
                                                    BODY = Body_i
           - Append(Body_i, GOALS, ALL_GOALS)  →  compute statically when
                                                    Body_i has known length
         * The result is one specialized clause per object clause
       - For the MI's base case (empty goal list):
         * Emit directly with extra args preserved

    4. RENAME recursive calls
       - MI calls in the residual body (Solve(ALL_GOALS, PROGRAM))
         become calls to the specialized predicate (SolveCountNatnum)
       - The PROGRAM argument is dropped (it was static)

    5. EMIT residual clauses as PredicateItem nodes
       - These enter the normal compilation pipeline
```

### Handling different MI patterns

The MI analysis in step 2 must recognize several structural patterns.
Rather than parsing arbitrary code, we match against known MI idioms:

**Pattern A: List-based tail-recursive (Solve, SolveCount, SolveLimit)**
```
MI([], ...)                                   # base
MI([GOAL, *GOALS], PROGRAM, ...) <- (         # recursive
    MatchClause(GOAL, BODY, PROGRAM),
    Append(BODY, GOALS, ALL_GOALS),
    MI(ALL_GOALS, PROGRAM, ...)
)
```

Specialization produces one clause per object clause.  The `Append` is
eliminated because `BODY` is statically known (its length and structure
come from the object clause).  For a fact (empty body), `ALL_GOALS =
GOALS` directly.  For a rule with body `[G1, G2]`, `ALL_GOALS = [G1,
G2, *GOALS]`.

**Pattern B: Non-tail-recursive (SolveTree)**
```
MI([], ..., [])                               # base
MI([GOAL, *GOALS], PROGRAM, ...) <- (         # recursive
    MatchClause(GOAL, BODY, PROGRAM),
    MI(BODY, PROGRAM, BODY_TREE),
    MI(GOALS, PROGRAM, GOALS_TREE)
)
```

Two recursive calls: one for the body, one for remaining goals.
Specialization must handle both.  Body goals become direct calls to
specialized predicates.  The remaining-goals call stays recursive (it
processes an unknown-length list).

**Pattern C: Extra pre-conditions (SolveLimit)**
```
MI([GOAL, *GOALS], PROGRAM, MAX) <- (
    MAX > 0, MAX1 := MAX - 1,                 # pre-condition
    MatchClause(GOAL, BODY, PROGRAM),
    ...
    MI(ALL_GOALS, PROGRAM, MAX1)
)
```

Pre-conditions before `MatchClause` are preserved verbatim in every
specialized clause.  Post-`MatchClause` goals that don't involve
`PROGRAM` are also preserved.

---

## Implementation Phases

### Phase 0: MI pattern recognizer  ✓ DONE

**Location:** `clausal/logic/specialization.py`

Implement `analyze_mi(clauses) → MIPattern` that inspects a set of MI
clauses and returns a structured description:

```python
@dataclass
class MIPattern:
    """Recognized meta-interpreter structure."""
    name: str                    # e.g. "SolveCount"
    arity: int                   # e.g. 3
    goal_arg: int                # position of goal-list argument (0-indexed)
    program_arg: int             # position of program argument (0-indexed)
    extra_args: list[int]        # positions of extra arguments (count, depth, tree)
    base_clause: Clause          # the [] base case
    recursive_clause: Clause     # the [GOAL, *GOALS] case
    pre_match_goals: list        # goals before MatchClause (e.g. MAX > 0)
    post_match_goals: list       # goals after MatchClause, before recursive call
    recursive_call_style: str    # "tail" or "split" (tail-recursive vs two-call)
```

The recognizer works by:
1. Finding the base clause (goal-list arg matches `[]`)
2. Finding the recursive clause (goal-list arg matches `[GOAL, *GOALS]`)
3. Walking the body to locate `MatchClause`, `Append`, and recursive
   self-calls
4. Classifying everything else as pre- or post-match goals

This is pattern matching on AST structure, not general program analysis.
It handles the five known MI shapes and raises `CannotSpecialize` for
anything it doesn't recognize.

**Tests:** `tests/test_specialization.py` — unit tests for pattern
recognition on each of the five MIs.

### Phase 1: Core unfolder  ✓ DONE

**Location:** `clausal/logic/specialization.py`

Implement `specialize_mi(mi_pattern, object_program, new_name) → list[PredicateItem]`:

1. **Evaluate** the object program to get a list of `[Head, Body]` pairs.
   - If `object_program` is a string naming a predicate, call it to get
     the list.
   - If it's already a list, use directly.

2. **For each object clause `[Head_i, Body_i]`**:

   a. Create fresh variables via `copy_term([Head_i, Body_i])`.

   b. Build the specialized clause head:
      - Goal-list arg: `[Head_i, *GOALS]` (match this specific head,
        remaining goals variable)
      - Program arg: removed entirely
      - Extra args: kept as-is

   c. Build the specialized clause body:
      - Pre-match goals: copied verbatim
      - For each goal G in Body_i:
        * If G matches a functor that appears as a head in the object
          program → emit a call to the specialized predicate with
          `[G, *REMAINING]` or just `G` (depending on tail vs split)
        * If G doesn't match any object head → leave as-is (it's a
          builtin or external call — this is an error for now, Phase 3
          handles it)
      - Recursive MI call: becomes a call to `new_name` with the program
        arg removed
      - Post-match goals: copied verbatim

   d. Actually, for the tail-recursive pattern, the transformation is
      simpler than the above.  The unfolding works at the level of the
      MI clause structure, not the object clause body:

      ```
      # MI recursive clause (after pattern recognition):
      MI([GOAL, *GOALS], PROGRAM, ...extra) <- (
          ...pre_match,
          MatchClause(GOAL, BODY, PROGRAM),
          Append(BODY, GOALS, ALL_GOALS),
          ...post_match,
          MI(ALL_GOALS, PROGRAM, ...extra')
      )

      # For object clause [Head_i, Body_i], substitute:
      #   GOAL = Head_i   (unified)
      #   BODY = Body_i   (from MatchClause)
      #   ALL_GOALS = [*Body_i, *GOALS]  (from Append)
      #
      # Result:
      NEW_NAME([Head_i, *GOALS], ...extra) <- (
          ...pre_match,
          ...post_match[ALL_GOALS ↦ [*Body_i, *GOALS]],
          NEW_NAME([*Body_i, *GOALS], ...extra')
      )
      ```

      For a fact (Body_i = []), ALL_GOALS = GOALS:
      ```
      NEW_NAME([Head_i, *GOALS], ...extra) <- (
          ...pre_match,
          ...post_match[ALL_GOALS ↦ GOALS],
          NEW_NAME(GOALS, ...extra')
      )
      ```

3. **Emit the base clause**:
   ```
   NEW_NAME([], ...extra_base_values)
   ```

4. **Return** the list of `PredicateItem` nodes.

**Tests:** Specialize each of the five MIs with the natnum and graph
programs.  Assert the residual clause count matches expectations.  Run
the specialized predicates and verify identical results to the
unspecialized versions.

### Phase 2: Pipeline integration

**Location:** `clausal/logic/compiler_v2.py`, `clausal/logic/specialization.py`

1. **Parse the `-metainterpreter` directive** in `_process_directives()`:
   - Store `(predicate_name, arity, program_arg_index)` on the
     module's metadata.

2. **Parse the `-specialize` directive**:
   - Store `(mi_name, source_program, new_name)` on the module's
     metadata.

3. **Implement `run_specialization()`** called from `compile_module()`:
   - For each `-specialize` directive:
     a. Look up the MI's clauses (from the current module or an import)
     b. Look up the MI's `-metainterpreter` annotation
     c. Evaluate the source program
     d. Call `specialize_mi()` from Phase 1
     e. Inject the resulting `PredicateItem` nodes into `predicate_nodes`
   - The injected predicates then flow through normal Step 4–7
     compilation.

4. **Handle imports**: If the MI is defined in a different module (e.g.
   `metainterpreters.clausal`), the `-metainterpreter` annotation must
   be discoverable from the importing module.  Store it on the
   `PredicateMeta` class as `_mi_annotation` so it travels with imports.

**Tests:** End-to-end `.clausal` files that import the MI library,
declare `-specialize`, and test the specialized predicates.

### Phase 3: Object programs with builtins and external calls

The Phase 1 unfolder assumes all goals in an object clause body match
heads in the same object program.  Real programs call builtins
(`In`, `Append`, arithmetic) or predicates from other modules.

**Approach:** Goals that don't match any head in the object program are
classified as **residual** — they pass through to the specialized code
unchanged.  The unfolder wraps them in a call that the normal compiler
handles.

For example, an object program:
```
[["factorial", N, R], [["gt", N, 0], ["sub", N, 1, N1],
                        ["factorial", N1, R1], ["mul", N, R1, R]]]
```

Here `gt`, `sub`, `mul` are not in the object program.  They must
remain as runtime goals.  The specialized clause would be:

```
SolveCountFactorial([["factorial", N, R], *GOALS], COUNT) <- (
    [["gt", N, 0]]  -- needs runtime dispatch
    ...
)
```

This requires either:
- A runtime `SolveGoal` predicate for unknown goals (falls back to the
  MI for these)
- A mapping from object-level functor names to clausal builtins

Phase 3 implements the first option: unknown goals are dispatched through
a small residual interpreter that handles only leaf goals.  This is a
standard technique in partial deduction ("residualization").

**Tests:** Object program with arithmetic/comparison goals.

### Phase 4: Termination control

For Phase 1–3, termination is guaranteed because:
- The object program is finite (finite number of clauses)
- Each object clause produces exactly one specialized clause
- The unfolder does not recursively unfold object-program calls (it
  just renames them)

True partial deduction (recursively unfolding object program calls too)
can diverge.  Phase 4 adds depth-bounded unfolding for cases where
deeper specialization is desired:

1. **Homeomorphic embedding test**: Compare each newly generated goal
   atom against the ancestor atoms in the unfolding tree.  If the new
   atom embeds a previous one (is structurally "bigger"), stop unfolding
   and memoize.

2. **Depth counter**: Simple backstop — never unfold more than N levels
   deep (configurable, default 10).

3. **Memoization table**: Track which `(functor, arg_pattern)` pairs have
   been specialized.  When a goal matches an already-specialized pattern,
   emit a call to the existing specialized predicate instead of
   re-unfolding.

Phase 4 is only needed for advanced use cases (specializing an MI that
itself does multi-level unfolding, or specializing with respect to a
recursive object program where inlining would be beneficial).

**Tests:** Recursive object programs, programs with mutual recursion.

### Phase 5: Conjunctive partial deduction (optional, future)

Standard partial deduction specializes individual atoms.  Conjunctive
partial deduction (Leuschel & De Schreye 1999) specializes *conjunctions*
as a unit, enabling:

- **Deforestation**: Eliminating intermediate list structures (e.g., the
  `ALL_GOALS` list in the tail-recursive MI)
- **Tupling**: Combining multiple traversals into one pass

This is a significant leap in complexity and is not needed for the core
MI specialization use case.  Phase 1–3 already eliminate the MI overhead.
Conjunctive PD would further optimize the residual code itself.

---

## Concrete example: full trace

### Input

MI (SolveCount from metainterpreters.clausal):
```
SolveCount([], _PROGRAM, 0),
SolveCount([GOAL, *GOALS], PROGRAM, COUNT) <- (
    MatchClause(GOAL, BODY, PROGRAM),
    Append(BODY, GOALS, ALL_GOALS),
    SolveCount(ALL_GOALS, PROGRAM, SUB_COUNT),
    COUNT := SUB_COUNT + 1
)
```

Object program (natnum):
```
[
    [["natnum", 0], []],
    [["natnum", ["s", X]], [["natnum", X]]]
]
```

### Step 1: Analyze MI

```
MIPattern(
    name="SolveCount", arity=3,
    goal_arg=0, program_arg=1,
    extra_args=[2],  # COUNT
    base_clause=SolveCount([], _, 0),
    recursive_clause=SolveCount([GOAL, *GOALS], PROGRAM, COUNT) <- ...,
    pre_match_goals=[],
    post_match_goals=[COUNT := SUB_COUNT + 1],
    recursive_call_style="tail"
)
```

### Step 2: Unfold — object clause 1 (fact)

Object clause: `[["natnum", 0], []]`
- Head = `["natnum", 0]`, Body = `[]`
- Substitute into MI recursive case:
  - GOAL = `["natnum", 0]`
  - BODY = `[]`
  - `Append([], GOALS, ALL_GOALS)` → `ALL_GOALS = GOALS`
- Residual clause:
  ```
  SolveCountNatnum([["natnum", 0], *GOALS], COUNT) <- (
      SolveCountNatnum(GOALS, SUB_COUNT),
      COUNT := SUB_COUNT + 1
  )
  ```

### Step 3: Unfold — object clause 2 (rule)

Object clause: `[["natnum", ["s", X']], [["natnum", X']]]`
(X' is a fresh variable from CopyTerm)
- Head = `["natnum", ["s", X']]`, Body = `[["natnum", X']]`
- Substitute into MI recursive case:
  - GOAL = `["natnum", ["s", X']]`
  - BODY = `[["natnum", X']]`
  - `Append([["natnum", X']], GOALS, ALL_GOALS)` →
    `ALL_GOALS = [["natnum", X'], *GOALS]`
- Residual clause:
  ```
  SolveCountNatnum([["natnum", ["s", X]], *GOALS], COUNT) <- (
      SolveCountNatnum([["natnum", X], *GOALS], SUB_COUNT),
      COUNT := SUB_COUNT + 1
  )
  ```

### Step 4: Base case

```
SolveCountNatnum([], 0)
```

### Final specialized program

```clausal
SolveCountNatnum([], 0),
SolveCountNatnum([["natnum", 0], *GOALS], COUNT) <- (
    SolveCountNatnum(GOALS, SUB_COUNT),
    COUNT := SUB_COUNT + 1
),
SolveCountNatnum([["natnum", ["s", X]], *GOALS], COUNT) <- (
    SolveCountNatnum([["natnum", X], *GOALS], SUB_COUNT),
    COUNT := SUB_COUNT + 1
)
```

No `In`, no `CopyTerm`, no `Append`, no `MatchClause`.  The counting
logic is woven directly into the clause structure.  This compiles through
the normal clausal pipeline.

---

## Key risks and mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| MI pattern too rigid | Medium | Start with the five known patterns; add a `CannotSpecialize` escape that falls back to unspecialized execution |
| Object program evaluation at compile time | Low | Programs are defined as facts/rules; evaluate via `call()` at module load time (already works for term expansion) |
| Variable freshening bugs | High | Lean on existing `CopyTerm` infrastructure; extensive test suite comparing specialized vs unspecialized results |
| Scope creep into general PE | Medium | Phases are strictly ordered; Phases 4–5 are explicitly deferred and optional |
| Interaction with tabling/CLP(FD) | Low | Specialized predicates are normal predicates — they can be tabled or use constraints via the usual directives |

---

## Testing strategy

Each phase has its own test layer:

1. **Phase 0 tests** — MI pattern recognition: feed each of the five MIs
   to `analyze_mi()`, assert the `MIPattern` fields.

2. **Phase 1 tests** — Core unfolder:
   - Specialize Solve/2 with natnum → run, compare results to
     unspecialized
   - Specialize SolveCount/3 with natnum → assert identical counts
   - Specialize SolveLimit/3 with graph → assert identical depth behavior
   - Specialize SolveTree/3 with natnum → assert identical proof trees
   - Property: for any MI and program, `Specialized(goal, extras...) ≡
     MI(goal, program, extras...)`

3. **Phase 2 tests** — End-to-end `.clausal` files with directives:
   ```clausal
   -import_from(metainterpreters, [SolveCount, MatchClause])
   -metainterpreter(SolveCount/3, program=1)
   -specialize(SolveCount, NatnumProgram, as=SolveCountNatnum)

   NatnumProgram(...) <- (...)

   Test("specialized count") <- SolveCountNatnum([["natnum", ["s", 0]]], 2)
   ```

4. **Phase 3 tests** — Object programs with external/builtin goals.

5. **Equivalence tests** — For every specialization, run both the
   original MI and the specialized version on the same inputs and assert
   identical solutions.

---

## Implementation Notes (Phase 0+1)

### Files created

- `clausal/logic/specialization.py` — `MIPattern`, `analyze_mi()`,
  `specialize_mi()`, `CannotSpecialize`
- `tests/test_specialization.py` — 49 tests (19 pattern recognition +
  28 unfolder + 2 equivalence)

### How it works at runtime

The specializer operates on **compiled runtime clauses** (Clause objects
with AST-node heads and bodies), not source text.  `analyze_mi()` inspects
the `_clauses` list of a PredicateMeta class and pattern-matches on Call,
Unify, Evaluate, Gt, StarUnpack nodes to recognize the MI structure.

`specialize_mi()` creates a new PredicateMeta class via `make_predicate()`,
builds specialized Clause objects by substituting object program data into
the MI template (using `_copy_term` for variable freshening and `_subst`
for structural substitution), then compiles via
`compile_predicate_trampoline()`.

### Key design choices

- **Works on runtime clauses**, not AST — avoids round-tripping through
  source/parse.  The imported MI's `pred_cls._clauses` are inspected
  directly.
- **Object programs must use Var()** for logic variables, not strings.
  The test helpers (`_make_natnum_program()`, `_make_graph_program()`)
  construct programs with proper Var sharing.
- **`_subst()` handles StarUnpack specially** — when substituting a Var
  that maps to a list, StarUnpack of that list is inlined (the elements
  are spliced in).

### TRO interaction

The tail recursion optimization (TRO) from commit 956b02b exposed two
edge cases when applied to specialized clauses:

1. **`_tro_args_safe` only checked top-level Vars** — list-valued tail
   call args like `[["natnum", X], StarUnpack(GOALS)]` were treated as
   "constant — always safe" because they're not Var instances.  Fixed to
   recursively collect all Var IDs via `_collect_var_ids`.

2. **TRO code gen can't handle StarUnpack in tail call args** — `deref()`
   doesn't expand StarUnpack nodes.  Fixed by rejecting TRO when any tail
   call arg contains StarUnpack (`_contains_star_unpack` helper).

See `/workspace/clausal-tailrecursion/TRO_EDGE_CASES.md` for full details
and diff.

---

## References

- Lloyd & Shepherdson (1991). *Partial Evaluation in Logic Programming.*
  Journal of Logic Programming, 11:217–242.
- Gallagher (1993). *Tutorial on Specialisation of Logic Programs.* PEPM.
- Leuschel, Jorgensen, Vanhoof & Bruynooghe (2004). *Offline
  Specialisation in Prolog Using a Hand-Written Compiler Generator.*
  TPLP 4(1):139–191.
- Leuschel & De Schreye (1999). *Conjunctive Partial Deduction.*
  Journal of Logic Programming, 41:233–277.
- Leuschel (1998). *Homeomorphic Embedding for Online Termination.*
- Sahlin (1993). *Mixtus: An Automatic Partial Evaluator for Full
  Prolog.* New Generation Computing, 12:7–51.
- Triska (2005–2023). *A Couple of Meta-interpreters in Prolog.*
  https://www.metalevel.at/acomip/
