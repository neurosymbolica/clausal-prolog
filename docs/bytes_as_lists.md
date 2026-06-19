# Bytes as Lists of Codes

in_ Clausal, a Python `bytes` value behaves as a **list of byte codes** — integers
in the range `[0, 255]` — at the logic level. This is the classical Prolog
*codes* representation, and it makes byte sequences participate in unification,
term inspection, and DCGs the way character strings do under
[strings as lists](strings_as_lists.md).

```clausal
--8<-- "tests/fixtures/docs/bytes_as_lists_examples.clausal:unification"
```

The motivating use case is **DCGs over binary protocols**: parsing and building
byte streams with `phrase//`.

---

## The codes model: a byte is an int

`str` and `bytes` look alike but are different domains, and Clausal keeps them
distinct:

| | `str` (chars model) | `bytes` (codes model) |
|---|---|---|
| literal | `"abc"` | `b"abc"` |
| decomposes to | `['a', 'b', 'c']` (1-char `str`s) | `[97, 98, 99]` (`int`s) |
| element fixed point? | yes — `"a"[0] is "a"` | **no** — `b"a"[0] == 97` |
| partial-term type | `SegString` | `SegBytes` |

A `str` is a list of *characters*; a `bytes` is a list of *integer codes*. This
mirrors Python itself: iterating a `str` yields 1-character strings, but
iterating `bytes` yields ints (`list(b"abc") == [97, 98, 99]`).

A byte therefore has **no fixed point** — it decomposes to an `int`, never to a
one-byte `bytes`:

```clausal
--8<-- "tests/fixtures/docs/bytes_as_lists_examples.clausal:no_fixed_point"
```

The empty `bytes` unifies with the empty list:

```clausal
--8<-- "tests/fixtures/docs/bytes_as_lists_examples.clausal:empty_bytes"
```

### It is unification-equivalence, not conversion

A `bytes` value stays a `bytes` object — it keeps `.decode()`, `.hex()`,
`b"a"[0] == 97`, every Python method. It merely *unifies with* its int-code
list at the unification layer; nothing is converted. The int list is a
**logical view**, exactly as the character list is for a `str`. A `bytes`
threaded through unification and recursion stays `bytes`, so you can still call
`.decode()` / `.hex()` on a bound result.

---

## Comparison with Prolog

Prolog has always had two string representations: **`chars`** (a list of
one-character atoms) and **`codes`** (a list of integer character codes).
Clausal's [strings as lists](strings_as_lists.md) is the `chars` model;
**bytes-as-lists is the `codes` model.**

The `codes` representation is what the Triska / DCG tradition uses for byte and
binary work — SWI's `get_byte/2`, code-list `phrase/2`, and so on. Integer
terminals are exactly what binary-protocol grammars want.

| Feature | Prolog `codes` | Clausal `bytes` |
|---------|----------------|-----------------|
| Representation | List of integer codes | Python `bytes` |
| Element type | `int` code | `int` in `[0, 255]` |
| DCGs over byte streams | Works (code lists) | Works (`bytes` subject, code terminals) |
| Underlying storage | Cons cells | Compact `bytes` object |
| Python interop | Requires conversion | Native `bytes` |

As with strings, Clausal takes the pragmatic middle path: a `bytes` *behaves
as* a list of codes at the logic level but remains a compact, interoperable
Python `bytes` object underneath.

---

## Term Inspection

The ISO inspection predicates follow the codes-model cons cell — an **int**
head and a **`bytes`** tail (symmetric with the char cons cell for `str`):

```clausal
--8<-- "tests/fixtures/docs/bytes_as_lists_examples.clausal:inspection"
```

So `b"abc"` has functor `'.'`, arity `2`, first argument `97` (an int), and
second argument `b"bc"` (the tail, still `bytes`).

---

## Pattern Matching

A clause-head or body list pattern destructures a `bytes` argument: the head
binds to an **int** code and the tail stays **`bytes`**.

```clausal
# skip  (illustrative — exercised by tests/test_bytes_patterns.py)
head_tail([H, *T], H, T),

# head_tail(b"abc", H, T)  binds  H = 97 (int),  T = b"bc" (bytes)
```

The same works as a body goal: `b"abc" is [First, *Rest]` binds `First = 97`
and `Rest = b"bc"`. Star variables bind to **`bytes`** substrings, preserving
the type — exactly as they bind to `str` substrings under
[strings as lists](strings_as_lists.md).

