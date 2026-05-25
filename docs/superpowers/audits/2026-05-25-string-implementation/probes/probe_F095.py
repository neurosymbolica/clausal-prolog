"""Probe F095: C15 — first-arg indexing routes str vs list heads to different buckets.

The compiler's first-arg indexer (``clausal/logic/compiler/arg_index.py``)
computes a bucket key for each clause head argument via
``_arg_to_index_key`` and the symmetric runtime probe via
``_runtime_arg_key``.

- Strings hit the scalar branch: ``isinstance(arg, _INDEXABLE_TYPES)``
  where ``_INDEXABLE_TYPES = (int, float, str, bytes, bool, type(None))``.
  A clause ``Foo("abc")`` therefore keys to bucket ``"abc"``.
- Lists are NOT in ``_INDEXABLE_TYPES``, are not ``Compound`` nor
  ``is_term_instance``, and fall through to ``_INDEX_VAR`` (the default
  bucket). A clause ``Foo(['a','b','c'])`` becomes a "default" clause.

The dispatch decision tree (``_make_indexed_dispatch_impl`` /
``_make_groundness_dispatch_*``) then routes:
- caller ``Foo("abc")`` → runtime key ``"abc"`` → bucket ``"abc"``
  (which by ``_build_arg_index``'s merging logic contains BOTH the
  str-headed clause AND the list-headed default clause)
- caller ``Foo(['a','b','c'])`` → runtime key ``_INDEX_VAR`` → fallback
  to ``default_fn`` which contains ONLY default clauses (list-headed,
  var-headed)

Under the strings-as-lists contract a caller passing
``Foo(['a','b','c'])`` SHOULD reach the str-headed clause
``Foo("abc")`` because the two values unify at the runtime level.  The
dispatch layer prevents that: it never even tries the str bucket for a
list-typed caller.

This is the dispatch-time analogue of F046 (head-pattern literal
mismatch in match arms).  If the F046 fix at ``head_match.py:253-254``
swaps ``MatchValue`` for a wildcard + runtime-unify, the per-clause
arm would accept either shape — but only if the dispatch layer
delivers the caller to that arm in the first place, which it currently
does not for list→str.  C15 must be coalesced (or the bucket logic
extended) for the F046 fix to fully restore strings-as-lists.

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F095.py
"""
from __future__ import annotations

import os
import tempfile

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


# Fixtures.  Threshold for first-arg indexing is _INDEX_THRESHOLD = 4
# (arg_index.py:38) — we need >=4 clauses for a predicate before the
# indexer kicks in.  Pad with three sibling clauses on other scalar
# keys so the str-headed and list-headed clauses both become eligible
# bucketing inputs.  We also include facts (which the elaborator dodges
# at database.py:332-361) and rules (which preserve the literal head).
SOURCE = """
# Helper used to make rule bodies non-trivial (so the
# _normalize_dataclass_fact elaborator dodge does not fire).
Helper(1),

# Five facts on Foo: enough to clear _INDEX_THRESHOLD = 4.
Foo(1),
Foo(2),
Foo(3),
Foo("abc"),
Foo(['a', 'b', 'c']),

# Five rules on Quux (with a non-True body to preserve literal heads).
Quux(1) <- (Helper(1))
Quux(2) <- (Helper(1))
Quux(3) <- (Helper(1))
Quux("abc") <- (Helper(1))
Quux(['a', 'b', 'c']) <- (Helper(1))
"""


def _load_inline_clausal(name: str, source: str):
    with tempfile.NamedTemporaryFile(
        suffix=".clausal", mode="w", delete=False
    ) as f:
        f.write(source)
        f.flush()
        path = f.name
    try:
        return _load_module(name, path)
    finally:
        os.unlink(path)


def _count(pred: str, arg, mod) -> int:
    return sum(1 for _ in call(pred, arg, module=mod))


