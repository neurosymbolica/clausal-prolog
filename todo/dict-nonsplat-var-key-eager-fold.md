# Non-splat dict literal with a variable key `{K: V}` is mis-folded to an eager constant

**Filed:** 2026-07-21 (query-taxonomy coverage sweep). **Sibling of the FIXED splat
case** `140388c1` (`fix(compiler): deref a variable splat-dict key at construction time`).
**Deep-dive merged** 2026-07-21 from the orchestrator's `DICT-VAR-KEY-FINDINGS.md`
(file absorbed here and deleted). **Re-verified live on HEAD `a1cb0230`** — the
bare-atom reification fix does not interact with construction; the compiler bug stands.
The same literal ALSO crashes the reifier — that is a separate, smaller fix:
`dict-var-key-reify-unhashable.md`.

## Symptom
A NON-splat dict literal whose KEY is a logic variable bound in the same clause frame
reads back wrong (the key is the Var object, not its value). Silent-wrong: no error.

```clausal
bad(GOT) <- (K is "age", OUT is {K: 20}, get(OUT, "age", GOT))   # GOT does NOT unify with 20
```

Controls that DO work (so this is specifically the var-KEY-in-a-non-splat-literal case):
- literal key: `{"age": 20}` ✓
- variable VALUE: `V is 20, {"age": V}` ✓ (var values already defer to call time)
- splat form: `{**OLD, K: 20}` ✓ (fixed in `140388c1`)

Repro runner (all four as Tests; currently 3 passed, 1 failed):
```
PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/versions/3.13.3/bin/python \
  -m clausal.testing t.clausal
```
(`is/2` is unification, `==/2` evaluates — `A == 20` is the right numeric check.)

## Root cause (two layers)
1. **Variable collection skips dict keys.** `clausal/logic/compiler/_vars.py` `_collect_vars`
   — the `DictTerm` branch (`# recurse into values (keys are ground)`) recurses into VALUES
   only, so a variable KEY is never registered as a clause var. The literal is therefore
   classified as a compile-time constant and built EAGERLY during module exec, when `K` is
   still unbound. (The plain-`dict` branch just above already recurses into keys.)
   Evidence of the eager build: `clausal/import_hook.py` `_make_intern_atom` docstring
   (~lines 68-86) — "dict literals are built eagerly during `exec` — before the bare-atom
   mint pass runs."
2. Because it is folded eager, the `$dict_key` deref added for the splat path (which runs at
   call time) does not save it — at eager-build time the key is genuinely unbound.
   NB fixing `_collect_vars` alone did NOT defer the literal in the first attempt — either
   that collector is not the operative one for a source-level clause-body dict (still a
   pythonic-AST `ast.Dict`/`DictLiteral`, not yet a `DictTerm`), or there is a second fold.
   The AST-level constant/foldable detection (the pass that lets `{"age": V}` defer but
   folds `{K: 20}`) is the other candidate — trace from
   `clausal/templating/term_rewriting.py` `visit_Dict` (~763) / `_visit_dict_key` (~726)
   into the clause-body compiler's constant hoisting. The var-VALUE path is the working
   reference to mirror.

## First attempt — why it was reverted (do NOT re-apply as-is)
(a) made `_collect_vars` recurse into `DictTerm` keys; (b) wrapped non-splat logic-var keys
with `$dict_key(...)` in `term_rewriting._visit_dict_key`; (c) registered `$dict_key` in
`import_hook`'s `module_dict` (next to `$intern_atom`). The literal was STILL built eagerly,
so `$dict_key` derefed an UNBOUND `K` → `instantiation_error` at module LOAD — converting a
silent-wrong into a load crash for any file containing such a literal. Lesson: the deref
alone is not enough; the literal must first DEFER to call time (so `K` is bound). Once it
defers, the `$dict_key` machinery already in place makes it correct.

## Reference pattern — the landed splat fix (`140388c1`)
- `clausal/logic/runtime/dict_ops.py`: `_dict_key(key)` — derefs; `instantiation_error`
  if still unbound (mirrors `_splat_data`).
- `clausal/logic/compiler/predicate.py`: `"$dict_key": _dict_key` registered in the two
  base_globals dicts (next to `$splat_data`, ~lines 753 & 1489).
- `clausal/logic/compiler/terms_to_ast.py`: `DictLiteral` lowering (~line 318) wraps a key
  with `$dict_key` when `is_var(k)` — in BOTH splat and non-splat branches. For splat this
  runs at CALL time (bound → correct); for non-splat it runs at eager-build time (unbound →
  this bug). So: make the non-splat var-key literal defer, and the existing wrap does the rest.
  Register `$dict_key` wherever the now-call-time construction resolves names.

## Definition of done
- All four repro cases pass (non-splat bound var key reads back).
- An UNBOUND non-splat key (`OUT is {K: 20}`, K never bound) fails/raises cleanly at call
  time — `catch/3`-able, NOT a module-LOAD crash.
- Regression test mirroring `tests/test_dict_splat_var_key.py`
  (+ `tests/fixtures/dict_splat_var_key.clausal`) for the non-splat form.
- Full suite: no NEW failures. The pre-existing failures are missing-solver deps — filter:
  `... | grep '^FAILED' | grep -viE 'sat|pysat|clp|scip|_lp|glop|ortools|solver'`.

## Impact / priority
LOW-MEDIUM: corpus domains use the splat form (`{**PROFILE, KEY: VALUE}`) for what_if, which is
fixed. The bare-var-key non-splat form is rare. But it is a SILENT-wrong (no error), so worth
fixing or at least making loud. Coordinate with `dict-var-key-reify-unhashable.md` (same
trigger literal, reflection layer) — fixing reflection first gives the auditor engine a loud
error instead of a crash while this deeper compiler fix is pending.
