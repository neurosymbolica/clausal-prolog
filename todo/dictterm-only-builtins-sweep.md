# Sweep: which other builtins are DictTerm-only while a sibling spelling is lenient?

**Filed:** 2026-08-31, the "Not addressed here" item from
[[done/get3-rejects-a-plain-dict-that-subscript-accepts]] when the profile API
(`get/3`, `get/4`, `tri_get/3`, `delete/3`) was widened to accept plain dicts.

The trap shape: one spelling of an operation accepts `DictTerm | dict`
(subscript, `DictTerm.__unify__`, structural `==`), a sibling spelling accepts
only `DictTerm` and fails SOFTLY — so a Python caller passing `{'k': v}` gets a
partly working profile and a wrong answer instead of an error.

Known DictTerm-only candidates, none yet checked for a lenient sibling:

- The KEY-first family in `clausal/logic/builtins/dict_set.py`: `dict_get/3`,
  `dict_put/4`, `dict_put_pairs/3`, `dict_remove/3`, `dict_merge/3`,
  `gen_dict/3`, `sub_dict/2`, `dict_size/2`, `dict_keys/2`, `dict_values/2`,
  `dict_pairs/2`, and `is_dict/1`.
- The `in` operator with a plain dict on the right: key mode works via the
  `iter()` fallback, but pair mode `(K, V) in D` iterates KEYS, not items, for
  a plain dict — `_in_iter` (`clausal/logic/runtime/body_star_unify.py`)
  special-cases only DictTerm for pair mode, so a plain dict yields keys that
  then fail to unify with the tuple pattern (silent no-solutions, found
  2026-08-31 while fixing [[done/in-predicate-does-not-accept-a-dict]]).
- The SetTerm twins of all of the above (`set_*` family vs plain `set`) —
  `structural_eq`/`unify` already accept plain sets, so the same asymmetry is
  possible.

For each: decide accept-the-plain-type (what the profile API did — right when a
strict sibling already accepts it) vs keep-DictTerm-only (fine while every
spelling agrees and the failure is loud). The property to enforce is no silent
half-acceptance; a table of spelling × type → behaviour is probably the
fastest way to see the disagreements.
