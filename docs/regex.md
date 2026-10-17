# Regex Module

The regex standard library module provides regular expression predicates. It wraps Python's `re` module with a relational interface. [Clausal Prolog](clausal_prolog.md) (`.clausal`), the ISO-syntax surface the examples on this page use, imports it through its facade `library(re)`. The [seam](syntax.md) names the same module `regex`, and in the seam alone named capture groups also bind logic variables automatically (see [Auto-Binding](#auto-binding)).

Everything on this page is **text**: a pattern is text, a subject is text, and
a captured group comes back as a **string** — never an atom. A `"…"`
literal is a string by default, so it compares equal to what the predicates
answer. The examples below also state
`:- set_prolog_flag(double_quotes, chars).` explicitly; under the temporary
`double_quotes` value `atom` a module's `"2026"` would be the atom
`'2026'`, which does not unify with the string a group binds; see
[Type Checking](type_checking.md#the-atom--string--list-table).

!!! note "Backslashes in patterns"

    Clausal Prolog has no raw strings. A double-quoted literal follows ISO
    escapes, so each regex backslash is written twice: the seam's
    `r"\d+"` is `"\\d+"` here. A single `"\d+"` is a syntax error
    (`invalid escape sequence '\d'`).

---

## Quick Example

```clausal
:- set_prolog_flag(double_quotes, chars).
:- use_module(library(re), [match/3]).

parse_date(DATE, YEAR, MONTH) :-
    match("(?P<year>\\d{4})-(?P<month>\\d{2})", DATE, G),
    get(G, year, YEAR),
    get(G, month, MONTH).

test("parse date") :-
    parse_date("2026-03", YEAR, MONTH),
    YEAR == "2026",
    MONTH == "03".
```

`match/3` answers the named groups as a dict, and `get/3` reads each group by
its name. (In the seam, a group named like a clause variable binds that
variable directly; see [Auto-Binding](#auto-binding).)

---

## Import

```text
--8<-- "tests/fixtures/docs/regex_sigs.txt:import_from"
```

Or import the whole module and qualify each call with the module name `re`:

```text
--8<-- "tests/fixtures/docs/regex_sigs.txt:import_module"
```

The regex `findall/3` is not in either list: in a `.clausal` file the goal
`findall(P, S, M)`, qualified as `re:findall(P, S, M)` too, is the
[`findall/3` meta-predicate](meta_predicates.md), so the regex `findall/3` is
reachable only from the seam (see [findall/3 (Regex)](#findall3-regex)).

---

## Predicates

### match/2 — Boolean match

`match(Pattern, String)` — succeeds if Pattern matches String (anchored at start):

```clausal
:- set_prolog_flag(double_quotes, chars).
:- use_module(library(re), [match/2]).

test("match digits") :-
    match("\\d+", "123").

test("match fails") :-
    \+ match("\\d+", "abc").

test("match anchored") :-
    \+ match("\\d+$", "123abc").
```

### match/3 — Group Extraction

`match(Pattern, String, Groups)` — unifies Groups with a dict of named groups (or tuple of positional groups). Read a named group with `get/3` (see [Dicts](dicts_sets.md)):

```clausal
:- set_prolog_flag(double_quotes, chars).
:- use_module(library(re), [match/3]).

test("named groups") :-
    match("(?P<year>\\d{4})-(?P<month>\\d{2})", "2026-03", G),
    get(G, year, YEAR),
    get(G, month, MONTH),
    YEAR == "2026",
    MONTH == "03".
```

With positional groups only, `Groups` is a Python tuple. Clausal Prolog has no
term that unifies with it or takes it apart (`G = (A, B)`, `G = [A, B]`,
`G =.. L`, `arg/3` and `functor/3` all fail on it), so this example is the
seam spelling:

```seam
-double_quotes(chars)
-import_from(regex, [match])

test("positional groups") <- (
    match(r"(\d+)-(\d+)", "42-99", G),
    G == ("42", "99")
)
```

**Mixed named + positional groups:** when a pattern mixes named and unnamed
groups, `Groups` is a dict keyed by the named-group names, with each *unnamed*
group added under its 1-based positional index (an integer key). For
`"(?P<A>\\d+)-(\\d+)"` against `"1-2"`, `Groups` is the dict whose pairs are
`['A'-"1", 2-"2"]` — a group name is an atom key, a captured value a string:

```clausal
:- set_prolog_flag(double_quotes, chars).
:- use_module(library(re), [match/3]).

test("mixed groups") :-
    match("(?P<A>\\d+)-(\\d+)", "1-2", G),
    dict_pairs(G, PAIRS),
    PAIRS == ['A'-"1", 2-"2"].
```

> **Gotcha — an unmatched optional named group is Python `None`.** An optional
> named group that does not participate in the match (e.g.
> `"(?P<tag>\\d+)?x"` against `"x"`) is Python `None` in `Groups`, mirroring
> `Match.groupdict()`; it is neither an atom nor an unbound variable. In the
> seam, auto-binding such a group binds `None` too. This differs from SWI,
> which omits the key entirely.

### search/2, search/3

Like match but unanchored — finds the pattern anywhere in the string:

```clausal
:- set_prolog_flag(double_quotes, chars).
:- use_module(library(re), [search/2, search/3]).

test("search found") :-
    search("\\d+", "abc123def").

test("search not found") :-
    \+ search("\\d+", "abcdef").

test("search groups") :-
    search("(?P<key>\\w+)=(?P<val>\\w+)", "foo bar=baz", G),
    get(G, key, KEY),
    get(G, val, VAL),
    KEY == "bar",
    VAL == "baz".
```

### replace/4

`replace(Pattern, Replacement, String, Result)` — regex substitution:

```clausal
:- set_prolog_flag(double_quotes, chars).
:- use_module(library(re), [replace/4]).

test("collapse spaces") :-
    replace("\\s+", " ", "a  b   c", R),
    R == "a b c".

test("remove digits") :-
    replace("\\d+", "", "a1b2c3", R),
    R == "abc".
```

### split/3

`split(Pattern, String, Fragments)` — split string by pattern:

```clausal
:- set_prolog_flag(double_quotes, chars).
:- use_module(library(re), [split/3]).

test("split csv") :-
    split(",\\s*", "a, b, c", F),
    F == ["a", "b", "c"].

test("split whitespace") :-
    split("\\s+", "x y z", F),
    F == ["x", "y", "z"].
```

### findall/3 (Regex)

`findall(Pattern, String, Match)` — nondeterministic; succeeds once for each non-overlapping match.

This predicate is **seam-only**. In a `.clausal` file the goal `findall(P, S, M)`
is always the [`findall/3` meta-predicate](meta_predicates.md), and so is the
qualified `re:findall(P, S, M)`; `call(re:findall, P, S, M)` is refused, because
at run time `re` names Python's `re` module
(`permission_error(access, python_module, re)`). The examples are the seam
spelling:

```seam
-double_quotes(chars)
-import_from(regex, [findall])

test("findall first") <- (findall(r"\d+", "a1b23c456", D), D == "1")
```

Fails if no matches are found. Following the `re.findall` oracle, the match
value is the whole-match string when the pattern has no capturing group, the
group's bare string when it has exactly one group, and a tuple of group
strings when it has two or more:

```seam
-double_quotes(chars)
-import_from(regex, [findall])

test("findall single group is a string") <- (
    findall(r"(\d)x", "1x2x", D), D == "1"
)
```

---

## Auto-Binding

**Auto-binding is seam-only.** In the seam, named groups whose names are spelled like clause [variables](syntax.md) — capital-initial (`YEAR`, `Year`) or leading-underscore (`_rest`) — are automatically bound to the same-named variable at compile time (via [goal expansion](term_expansion.md)). This is the key feature that makes regex feel native in seam source. A lowercase group name is an atom spelling, so it stays regex-only and binds nothing.

A `.clausal` file does not auto-bind: a group named `YEAR` leaves the clause
variable `YEAR` unbound, for literal and dynamic patterns alike. Use
`match/3` or `search/3` and read each group with `get/3`, as in the
[Quick Example](#quick-example). The examples in this section are the seam
spelling.

### Capital-Initial Groups

```seam
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

```seam
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

The seam's goal expansion pass detects `(?P<NAME>...)` patterns where NAME matches a variable in scope. It rewrites the match/2 call into match/3 plus unification (seam syntax):

```seam
--8<-- "tests/fixtures/docs/regex_sigs.txt:expansion_example"
```

You never see the expanded form — just use the variable names in your pattern.

---

## Practical Patterns

### Log Parsing

```clausal
:- set_prolog_flag(double_quotes, chars).
:- use_module(library(re), [match/2, match/3]).

parse_log_line(LINE, LEVEL, MESSAGE) :-
    match("(?P<level>INFO|WARN|ERROR)\\s+(?P<message>.+)", LINE, G),
    get(G, level, LEVEL),
    get(G, message, MESSAGE).

is_error(LINE) :-
    match("^ERROR", LINE).

test("parse log info") :-
    parse_log_line("INFO system started", LEVEL, MSG),
    LEVEL == "INFO",
    MSG == "system started".

test("is error") :-
    is_error("ERROR disk full").

test("not error") :-
    \+ is_error("INFO ok").
```

### CSV Field Extraction

```clausal
:- set_prolog_flag(double_quotes, chars).
:- use_module(library(re), [split/3]).

parse_csv(LINE, FIELDS) :-
    split(",\\s*", LINE, FIELDS).

test("parse csv") :-
    parse_csv("a, b, c", FIELDS),
    FIELDS == ["a", "b", "c"].
```

### URL Routing

```clausal
:- set_prolog_flag(double_quotes, chars).
:- use_module(library(re), [match/2, match/3]).

route_user(PATH, USER_ID) :-
    match("/users/(?P<user_id>\\d+)", PATH, G),
    get(G, user_id, USER_ID).

route_api(PATH) :-
    match("^/api/v\\d+/", PATH).

test("route user") :-
    route_user("/users/42", UID),
    UID == "42".

test("route api") :-
    route_api("/api/v2/data").

test("not api") :-
    \+ route_api("/users/1").
```

### Data Validation

```clausal
:- set_prolog_flag(double_quotes, chars).
:- use_module(library(re), [match/2]).

valid_email(S) :-
    match("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", S).

valid_ipv4(S) :-
    match("^\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}$", S).

test("valid email") :-
    valid_email("alice@example.com").

test("invalid email") :-
    \+ valid_email("not-an-email").

test("valid ipv4") :-
    valid_ipv4("192.168.1.1").
```

### Combining Regex with findall (Meta-Predicate)

In the seam, the [`findall` meta-predicate](meta_predicates.md) collects all
regex matches into a list. It needs the regex `findall/3`, which `.clausal`
cannot reach (see [findall/3 (Regex)](#findall3-regex)), so this is the seam
spelling:

```seam
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

Patterns can be variables — they are compiled at runtime. A string is a list
of characters, so `append/3` builds a pattern (the seam can also use an
f-string, `f"^{PREFIX}"`):

```clausal
:- set_prolog_flag(double_quotes, chars).
:- use_module(library(re), [match/2]).

match_prefix(PREFIX, TEXT) :-
    append("^", PREFIX, PAT),
    match(PAT, TEXT).

test("dynamic prefix") :-
    match_prefix("hello", "hello world").

test("dynamic prefix fail") :-
    \+ match_prefix("bye", "hello world").
```

Dynamic patterns are compiled at runtime (no precompilation). In the seam,
named-group auto-binding still applies: a group whose name (capital-initial or leading-underscore)
matches an in-scope clause variable is bound at runtime when it participates in
the match. Because the group names are unknown until the goal runs, a variable
is only bound when its matching group is actually present — otherwise it is
left untouched. This is one deliberate divergence from static (string-literal)
patterns, where an optional group that did not participate in the match binds
its variable to Python `None`: in dynamic mode every in-scope clause variable
is a binding candidate, so a non-participating group leaves the variable
unbound rather than clobbering it with `None`. Like all auto-binding, this is
seam-only; the example is the seam spelling:

```seam
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
- **Double every backslash** in a `.clausal` pattern literal: `"\\d+"`, not `"\d+"`.
- **Auto-binding is seam-only**, and requires a variable-shaped group name there: capital-initial (`(?P<YEAR>...)`, `(?P<Year>...)`) or leading-underscore (`(?P<_rest>...)`). A group named `(?P<year>...)` (lowercase) will NOT auto-bind. In `.clausal`, read groups with `match/3` and `get/3`.
- **Regex findall vs [meta-predicate findall](meta_predicates.md)**: The regex `findall/3` is nondeterministic (yields one match at a time). The meta-predicate `findall/3` collects all solutions into a list. In the seam, use qualified names (`regex.findall`) if both are imported; in `.clausal`, `findall/3` is always the meta-predicate.
- **Dynamic patterns skip precompilation**. For hot loops, prefer string literals so the pattern is compiled once at load time.

---

??? info "Test coverage"

    Tests are in `tests/test_regex.py` (93 tests).

    - **match/2**: digits, anchoring, email, empty, unicode
    - **match/3**: named groups, positional groups, no match
    - **Auto-binding**: ALLCAPS groups, TitleCase groups, leading-underscore groups
    - **search/2,3**: unanchored search, group extraction
    - **replace/4**: whitespace, digit removal, backreferences
    - **split/3**: comma, whitespace
    - **findall/3**: multiple matches, no matches
    - **Edge cases**: dynamic patterns, pattern variables
    - **Fixture integration**: `regex_basic.seam` (25 tests), `regex_autobind.seam` (17 tests)

---

*See also: [Term & Goal Expansion](term_expansion.md) — how auto-binding and pattern precompilation work under the hood.*
*See also: [Module System](import.md) — importing the regex module.*
