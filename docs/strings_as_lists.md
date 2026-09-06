# Strings as Lists of Characters

In Clausal a string **is** the list of its one-character atoms — the ISO
Prolog *chars* model, as in Scryer. You can use list predicates, pattern
matching, and DCGs on strings directly; no conversion needed, because there is
nothing to convert.

!!! note "Writing a string literal"
    A double-quoted literal means a string only in a file that declares
    [`-double_quotes(chars)`](directives.md#-double_quotes). The engine default
    is still `atom`, where `"hello"` is the atom `hello`; the default flips to
    `chars` once every module has migrated. Every example on this page is run
    under `-double_quotes(chars)`. A single-quoted `'hello'` is always an atom,
    in either mode.

---

## Why?

In logic programming, sequences are the universal data structure. Lists hold
elements; strings hold characters. The operations you want on both are the same:
split, join, reverse, search, filter, iterate. Maintaining two parallel sets of
predicates — one for lists, one for strings — doubles the API surface and forces
users to constantly ask "am I working with a string or a list right now?"

Clausal answers that by making the string *be* the list. Under the hood a string
is still a Python `str` (fast, compact, interoperable with Python libraries) —
it is never expanded into a chain of cons cells — but at the logic level
`"hello"` and `['h', 'e', 'l', 'l', 'o']` are one and the same term.

The elements are **character atoms**: `'h'` is the atom whose spelling is the
single character `h`, not the one-character string `"h"`. So
`nth0(0, "abc", C)` gives `C = 'a'`, and `in_("a", "abc")` fails — `"a"` is the
*list* `['a']`, not the character.

---

## Unification

A string unifies with the list of its character atoms:

```clausal
--8<-- "tests/fixtures/docs/strings_as_lists_examples.clausal:unification"
```

String-to-string unification is unchanged — `"abc" = "abc"` succeeds by
equality (no element-wise comparison needed).

The empty string unifies with the empty list:

```clausal
--8<-- "tests/fixtures/docs/strings_as_lists_examples.clausal:empty_string"
```

---

## Pattern Matching

Multi-star list patterns work on strings. Star variables bind to
**substrings** (not character lists), preserving the `str` type:

```clausal
--8<-- "tests/fixtures/docs/strings_as_lists_examples.clausal:pattern_matching"
```

This is the same pattern syntax used for lists — no special string patterns
needed. when matching a string, `*Prefix` binds to a substring; when matching
a list, it binds to a sublist.

**`[*XS]` is not a list test.** Because a string unifies with list patterns,
`Listish([*XS])` succeeds for `Listish("met")` too — binding `XS` to the whole
string — and `[H, *T]` destructures a string one character at a time. A
recursive list-walking predicate written the obvious way therefore walks
*into* every string in its input instead of treating it as a leaf. When a
predicate must recurse over lists but pass strings through whole, gate the
destructuring clause explicitly: `ISLIST is ++isinstance(X, list),
ISLIST is True` before matching `[H, *T]`. (Found the expensive way by the
rewriter's rule walker — see `clausal/rewrite/rules/head_fold.clausal` for
the in-tree example of the gate.)

---

## List Predicates on Strings

All [list predicates](lists.md) accept strings. when every input is a string and the result
is a character sequence, the result is returned as a string:

### append

```clausal
--8<-- "tests/fixtures/docs/strings_as_lists_examples.clausal:append_examples"
```

### length

```clausal
--8<-- "tests/fixtures/docs/strings_as_lists_examples.clausal:length_example"
```

### in_ (Member)

```clausal
--8<-- "tests/fixtures/docs/strings_as_lists_examples.clausal:member_examples"
```

### reverse

```clausal
--8<-- "tests/fixtures/docs/strings_as_lists_examples.clausal:reverse_example"
```

### take, drop, split_at

```clausal
--8<-- "tests/fixtures/docs/strings_as_lists_examples.clausal:take_drop_split"
```

### list_item

```clausal
--8<-- "tests/fixtures/docs/strings_as_lists_examples.clausal:list_item_example"
```

---

## DCGs on Strings

[Definite Clause Grammars](dcg.md) parse strings directly:

```clausal
-double_quotes(chars)

# `'digit'` is single-quoted: char_type/2's Type argument is an ATOM, and a
# bare `digit` here would name the nonterminal defined on the next line.
digit >> ([D], {char_type(D, 'digit')})
digits >> (digit)
digits >> (digit, digits)

Test("parse digits") <- phrase(digits, "123")
Test("partial parse") <- (
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

```clausal
-double_quotes(chars)

letter >> ([C], {char_type(C, alpha)})
space >> ([' '])
word >> (letter)
word >> (letter, word)
words >> (word)
words >> (word, space, words)

Test("parse words") <- phrase(words, "hello world")
```

---

## Type Checking

Three predicates test sequence types (see [Type Checking](type_checking.md) for the full set):

| Predicate | Strings | Lists | Atoms | Purpose |
|-----------|---------|-------|-------|---------|
| `is_list/1` | Succeeds | Succeeds | Fails | Polymorphic: is this a list-shaped value (list or char-sequence str)? |
| `is_str/1`, `string/1` | Succeeds | Fails | Fails | Exact type test: is this a Python str? |
| `is_chars/1` | Succeeds | Succeeds | Fails | union test: is this a character sequence? |

`is_list/1` is polymorphic over `list` and `str` (audit 2026-05-25, F080)
so it agrees with every list-flavoured builtin — `append`, `length`,
`reverse`, `member`, `maplist`, `take`, `drop`, etc. — all of which
accept a `str` as a character sequence. Use `is_str/1` when you
specifically need to distinguish a `str` from a `list`.

None of the three accepts an **atom**: an atom is a symbol, not a sequence.
`atom("hello")` and `string(hello)` are both false, and the two never unify.
The atom-flavoured predicates in the next section are the bridge between them.

```clausal
--8<-- "tests/fixtures/docs/strings_as_lists_examples.clausal:type_checking"
```

---

## The `atom_*` family works on ATOMS

The ISO `atom_*` predicates (`atom_chars/2`, `atom_codes/2`, `atom_concat/3`,
`sub_atom/5`, `atom_length/2`, `upcase_atom/2`, `downcase_atom/2`) take an
**atom** in the atom position and give atoms back. Handing one a string raises
`type_error(atom, …)` — it is not a silent failure:

```clausal
--8<-- "tests/fixtures/docs/strings_as_lists_examples.clausal:atom_family"
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
`nth0/3`) — they work uniformly on strings and lists, because a string is a
list.

