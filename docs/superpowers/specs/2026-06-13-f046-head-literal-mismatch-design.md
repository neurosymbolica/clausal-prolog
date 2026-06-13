# F046 — Head-Pattern String-Literal Mismatch — Design Spec

**Date:** 2026-06-13
**Author:** Michael Amy (with Claude)
**Status:** Draft — pending user review before plan-writing
**Closes:** F046 (audit `2026-05-25-string-implementation`, class C4)
**Related:** F048 (compound heads — inherits this fix), F095 (first-arg indexing
canonicalisation — already landed, composes with this fix)

---

## Goal

Restore the strings-as-lists contract for **clause heads that pin a string
literal**. A rule

```
Quux("abc") <- (Helper(1))
```

must match a char-list caller `Quux(['a','b','c'])` with exactly one solution,
identically to how it already matches the str caller `Quux("abc")`. This is the
single largest-blast-radius finding from the string audit; it was deferred from
Phase 2 (user decision 2026-05-26) to its own spec because the fix touches the
compiler and may affect any existing user predicate with a literal-in-head rule
clause.

---

## Background

### The bug

A clause head argument that is a Python `str` compiles, at
`clausal/logic/compiler/head_match.py:253-254`, to:

```python
if isinstance(term, (int, float, str, bytes, complex)):
    return ast.MatchValue(value=ast.Constant(value=term))
```

So `Quux("abc")` becomes a `match` arm `case ("abc",):`. Python's `match`
compares `MatchValue` patterns with the builtin `==`. The incoming caller value
`['a','b','c']` is a plain Python `list`, and `"abc" == ['a','b','c']` is
`False`, so the arm is rejected and the clause silently fails to match — **zero
solutions instead of one.**

Crucially, **no clausal term participates in that comparison.** The head literal
is a bare Python `str`; the caller value is a bare Python `list`. The
strings-as-lists contract lives in the runtime `unify()` layer (and in
`SegString.__eq__` / `SegList.__eq__`), none of which is consulted by a raw
`MatchValue`. This is why the bug **cannot** be fixed by changing any term's
`__eq__`: the only repair is to stop using Python `==` for the comparison and
route it through `unify()` instead.

### Why the symmetric case already works

A list-literal head `Zorp(['a','b','c']) <- body` does **not** hit the
`MatchValue` branch. Lists route through the path at `head_match.py:258`, which
emits a **wildcard capture** (`case _lcap0:`) plus a runtime `unify`/list-guard
that wraps the case body. Because the pattern is a wildcard, every caller enters
the arm, and the `unify` guard then applies the strings-as-lists contract
correctly. List heads therefore match str callers. The fix makes str heads
behave the same way.

### Why facts dodge it

`_normalize_dataclass_fact` (`clausal/logic/database.py:332-361`), gated by
`body_goals == [True]` at `database.py:274`, rewrites ground literal head fields
into a fresh `Var` + `Unify(var, value)` body goal *before* the clause is
asserted. This sidesteps the `MatchValue` branch entirely (the head now holds
only a `Var`). The gate also catches `<- (True)` rule bodies. Only rules with a
**real** body goal survive with the literal embedded in the head — those are the
clauses that expose F046.

### What already landed

F095 (Phase 2 Task 8, commit `9494e22`) canonicalised **first-arg indexing** so
that a str-literal head and a char-list caller hash into the **same dispatch
bucket** (`arg_index.py:_charlist_to_str_or_none`). That fixed the dispatch-layer
half of the contract. F046 is the remaining **compile-layer** half: even when the
caller reaches the correct bucket, the per-clause `match` inside that bucket still
rejects it via `MatchValue`. The two fixes compose — `arg_index.py` emits bucket
*keys*, not match patterns, so there is exactly **one** `MatchValue` fix site.

### Prior context

Commit `aa2155d` ("Compiler: head patterns accept strings in clause matching")
widened the runtime destructuring path so list-literal heads match string
callers, fixing three sites. The fourth site — `MatchValue(Constant(<str>))` for
string-literal heads — was never addressed. That fourth site is F046.

---

## Approach: narrow fix (user decision 2026-06-13)

Three approaches were identified during the audit: (1) narrow — split `str` out
of the `MatchValue` tuple at the single compiler site; (2) broad — lift the
`_normalize_dataclass_fact` gate to run for all clauses; (3) combined. The
**narrow** approach is chosen because it has both the smallest correctness
surface and the smallest performance surface: it touches exactly the buggy type
(`str`) at exactly one site, and leaves the genuinely-fast numeric/atom literal
dispatch (`int`/`float`/`complex`) untouched. The broad approach would
deoptimize literal dispatch for types F046 does not even affect; combined is
largely redundant.

