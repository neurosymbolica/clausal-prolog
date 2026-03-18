# Regex Module

The `regex` standard library module provides regular expression predicates for `.clausal` files. It wraps Python's `re` module with a relational interface, including auto-binding of named capture groups to logic variables.

The implementation lives in `clausal/modules/regex.py`.

---

## Import

```
-import_from(regex, [Match, Search, Replace, Split, FindAll])
```

Or via module import:

```
-import_module(regex)
# then use regex.Match(...), regex.Search(...), etc.
```

---

## Predicates

### Match/2 — Boolean Match

`Match(Pattern, String)` — succeeds if Pattern matches String (anchored at start):

```
Match(r"\d+", "123")           # succeeds
Match(r"\d+", "abc")           # fails
Match(r"\d+$", "123abc")       # fails (no match at end)
```

### Match/3 — Group Extraction

`Match(Pattern, String, Groups)` — unifies Groups with a dict of named groups (or tuple of positional groups):

```
Match(r"(?P<year>\d{4})-(?P<month>\d{2})", "2026-03", G_)
# G_ = {"year": "2026", "month": "03"}

Match(r"(\d+)-(\d+)", "42-99", G_)
# G_ = ("42", "99")
```

### Auto-Binding

Named groups using ALLCAPS or trailing-underscore names are automatically bound to corresponding clause variables at compile time (via goal expansion):

```
Test("auto-bind YEAR") <- (
    YEAR_ is "2026" and
    Match(r"(?P<YEAR>\d{4})-\d{2}", "2026-03")
)
```

The goal expansion pass detects `(?P<YEAR>...)` and generates code to unify the `YEAR` group with the `YEAR_` variable.

### Search/2, Search/3

Like Match but unanchored — finds the pattern anywhere in the string:

```
Search(r"\d+", "abc123def")    # succeeds
Search(r"\d+", "abcdef")       # fails

Search(r"(?P<key>\w+)=(?P<val>\w+)", "foo bar=baz", G_)
# G_ = {"key": "bar", "val": "baz"}
```

### Replace/4

`Replace(Pattern, Replacement, String, Result)` — regex substitution:

```
Replace(r"\s+", " ", "a  b   c", R_)          # R_ = "a b c"
Replace(r"\d+", "", "a1b2c3", R_)              # R_ = "abc"
Replace(r"(\w+)", r"[\1]", "hi lo", R_)        # R_ = "[hi] [lo]"
```

### Split/3

`Split(Pattern, String, Fragments)` — split string by pattern:

```
Split(r",\s*", "a, b, c", F_)     # F_ = ["a", "b", "c"]
Split(r"\s+", "x y z", F_)        # F_ = ["x", "y", "z"]
```

### FindAll/3

`FindAll(Pattern, String, Match)` — nondeterministic; succeeds once for each non-overlapping match:

```
FindAll(r"\d+", "a1b23c456", D_)
# D_ = "1", then "23", then "456"
```

Fails if no matches are found.

---

## Pattern Precompilation

The goal expansion pass (`clausal/logic/goal_expansion.py`) detects string-literal patterns and precompiles them to `re.Pattern` objects at load time. This avoids recompiling the regex on every call.

---

## Dynamic Patterns

Patterns can be variables or f-strings:

```
Test("dynamic match") <- Match(f"^{"hello"}", "hello world")
Test("dynamic pattern") <- (PAT_ is r"\d+", Match(PAT_, "42"))
```

Dynamic patterns are compiled at runtime (no precompilation).

---

??? info "Test coverage"

    Tests are in `tests/test_regex.py` (93 tests).

    - **Match/2**: digits, anchoring, email, empty, unicode
    - **Match/3**: named groups, positional groups, no match
    - **Auto-binding**: ALLCAPS groups, trailing-underscore groups
    - **Search/2,3**: unanchored search, group extraction
    - **Replace/4**: whitespace, digit removal, backreferences
    - **Split/3**: comma, whitespace
    - **FindAll/3**: multiple matches, no matches
    - **Edge cases**: dynamic patterns, pattern variables
    - **Fixture integration**: `regex_basic.clausal` (25 tests), `regex_autobind.clausal` (17 tests)
