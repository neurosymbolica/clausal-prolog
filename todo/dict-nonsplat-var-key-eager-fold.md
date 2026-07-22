# Non-splat dict literal with a variable key `{K: V}` is mis-folded to an eager constant

**Filed:** 2026-07-21 (query-taxonomy coverage sweep). **Sibling of the FIXED splat
case** `140388c1` (`fix(compiler): deref a variable splat-dict key at construction time`).

## Symptom
A NON-splat dict literal whose KEY is a logic variable bound in the same clause frame
reads back wrong (the key is the Var object, not its value):

```clausal
bad(GOT) <- (K is "age", OUT is {K: 20}, get(OUT, "age", GOT))   # GOT does NOT unify with 20
```

Controls that DO work (so this is specifically the var-KEY-in-a-non-splat-literal case):
- literal key: `{"age": 20}` ✓
- variable VALUE: `V is 20, {"age": V}` ✓ (var values already defer to call time)
- splat form: `{**OLD, K: 20}` ✓ (fixed in `140388c1`)

## Root cause (two layers)
1. **Variable collection skips dict keys.** `clausal/logic/compiler/_vars.py` `_collect_vars`
   — the `DictTerm` branch (`# recurse into values (keys are ground)`) recurses into VALUES
   only, so a variable KEY is never registered as a clause var. The literal is therefore
   classified as a compile-time constant and built EAGERLY during module exec, when `K` is
   still unbound. (The plain-`dict` branch just above already recurses into keys.)
2. Because it is folded eager, the `$dict_key` deref added for the splat path (which runs at
   call time) does not save it — at eager-build time the key is genuinely unbound.

A first attempt (recurse into DictTerm keys in `_vars.py` + wrap non-splat var keys with
`$dict_key` in `term_rewriting.visit_Dict` + register `$dict_key` in `import_hook`) only
converted the silent-wrong into an `instantiation_error` at LOAD time — confirming the eager
fold happens before `K` binds, and risking module-load breakage. Reverted; the splat-only fix
shipped instead.

## Fix direction
Make a variable KEY mark the dict literal NON-constant so it defers to call time, exactly as a
variable VALUE already does. Find the AST-level constant/foldable detection for dict literals
(the pass that lets `{"age": V}` defer but folds `{K: 20}`) and have it treat a variable key
as non-constant; then the existing `$dict_key` deref makes it correct. Add a regression test
mirroring `tests/test_dict_splat_var_key.py` for the non-splat form.

## Impact / priority
LOW-MEDIUM: corpus domains use the splat form (`{**PROFILE, KEY: VALUE}`) for what_if, which is
fixed. The bare-var-key non-splat form is rare. But it is a SILENT-wrong (no error), so worth
fixing or at least making loud.
