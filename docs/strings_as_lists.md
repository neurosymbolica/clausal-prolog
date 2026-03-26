# Strings as Lists of Characters

In Clausal, strings are treated as lists of single-character strings at the
logic level. You can use list predicates, pattern matching, and DCGs on strings
directly — no conversion needed.

---

## Why?

In logic programming, sequences are the universal data structure. Lists hold
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
# skip
Test("string = char list") <- "abc" == ['a', 'b', 'c']
Test("with vars") <- ("abc" == [X, Y, Z], X == 'a', Y == 'b', Z == 'c')
Test("partial") <- ("hello" == ['h', 'e', X, Y, 'o'], X == 'l', Y == 'l')
```

String-to-string unification is unchanged — `"abc" = "abc"` succeeds by
equality (no element-wise comparison needed).

The empty string unifies with the empty list:

```clausal
# skip
Test("empty") <- "" == []
```

---

## Pattern Matching

Multi-star list patterns work on strings:

```clausal
# skip
starts_with([*Prefix, *_], Prefix)
ends_with([*_, *Suffix], Suffix)
contains([*_, X, *_], X)

Test("prefix") <- starts_with("hello", ['h', 'e', 'l'])
Test("suffix") <- ends_with("hello", ['l', 'o'])
Test("contains l") <- contains("hello", 'l')
```

This is the same pattern syntax used for lists — no special string patterns
needed.

---

## List Predicates on Strings

All list predicates accept strings. When every input is a string and the result
is a character sequence, the result is returned as a string:

### Append

```clausal
# skip
Test("concat") <- Append("hel", "lo", "hello")
Test("prefix match") <- Append("hel", X, "hello"), X == "lo"
Test("suffix match") <- Append(X, "lo", "hello"), X == "hel"
Test("split") <- Append(X, Y, "hello"), X == "he", Y == "llo"
```

### Length

```clausal
# skip
Test("length") <- Length("hello", 5)
```

### In (Member)

```clausal
# skip
Test("member") <- In('e', "hello")
Test("enumerate") <- (
    FindAll(C, In(C, "abc"), Chars),
    Chars == ['a', 'b', 'c']
)
```

### Reverse

```clausal
# skip
Test("reverse") <- Reverse("hello", "olleh")
```

### Take, Drop, SplitAt

```clausal
# skip
Test("take") <- Take(3, "hello", "hel")
Test("drop") <- Drop(3, "hello", "lo")
Test("split") <- SplitAt(3, "hello", "hel", "lo")
```

### GetItem

```clausal
# skip
Test("index") <- GetItem("hello", 1, 'e')
```

---

## DCGs on Strings

Definite Clause Grammars parse strings directly:

```clausal
digit >> ([D], {CharType(D, digit)})
digits >> (digit)
digits >> (digit, digits)

Test("parse digits") <- phrase(digits, "123")
Test("partial parse") <- (
    phrase(digits, "12ab", Rest),
    Rest == ['a', 'b']
)
```

No `AtomChars` conversion is needed. Pass a string to `phrase/2` or `phrase/3`
and the DCG consumes its characters as list elements.

### Character-Level Grammars

Because strings are character lists, you can write character-level grammars
naturally:

```clausal
letter >> ([C], {CharType(C, alpha)})
space >> ([' '])
word >> (letter)
word >> (letter, word)
words >> (word)
words >> (word, space, words)

Test("parse words") <- phrase(words, "hello world")
```

---

## Type Checking

Two predicates test sequence types:

| Predicate | Strings | Lists | Purpose |
|-----------|---------|-------|---------|
| `IsList/1` | Fails | Succeeds | Exact type test: is this a Python list? |
| `IsStr/1` | Succeeds | Fails | Exact type test: is this a Python str? |
| `IsChars/1` | Succeeds | Succeeds | Union test: is this a character sequence? |

Use `IsChars/1` when you want to accept both strings and lists. Use `IsList/1`
or `IsStr/1` when you need to distinguish the two.

```clausal
# skip
Test("is_chars string") <- IsChars("hello")
Test("is_chars list") <- IsChars([1, 2, 3])
Test("is_list string fails") <- not IsList("hello")
Test("is_str list fails") <- not IsStr([1, 2, 3])
```

---

## String-Specific Predicates

The traditional string predicates (`AtomChars/2`, `AtomConcat/3`, `SubAtom/5`,
`AtomLength/2`, etc.) still work. They are useful for:

- **Explicit conversion:** `AtomChars("hello", Chars)` gives you a plain list
  when you specifically need one
- **Code-point operations:** `AtomCodes/2`, `CharCode/2` relate characters to
  integer code points
- **Character classification:** `CharType/2` tests character types (alpha, digit,
  etc.)
- **Case conversion:** `UpcaseAtom/2`, `DowncaseAtom/2`
- **ISO Prolog compatibility**

For concatenation, splitting, length, and membership, prefer the list predicates
(`Append/3`, `Length/2`, `In/2`) — they work uniformly on both strings and lists.

---

## How It Works

Clausal keeps Python `str` as the internal representation of strings. This
preserves performance (string comparison, hashing, and concatenation are fast)
and Python interoperability (strings passed to Python functions remain `str`).

The logic layer adds string-as-list behaviour in three places:

1. **Unification:** When a string meets a list, the string is treated as a list
   of its characters. `"abc"` unifies with `['a', 'b', 'c']` element-wise.
   String-vs-string remains fast equality.

2. **Pattern matching:** SegList (the data structure behind multi-star patterns)
   accepts strings as match targets. `[*A, 'l', *B]` can match against
   `"hello"`.

3. **Builtins:** List predicates accept strings wherever they accept lists. When
   the result should be a string (all inputs were strings, result is a char
   sequence), a string is returned.

This is a Liskov-style subtyping approach: a string can be used anywhere a list
of characters is expected, with no loss of functionality.

---

## Comparison with Prolog

In Prolog systems like Scryer Prolog, strings *are* lists of characters — the
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
| Pattern matching | Works | Works (via SegList) |
| Performance | O(n) cons cells | O(1) Python str operations |
| Python interop | Requires conversion | Native `str` |

---

## Examples

### Palindrome check (works on both strings and lists)

```clausal
palindrome(XS) <- Reverse(XS, XS)

Test("list palindrome") <- palindrome([1, 2, 1])
Test("string palindrome") <- palindrome("racecar")
Test("not palindrome") <- not palindrome("hello")
```

### Character frequency

```clausal
char_count(Str, Char, Count) <- (
    FindAll(C, (In(C, Str), C == Char), Matches),
    Length(Matches, Count)
)

Test("count l") <- char_count("hello", 'l', 2)
Test("count z") <- char_count("hello", 'z', 0)
```

### Simple tokenizer with DCGs

```clausal
alpha >> ([C], {CharType(C, alpha)})
digit >> ([C], {CharType(C, digit)})

alphas >> (alpha)
alphas >> (alpha, alphas)

digits >> (digit)
digits >> (digit, digits)

token(word) >> (alphas)
token(number) >> (digits)

Test("word token") <- phrase(token(word), "hello")
Test("number token") <- phrase(token(number), "42")
```
