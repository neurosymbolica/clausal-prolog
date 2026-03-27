# SWI-Prolog Packs Worth Porting as Builtins

Ranked by usefulness — how often a typical Prolog project would reach for this if it existed.

---

## Tier 2 — Most Serious Projects Benefit

### 7. mavis — Optional Type Declarations
- **Pack:** https://www.swi-prolog.org/pack/list?p=mavis
- **What it does:** Lets you declare argument types for predicates (`:-type foo(+integer, -list)`). Checks at runtime. Catches errors early without abandoning Prolog's dynamic nature.
- **Why port it:** "What types does this predicate expect?" is the #1 question when reading someone else's Prolog code. Even optional, non-enforced declarations dramatically improve readability and tooling.
- **Downloads:** 1,130
- **Complexity to port:** Medium — uses `term_expansion` and runtime hooks.

### 8. func — Function Application and Composition
- **Pack:** https://www.swi-prolog.org/pack/list?p=func
- **What it does:** Allows `Y = ~succ(~succ(0))` style nested function calls instead of chaining intermediate variables. Also provides composition operators.
- **Why port it:** Prolog's insistence on explicit unification variables for every intermediate result makes simple transformations verbose. Function notation is the most-requested syntactic sugar in Prolog communities.
- **Downloads:** 399 (well-rated)
- **Complexity to port:** Medium — uses `goal_expansion`.

### 10. clpBNR — CLP over Reals via Interval Arithmetic
- **Pack:** https://www.swi-prolog.org/pack/list?p=clpBNR
- **What it does:** Constraint Logic Programming over reals, integers, and booleans using interval narrowing. More robust than `clpqr` for many practical problems.
- **Why port it:** CLP(FD) is standard for integers, but real-valued constraints are increasingly needed (engineering, optimization, verification). clpBNR is actively maintained and well-documented.
- **Downloads:** 4,160
- **Complexity to port:** Medium-High — pure Prolog but relies heavily on attributed variables.

### 11. memo — Persistent Memoisation
- **Pack:** https://www.swi-prolog.org/pack/list?p=memo
- **What it does:** Declare a predicate as memoised; results are cached persistently (to disk) across sessions. Volatile mode also available for in-session caching.
- **Why port it:** Tabling handles the in-session case, but memo-to-disk for expensive computations (web API calls, heavy analysis) is a different need. Transforms `O(n)` repeated work into `O(1)` lookups.
- **Downloads:** 1,025
- **Complexity to port:** Medium — needs persistence backend.

### 12. quickcheck — Property-Based Testing
- **Pack:** https://www.swi-prolog.org/pack/list?p=quickcheck
- **What it does:** Generate random test cases from type declarations. Shrinks failing cases to minimal counterexamples.
- **Why port it:** PlUnit (example-based testing) is built-in everywhere; property-based testing is the natural complement. Prolog's backtracking makes it especially well-suited to shrinking.
- **Downloads:** 218
- **Complexity to port:** Medium — needs random generators per type.

---

## Tier 3 — Valuable for Specific Domains but Broadly Useful

### 13. tokenize — Text Tokenization
- **Pack:** https://www.swi-prolog.org/pack/list?p=tokenize
- **What it does:** Split text into tokens (words, numbers, punctuation, whitespace) with configurable rules.
- **Why port it:** The first step in almost any NLP or text-processing pipeline. Surprisingly absent from standard libraries given Prolog's strengths in symbolic processing.
- **Downloads:** 391
- **Complexity to port:** Low — pure Prolog / DCG based.

### 17. callgraph — Predicate Call Graph Visualisation
- **Pack:** https://www.swi-prolog.org/pack/list?p=callgraph
- **What it does:** Analyses source and produces a visual graph of which predicates call which. Output to DOT/Graphviz.
- **Why port it:** Essential for understanding unfamiliar codebases. Most IDEs for other languages provide this; Prolog should too. Second-most downloaded pack overall (3,962).
- **Downloads:** 3,962
- **Complexity to port:** Medium — source analysis + DOT output.

### 18. cli_table / clitable — Pretty Terminal Tables
- **Pack:** https://www.swi-prolog.org/pack/list?p=cli_table
- **What it does:** Formats tabular data with Unicode box-drawing characters for terminal display.
- **Why port it:** Prolog is REPL-first. Dumping query results as aligned, bordered tables makes interactive exploration vastly more productive. Small library, big UX improvement
- **Downloads:** 68 / 542
- **Complexity to port:** Low — pure Prolog, string formatting.

## Tier 4 — Nice to Have, Worth Considering

### 21. with — Context Managers
- **Pack:** https://www.swi-prolog.org/pack/list?p=with
- **What it does:** `with(open(File, read, S), read_term(S, T))` — ensures cleanup even on failure/exception.
- **Why port it:** `setup_call_cleanup/3` is the primitive; `with` makes the pattern ergonomic.
- **Downloads:** 338
- **Complexity to port:** Low.

