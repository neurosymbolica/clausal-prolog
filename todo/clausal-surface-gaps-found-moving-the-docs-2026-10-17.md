# `.clausal` gaps found while moving the docs' examples off seam syntax

Filed 2026-10-17 by iso-export-lane. While the docs' examples moved from
seam syntax to Clausal Prolog (`.clausal`), each example was run in both
surfaces. These are the places where the seam works and `.clausal` does not.
Each docs page keeps the affected block as a ```seam block and says so. OPEN.

**Verified** means re-run by the filer on main c84149fb. **Reported** means
measured by the batch that converted the page, with its exact goal, and not
re-run separately.

## Engine bugs (the most important)

1. **FIXED 2026-10-20 (commit 9d1232d1)** The native front end now lowers
   their goal arguments as goals (`iso_l3._META_GOAL_ARGS`), as it does
   for `catch/3`. Pinned in tests/fixtures/catch_error_clausal_body.clausal
   and tests/iso_l3/test_l3_s1_bodies.py::test_catch_error_and_catch_recover_goal_arguments_are_goals;
   exceptions.md's examples are Clausal Prolog now.
   **`catch_error/2` and `catch_recover/3` do not compile in a `.clausal`
   clause body** (verified).
   - `t(R) :- catch_error(throw(boom(42)), R).` fails to load with
     `NotImplementedError: terms_to_goalop: goal shape not yet supported
     (tuple): ('throw', ('boom', 42))`.
   - The same goal works at the top level:
     `-g "catch_error(throw(boom(42)), R)"` gives `R = boom(42)`.
   - Page: exceptions.md.
2. **FIXED 2026-10-20 (commit 55a37b9c)** `entailed/1` and `clpq.entailed/1`
   now read a relation cell as well as a seam node, on both solvers; docs/clpq.md
   shows the Clausal Prolog spelling. Pinned in
   tests/test_clpq_entailed_relation_cells.py::test_clausal_entailed_relation_holds
   and ::test_clausal_program_under_each_solver.
   **`entailed/1` always fails, silently** (verified).
   - `:- use_module(library(clpq)). t :- in_q(X, 0, 100), {X =< 4},
     entailed(X =< 5).` answers `false`.
   - The builtin reads only seam syntax-tree nodes; both CLP(Q) backends
     behave the same.
   - Page: clpq.md.
3. **FIXED 2026-10-20 (commit bfe07aa3)** Both front ends now record each
   rule's variables by source name (`Predicate.var_names`), and goal
   expansion binds a group to the variable spelled exactly like it, head
   or body. Pinned by tests/fixtures/regex_named_groups.clausal and
   tests/iso_l3/test_l3_regex_named_groups.py; the three pages' examples
   are Clausal Prolog again (commit 8b4c7daa).
   **Regex named-group auto-binding binds nothing** (verified).
   - With `:- use_module(library(re), [match/2])`, the clause
     `parse_date(D, YEAR, MONTH) :- match("(?P<YEAR>\\d{4})-(?P<MONTH>\\d{2})", D).`
     makes `parse_date("2024-03", Y, M)` succeed with `Y` and `M` unbound.
   - Root cause (reported): a `.clausal` clause's head variables reach the
     goal expansion renamed `arg_0`, `arg_1`, so no group finds its
     variable.
   - Pages: regex.md, compiler.md, term_expansion.md.
4. **Python tuples cannot be taken apart** (reported). `G = (A, B)`,
   `G = [A, B]`, `G =.. L`, `arg/3` and `functor/3` all fail on a Python
   tuple. Two effects:
   - regex positional groups;
   - sqlite multi-column rows: `query("db1", "SELECT name, age FROM users",
     (N, A))` fails although the row exists.
5. **FIXED 2026-10-20 (commit 5b5dbf50)** `Database.get_dispatch` now
   answers from a row the module adopted at import, so both imports
   resolve, on both surfaces, for direct calls and meta-calls. Pinned in
   tests/test_import_same_name_different_arity.py.
   **Importing `p/1` from one module and `p/2` from another keeps only the
   later import** (reported, both surfaces). Calling `p(X)` then raises an
   arity mismatch; ISO and Scryer keep both.
6. **FIXED 2026-10-20 (commit bf34aa5c)** The reader refuses an empty
   argument list (ISO 6.3.3; Scryer: `incomplete_reduction`), so `nl()` is
   a syntax error with its position in `.clausal`, `.pl` (both front ends)
   and `-g`. Pinned in
   tests/iso_l3/test_l3_empty_argument_list_syntax_error.py.
   **`nl()` crashes** with an internal `TypeError` ("the 1-tuple ('nl',) is
   reserved") instead of raising an ISO syntax error (reported).

## Missing from `.clausal`, present in the seam (reported)

- **CLP(B):**
  - `sat(X & Y)`, `sat(X | Y)` and `sat(~X)` are syntax errors.
  - `sat(X * Y)`, `sat(X + Y)` and `sat(and(X, Y))` raise a Python
    `TypeError` (`'TypeError'(Msg)`, not an ISO error).
  - `:- use_module(library(clpb))` and `library(clpr)` are refused as
    unknown libraries.
  - `clpr:real((X =< 2.0))` raises `TypeError: clpr constraint block:
    unsupported node str`.
  - Pages: clpb.md, clpr.md, constraints.md.
- **Z3:** `'z3.integer'([1 =< X, X =< 3])` raises `TypeError: Cannot
  translate 'tuple' to Z3`. z3.md stays seam.
- **`if_/3` (library(reif))** works only as a written body goal.
  - `call(if_(...))`, `G = if_(...), G` and a lambda calling it all raise
    `existence_error(procedure, if_/3)`.
  - `if_(X #= 3, …)` raises `existence_error((#=)/3)`, and a comparison
    as its condition is undefined (`>=/3`).
  - `if_` as a grammar body calls an undefined `if_/5`.
- **Regex `findall/3`** is unreachable.
  - The call compiles as the meta-predicate `findall/3`.
    (2026-10-20: fixed. After `:- use_module(library(re), [findall/3]).`
    the body `findall(P, S, M)` and `re:findall(P, S, M)` run the regex
    predicate; `tests/test_imported_special_form_names.py`.)
  - `call(re:findall, …)` raises `permission_error(access, python_module,
    re)`, because `re` resolves to Python's module.
- **Importing `get/2` from library(http)** hides the dict builtin `get/3`:
  `get(P, scheme, S)` raises `type_error(text, …)`.
- **No literal syntax** for dicts, sets, bytes (`b"abc"`), f-strings or
  JSON `null` (`parse("null", N)` gives no atom `null`).
- **No yall lambdas:** `[X]>>G` raises `existence_error((>>)/N)`.
  `library(lambda)`'s `\X^G` works.
- **No `format/3` or `with_output_to/2`**, so a writer's output cannot be
  captured as text.
- **No ISO streams** (`open/3,4`). This is already listed in the ISO
  compatibility report.
- **Directives:** 16 seam directives are "unknown directive" in `.clausal`:
  `private/1`, `strict_atoms/0`, `implicit_atoms/0`, `implicit_functors/0`,
  `hide/1`, `shallow/1`, `allow_singletons/0`, `specialize/3`, `edcg_acc/5`,
  `edcg_pass/1`, `edcg_pred/3`, `double_quotes/1`, `tagged_terms/0`,
  `backend/1`, `import_from/2`, `import_module/1`.
- **Units:**
  - `has_units(F, newton)` fails when given a unit name; it works when
    given a quantity.
  - `X is 5 * kilo` raises `type_error(evaluable, kilo/0)`.
  - A qualified currency (`united_states:usd`) is refused in a declaration.
  - The currency predicates refuse a bare currency name:
    `money("7.89", euro, X)` raises `type_error(currency, euro)`.
- **Reflection:** `reified_clause/2` arrow patterns
  (`(H :- G1, G2)`) and the seam's short `Clause(H, G)` match nothing.
- **Field names:** a functor without a `:- constructors(...)` declaration
  has none in `.clausal`.

## Smaller differences (reported)

- `listing/1` prints seam syntax for `.clausal` code; `listing(digits//1)`
  prints `StarUnpack(...)`.
- `catch(X > 0, E, true)`, and a cross-unit comparison, report the context
  `(is)/2` rather than `(>)/2`.
- **FIXED 2026-10-20 (commit 3acb7b5b)** The hint is spelled for the
  surface that defines the predicate (`:- dynamic(f/N).` for `.clausal` and
  `.pl`); pinned in tests/test_dynamic_hint_names_the_surface.py.
  The `permission_error` message text says "declare it -dynamic(...)" even
  when raised from `.clausal`.
- `dict_pairs(D, [K-1])` with `K` unbound fails silently.
- `module_constant(m, max_retries, V)` fails when the module is given by
  name.
- `py_os:pid(P)` raises `existence_error`.
- `number/1` fails on the bare `Decimal` that `strip_units/2` returns (both
  surfaces).
- `clausal-fmt` refuses a `.clausal` file (exit 2), so it formats seam
  only.
- `:- use_module(regex, [match/2])` loads through the seam's `regex` alias,
  outside the `library(re)` facade.
- In both surfaces, ISO `is/2` in a clause body keeps a predicate from
  tail-call optimisation, and so does the seam's prefix CLP `==`. The old
  compiler.md example claimed otherwise.
