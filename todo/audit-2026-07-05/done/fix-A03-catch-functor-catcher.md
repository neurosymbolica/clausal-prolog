# fix(A03-F004): catch/3 never matches declared-functor exception terms

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/03-compiler-goals/findings.md` A03-F004
**Design:** A03-D001 (parked — recommendation (a) below does not need it resolved)
**Tests:** `tests/audit_2026_07_05/test_03_compiler_goals.py::TestF004CatchFunctorCatcher` (3 xfail — flip to pass)

## Bug

`_catcher_to_structural` (`control_constructs.py:642-647`) rewrites a
catcher `Call(LoadName("kab"), [N])` into `Compound("kab", (N,))`. The
throw site (`term_to_ast_expr`) constructs the module's declared `kab`
functor-class instance. `unify(Compound("kab",(N,)), kab(7))` is False, so
the catcher never matches and catch rethrows:

    -private([kab(KA)])
    cfun(N, R) <- catch(throw(kab(7)), kab(N), R is "caught")   # never catches

Works: var catchers, str/int catchers, builtin `error(...)` Compounds
(thrown as Compounds), and passing a PRE-BUILT instance through a variable
catcher argument (`targ` control). Broken: exactly the corpus idiom
(exception functors declared in `-private`/`-module`).

## Fix direction

Resolve the catcher name against the same term-class environment the throw
site uses: in `_compile_catch_impl`, lower the catcher with
`term_to_ast_expr` (which emits `kab(N)` construction when `kab` is a known
term class in `base_globals`) instead of pre-converting to Compound; keep
the Compound conversion only as fallback for names with no term class
(builtin error terms). `_catcher_to_structural` recursion must then only
run on unresolvable names.

Do NOT solve this by making `unify` accept Compound↔instance — that is
A01-D004 territory (parked) with index/tabling-key ramifications.

## Acceptance

- `cfun`/`cchain` catch and bind (7/5); root-cause unify probe updated.
- Controls stay green: var/str catchers, instance-through-var catcher,
  rethrow-on-miss, nondet recovery, catch_error/catch_recover.
- Cross-module functors: a catcher naming an IMPORTED functor must resolve
  to the same class (atoms are module-scoped — add a test with
  `-import_from`).
