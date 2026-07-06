# fix(A10-F005): regex auto-binding silently loses bindings for body-only named groups

**Problem.** `goal_expansion._expand_regex` binds each ALLCAPS named group via
`Unify(target_var, thunk)` where `target_var = ctx.find_var_for_group(name)`.
`find_var_for_group` (goal_expansion.py:75-83) resolves `YEAR` → field name
`"year"` against `_clause_vars`, which `_collect_vars_from_term` populates only
from term-instance FIELD names (head args, plus junk keys like `left`/`right`
from operator-node dataclasses; bare Vars in Call args return early at
:106-108). A group naming a variable that appears only in the BODY gets the
"typo" fallback — a fresh Var — so the match succeeds and the binding is
silently lost. The docs snippet (`term_expansion_sigs.txt` regex_auto_binding:
"what the compiler sees: `YEAR is _G["YEAR"]`") promises by-NAME binding.

**Repro/test.** test_10_rewriting_import.py::test_F005_regex_body_only_group_binds
(xfail); guard ::test_F005_guard_regex_head_var_group_binds.

**Fix directions (pick one):**
1. Give goal expansion a name→Var map that actually covers body vars: the
   clause's Vars are allocated by named walrus expressions in generated code —
   record the name at allocation (e.g. `Var(name=…)` if supported, or a
   side-table `{name: var}` emitted by TermTransformer onto the Predicate
   node) and let `find_var_for_group` consult it.
2. Fallback heuristic: extend `_collect_vars_from_term` to also walk operator
   dataclass fields into nested Vars keyed by the group-derived field name of
   the ENCLOSING head only — insufficient for true body-only vars; not
   recommended alone.
3. If by-name body binding is declared out of scope: make the unmatched-group
   case a load-time warning/error instead of a silent fresh Var, and fix the
   docs to say groups bind head arguments only.

Also fix the `_clause_vars` junk-key pollution (`left`/`right`/`operand`
field names can accidentally match a group named LEFT/RIGHT/OPERAND — a
group `(?P<LEFT>…)` would bind to an unrelated operand Var).
