# Regex Module

The `regex` standard library module provides regular expression predicates for `.clausal` files. It wraps Python's `re` module with a relational interface, including auto-binding of named capture groups to logic variables.

---

## Quick Example

```clausal
-import_from(regex, [Match])

ParseDate(DATE, YEAR, MONTH) <- (
    Match(r"(?P<YEAR>\d{4})-(?P<MONTH>\d{2})", DATE)
)

Test("parse date") <- (
    ParseDate("2026-03", YEAR, MONTH),
    YEAR == "2026",
    MONTH == "03"
)
```

The named groups `YEAR` and `MONTH` are automatically bound to the clause variables of the same name — no explicit group extraction needed.

---

## Import

```clausal
# skip
-import_from(regex, [Match, Search, Replace, Split, findall])
```

Or via [module import](import.md):

```clausal
# skip
-import_module(regex)
# then use regex.Match(...), regex.Search(...), etc.
```

---

## Predicates

### Match/2 — Boolean Match

`Match(Pattern, String)` — succeeds if Pattern matches String (anchored at start):

```clausal
-import_from(regex, [Match])

Test("match digits") <- Match(r"\d+", "123")
Test("match fails") <- (not Match(r"\d+", "abc"))
Test("match anchored") <- (not Match(r"\d+$", "123abc"))
```

### Match/3 — Group Extraction

`Match(Pattern, String, Groups)` — unifies Groups with a dict of named groups (or tuple of positional groups):

```clausal
-import_from(regex, [Match])

Test("named groups") <- (
    Match(r"(?P<year>\d{4})-(?P<month>\d{2})", "2026-03", G),
    YEAR is ++G["year"],
    MONTH is ++G["month"],
    YEAR == "2026",
    MONTH == "03"
)

Test("positional groups") <- (
    Match(r"(\d+)-(\d+)", "42-99", G),
    G == ("42", "99")
)
```

### Search/2, Search/3

Like Match but unanchored — finds the pattern anywhere in the string:

```clausal
-import_from(regex, [Search])

Test("search found") <- Search(r"\d+", "abc123def")
Test("search not found") <- (not Search(r"\d+", "abcdef"))

Test("search groups") <- (
    Search(r"(?P<key>\w+)=(?P<val>\w+)", "foo bar=baz", G),
    KEY is ++G["key"],
    VAL is ++G["val"],
    KEY == "bar",
    VAL == "baz"
)
```

### Replace/4

`Replace(Pattern, Replacement, String, Result)` — regex substitution:

```clausal
-import_from(regex, [Replace])

Test("collapse spaces") <- (Replace(r"\s+", " ", "a  b   c", R), R == "a b c")
Test("remove digits") <- (Replace(r"\d+", "", "a1b2c3", R), R == "abc")
```

### Split/3

`Split(Pattern, String, Fragments)` — split string by pattern:

```clausal
-import_from(regex, [Split])

Test("split csv") <- (Split(r",\s*", "a, b, c", F), F == ["a", "b", "c"])
Test("split whitespace") <- (Split(r"\s+", "x y z", F), F == ["x", "y", "z"])
```

### findall/3 (Regex)

`findall(Pattern, String, Match)` — nondeterministic; succeeds once for each non-overlapping match:

```clausal
-import_from(regex, [findall])

Test("findall first") <- (findall(r"\d+", "a1b23c456", D), D == "1")
```

Fails if no matches are found.

---

## Auto-Binding

Named groups using ALLCAPS or leading-underscore names are automatically bound to corresponding clause [variables](syntax.md) at compile time (via [goal expansion](term_expansion.md)). This is the key feature that makes regex feel native in Clausal.

### ALLCAPS Groups

```clausal
-import_from(regex, [Match])

ParseEmail(EMAIL, USER, DOMAIN) <- (
    Match(r"(?P<USER>[^@]+)@(?P<DOMAIN>.+)", EMAIL)
)

Test("parse email") <- (
    ParseEmail("alice@example.com", USER, DOMAIN),
    USER == "alice",
    DOMAIN == "example.com"
)
```

### Leading-Underscore Groups

```clausal
-import_from(regex, [Search])

ExtractPort(URL, _port) <- (
    Search(r":(?P<_port>\d+)", URL)
)

Test("extract port") <- (
    ExtractPort("http://localhost:8080/api", PORT),
    PORT == "8080"
)
```

### How It Works

The goal expansion pass detects `(?P<NAME>...)` patterns where NAME matches a variable in scope. It rewrites the Match/2 call into Match/3 plus unification:

```clausal
# skip
# Before expansion (what you write):
Match(r"(?P<YEAR>\d{4})-(?P<MONTH>\d{2})", S)

# After expansion (what the compiler sees):
Match(r"(?P<YEAR>\d{4})-(?P<MONTH>\d{2})", S, _G),
YEAR is _G["YEAR"], MONTH is _G["MONTH"]
```