### 22. sweet — Syntactic Sugar
- **Pack:** https://www.swi-prolog.org/pack/list?p=sweet
- **What it does:** `if-then-else` without cut, `forall` variants, `unless`, `when`, and other control-flow helpers.
- **Why port it:** Makes Prolog code more readable for people coming from other languages, without sacrificing semantics.
- **Downloads:** 797
- **Complexity to port:** Low — goal_expansion macros.

### 23. delay — Avoiding Instantiation Errors
- **Pack:** https://www.swi-prolog.org/pack/list?p=delay
- **What it does:** Wraps built-in predicates so they delay (via coroutining) instead of throwing instantiation errors.
- **Why port it:** Makes predicates like `succ/2`, `plus/3`, `atom_codes/2` work relationally in more modes. Moves Prolog closer to its declarative ideal.
- **Downloads:** 845
- **Complexity to port:** Medium — uses `freeze/when` and wrapper generation.

### 24. rdet — Runtime Determinacy Checking
- **Pack:** https://www.swi-prolog.org/pack/list?p=rdet
- **What it does:** Annotate predicates as expected-deterministic; get warnings if they leave choice points.
- **Why port it:** Unwanted nondeterminism is one of the most common Prolog bugs. This catches it early.
- **Downloads:** 180
- **Complexity to port:** Low-Medium.

### 25. union_find — union-Find Algorithm
- **Pack:** https://www.swi-prolog.org/pack/list?p=union_find
- **What it does:** Disjoint-set data structure with near-O(1) union and find.
- **Why port it:** Fundamental algorithm for equivalence classes, graph connectivity, type inference, constraint solving. Used as a building block by many other libraries.
- **Downloads:** 49
- **Complexity to port:** Low — can be done with attributed variables or mutable terms.

### 26. condition — Common-Lisp-Style Condition System
- **Pack:** https://www.swi-prolog.org/pack/list?p=condition
- **What it does:** Restartable exceptions: signal a condition, let a handler choose how to recover, resume execution at the signal point.
- **Why port it:** Much more powerful than throw/catch for recoverable errors. Prolog's backtracking makes this even more natural than in Lisp.
- **Downloads:** 695
- **Complexity to port:** Medium.

### 27. reif_utils — Reified Utility Predicates
- **Pack:** https://www.swi-prolog.org/pack/list?p=reif_utils
- **What it does:** Reified versions of common predicates (membership, comparison, type tests) for use with `if_/3` from reif.
- **Why port it:** Natural companion to reif (#1). Without these, users have to write their own `_t` predicates for everything.
- **Downloads:** 25
- **Complexity to port:** Low — pure Prolog, depends on reif.

### 28. pPEG — Parsing Expression Grammars
- **Pack:** https://www.swi-prolog.org/pack/list?p=pPEG
- **What it does:** Define PEG grammars as strings, parse text into ASTs. Packrat parsing with memoisation.
- **Why port it:** PEGs are deterministic and often easier to reason about than DCGs for practical parsing tasks. Good complement to DCGs, not a replacement.
- **Downloads:** 216
- **Complexity to port:** Medium.

### 29. openapi — OpenAPI / Swagger Interface
- **Pack:** https://www.swi-prolog.org/pack/list?p=openapi
- **What it does:** Generate or consume REST APIs from OpenAPI specs. Auto-routing, validation, documentation.
- **Why port it:** If your Prolog has an HTTP server, adding OpenAPI support makes it viable for real-world web services.
- **Downloads:** 310
- **Complexity to port:** High — depends on HTTP framework, JSON, YAML.

### 30. lsp_server — Language Server Protocol
- **Pack:** https://www.swi-prolog.org/pack/list?p=lsp_server
- **What it does:** Full LSP implementation — completion, diagnostics, go-to-definition, hover, references.
- **Why port it:** Editor integration is non-negotiable for adoption. If you want people to use your Prolog, ship an LSP. Most downloaded pack overall (4,022).
- **Downloads:** 4,022
- **Complexity to port:** Very High — but very high value. Depends on your Prolog's introspection capabilities.

---

## Summary: Suggested Porting Priority

| Priority | Pack | Effort | Impact |
|----------|------|--------|--------|
| 🔴 Do first | reif | Low | Massive — changes how people write Prolog |
| 🔴 Do first | list_util | Low | High — eliminates daily friction |
| 🔴 Do first | lambda | Low | High — enables idiomatic higher-order code |
| 🔴 Do first | dcgutils | Low | High — completes a core feature |
| 🟠 Do soon | date_time | Medium | High — every real app needs dates |
| 🟠 Do soon | log4p | Low-Med | High — required for production use |
| 🟠 Do soon | mavis | Medium | High — readability and correctness |
| 🟠 Do soon | func | Medium | Medium-High — ergonomics |
| 🟡 Do next | tokenize | Low | Medium — text processing enabler |
| 🟡 Do next | quickcheck | Medium | Medium — testing infrastructure |
| 🟡 Do next | prosqlite | High | High — but requires C FFI |
| 🟡 Do next | cli_table | Low | Medium — REPL quality of life |
| 🟢 when ready | clpBNR | High | Domain-specific but valuable |
| 🟢 when ready | lsp_server | Very High | Critical for adoption |
| 🟢 when ready | openapi | High | Web service enabler |
