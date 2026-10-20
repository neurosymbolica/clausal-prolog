# fix(A11-F002): regex predicates str()-coerce their subject — unbound Var matches its own repr; char-lists become repr garbage

Every predicate in `clausal/modules/py/re.py` (:64-161) does
`compiled.match(str(string))` with no instantiation/type guard:
- unbound Var: `search(r"^_\d+$", X)` SUCCEEDS against the Var's internal name
  ("_23") — answers depend on the allocation counter; `replace` rewrote a Var
  repr to "X31".
- char-list subject (strings-as-lists Liskov, docs/strings_as_lists.md):
  `match(r"\d+", ["1","2","3"])` fails (repr starts with `[`);
  `search(r"'", ["a"])` falsely succeeds on the repr quotes; replace/split
  produce garbage.
- bound non-str silently stringified (`match(r"\d+", 123)` matches "123").

**Fix** (per A11-D002 recommendation): raise `instantiation_error` on unbound
(house style: logic/builtins/chars.py:161); join a list of 1-char strings to
str (Liskov); `type_error` otherwise. Never `str(term)`.

**Tests**: test_F002_search_unbound_subject_no_solution,
test_F002_match_charlist_equals_string, test_F002_charlist_repr_false_positive
(all xfail).