You never see the expanded form — just use the variable names in your pattern.

---

## Practical Patterns

### Log Parsing

```clausal
-import_from(regex, [Match])

ParseLogLine(LINE, LEVEL, MESSAGE) <- (
    Match(r"(?P<LEVEL>INFO|WARN|ERROR)\s+(?P<MESSAGE>.+)", LINE)
)

IsError(LINE) <- Match(r"^ERROR", LINE)

Test("parse log info") <- (
    ParseLogLine("INFO system started", LEVEL, MSG),
    LEVEL == "INFO",
    MSG == "system started"
)
Test("is error") <- IsError("ERROR disk full")
Test("not error") <- (not IsError("INFO ok"))
```

### CSV Field Extraction

```clausal
-import_from(regex, [Split])

ParseCsv(LINE, FIELDS) <- Split(r",\s*", LINE, FIELDS)

Test("parse csv") <- (
    ParseCsv("a, b, c", FIELDS),
    FIELDS == ["a", "b", "c"]
)
```

### URL Routing

```clausal
-import_from(regex, [Match])

RouteUser(PATH, USER_ID) <- (
    Match(r"/users/(?P<USER_ID>\d+)", PATH)
)

RouteApi(PATH) <- Match(r"^/api/v\d+/", PATH)

Test("route user") <- (RouteUser("/users/42", UID), UID == "42")
Test("route api") <- RouteApi("/api/v2/data")
Test("not api") <- (not RouteApi("/users/1"))
```

### Data Validation

```clausal
-import_from(regex, [Match])

ValidEmail(S) <- Match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", S)
ValidIpv4(S) <- Match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", S)

Test("valid email") <- ValidEmail("alice@example.com")
Test("invalid email") <- (not ValidEmail("not-an-email"))
Test("valid ipv4") <- ValidIpv4("192.168.1.1")
```

### Combining Regex with findall (Meta-Predicate)

Use the [`findall` meta-predicate](meta_predicates.md) to collect all regex matches into a list:

```clausal
-import_module(regex)

AllNumbers(TEXT, NUMBERS) <- (
    findall(
        NUM,
        regex.findall(r"\d+", TEXT, NUM),
        NUMBERS
    )
)

Test("all numbers") <- (
    AllNumbers("a1b23c456", NUMS),
    NUMS == ["1", "23", "456"]
)
```

---

## Pattern Precompilation

The goal expansion pass (`clausal/logic/goal_expansion.py`) detects string-literal patterns and precompiles them to `re.Pattern` objects at load time. This avoids recompiling the regex on every call.

---

## Dynamic Patterns

Patterns can be variables or f-strings — they are compiled at runtime:

```clausal
-import_from(regex, [Match])

MatchPrefix(PREFIX, TEXT) <- (
    PAT is f"^{PREFIX}",
    Match(PAT, TEXT)
)

Test("dynamic prefix") <- MatchPrefix("hello", "hello world")
Test("dynamic prefix fail") <- (not MatchPrefix("bye", "hello world"))
```

Dynamic patterns are compiled at runtime (no precompilation).

---

## Gotchas

- **Match is anchored at start**; Search is not. Use `Search` when you want to find a pattern anywhere in the string.
- **Auto-binding requires ALLCAPS or leading-underscore** group names. A group named `(?P<year>...)` (lowercase, no leading underscore) will NOT auto-bind — use `(?P<YEAR>...)` instead.
- **Regex findall vs [meta-predicate findall](meta_predicates.md)**: The regex `findall/3` is nondeterministic (yields one match at a time). The meta-predicate `findall/3` collects all solutions into a list. Use qualified names (`regex.findall`) if both are imported.
- **Dynamic patterns skip precompilation**. For hot loops, prefer string literals so the pattern is compiled once at load time.

---

??? info "Test coverage"

    Tests are in `tests/test_regex.py` (93 tests).

    - **Match/2**: digits, anchoring, email, empty, unicode
    - **Match/3**: named groups, positional groups, no match
    - **Auto-binding**: ALLCAPS groups, leading-underscore groups
    - **Search/2,3**: unanchored search, group extraction
    - **Replace/4**: whitespace, digit removal, backreferences
    - **Split/3**: comma, whitespace
    - **findall/3**: multiple matches, no matches
    - **Edge cases**: dynamic patterns, pattern variables
    - **Fixture integration**: `regex_basic.clausal` (25 tests), `regex_autobind.clausal` (17 tests)

---

*See also: [Term & Goal Expansion](term_expansion.md) — how auto-binding and pattern precompilation work under the hood.*
*See also: [Module System](import.md) — importing the regex module.*
