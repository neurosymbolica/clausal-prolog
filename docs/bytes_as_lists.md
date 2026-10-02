# Bytes as Lists of Codes

In Clausal, a Python `bytes` value behaves as a **list of byte codes** — integers
in the range `[0, 255]` — at the logic level. This is the classical Prolog
*codes* representation, and it makes byte sequences participate in unification,
term inspection, and DCGs the way character strings do under
[strings as lists](strings_as_lists.md).

```seam
--8<-- "tests/fixtures/docs/bytes_as_lists_examples.seam:unification"
```

The motivating use case is **DCGs over binary protocols**: parsing and building
byte streams with `phrase//`.

---

## The codes model: a byte is an int

A string and a `bytes` look alike but are different kinds, and Clausal keeps
them distinct:

| | string (chars model) | `bytes` (codes model) |
|---|---|---|
| literal | `"abc"` (the default reading of `"…"`) | `b"abc"` |
| decomposes to | `['a', 'b', 'c']` (char atoms — an atom is a 1-char Python `str`) | `[97, 98, 99]` (`int`s) |
| element fixed point? | **no** — the element of `"a"` is the char atom `'a'`, and `"a"` itself is the list `['a']` | **no** — `b"a"[0] == 97` |
| partial-term type | `SegString` | `SegBytes` |

A string is a list of *characters*; a `bytes` is a list of *integer codes*. This
mirrors Python itself: iterating a `str` yields 1-character strings, but
iterating `bytes` yields ints (`list(b"abc") == [97, 98, 99]`).

A byte therefore has **no fixed point** — it decomposes to an `int`, never to a
one-byte `bytes`:

```seam
--8<-- "tests/fixtures/docs/bytes_as_lists_examples.seam:no_fixed_point"
```

The empty `bytes` unifies with the empty list:

```seam
--8<-- "tests/fixtures/docs/bytes_as_lists_examples.seam:empty_bytes"
```

### It is unification-equivalence, not conversion

A `bytes` value stays a `bytes` object — it keeps `.decode()`, `.hex()`,
`b"a"[0] == 97`, every Python method. It merely *unifies with* its int-code
list at the unification layer; nothing is converted. The int list is a
**logical view**, exactly as the character list is for a string. A `bytes`
threaded through unification and recursion stays `bytes`, so you can still call
`.decode()` / `.hex()` on a bound result.

---

## Comparison with Prolog

Prolog has always had two string representations: **`chars`** (a list of
one-character atoms) and **`codes`** (a list of integer character codes).
Clausal's [strings as lists](strings_as_lists.md) is the `chars` model;
**bytes-as-lists is the `codes` model.**

The `codes` representation is what the Triska / DCG tradition uses for byte and
binary work — ISO's `get_byte/2`, code-list `phrase/2`, and so on. Integer
terminals are exactly what binary-protocol grammars want.

| Feature | Prolog `codes` | Clausal `bytes` |
|---------|----------------|-----------------|
| Representation | List of integer codes | Python `bytes` |
| Element type | `int` code | `int` in `[0, 255]` |
| DCGs over byte streams | Works (code lists) | Works (`bytes` subject, code terminals) |
| Underlying storage | Cons cells | Compact `bytes` object |
| Python interop | Requires conversion | Native `bytes` (a goal-position seam hands back the `bytes` itself) |

As with strings, Clausal takes the pragmatic middle path: a `bytes` *behaves
as* a list of codes at the logic level but remains a compact, interoperable
Python `bytes` object underneath.

---

## Term Inspection

The ISO inspection predicates follow the codes-model cons cell — an **int**
head and a **`bytes`** tail (symmetric with the char cons cell for a string):

```seam
--8<-- "tests/fixtures/docs/bytes_as_lists_examples.seam:inspection"
```

So `b"abc"` has functor `'.'`, arity `2`, first argument `97` (an int), and
second argument `b"bc"` (the tail, still `bytes`).

---

## List Predicates

The [list predicates](lists.md) accept a `bytes` value as a sequence of codes.
Element results are int codes; sequence results reconstruct as `bytes`
(input-type-wins):

```seam
--8<-- "tests/fixtures/docs/bytes_as_lists_examples.seam:list_predicates"
```

---

## Type Checks

```seam
--8<-- "tests/fixtures/docs/bytes_as_lists_examples.seam:type_checks"
```

`is_list/1` accepts a `bytes` (it is list-shaped). `is_codes/1` is the codes
analog of `is_chars/1`: it succeeds for a `bytes` or a list of ints in
`[0, 255]`. `is_str/1` and `is_chars/1` stay `false` for a `bytes` — a `bytes`
is not a string, and a code sequence is not a character sequence.

---

## Pattern Matching

A clause-head or body list pattern destructures a `bytes` argument: the head
binds to an **int** code and the tail stays **`bytes`**.

```seam
head_tail([H, *T], H, T),

test("head tail") <- (head_tail(b"abc", H, T), H is 97, T is b"bc")
```

