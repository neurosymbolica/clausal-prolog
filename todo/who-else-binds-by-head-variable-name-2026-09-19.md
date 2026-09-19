# Sweep: what else in the engine binds by HEAD-VARIABLE NAME?

Raised by iso-export-lane 2026-09-19, and the framing is the useful part: the
two instances found so far were each found BY ACCIDENT (a failing suite), not
by looking for the pattern. It is a CLASS, and a cell head cannot honour any
member of it, because a cell carries no names.

## The two known members

1. **Regex auto-binding** (`goal_expansion._collect_vars_from_term`).
   `match(r"(?P<YEAR>...)")` binds the group YEAR to the clause head's YEAR
   variable by NAME. Against a cell head the name -> Var map came back empty
   and 28 tests failed with everything UNBOUND and no error -- the only
   visible symptom was a singleton warning for the variable the expansion was
   meant to bind. Fixed by taking the names from the class the module binds.
2. **`_extract_param_names` -> `register_signature`**, which feeds
   `signature/3`, `vary/3` and `unbound_keys/2`. Answers None for a cell;
   names now come from the declaration.

## Not yet checked, and each is a candidate

* **Dot-attribute access** (`P.key`, shipped 2026-07-29) -- reads a TERM field
  by name. Terms have been cells since P3-2/Task 3, so if this reads an
  instance it is ALREADY broken, not broken by the head flip.
* **EDCG hidden arguments** (`p(L, _edcg_counter_in=0)`) -- resolved by name
  at the CALL site against a generated argument list. Kept working through
  the keyword-lint carve-out, but nothing pins WHY it still resolves.
* **DCG** `phrase/2` and the `normalize_seg_input` callers (already parked in
  memory as 8 sites that read a bare-str atom as text).
* **`-import_from` aliasing**, which rebinds a class under a local name while
  the row lives under the exporter's -- a name-keyed lookup by construction.

## How to sweep it properly

Not `grep term_field_names`: that finds every positional reader too (~160
sites, mostly innocent). The pattern is narrower -- a field NAME compared
against, or used to look up, a name that came from SOMEWHERE ELSE (a regex
group, a keyword argument, a dotted attribute, an import alias). An AST pass
for `getattr(<term>, <non-literal>)` and for dict lookups keyed on
`term_field_names(...)` output would find it; a text grep will not.

**Do this before P4 deletes the class**, because the class is currently what
answers "what are this functor's field names", and every member of this class
is silently relying on it.
