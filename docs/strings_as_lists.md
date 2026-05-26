# Strings as Lists of Characters

in_ Clausal, strings are treated as lists of single-character strings at the
logic level. You can use list predicates, pattern matching, and DCGs on strings
directly — no conversion needed.

---

## Why?

in_ logic programming, sequences are the universal data structure. Lists hold
elements; strings hold characters. The operations you want on both are the same:
split, join, reverse, search, filter, iterate. Maintaining two parallel sets of
predicates — one for lists, one for strings — doubles the API surface and forces
users to constantly ask "am I working with a string or a list right now?"

Clausal eliminates this by treating a string as a list of its characters
wherever a list is expected. Under the hood, strings are still Python `str`
objects (fast, compact, interoperable with Python libraries). But at the logic
level, `"hello"` and `['h', 'e', 'l', 'l', 'o']` are interchangeable.

---

## Unification

A string unifies with a list of single-character strings:

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

### get_item

```clausal
--8<-- "tests/fixtures/docs/strings_as_lists_examples.clausal:get_item_example"
```

---

## DCGs on Strings

[Definite Clause Grammars](dcg.md) parse strings directly:

```clausal
digit >> ([D], {char_type(D, digit)})
digits >> (digit)
digits >> (digit, digits)

Test("parse digits") <- phrase(digits, "123")
Test("partial parse") <- (
    phrase(digits, "12ab", Rest),
    Rest == ['a', 'b']
)
```

No `atom_chars` conversion is needed. Pass a string to `phrase/2` or `phrase/3`
and the DCG consumes its characters as list elements.

### Character-Level Grammars

Because strings are character lists, you can write character-level grammars
naturally:

```clausal
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

Two predicates test sequence types (see [Type Checking](type_checking.md) for the full set):

| Predicate | Strings | Lists | Purpose |
|-----------|---------|-------|---------|
| `is_list/1` | Fails | Succeeds | Exact type test: is this a Python list? |
| `is_str/1` | Succeeds | Fails | Exact type test: is this a Python str? |
| `is_chars/1` | Succeeds | Succeeds | union test: is this a character sequence? |

Use `is_chars/1` when you want to accept both strings and lists. Use `is_list/1`
or `is_str/1` when you need to distinguish the two.

```clausal
--8<-- "tests/fixtures/docs/strings_as_lists_examples.clausal:type_checking"
```

---

## String-Specific Predicates

The traditional string predicates (`atom_chars/2`, `atom_concat/3`, `sub_atom/5`,
`atom_length/2`, etc.) still work. They are useful for:

- **Explicit conversion:** `atom_chars("hello", Chars)` gives you a plain list
  when you specifically need one
- **Code-point operations:** `atom_codes/2`, `char_code/2` relate characters to
  integer code points
- **Character classification:** `char_type/2` tests character types (alpha, digit,
  etc.)
- **Case conversion:** `upcase_atom/2`, `downcase_atom/2`
- **ISO Prolog compatibility**

For concatenation, splitting, length, and membership, prefer the [list predicates](lists.md)
(`append/3`, `length/2`, `in_/2`) — they work uniformly on both strings and lists.

---

## How It Works

Clausal keeps Python `str` as the internal representation of strings. This
preserves performance (string comparison, hashing, and concatenation are fast)
and Python interoperability (strings passed to Python functions remain `str`).

The logic layer adds string-as-list behaviour in four places:

1. **Unification:** when a string meets a list, the string is treated as a list
   of its characters. `"abc"` unifies with `['a', 'b', 'c']` element-wise.
   String-vs-string remains fast equality.

2. **Pattern matching:** Multi-star patterns (`[*A, 'l', *B]`) accept strings
   as match targets. Star variables bind to **substrings** (e.g. `A = "he"`,
   `B = "lo"`), preserving the `str` type throughout — no character-list
   conversion happens.

3. **Builtins:** List predicates accept strings wherever they accept lists. when
   the result should be a string (all inputs were strings, result is a char
   sequence), a string is returned.

4. **Head patterns:** Compiled clause head patterns like `[H, *T]` work on
   strings. `H` binds to a single character, `T` binds to the remaining
   substring (`str`, not a list).

This is a Liskov-style subtyping approach: a string can be used anywhere a list
of characters is expected, with no loss of functionality.

---

## Code-point vs grapheme semantics

Clausal's strings-as-lists contract operates at **code-point granularity**,
not grapheme granularity. This means:

- A multi-codepoint emoji like `"👍🏽"` (thumbs-up + skin-tone modifier)
  has `len("👍🏽") == 2` and unifies with `["👍", "🏽"]`, not `["👍🏽"]`.
- A base character followed by a combining mark — `"é"` written as
  decomposed form (base `e` + combining acute U+0301) — has length 2 and unifies
  with `["e", "́"]`. The same character in precomposed form (`"é"`, U+00E9)
  has length 1 and unifies with `["é"]`. NFC and NFD representations of the
  same grapheme do not unify with each other.
- Lone surrogate halves are processed as individual code points
  (Python permits malformed Unicode at the surrogate level).
- List elements that are multi-character strings (e.g. `["ab", "c"]`)
  are **rejected** by the per-element check; only 1-character list elements
  participate in str↔list unification.

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

in_ Prolog systems like [Scryer Prolog](scryer.md), strings *are* lists of characters — the
same data structure, with no distinction. This gives maximum uniformity at the
cost of performance (no compact string representation) and foreign-function
interop (every string is a linked list of character atoms).

Clausal takes a pragmatic middle path: strings *behave as* lists of characters
at the logic level, but remain Python `str` objects internally. You get the
logical uniformity of Prolog's approach with the performance and interop of
Python's native strings.

| Feature | Traditional Prolog | Clausal |
|---------|-------------------|---------|
| String representation | List of character atoms | Python `str` |
| `append/3` on strings | Works (strings are lists) | Works (strings behave as lists) |
| DCGs on strings | Works | Works |
| Pattern matching | Works | Works — star vars bind to substrings |
| Performance | O(n) cons cells | O(1) Python str operations |
| Python interop | Requires conversion | Native `str` |

---

## Examples

### Palindrome check (works on both strings and lists)

```clausal
palindrome(XS) <- reverse(XS, XS)

Test("list palindrome") <- palindrome([1, 2, 1])
Test("string palindrome") <- palindrome("racecar")
Test("not palindrome") <- not palindrome("hello")
```

### Character frequency

Using [findall](meta_predicates.md) to count matching characters:

```clausal
char_count(Str, Char, Count) <- (
    findall(C, (in_(C, Str), C == Char), Matches),
    length(Matches, Count)
)

Test("count l") <- char_count("hello", 'l', 2)
Test("count z") <- char_count("hello", 'z', 0)
```

### Simple tokenizer with DCGs

```clausal
alpha >> ([C], {char_type(C, alpha)})
digit >> ([C], {char_type(C, digit)})

alphas >> (alpha)
alphas >> (alpha, alphas)

digits >> (digit)
digits >> (digit, digits)

token(word) >> (alphas)
token(number) >> (digits)

Test("word token") <- phrase(token(word), "hello")
Test("number token") <- phrase(token(number), "42")
```