The same works as a body goal: `b"abc" is [First, *Rest]` binds `First = 97`
and `Rest = b"bc"`. Star variables bind to **`bytes`** substrings, preserving
the type — exactly as they bind to string substrings under
[strings as lists](strings_as_lists.md). Multi-star patterns
(`[*A, *B]`, `[*_, X, *_]`) match `bytes` too, and enumerate splits on
backtracking just as they do for lists and strings.

The flip side is that `[*XS]` is **not** a list test — a `bytes` (or a
string) matches it too, and a recursive list-walker destructures a `bytes`
byte by byte instead of passing it through as a leaf. See the note under
[Pattern Matching in strings-as-lists](strings_as_lists.md#pattern-matching)
for the explicit `++isinstance(X, list)` gate.

---

## DCGs over Binary Protocols

This is the headline use case. A [DCG](dcg.md) parses a `bytes` subject with
`phrase//2,3`; terminals are written as **integer code lists**, and the `bytes`
remainder is preserved as `bytes`.

```seam
g >> ([71, 69, 84, 32])          # [71,69,84,32] is the code list for b"GET "

test("GET prefix") <- (phrase(g, b"GET /x", REST), REST is b"/x")
test("GET whole") <- phrase(g, b"GET ")
```

You can also wrap a `bytes` literal in the `sequence//1` non-terminal to match
it as a unit:

```seam
header >> (sequence(b"GET "))

test("sequence of bytes") <- (phrase(header, b"GET /index", REST), REST is b"/index")
```

Under `phrase/3`, when the subject is a `bytes`, the residue is bound to a
`bytes` slice — the input type is preserved end to end.

---

## Promiscuity: in-range int lists unify with bytes

Because byte codes are ordinary integers, **any** list of ints in `[0, 255]`
unifies with the matching `bytes`:

```seam
--8<-- "tests/fixtures/docs/bytes_as_lists_examples.seam:promiscuity"
```

This is intentional and symmetric with strings-as-lists (where any list of
one-character **atoms** unifies with the matching string). The contract only fires when a
`bytes` object is actually present on one side of the unification — two plain
int lists unify as int lists, and **nothing ever spuriously becomes `bytes`.**

---

## Out of Scope

```seam
--8<-- "tests/fixtures/docs/bytes_as_lists_examples.seam:out_of_scope"
```

- **No string ↔ `bytes` cross-unification.** `"abc"` does not unify with
  `b"abc"`, and `['a', 'b', 'c']` does not unify with `b"abc"`. They are
  distinct domains; cross between them explicitly with `.encode()` / `.decode()`.
- **Out-of-range / non-int elements fail, they do not raise.** `b"a"` simply
  does not unify with `[256]` — there is no byte equal to 256.
- **`bytearray` is not in scope.** Only immutable `bytes` is a logic term;
  mutable `bytearray` is not addressed.

---

## Current scope and limitations

The codes contract is wired through the same layers as strings-as-lists:

- **Unification** — `bytes` ↔ int-code list, both directions, element binding,
  length-mismatch failure, with the `bytes` type preserved.
- **Pattern matching** — single- and multi-star clause-head and body patterns
  (`[H, *T]`, `[*A, *B]`, `[*_, X, *_]`) bind int elements and `bytes`
  sub-slices (`b"abc" is [F, *R]` → `F = 97`, `R = b"bc"`), enumerating splits
  on backtracking.
- **List-library predicates** — `append/3`, `in_/2`, `length/2`, `reverse/2`,
  `take/3`, `drop/3`, `split_at/4`, `list_item/3`, `last/2`, etc. accept a
  `bytes` value as a code sequence; element results are int codes and sequence
  results reconstruct as `bytes` (input-type-wins).
- **Term inspection** — `functor/3`, `arg/3`, `unpack/2` (`=..`).
- **`SegBytes`** — the partial-byte-string term (the codes analog of
  `SegString`): concrete `bytes` segments alternating with variable-length
  holes that bind to `bytes` substrings. See `clausal.terms.SegBytes`.
- **DCGs / `phrase//`** — `bytes` subjects with integer-code terminals and
  `sequence//1`, with the remainder preserved as `bytes`.
- **Type checks** — `is_list/1` accepts a `bytes` (it is list-shaped), and
  `is_codes/1` is the codes analog of `is_chars/1` (succeeds for a `bytes` or a
  list of ints in `[0, 255]`). `is_str/1` and `is_chars/1` stay `false` for a
  `bytes` — a `bytes` is not a string, and is a *code* sequence, not a *char*
  sequence.
- **Clause dispatch & first-argument indexing** — a `bytes`-literal clause head
  matches an int-list caller and buckets with it.

Out-of-scope remains: no string/`bytes` cross-unification, and no `bytearray`
support (only immutable `bytes`).

---

## See also

- [Strings as Lists of Characters](strings_as_lists.md) — the `chars`-model
  sibling of this feature.
- [DCGs](dcg.md) — definite clause grammars.
- [Term Inspection](term_inspection.md) — `functor/3`, `arg/3`, `unpack/2`.