!!! note "Single-star vs multi-star"
    Single-star patterns (`[H, *T]`, `[*T]`) match `bytes` today. Patterns with
    **two or more** star variables (`[*A, *B]`, `[*_, X, *_]`) do **not** yet
    match a `bytes` argument — see [Current scope and limitations](#current-scope-and-limitations).

---

## DCGs over Binary Protocols

This is the headline use case. A [DCG](dcg.md) parses a `bytes` subject with
`phrase//2,3`; terminals are written as **integer code lists**, and the `bytes`
remainder is preserved as `bytes`.

```clausal
# skip  (illustrative — exercised by tests/test_bytes_dcg.py and
#         tests/test_bytes_patterns.py)
g >> ([71, 69, 84, 32])          # [71,69,84,32] is the code list for b"GET "

# phrase(g, b"GET /x", Rest)  succeeds with  Rest = b"/x"  (bytes)
# phrase(g, b"GET ")          succeeds (full consumption)
```

You can also wrap a `bytes` literal in the `sequence//1` non-terminal to match
it as a unit:

```clausal
# skip  (illustrative — exercised by tests/test_bytes_dcg.py)
header >> (sequence(b"GET "))

# phrase(header, b"GET /index", Rest)  succeeds with  Rest = b"/index"
```

Under `phrase/3`, when the subject is a `bytes`, the residue is bound to a
`bytes` slice — the input type is preserved end to end. (These grammar examples
are marked `# skip` only because the documentation test harness compiles each
block in isolation; the behaviour itself is covered by the test suite.)

---

## Promiscuity: in-range int lists unify with bytes

Because byte codes are ordinary integers, **any** list of ints in `[0, 255]`
unifies with the matching `bytes`:

```clausal
--8<-- "tests/fixtures/docs/bytes_as_lists_examples.clausal:promiscuity"
```

This is intentional and symmetric with strings-as-lists (where any list of
1-char strings unifies with the matching `str`). The contract only fires when a
`bytes` object is actually present on one side of the unification — two plain
int lists unify as int lists, and **nothing ever spuriously becomes `bytes`.**

---

## Out of Scope

```clausal
--8<-- "tests/fixtures/docs/bytes_as_lists_examples.clausal:out_of_scope"
```

- **No `str` ↔ `bytes` cross-unification.** `"abc"` does not unify with
  `b"abc"`, and `['a', 'b', 'c']` does not unify with `b"abc"`. They are
  distinct domains; cross between them explicitly with `.encode()` / `.decode()`.
- **Out-of-range / non-int elements fail, they do not raise.** `b"a"` simply
  does not unify with `[256]` — there is no byte equal to 256.
- **`bytearray` is not in scope.** Only immutable `bytes` is a logic term;
  mutable `bytearray` is not addressed.

---

## Current scope and limitations

bytes-as-lists is wired through the layers that the binary-protocol use case
needs, but it is **narrower than strings-as-lists**. Today the codes contract
covers:

- **Unification** — `bytes` ↔ int-code list, both directions, element binding,
  length-mismatch failure, with the `bytes` type preserved.
- **Single-star pattern matching** — clause-head and body patterns `[H, *T]`
  bind an int head and a `bytes` tail (`b"abc" is [F, *R]` → `F = 97`,
  `R = b"bc"`).
- **Term inspection** — `functor/3`, `arg/3`, `unpack/2` (`=..`).
- **`SegBytes`** — the partial-byte-string term (the codes analog of
  `SegString`): concrete `bytes` segments alternating with variable-length
  holes that bind to `bytes` substrings. See `clausal.terms.SegBytes`.
- **DCGs / `phrase//`** — `bytes` subjects with integer-code terminals and
  `sequence//1`, with the remainder preserved as `bytes`.
- **Clause dispatch & first-argument indexing** — a `bytes`-literal clause head
  matches an int-list caller and buckets with it.

Not yet bytes-aware (these accept `str`/`list` but not `bytes`):

- **Multi-star head patterns** — `[*A, *B]`, `[*_, X, *_]` (two or more star
  variables) do not yet match a `bytes` argument. Single-star patterns do.
- The high-level **list-library predicates** — `append/3`, `in_/2`, `reverse/2`,
  `take/3`, `drop/3`, `list_item/3`, and `length/2` in compute mode. Use an
  explicit code list, or `phrase//` for sequence work, until these are extended.
- The **type-check predicates** `is_list/1` and `is_chars/1` report `false` for
  a `bytes` value (and `is_str/1` correctly reports `false` — a `bytes` is not a
  `str`).

These gaps correspond to the audit classes the strings-as-lists work covered for
`str` (the polymorphic-builtin and type-check classes) but which have no `bytes`
analog yet. Prefer **explicit code lists**, **single-star patterns**, or
**`phrase//`** for byte-sequence work that the list predicates would otherwise
handle.

---

## See also

- [Strings as Lists of Characters](strings_as_lists.md) — the `chars`-model
  sibling of this feature.
- [DCGs](dcg.md) — definite clause grammars.
- [Term Inspection](term_inspection.md) — `functor/3`, `arg/3`, `unpack/2`.