---

## How It Works

Clausal keeps Python `str` as the internal representation of strings. This
preserves performance (string comparison, hashing, and concatenation are fast)
and Python interoperability (strings passed to Python functions remain `str`).
**The representation is never materialised into cons cells** — a string is a
`str`, a proper list is a `list`, and a partial list or partial string is the
engine's `SegList`/`SegString`. The `'.'/2` cons structure is only ever a
*view* onto those, produced on demand by `functor/3`, `arg/3`, `=..` and
`write_canonical/1`.

The logic layer makes the string *be* its char list in four places:

1. **Unification:** when a string meets a list, they unify element-wise against
   the string's character atoms. `"abc"` unifies with `['a', 'b', 'c']`.
   String-vs-string remains fast equality.

2. **Pattern matching:** Multi-star patterns (`[*A, 'l', *B]`) accept strings
   as match targets. Star variables bind to **substrings** (e.g. `A = "he"`,
   `B = "lo"`), preserving the `str` type throughout — no character-list
   conversion happens.

3. **Builtins:** List predicates accept strings wherever they accept lists. When
   the result should be a string (all inputs were strings, result is a char
   sequence), a string is returned.

4. **Head patterns:** Compiled clause head patterns like `[H, *T]` work on
   strings. `H` binds to a **char atom**, `T` binds to the remaining
   substring (`str`, not a list).

!!! warning "Strings are not indexed"
    First-argument indexing keys on atoms, numbers and functors. A **string**
    first argument is not indexable — a string head and a char-list head are
    the same term, so both land in the same full-scan bucket. A fact table
    keyed by symbols should key them as **atoms**, not as strings.

---

## Code-point vs grapheme semantics

Clausal's strings-as-lists contract operates at **code-point granularity**,
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
**before** handing the string to Clausal — Clausal sees code points.

---

## Comparison with Prolog

Clausal follows [Scryer Prolog](scryer.md) here: a string **is** the list of
its character atoms, the two never unify with an atom, and the `atom_*` family
raises `type_error(atom, …)` on a string. Scryer likewise keeps a compact
internal representation rather than materialising cons cells; Clausal's is the
Python `str`, so a string handed to a Python callee is a `str` with no
conversion at all.

This doc covers the **`chars`** model (a `str` is the list of its
one-character atoms). Clausal also has the Prolog **`codes`** model for byte
sequences: a Python `bytes` behaves as a list of integer codes in `[0, 255]`,
written `b"…"`. See [Bytes as Lists of Codes](bytes_as_lists.md) for
byte-stream unification and binary-protocol DCGs.

| Feature | Traditional Prolog | Clausal |
|---------|-------------------|---------|
| String representation | List of character atoms | Python `str` — the same *term*, a compact representation |
| `"abc" = [a, b, c]` | True | True |
| `atom("abc")` | False | False |
| `atom_length("abc", N)` | `type_error(atom, …)` | `type_error(atom, …)` |
| `append/3` on strings | Works (strings are lists) | Works (strings are lists) |
| DCGs on strings | Works | Works |
| Pattern matching | Works | Works — star vars bind to substrings |
| Performance | O(n) cons cells | O(1) Python str operations |
| Python interop | Requires conversion | Native `str` |

---

## Examples

### Palindrome check (works on both strings and lists)

```clausal
-double_quotes(chars)

palindrome(XS) <- reverse(XS, XS)

Test("list palindrome") <- palindrome([1, 2, 1])
Test("string palindrome") <- palindrome("racecar")
Test("not palindrome") <- (not palindrome("hello"))
```

### Character frequency

Using [findall](meta_predicates.md) to count matching characters:

```clausal
-double_quotes(chars)

char_count(STR, CHAR, COUNT) <- (
    findall(C, (in_(C, STR), C is CHAR), MATCHES),
    length(MATCHES, COUNT)
)

# The Char argument is a CHARACTER — a one-character atom, written 'l'.
# "l" would be the one-element string ['l'], which is not an element.
Test("count l") <- char_count("hello", 'l', 2)
Test("count z") <- char_count("hello", 'z', 0)
```

### Simple tokenizer with DCGs

```clausal
-double_quotes(chars)

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

Test("word token") <- phrase(token('word'), "hello")
Test("number token") <- phrase(token('number'), "42")
```
