# Regex Module

The `regex` standard library module provides regular expression predicates for `.clausal` files. It wraps Python's `re` module with a relational interface, including auto-binding of named capture groups to logic variables.

Everything on this page is **text**: a pattern is text, a subject is text, and
a captured group comes back as a **string** — never an atom. Every example
below therefore opens with [`-double_quotes(chars)`](directives.md), so its
`"…"` literals *are* strings and compare equal to what the predicates answer.
Without that directive a module's `"2026"` is the atom `'2026'`, which will
not unify with the string a group binds; see
[Type Checking](type_checking.md#the-atom--string--list-table).

---

## Quick Example

```clausal
-double_quotes(chars)
-allow_singletons
# Named-group auto-bind: the second occurrence of YEAR/MONTH lives
# inside the pattern STRING, invisible to the singleton counter's
# AST-Name check — a known, documented lint gap for this pattern.
-import_from(regex, [match])

parse_date(DATE, YEAR, MONTH) <- (
    match(r"(?P<YEAR>\d{4})-(?P<MONTH>\d{2})", DATE)
)

test("parse date") <- (
    parse_date("2026-03", YEAR, MONTH),
    YEAR == "2026",
    MONTH == "03"
)
```

The named groups `YEAR` and `MONTH` are automatically bound to the clause variables of the same name — no explicit group extraction needed.

---

## Import

```clausal
--8<-- "tests/fixtures/docs/regex_sigs.txt:import_from"
```

Or via [module import](import.md):

```clausal
--8<-- "tests/fixtures/docs/regex_sigs.txt:import_module"
```

---

## Predicates

### match/2 — Boolean match

`match(Pattern, String)` — succeeds if Pattern matches String (anchored at start):

```clausal
-double_quotes(chars)
-import_from(regex, [match])

test("match digits") <- match(r"\d+", "123")
test("match fails") <- (not match(r"\d+", "abc"))
test("match anchored") <- (not match(r"\d+$", "123abc"))
```

### match/3 — Group Extraction

`match(Pattern, String, Groups)` — unifies Groups with a dict of named groups (or tuple of positional groups):

```clausal
-double_quotes(chars)
-import_from(regex, [match])

test("named groups") <- (
    match(r"(?P<year>\d{4})-(?P<month>\d{2})", "2026-03", G),
    YEAR is ++G["year"],
    MONTH is ++G["month"],
    YEAR == "2026",
    MONTH == "03"
)

test("positional groups") <- (
    match(r"(\d+)-(\d+)", "42-99", G),
    G == ("42", "99")
)
```

**Mixed named + positional groups:** when a pattern mixes named and unnamed
groups, `Groups` is a dict keyed by the named-group names, with each *unnamed*
group added under its 1-based positional index (an integer key). For
`r"(?P<A>\d+)-(\d+)"` against `"1-2"`, `Groups` is `{"A": "1", 2: "2"}`.

> **Gotcha — unmatched optional named group binds `None`.** An optional named
> group that does not participate in the match (e.g. `r"(?P<TAG>\d+)?x"`
> against `"x"`) auto-binds Python `None`, mirroring `Match.groupdict()`. This
> differs from SWI, which omits the key entirely.

### search/2, search/3

Like match but unanchored — finds the pattern anywhere in the string:

```clausal
-double_quotes(chars)
-import_from(regex, [search])

test("search found") <- search(r"\d+", "abc123def")
test("search not found") <- (not search(r"\d+", "abcdef"))

test("search groups") <- (
    search(r"(?P<key>\w+)=(?P<val>\w+)", "foo bar=baz", G),
    KEY is ++G["key"],
    VAL is ++G["val"],
    KEY == "bar",
    VAL == "baz"
)
```

### replace/4

`replace(Pattern, Replacement, String, Result)` — regex substitution:

```clausal
-double_quotes(chars)
-import_from(regex, [replace])

test("collapse spaces") <- (replace(r"\s+", " ", "a  b   c", R), R == "a b c")
test("remove digits") <- (replace(r"\d+", "", "a1b2c3", R), R == "abc")
```

### split/3

`split(Pattern, String, Fragments)` — split string by pattern:

```clausal
-double_quotes(chars)
-import_from(regex, [split])

test("split csv") <- (split(r",\s*", "a, b, c", F), F == ["a", "b", "c"])
test("split whitespace") <- (split(r"\s+", "x y z", F), F == ["x", "y", "z"])
```

### findall/3 (Regex)

`findall(Pattern, String, match)` — nondeterministic; succeeds once for each non-overlapping match:

```clausal
-double_quotes(chars)
-import_from(regex, [findall])

test("findall first") <- (findall(r"\d+", "a1b23c456", D), D == "1")
```

Fails if no matches are found. Following the `re.findall` oracle, the match
value is the whole-match string when the pattern has no capturing group, the
group's bare string when it has exactly one group, and a tuple of group
strings when it has two or more:

```clausal
-double_quotes(chars)
-import_from(regex, [findall])

test("findall single group is a string") <- (
    findall(r"(\d)x", "1x2x", D), D == "1"
)
```

---

## Auto-Binding

Named groups using ALLCAPS or leading-underscore names are automatically bound to corresponding clause [variables](syntax.md) at compile time (via [goal expansion](term_expansion.md)). This is the key feature that makes regex feel native in Clausal.

### ALLCAPS Groups

```clausal
-double_quotes(chars)
-allow_singletons
# Named-group auto-bind: the head params' second occurrence lives
# inside the pattern STRING, invisible to the singleton counter.
-import_from(regex, [match])

parse_email(EMAIL, USER, DOMAIN) <- (
    match(r"(?P<USER>[^@]+)@(?P<DOMAIN>.+)", EMAIL)
)

test("parse email") <- (
    parse_email("alice@example.com", USER, DOMAIN),
    USER == "alice",
    DOMAIN == "example.com"
)
```

### Leading-Underscore Groups

```clausal
-double_quotes(chars)
-allow_singletons
# Named-group auto-bind: _port's second occurrence lives inside the
# pattern STRING, invisible to the singleton counter.
-import_from(regex, [search])

extract_port(URL, _port) <- (
    search(r":(?P<_port>\d+)", URL)
)

test("extract port") <- (
    extract_port("http://localhost:8080/api", PORT),
    PORT == "8080"
)
```

### How It Works

The goal expansion pass detects `(?P<NAME>...)` patterns where NAME matches a variable in scope. It rewrites the match/2 call into match/3 plus unification:

```clausal
--8<-- "tests/fixtures/docs/regex_sigs.txt:expansion_example"
```

You never see the expanded form — just use the variable names in your pattern.

---

## Practical Patterns

### Log Parsing

```clausal
-double_quotes(chars)
-allow_singletons
# Named-group auto-bind: LEVEL/MESSAGE's second occurrence lives inside
# the pattern STRING, invisible to the singleton counter.
-import_from(regex, [match])

parse_log_line(LINE, LEVEL, MESSAGE) <- (
    match(r"(?P<LEVEL>INFO|WARN|ERROR)\s+(?P<MESSAGE>.+)", LINE)
)

is_error(LINE) <- match(r"^ERROR", LINE)

test("parse log info") <- (
    parse_log_line("INFO system started", LEVEL, MSG),
    LEVEL == "INFO",
    MSG == "system started"
)
test("is error") <- is_error("ERROR disk full")
test("not error") <- (not is_error("INFO ok"))
```

### CSV Field Extraction

```clausal
-double_quotes(chars)
-import_from(regex, [split])

parse_csv(LINE, FIELDS) <- split(r",\s*", LINE, FIELDS)

test("parse csv") <- (
    parse_csv("a, b, c", FIELDS),
    FIELDS == ["a", "b", "c"]
)
```

### URL Routing

```clausal
-double_quotes(chars)
-allow_singletons
# Named-group auto-bind: USER_ID's second occurrence lives inside the
# pattern STRING, invisible to the singleton counter.
-import_from(regex, [match])

route_user(PATH, USER_ID) <- (
    match(r"/users/(?P<USER_ID>\d+)", PATH)
)

route_api(PATH) <- match(r"^/api/v\d+/", PATH)

test("route user") <- (route_user("/users/42", UID), UID == "42")
test("route api") <- route_api("/api/v2/data")
test("not api") <- (not route_api("/users/1"))
```

### Data Validation

```clausal
-double_quotes(chars)
-import_from(regex, [match])

valid_email(S) <- match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", S)
valid_ipv4(S) <- match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", S)

test("valid email") <- valid_email("alice@example.com")
test("invalid email") <- (not valid_email("not-an-email"))
test("valid ipv4") <- valid_ipv4("192.168.1.1")
```

### Combining Regex with findall (Meta-Predicate)

Use the [`findall` meta-predicate](meta_predicates.md) to collect all regex matches into a list:

```clausal
-double_quotes(chars)
-import_module(regex)

all_numbers(TEXT, NUMBERS) <- (
    findall(
        NUM,
        regex.findall(r"\d+", TEXT, NUM),
        NUMBERS
    )
)

test("all numbers") <- (
    all_numbers("a1b23c456", NUMS),
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
-double_quotes(chars)
-import_from(regex, [match])

match_prefix(PREFIX, TEXT) <- (
    PAT is f"^{PREFIX}",
    match(PAT, TEXT)
)

test("dynamic prefix") <- match_prefix("hello", "hello world")
test("dynamic prefix fail") <- (not match_prefix("bye", "hello world"))
```

Dynamic patterns are compiled at runtime (no precompilation). Named-group
auto-binding still applies: a group whose name (ALLCAPS or leading-underscore)
matches an in-scope clause variable is bound at runtime when it participates in
the match. Because the group names are unknown until the goal runs, a variable
is only bound when its matching group is actually present — otherwise it is
left untouched. This is one deliberate divergence from static (string-literal)
patterns, where an optional group that did not participate in the match binds
its variable to Python `None`: in dynamic mode every in-scope clause variable
is a binding candidate, so a non-participating group leaves the variable
unbound rather than clobbering it with `None`.

```clausal
-double_quotes(chars)
-allow_singletons
# Dynamic-pattern auto-bind: YEAR's binding happens at runtime from the
# pattern's group name, which isn't visible to the singleton counter
# (the pattern itself is a variable here, not a literal).
-import_from(regex, [match])

find_year(PAT, S, YEAR) <- match(PAT, S)

test("dynamic autobind") <- find_year(r"(?P<YEAR>\d+)", "2026", "2026")
```

---

## Gotchas

- **match is anchored at start**; search is not. Use `search` when you want to find a pattern anywhere in the string.
- **Auto-binding requires ALLCAPS or leading-underscore** group names. A group named `(?P<year>...)` (lowercase, no leading underscore) will NOT auto-bind — use `(?P<YEAR>...)` instead.
- **Regex findall vs [meta-predicate findall](meta_predicates.md)**: The regex `findall/3` is nondeterministic (yields one match at a time). The meta-predicate `findall/3` collects all solutions into a list. Use qualified names (`regex.findall`) if both are imported.
- **Dynamic patterns skip precompilation**. For hot loops, prefer string literals so the pattern is compiled once at load time.

---

??? info "Test coverage"

    Tests are in `tests/test_regex.py` (93 tests).

    - **match/2**: digits, anchoring, email, empty, unicode
    - **match/3**: named groups, positional groups, no match
    - **Auto-binding**: ALLCAPS groups, leading-underscore groups
    - **search/2,3**: unanchored search, group extraction
    - **replace/4**: whitespace, digit removal, backreferences
    - **split/3**: comma, whitespace
    - **findall/3**: multiple matches, no matches
    - **Edge cases**: dynamic patterns, pattern variables
    - **Fixture integration**: `regex_basic.clausal` (25 tests), `regex_autobind.clausal` (17 tests)

---

*See also: [Term & Goal Expansion](term_expansion.md) — how auto-binding and pattern precompilation work under the hood.*
*See also: [Module System](import.md) — importing the regex module.*