### Mechanism

The fix mirrors the existing list/dict/set guard machinery already in
`head_match.py`. Those guards emit a wildcard-capture pattern and record a guard
tuple that `compile_head_to_match_case` later assembles into an `if unify(...)`
wrapper around the case body. The str path plugs into the same two seams.

**Site 1 — `head_to_match_pattern` (`head_match.py:253`).** Split `str` out of
the scalar tuple. `int`/`float`/`bytes`/`complex` keep emitting `MatchValue`
(fast path, unchanged — see the bytes subsection for why bytes stays). For a
`str` literal:

- generate a capture name `_scap{n}` (parallel to the list path's `_lcap{n}`),
- record a guard tuple `("str", cap_name, literal)` in the `list_guards`
  accumulator,
- return a wildcard `ast.MatchAs(pattern=None, name=cap_name)`.

```python
# Python scalar literals (non-string): C-level == in the match arm. Fast path.
if isinstance(term, (int, float, bytes, complex)):
    return ast.MatchValue(value=ast.Constant(value=term))

# String literal: wildcard capture + runtime unify guard, mirroring the
# list-literal path below. Routes the comparison through unify() so the
# strings-as-lists contract (str <-> char-list) is honoured. (F046)
if isinstance(term, str):
    cap_name = f"_scap{len(list_guards) if list_guards is not None else 0}"
    if list_guards is not None:
        list_guards.append(("str", cap_name, term))
    return ast.MatchAs(pattern=None, name=cap_name)
```

**Site 2 — `compile_head_to_match_case` (`head_match.py`, the guard-assembly
block alongside the existing dict/set guard consumers, ~L997-1050).** Consume the
`("str", cap_name, literal)` tuples and wrap the case body with a
**performance-mitigated** guard:

```python
str_guards = [g for g in list_guards if g and g[0] == "str"]
for _tag, cap_name, literal in str_guards:
    # if _scap == "abc" or unify(_scap, "abc", trail): <inner>
    inner = [ast.If(
        test=ast.BoolOp(
            op=ast.Or(),
            values=[
                ast.Compare(
                    left=_name(cap_name),
                    ops=[ast.Eq()],
                    comparators=[ast.Constant(value=literal)],
                ),
                _call(_name("unify"), _name(cap_name),
                      ast.Constant(value=literal), _name(trail_name)),
            ],
        ),
        body=inner,
        orelse=[],
    )]
```

The `_scap == "abc"` disjunct short-circuits at C speed for the common
same-type case (a `str` caller against a `str` head); only `list` / `SegString`
callers fall through to `unify`. This recovers nearly all of the speed that the
bare `MatchValue` provided while restoring correctness.

### Performance

The current `MatchValue` is the fast path: a C-level `==` *inside* CPython's
`match` dispatch, which also lets the `match` statement use the literal to
*discriminate* (cheaply skip non-matching clauses). The fix replaces it with a
wildcard capture + `unify` guard, which (a) always enters the arm (loses
match-level discrimination) and (b) adds per-call function + trail overhead.

This cost is bounded and localized:

- **Only `str`-literal heads convert.** Numeric/atom dispatch tables are
  untouched.
- **The `== or unify` short-circuit** keeps same-type (`str`-caller) calls near
  native speed.
- **First-arg indexing (F095) already buckets** str-literal heads and their
  char-list callers together, so the per-clause `match` only ever sees relevant
  clauses — the lost discrimination does not degrade to an O(n) scan across an
  unrelated dispatch table.

**Verification requirement:** add a micro-benchmark under `benchmarks/`
following the existing benchmark conventions, exercising a str-literal dispatch
table called (i) with a str caller (same-type fast path) and (ii) with a
char-list caller (unify path), to confirm no regression on the same-type path
and acceptable cost on the cross-type path.

### bytes — out of scope (documented decision)

A `bytes` literal **can** appear in a clause head: `.clausal` source is parsed
as Python AST, so `Quux(b"abc") <- body` is syntactically valid and reaches the
same `head_match.py:253` tuple. Despite that, `bytes` is **deliberately left on
the `MatchValue` fast path** and is **not** converted by this fix, for three
reasons:

1. **No bytes-as-lists contract exists.** The runtime unify path pairs
   `(list, str)` only — there is no bytes branch in `list_unify`, no `SegBytes`
   analog to `SegString`, and `bytes.__eq__` against a list is just `False`. So
   `unify(b"abc", [...], trail)` returns `False` today under every rule.
2. **No F046-analogous bug exists for bytes.** Because no bytes↔list contract
   exists, a `bytes`-literal head and any list caller do not unify under *any*
   current rule. Converting bytes from `MatchValue` to wildcard+`unify` would
   change no observable behaviour — it would only add cost.
3. **The char-list form of bytes is genuinely ambiguous.** For `str` the
   contract is unambiguous (`"abc" ↔ ['a','b','c']`, since iterating a str
   yields 1-char strs). But iterating `bytes` yields **ints**
   (`list(b"abc") == [97, 98, 99]`, *not* `[b'a', b'b', b'c']`). Defining the
   canonical list form of bytes is a real design question, not a mechanical
   extension.

`bytes` in Clausal is a Python-interop type (sockets and HTTP hand it back —
e.g. `modules/py/tcp.py`, `modules/py/http.py`), not a first-class clausal
string. Making it behave like `str` is its own feature, separate from F046.

**Extension point (future work).** The narrow fix leaves a clean path to add
bytes later: once a bytes-as-lists runtime contract is designed (including a
decision on its canonical list element type), `bytes` simply moves from the
`MatchValue` tuple into the same `str` branch at site 1 — one line at the
compiler — plus whatever runtime unify contract is built. This spec records the
exclusion so the decision is explicit rather than silent.

### Compound heads (F048)

Compound heads containing a string literal (e.g. `Quux(foo("abc")) <- body`)
inherit this fix automatically: the parser/elaborator lifts the compound
argument into a body `Unify`, and when that resolves to a `str` it routes through
the same str branch. No separate work is required; a regression test covers it.

---

## Testing and lock-in

### Flip the existing adversarial test

`tests/audit_2026_05_25/test_class_C04_head_literal_mismatch.py::`
`test_F046_rule_str_head_matches_charlist_caller` is currently
`@pytest.mark.xfail(strict=True)`. Remove the xfail marker so it asserts
positively: all 8 cross-call combinations (fact/rule × str-head/list-head ×
str-caller/list-caller) return exactly 1 solution each. Under strict xfail this
test will already flip to a failure the moment the fix lands (alerting us); the
spec converts it to a permanent passing regression guard.

### New coverage

- **Multi-clause str-literal dispatch table reached by a char-list caller** —
  exercises the indexing layer (F095) and the converted head together; confirms
  the caller reaches the right bucket *and* matches inside it.
- **`SegString` caller against a str-literal head** — confirms the `unify` guard
  handles a partial-string runtime term, not just plain `str`/`list`.
- **Compound str-literal head (F048)** — `Quux(foo("abc")) <- body` matched by
  the char-list-bearing equivalent.
- **`bytes`-literal-head regression** — `Quux(b"abc")` still matches a `bytes`
  caller and remains on the `MatchValue` fast path (guards against an accidental
  conversion of bytes; documents the deliberate exclusion in executable form).
- **Same-type fast path** — `str`-head matched by a `str` caller still returns
  one solution (the `== ` short-circuit disjunct).

### Full-suite regression

Run the entire test suite. The blast radius is existing user predicates with
literal-in-head rule clauses; the suite is the safety net for behavioural drift.

### Benchmark

Add the str-literal dispatch micro-benchmark described under *Performance*.

---

## Ledger and doc updates

On landing:

- `findings.md` F046 entry — flip `**Status:**` from "deferred to follow-up
  spec" to "fixed in `<sha>`".
- `findings.md` F048 note — update to reflect the inherited fix.
- `findings.md` audit summary — update the deferred/closed counts and the
  XFAIL/deferred-findings tables (F046 moves from deferred to closed; F068
  remains the sole architectural deferral).
- `README.md` (audit dir) — update the "Findings deferred" line and the closing
  summary so F046 is no longer listed as scheduled follow-up work.

---

## Out of scope

- **bytes-as-lists contract** — documented above as future work with a defined
  extension point.
- **The broad elaborator-gate approach** — rejected in favour of the narrow fix.
- **F068** — unrelated architectural deferral; remains deferred.

---

## Success criteria

1. `test_F046_rule_str_head_matches_charlist_caller` passes (xfail removed); all
   8 cross-calls return 1 solution.
2. New tests (multi-clause indexing, `SegString` caller, compound head, bytes
   regression, same-type fast path) pass.
3. Full test suite passes with no regressions.
4. Benchmark confirms no regression on the same-type str-caller path.
5. Ledger and README updated; F046 closed.
