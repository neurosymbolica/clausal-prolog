# Strings as Lists of Characters

In Clausal Prolog a string **is** the list of its one-character atoms — the ISO
Prolog *chars* model, as in Scryer. You can use list predicates, pattern
matching, and DCGs on strings directly; no conversion needed, because there is
nothing to convert.

!!! note "Writing a string literal"
    A double-quoted literal `"hello"` is a **string** — the engine default
    since 2026-09-26, as in Scryer and Trealla. A single-quoted `'hello'` is
    always an atom. A module that still needs the old reading can declare
    [`-double_quotes(atom)`](directives.md#-double_quotes), a temporary
    per-module setting; `chars` (the default) and `atom` are the only modes.
    Code lists have no mode: they are written `b"..."` (see
    [Bytes as Lists of Codes](bytes_as_lists.md)).

---

## Why?

In logic programming, sequences are the universal data structure. Lists hold
elements; strings hold characters. The operations you want on both are the same:
split, join, reverse, search, filter, iterate. Maintaining two parallel sets of
predicates — one for lists, one for strings — doubles the API surface and forces
users to constantly ask "am I working with a string or a list right now?"

Clausal Prolog answers that by making the string *be* the list. Under the hood a
string stays a compact value carrying its text (fast, and never expanded
into a chain of cons cells) — a bare Python `str` is an atom now, not a
string, so this isn't literally a `str`; see [Atoms vs
strings](syntax.md#atoms-vs-strings) — but at the logic level `"hello"` and
`['h', 'e', 'l', 'l', 'o']` are one and the same term.

The elements are **character atoms**: `'h'` is the atom whose spelling is the
single character `h`, not the one-character string `"h"`. So
`list_item(0, "abc", C)` gives `C = 'a'`, and `in_("a", "abc")` fails — `"a"` is the
*list* `['a']`, not the character.

---

## Unification

A string unifies with the list of its character atoms:

```seam
--8<-- "tests/fixtures/docs/strings_as_lists_examples.seam:unification"
```

String-to-string unification is unchanged — `"abc" = "abc"` succeeds by
equality (no element-wise comparison needed).

The empty string unifies with the empty list:

```seam
--8<-- "tests/fixtures/docs/strings_as_lists_examples.seam:empty_string"
```

---

## Pattern Matching

Multi-star list patterns work on strings. Star variables bind to
**substrings** (not character lists, and not atoms — a substring stays a
string):

```seam
--8<-- "tests/fixtures/docs/strings_as_lists_examples.seam:pattern_matching"
```

This is the same pattern syntax used for lists — no special string patterns
needed. when matching a string, `*Prefix` binds to a substring; when matching
a list, it binds to a sublist.

**`[*XS]` is not a list test.** Because a string unifies with list patterns,
`listish([*XS])` succeeds for `listish("met")` too — binding `XS` to the whole
string — and `[H, *T]` destructures a string one character at a time. A
recursive list-walking predicate written the obvious way therefore walks
*into* every string in its input instead of treating it as a leaf. When a
predicate must recurse over lists but pass strings through whole, gate the
destructuring clause explicitly: `ISLIST is ++isinstance(X, list),
ISLIST is True` before matching `[H, *T]`. (Found the expensive way by the
rewriter's rule walker — see `clausal/rewrite/rules/head_fold.seam` for
the in-tree example of the gate.)

---

## List Predicates on Strings

All [list predicates](lists.md) accept strings. when every input is a string and the result
is a character sequence, the result is returned as a string:

### append

```seam
--8<-- "tests/fixtures/docs/strings_as_lists_examples.seam:append_examples"
```

### length

```seam
--8<-- "tests/fixtures/docs/strings_as_lists_examples.seam:length_example"
```

### in_ (Member)

```seam
--8<-- "tests/fixtures/docs/strings_as_lists_examples.seam:member_examples"
```

### reverse

```seam
--8<-- "tests/fixtures/docs/strings_as_lists_examples.seam:reverse_example"
```

### take, drop, split_at

```seam
--8<-- "tests/fixtures/docs/strings_as_lists_examples.seam:take_drop_split"
```

### list_item

```seam
--8<-- "tests/fixtures/docs/strings_as_lists_examples.seam:list_item_example"
```

---

## DCGs on Strings

[Definite Clause Grammars](dcg.md) parse strings directly:

```seam
# `'digit'` is single-quoted: char_type/2's Type argument is an ATOM, and a
# bare `digit` here would name the nonterminal defined on the next line.
digit >> ([D], {char_type(D, 'digit')})
digits >> (digit)
digits >> (digit, digits)

test("parse digits") <- phrase(digits, "123")
test("partial parse") <- (
    phrase(digits, "12ab", REST),
    REST is ['a', 'b'],   # the leftover is the string "ab"
    string(REST)
)
```

No `atom_chars` conversion is needed. Pass a string to `phrase/2` or `phrase/3`
and the DCG consumes its characters as list elements.

### Character-Level Grammars

Because strings are character lists, you can write character-level grammars
naturally:

```seam
letter >> ([C], {char_type(C, 'alpha')})
space >> ([' '])
word >> (letter)
word >> (letter, word)
words >> (word)
words >> (word, space, words)

test("parse words") <- phrase(words, "hello world")
```

---

## Type Checking

Three predicates test sequence types (see [Type Checking](type_checking.md) for the full set):

| Predicate | `"ab"` | `['a','b']` | `[1, 2]` | atoms | Purpose |
|-----------|--------|-------------|----------|-------|---------|
| `is_list/1` | Succeeds | Succeeds | Succeeds | Fails | Polymorphic: is this a list-shaped value (a `list` or a string)? |
| `is_str/1`, `string/1` | Succeeds | Succeeds | Fails | Fails | Is this a **string** — a sequence of characters? |
| `is_chars/1` | Succeeds | Succeeds | Succeeds | Fails | union test: is this a character sequence or a list? |

`is_list/1` is polymorphic over `list` and string (audit 2026-05-25, F080)
so it agrees with every list-flavoured builtin — `append`, `length`,
`reverse`, `member`, `maplist`, `take`, `drop`, etc. — all of which
accept a string as a character sequence. Use `is_str/1` when you need to know
that a value is *text* rather than an arbitrary list. A bare atom (a plain
`str`) satisfies neither — see [Atoms vs strings](syntax.md#atoms-vs-strings).

`is_str/1` tests the **term**, not its storage: `"ab"` and `['a', 'b']` are one
term, so both answer true, and so do `""` and `[]`.

None of the three accepts an **atom**: an atom is a symbol, not a sequence.
`atom("hello")` and `string(hello)` are both false, and the two never unify.
The atom-flavoured predicates in the next section are the bridge between them.

```seam
--8<-- "tests/fixtures/docs/strings_as_lists_examples.seam:type_checking"
```

---

## The `atom_*` family works on ATOMS

The ISO `atom_*` predicates (`atom_chars/2`, `atom_codes/2`, `atom_concat/3`,
`sub_atom/5`, `atom_length/2`, `upcase_atom/2`, `downcase_atom/2`) take an
**atom** in the atom position and give atoms back. Handing one a string raises
`type_error(atom, …)` — it is not a silent failure:

```seam
--8<-- "tests/fixtures/docs/strings_as_lists_examples.seam:atom_family"
```

That makes `atom_chars/2` the **bridge between the two kinds**: it turns an
atom into the string (equivalently, the char list) of its spelling, and turns
text back into an atom.

- **Atom ↔ text:** `atom_chars(hello, S)` gives the char list
  `['h','e','l','l','o']`, which unifies with `"hello"` because they are the
  same term; `atom_chars(A, "hello")` gives `A = hello`.
- **Code-point operations:** `atom_codes/2` and `char_code/2` relate characters
  to integer code points.
- **Character classification:** `char_type/2` tests a **char atom** —
  `char_type('a', alpha)`.
- **Case conversion:** `upcase_atom/2`, `downcase_atom/2` — atom in, atom out.

For concatenation, splitting, length, and membership **of strings**, use the
[list predicates](lists.md) (`append/3`, `length/2`, `in_/2`, `reverse/2`,
`list_item/3`) — they work uniformly on strings and lists, because a string is a
list.

---

## How It Works

A bound string is internally a compact value that wraps its Python `str`
text — not a bare `str` itself, since a bare `str` is now an atom (see
[Atoms vs strings](syntax.md#atoms-vs-strings)). This preserves performance
(comparison and concatenation on the wrapped text are fast). What Python
sees depends on the crossing: a goal-position seam (`for S in --p(S):`)
hands back the engine's own term, the carrier `('$chars', 'hello')`, and
`clausal.to_python(S)` gives the `str` `'hello'` (a char list built as a plain
list, e.g. by `atom_chars/2`, gives `['h', 'e', …]` unless you ask for
`to_python_text(S)`); an argument passed to a
Python callee from a clause body (`Y is ++f(S)`) arrives as a plain `str`.
See [Python integration](python_integration.md).
**The representation is never materialised into cons cells** — a proper
list is a `list`, and a partial list or partial string is the engine's
`SegList`/`SegString`. The `'.'/2` cons structure is only ever a *view* onto
those, produced on demand by `functor/3`, `arg/3`, `=..` and
`write_canonical/1`.

The logic layer makes the string *be* its char list in four places:

1. **Unification:** when a string meets a list, they unify element-wise against
   the string's character atoms. `"abc"` unifies with `['a', 'b', 'c']`.
   String-vs-string remains fast equality.

2. **Pattern matching:** Multi-star patterns (`[*A, 'l', *B]`) accept strings
   as match targets. Star variables bind to **substrings** (e.g. `A = "he"`,
   `B = "lo"`) — still strings throughout, not atoms — with no
   character-list conversion happening.

3. **Builtins:** List predicates accept strings wherever they accept lists. When
   the result should be a string (all inputs were strings, result is a char
   sequence), a string is returned.

4. **Head patterns:** Compiled clause head patterns like `[H, *T]` work on
   strings. `H` binds to a **char atom**, `T` binds to the remaining
   substring (still a string, not a list — and not an atom).

!!! warning "Strings are not indexed"
    First-argument indexing keys on atoms, numbers and functors. A **string**
    first argument is not indexable — a string head and a char-list head are
    the same term, so both land in the same full-scan bucket. A fact table
    keyed by symbols should key them as **atoms**, not as strings.

---

## Code-point vs grapheme semantics

Clausal Prolog's strings-as-lists contract operates at **code-point granularity**,
not grapheme granularity. This means:

- A multi-codepoint emoji like `"👍🏽"` (thumbs-up + skin-tone modifier)
  has `len("👍🏽") == 2` and unifies with `['👍', '🏽']`, not `['👍🏽']`.
- A base character followed by a combining mark — `"é"` written as
  decomposed form (base `e` + combining acute U+0301) — has length 2 and unifies
  with `['e', '́']`. The same character in precomposed form (`"é"`, U+00E9)
  has length 1 and unifies with `['é']`. NFC and NFD representations of the
  same grapheme do not unify with each other.
- Lone surrogate halves are processed as individual code points
  (Python permits malformed Unicode at the surrogate level).
- Only **one-character atoms** are string elements. A list of multi-character
  atoms (`['ab', 'c']`) does not unify with a string, and neither does a list
  of one-character *strings* (`["a", "b"]`, which is a list of two one-element
  lists).

This rule applies uniformly across:

- C-level `unify` (str ↔ list).
- `SegList` and `SegString` walks and unification.
- Head and body multi-star patterns over string targets.
- `phrase/2,3` and DCG terminals.
- `char_type`, `char_code`, `atom_chars`, `atom_codes`.
- All polymorphic list builtins (`append`, `length`, `member`, etc.).

If your application needs grapheme-aware processing (e.g. cursor
movement in a text editor), use the standard Python library
`unicodedata` or the third-party `regex`/`grapheme` packages
**before** handing the string to the engine — it sees code points.

---

## Comparison with Prolog

Clausal Prolog follows [Scryer Prolog](https://github.com/mthom/scryer-prolog) here: a string **is** the list of
its character atoms, the two never unify with an atom, and the `atom_*` family
raises `type_error(atom, …)` on a string. Scryer likewise keeps a compact
internal representation rather than materialising cons cells; Clausal Prolog's wraps
a Python `str`.

This doc covers the **`chars`** model (a string is the list of its
one-character atoms). Clausal Prolog also has the Prolog **`codes`** model for byte
sequences: a Python `bytes` behaves as a list of integer codes in `[0, 255]`,
written `b"…"`. See [Bytes as Lists of Codes](bytes_as_lists.md) for
byte-stream unification and binary-protocol DCGs.

| Feature | Traditional Prolog | Clausal Prolog |
|---------|-------------------|---------|
| String representation | List of character atoms | wraps a Python `str` — the same *term* as the char list, a compact representation |
| `"abc" = [a, b, c]` | True | True |
| `atom("abc")` | False | False |
| `atom_length("abc", N)` | `type_error(atom, …)` | `type_error(atom, …)` |
| `append/3` on strings | Works (strings are lists) | Works (strings are lists) |
| DCGs on strings | Works | Works |
| Pattern matching | Works | Works — star vars bind to substrings |
| Performance | O(n) cons cells | O(1) Python str operations |
| Python interop | Requires conversion | `to_python` gives a `str`; a `++` callee receives a `str` |

---

## Examples

### Palindrome check (works on both strings and lists)

```seam
palindrome(XS) <- reverse(XS, XS)

test("list palindrome") <- palindrome([1, 2, 1])
test("string palindrome") <- palindrome("racecar")
test("not palindrome") <- (not palindrome("hello"))
```

### Character frequency

Using [findall](meta_predicates.md) to count matching characters:

```seam
char_count(STR, CHAR, COUNT) <- (
    findall(C, (in_(C, STR), C is CHAR), MATCHES),
    length(MATCHES, COUNT)
)

# The Char argument is a CHARACTER — a one-character atom, written 'l'.
# "l" would be the one-element string ['l'], which is not an element.
test("count l") <- char_count("hello", 'l', 2)
test("count z") <- char_count("hello", 'z', 0)
```

### Simple tokenizer with DCGs

```seam
# char_type/2's Type argument and the token tags are ATOMS, single-quoted
# so they cannot be mistaken for the nonterminals of the same spelling.
alpha >> ([C], {char_type(C, 'alpha')})
digit >> ([C], {char_type(C, 'digit')})

alphas >> (alpha)
alphas >> (alpha, alphas)

digits >> (digit)
digits >> (digit, digits)

token('word') >> (alphas)
token('number') >> (digits)

test("word token") <- phrase(token('word'), "hello")
test("number token") <- phrase(token('number'), "42")
```