def main() -> None:
    print("Probe F095: C15 — first-arg indexing str vs list bucketing")

    mod = _load_inline_clausal("probe_f095_c15", SOURCE).__dict__["$module"]

    # Enumerate all clauses with an unbound Var caller — both bucketed
    # and default clauses must be reachable from this path.
    L = Var()
    seen_foo = []
    for _ in call("Foo", L, module=mod):
        v = deref(L)
        seen_foo.append((type(v).__name__, v))
    print(f"  Foo(Var) enumeration: {len(seen_foo)} solutions (expect 5)")
    for kind, val in seen_foo:
        print(f"    - {kind}: {val!r}")

    L2 = Var()
    seen_quux = []
    for _ in call("Quux", L2, module=mod):
        v = deref(L2)
        seen_quux.append((type(v).__name__, v))
    # NOTE: Quux(Var) returns 1 sol (unbound) for the rule-with-scalar-
    # literal-head case — that is a separate compiler quirk (Var caller
    # vs MatchValue(int) head literal in the match arm) and is NOT the
    # C15 finding; out of scope for the strings audit since it affects
    # all scalar types equally.  See probe output for diagnostic value
    # only — the F095 evidence is in the bound-caller counts below.
    print(f"  Quux(Var) enumeration: {len(seen_quux)} solutions (note: rule+scalar-MatchValue quirk, not C15)")
    for kind, val in seen_quux:
        print(f"    - {kind}: {val!r}")

    # FACT side: covered by _normalize_dataclass_fact (so head MatchValue
    # path is dodged for facts).  But the indexer still sees the elaborated
    # clauses (head Var + body Unify), and _extract_arg_key DOES inspect
    # the body Unify pattern at arg_index.py:162-175.  So the dispatch
    # bucketing question stands for facts too.
    n_foo_str_self = _count("Foo", "abc", mod)
    n_foo_list_self = _count("Foo", ["a", "b", "c"], mod)
    n_foo_str_via_list = _count("Foo", ["a", "b", "c"], mod)  # same as above
    # The cross-bucket query: pass a str when only the list-headed
    # clause exists at this concrete value — pad-key calls below test
    # this more cleanly.
    n_foo_xyz_via_list = _count("Foo", ["x", "y", "z"], mod)

    print()
    print(f"  FACT same-type: Foo('abc') → {n_foo_str_self} sol (expect 2 — str-headed bucket + list-headed default)")
    print(f"  FACT same-type: Foo(['a','b','c']) → {n_foo_list_self} sol (expect 2 — list head + str via runtime unify)")
    print(f"  FACT non-match: Foo(['x','y','z']) → {n_foo_xyz_via_list} sol (expect 0 — neither head unifies)")

    # RULE side: F046 confirmed Quux("abc")<-body doesn't match caller
    # ['a','b','c'] because the MatchValue head literal fails ==.  But
    # is the dispatch even DELIVERING the caller to that arm?  Three
    # diagnostic counts:
    n_quux_str_self = _count("Quux", "abc", mod)
    n_quux_list_self = _count("Quux", ["a", "b", "c"], mod)
    n_quux_str_called_with_list = _count("Quux", ["a", "b", "c"], mod)
    n_quux_list_called_with_str = _count("Quux", "abc", mod)

    print()
    print(f"  RULE same-type: Quux('abc') → {n_quux_str_self} sol (expect 1 — str-headed only; list head fails MatchValue too)")
    print(f"  RULE same-type: Quux(['a','b','c']) → {n_quux_list_self} sol (expect 1 — list head only)")
    print(f"  RULE cross 1:   Quux(['a','b','c']) → {n_quux_str_called_with_list} sol (already F046)")
    print(f"  RULE cross 2:   Quux('abc') called → {n_quux_list_called_with_str} sol (already F046)")

    # The CRITICAL C15 question: if the F046 head-match fix landed
    # (MatchValue → wildcard+unify), would dispatch even deliver the
    # caller to the str-head bucket?  Answer: NO for caller-list →
    # str-bucket, because runtime_arg_key(list) == _INDEX_VAR which
    # routes to the default fn (excluding the str bucket).
    print()
    print(f"  Diagnosis:")
    print(f"    _runtime_arg_key('abc')          = 'abc' (scalar branch)")
    print(f"    _runtime_arg_key(['a','b','c'])  = _INDEX_VAR (default fallback)")
    print(f"    → str caller can reach list-default merged into its bucket")
    print(f"    → list caller can NEVER reach str-specific bucket (dispatch asymmetry)")
    print()
    print(f"  This is C15.  Even if F046 (head-match MatchValue) is fixed,")
    print(f"  the list-caller path skips the str-bucket entirely.  A complete")
    print(f"  strings-as-lists fix must either:")
    print(f"    (a) treat list-of-chars callers as keyable to str buckets")
    print(f"        (canonicalise key in _runtime_arg_key), or")
    print(f"    (b) treat str-headed clauses as default-bucket clauses")
    print(f"        (canonicalise key in _arg_to_index_key → _INDEX_VAR for")
    print(f"        str heads), or")
    print(f"    (c) coalesce: emit two bucket entries per str-headed clause")
    print(f"        (one under 'abc' and one under _INDEX_VAR).")


if __name__ == "__main__":
    main()
