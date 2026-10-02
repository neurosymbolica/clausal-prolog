"""Tests for regex integration — API design exploration.

Naming: match, search, findall, replace, split — qualified as re.match etc.
when imported via ``-import_module(re)``.

Two binding modes:

EXPLICIT (match/3) — works without goal expansion:
    match(r"(?P<year>\\d{4})-(?P<month>\\d{2})", S, G) and
    YEAR is ++G["year"]
    (lowercase group names → not logic variables → no auto-binding)

COMPACT (match/2 with named groups) — requires goal expansion:
    match(r"(?P<YEAR>\\d{4})-(?P<MONTH>\\d{2})", S)
    # YEAR and MONTH auto-bound because ALLCAPS = logic variable

Auto-binding convention:
    Only named groups whose names meet the logic variable convention
    (ALLCAPS or _leading_underscore) are auto-bound. This gives the user
    explicit control:
        (?P<YEAR>\\d{4})   → auto-binds YEAR   (ALLCAPS)
        (?P<_rest>\\w+)    → auto-binds _rest   (leading underscore)
        (?P<year>\\d{4})   → NOT auto-bound    (lowercase, not a logic var)
        (?P<internal>\\w+) → NOT auto-bound    (just a regex group name)

    This means you can have named groups for regex purposes (backreferences,
    readability) without them leaking into the logic variable namespace.

Goal expansion for the compact form:
    1. At compile time, re.compile(pattern).groupindex extracts group names
       (works without running the regex — just parsing the pattern)
    2. Filters to groups matching logic variable naming convention
    3. Pre-compiles regex into module init item (ModuleExpansionState)
    4. Expands the goal to use the compiled object + unify each matching group
    5. Validates pattern at compile time (bad regex → compile error)
    6. For dynamic patterns (f-strings), skips everything — use match/3
"""

from __future__ import annotations

import pytest

from clausal.logic.solve import call, query
from clausal.logic.variables import Var, deref, Trail
from clausal.logic.cells import chars
from clausal.import_hook import _load_module
from tests._suffix import SEAM, seam_path


# ── Helpers ──────────────────────────────────────────────────────────────────

# The inline modules below MEAN STRINGS by every ``"..."`` they write:
# regex patterns and subject text (THE FLIP, migration rule (c)).
_REGEX_IMPORT = ('-double_quotes(chars)\n'
                 '-import_from(py.re, [match, search, replace, split, findall])\n')


def _load(name, src_text, tmp_path):
    """write a .clausal file and load it."""
    p = tmp_path / f"{name}{SEAM}"
    p.write_text(_REGEX_IMPORT + src_text)
    mod = _load_module(name, str(p))
    return mod.__dict__["$module"]


def _succeeds(functor, *args, module):
    for _ in call(functor, *args, module=module):
        return True
    return False


def _first(functor, *args, module, out_index=-1):
    """Call with a Var at out_index, return first deref'd result."""
    v = Var()
    full = list(args)
    if out_index == -1:
        full.append(v)
    else:
        full.insert(out_index, v)
    for _ in call(functor, *full, module=module):
        return deref(v)
    return None


def _all(functor, *args, module, out_index=-1):
    """Call with a Var at out_index, return all deref'd results."""
    v = Var()
    full = list(args)
    if out_index == -1:
        full.append(v)
    else:
        full.insert(out_index, v)
    results = []
    for _ in call(functor, *full, module=module):
        results.append(deref(v))
    return results


def _call_multi(functor, *args, module, out_names):
    """Call with multiple output Vars, return list of result dicts."""
    vs = {name: Var() for name in out_names}
    full = list(args) + [vs[n] for n in out_names]
    results = []
    for _ in call(functor, *full, module=module):
        results.append({n: deref(vs[n]) for n in out_names})
    return results


# ══════════════════════════════════════════════════════════════════════════════
# TIER 1: Boolean match — match/2 (Pattern, String) → succeeds/fails
# ══════════════════════════════════════════════════════════════════════════════

class TestMatchBoolean:
    """match/2 with no auto-bindable groups: pattern + string, boolean test."""

    def test_digits_match(self, tmp_path):
        # nv
        mod = _load("rm1", r"""
is_digits(S) <- match(r"\d+", S)
""", tmp_path)
        assert _succeeds("is_digits", chars("123"), module=mod)

    def test_digits_no_match(self, tmp_path):
        # nv
        mod = _load("rm2", r"""
is_digits(S) <- match(r"\d+", S)
""", tmp_path)
        assert not _succeeds("is_digits", chars("abc"), module=mod)

    def test_anchored_at_start(self, tmp_path):
        """match is anchored at start (like Python re.match)."""
        # nv
        mod = _load("rm3", r"""
starts_digit(S) <- match(r"\d+", S)
""", tmp_path)
        assert not _succeeds("starts_digit", chars("abc123"), module=mod)
        assert _succeeds("starts_digit", chars("123abc"), module=mod)

    def test_fullmatch_via_dollar(self, tmp_path):
        # nv
        mod = _load("rm4", r"""
all_digits(S) <- match(r"\d+$", S)
""", tmp_path)
        assert _succeeds("all_digits", chars("123"), module=mod)
        assert not _succeeds("all_digits", chars("123abc"), module=mod)

    def test_email_validation(self, tmp_path):
        # nv
        mod = _load("rm5", r"""
is_email(S) <- match(r"[^@]+@[^@]+\.[^@]+", S)
""", tmp_path)
        assert _succeeds("is_email", chars("user@example.com"), module=mod)
        assert not _succeeds("is_email", chars("not-an-email"), module=mod)


# ══════════════════════════════════════════════════════════════════════════════
# TIER 2: Explicit group extraction — match/3 (Pattern, String, GroupsDict)
#
# Works without goal expansion. Use lowercase group names (not logic vars)
# so they stay in the regex domain. Extract via ++G["name"].
# ══════════════════════════════════════════════════════════════════════════════

class TestMatchExplicitGroups:
    """match/3: returns groups dict for manual extraction via ++."""

    def test_named_groups(self, tmp_path):
        # nv
        mod = _load("rg1", r"""
parse_date(S, YEAR, MONTH, DAY) <- (
    match(r"(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})", S, G) and
    YEAR is ++G["year"] and
    MONTH is ++G["month"] and
    DAY is ++G["day"]
)
""", tmp_path)
        results = _call_multi("parse_date", chars("2026-03-16"), module=mod,
                              out_names=["y", "m", "d"])
        assert results == [{"y": chars("2026"), "m": chars("03"), "d": chars("16")}]

    def test_positional_groups(self, tmp_path):
        """No named groups → GroupsDict is a tuple of positional captures."""
        # nv
        mod = _load("rg2", r"""
parse_pair(S, A, B) <- (
    match(r"(\d+)-(\d+)", S, G) and
    A is ++G[0] and
    B is ++G[1]
)
""", tmp_path)
        results = _call_multi("parse_pair", chars("42-99"), module=mod,
                              out_names=["a", "b"])
        assert results == [{"a": chars("42"), "b": chars("99")}]

    def test_no_match_fails(self, tmp_path):
        # nv
        mod = _load("rg3", r"""
try_parse(S, G) <- match(r"(?P<x>\d+)", S, G)
""", tmp_path)
        assert _first("try_parse", chars("abc"), module=mod) is None

    def test_mixed_named_positional(self, tmp_path):
        """Named groups produce a dict; positional groups not in the dict."""
        # nv
        mod = _load("rg4", r"""
parse_ver(S, MAJOR) <- (
    match(r"v(?P<major>\d+)\.\d+", S, G) and
    MAJOR is ++G["major"]
)
""", tmp_path)
        assert _first("parse_ver", chars("v3.14"), module=mod) == chars("3")


# ══════════════════════════════════════════════════════════════════════════════
# TIER 3: COMPACT auto-binding — match/2 with ALLCAPS group names
#
# Convention: ALLCAPS group name → auto-unify with same-named logic variable.
# lowercase group name → ignored by auto-binding (regex-only group).
#
# Goal expansion rewrites:
#     match(r"(?P<YEAR>\d{4})-(?P<MONTH>\d{2})", S)
# into (conceptually):
#     _re_0 = re.compile(r"...")              ← module init item
#     _m = _re_0.match(deref(S))             ← at runtime
#     if _m is None: fail
#     unify(YEAR, _m.group("YEAR"), trail)   ← generated per ALLCAPS group
#     unify(MONTH, _m.group("MONTH"), trail)
# ══════════════════════════════════════════════════════════════════════════════

class TestMatchAutoBinding:
    """match/2 with ALLCAPS named groups: auto-bind to clause variables."""

    def test_basic_auto_bind(self, tmp_path):
        """ALLCAPS group names auto-bind to same-named logic variables."""
        # nv
        mod = _load("ab1", r"""
parse_date(S, YEAR, MONTH, DAY) <- match(r"(?P<YEAR>\d{4})-(?P<MONTH>\d{2})-(?P<DAY>\d{2})", S)
""", tmp_path)
        results = _call_multi("parse_date", chars("2026-03-16"), module=mod,
                              out_names=["y", "m", "d"])
        assert results == [{"y": chars("2026"), "m": chars("03"), "d": chars("16")}]

    def test_auto_bind_no_match_fails(self, tmp_path):
        """If the regex doesn't match, the whole goal fails."""
        # nv
        mod = _load("ab2", r"""
parse_date(S, YEAR, MONTH, DAY) <- match(r"(?P<YEAR>\d{4})-(?P<MONTH>\d{2})-(?P<DAY>\d{2})", S)
""", tmp_path)
        assert not _succeeds("parse_date", chars("not-a-date"),
                             Var(), Var(), Var(), module=mod)

    def test_auto_bind_constrains_input(self, tmp_path):
        """If a group variable is already bound, auto-binding acts as a test."""
        # nv
        mod = _load("ab3", r"""
is_year(S, YEAR) <- match(r"(?P<YEAR>\d{4})-\d{2}-\d{2}", S)
""", tmp_path)
        # YEAR is output — gets bound
        assert _first("is_year", chars("2026-03-16"), module=mod) == chars("2026")
        # YEAR is input — constrains (should succeed when correct)
        assert _succeeds("is_year", chars("2026-03-16"), chars("2026"), module=mod)
        # YEAR is input — constrains (should fail when wrong)
        assert not _succeeds("is_year", chars("2026-03-16"), chars("1999"), module=mod)

    def test_auto_bind_search(self, tmp_path):
        """Auto-binding also works with search (unanchored)."""
        # nv
        mod = _load("ab4", r"""
find_tag(TEXT, TAG) <- search(r"<(?P<TAG>\w+)>", TEXT)
""", tmp_path)
        assert _first("find_tag", chars("text <bold> more"), module=mod) == chars("bold")

    def test_auto_bind_single_group(self, tmp_path):
        # nv
        mod = _load("ab5", r"""
first_word(S, WORD) <- match(r"(?P<WORD>\w+)", S)
""", tmp_path)
        assert _first("first_word", chars("hello world"), module=mod) == chars("hello")

    def test_auto_bind_many_groups(self, tmp_path):
        # nv
        mod = _load("ab6", r"""
parse_url(S, SCHEME, HOST, PORT, PATH) <- match(r"(?P<SCHEME>https?)://(?P<HOST>[^:/]+):(?P<PORT>\d+)(?P<PATH>/\S*)", S)
""", tmp_path)
        results = _call_multi(
            "parse_url", chars("https://example.com:8080/api/v1"), module=mod,
            out_names=["s", "h", "p", "path"])
        assert results == [{"s": chars("https"), "h": chars("example.com"),
                            "p": chars("8080"), "path": chars("/api/v1")}]

    def test_leading_underscore_group(self, tmp_path):
        """_leading_underscore group names also auto-bind."""
        # nv
        mod = _load("ab7", r"""
first_word(S, _word) <- match(r"(?P<_word>\w+)", S)
""", tmp_path)
        assert _first("first_word", chars("hello world"), module=mod) == chars("hello")


# ══════════════════════════════════════════════════════════════════════════════
# TIER 4: Mixed — ALLCAPS groups auto-bind, lowercase groups don't
# ══════════════════════════════════════════════════════════════════════════════

class TestMixedGroupNames:
    """Pattern has both ALLCAPS and lowercase groups. Only ALLCAPS auto-bind."""

    def test_selective_binding(self, tmp_path):
        """Only ALLCAPS groups are auto-bound; lowercase groups are ignored."""
        # nv
        mod = _load("mx1", r"""
parse_log(LINE, LEVEL) <- match(r"(?P<timestamp>\S+)\s+(?P<LEVEL>INFO|WARN|ERROR):\s+(?P<msg>.*)", LINE)
""", tmp_path)
        # LEVEL is auto-bound; timestamp and msg are not (lowercase)
        assert _first("parse_log", chars("2026-03-16 ERROR: disk full"),
                       module=mod) == chars("ERROR")

    def test_lowercase_groups_still_work_in_regex(self, tmp_path):
        """Lowercase groups still function as regex groups (backreferences etc.)
        — they just don't auto-bind to logic variables."""
        # nv
        mod = _load("mx2", r"""
has_repeated_word(S) <- search(r"(?P<word>\w+)\s+(?P=word)", S)
""", tmp_path)
        assert _succeeds("has_repeated_word", chars("the the cat"), module=mod)
        assert not _succeeds("has_repeated_word", chars("the cat sat"), module=mod)

    def test_explicit_extraction_of_lowercase_group(self, tmp_path):
        """Lowercase groups accessible via match/3 + ++ even though not auto-bound."""
        # nv
        mod = _load("mx3", r"""
parse_log(LINE, LEVEL, MSG) <- (
    match(r"(?P<timestamp>\S+)\s+(?P<LEVEL>\w+):\s+(?P<msg>.*)", LINE, G) and
    LEVEL is ++G["LEVEL"] and
    MSG is ++G["msg"]
)
""", tmp_path)
        results = _call_multi("parse_log", chars("2026-03-16 ERROR: disk full"),
                              module=mod, out_names=["level", "msg"])
        assert results == [{"level": chars("ERROR"), "msg": chars("disk full")}]


# ══════════════════════════════════════════════════════════════════════════════
# TIER 5: search and findall
# ══════════════════════════════════════════════════════════════════════════════

class TestSearch:
    """search: like match but unanchored (finds pattern anywhere)."""

    def test_search_finds_in_middle(self, tmp_path):
        # nv
        mod = _load("rs1", r"""
find_digits(S, D) <- search(r"(?P<D>\d+)", S)
""", tmp_path)
        assert _first("find_digits", chars("abc123def"), module=mod) == chars("123")

    def test_search_with_explicit_groups(self, tmp_path):
        # nv
        mod = _load("rs2", r"""
find_kv(S, KEY, VAL) <- (
    search(r"(?P<key>\w+)=(?P<val>\w+)", S, G) and
    KEY is ++G["key"] and
    VAL is ++G["val"]
)
""", tmp_path)
        results = _call_multi("find_kv", chars("foo bar=baz qux"), module=mod,
                              out_names=["k", "v"])
        assert results == [{"k": chars("bar"), "v": chars("baz")}]


class TestFindAll:
    """findall/3: Pattern, String, match → nondeterministic.
    One solution per non-overlapping match. Qualified as re.findall to
    avoid conflict with the meta-predicate findall."""

    def test_findall_strings(self, tmp_path):
        """No groups → each match is a plain string."""
        # nv
        mod = _load("rf1", r"""
digit_run(S, D) <- findall(r"\d+", S, D)
""", tmp_path)
        assert _all("digit_run", chars("a1b23c456"), module=mod) == [chars("1"), chars("23"), chars("456")]

    def test_findall_no_matches(self, tmp_path):
        # nv
        mod = _load("rf2", r"""
digit_run(S, D) <- findall(r"\d+", S, D)
""", tmp_path)
        assert _all("digit_run", chars("abc"), module=mod) == []

    def test_findall_with_groups(self, tmp_path):
        """Groups → each match is a tuple of group strings."""
        # nv
        mod = _load("rf3", r"""
pairs(S, PAIR) <- findall(r"(\w+)=(\w+)", S, PAIR)
""", tmp_path)
        results = _all("pairs", chars("a=1 b=2 c=3"), module=mod)
        assert results == [(chars("a"), chars("1")), (chars("b"), chars("2")), (chars("c"), chars("3"))]

    def test_findall_backtracking(self, tmp_path):
        """findall solutions participate in Clausal backtracking."""
        # nv
        mod = _load("rf4", r"""
line("errors: 3 warnings: 5"),
line("errors: 0 warnings: 1"),

nonzero_error_count(COUNT) <- (
    line(L) and
    findall(r"errors: (\d+)", L, COUNT) and
    COUNT != "0"
)
""", tmp_path)
        results = _all("nonzero_error_count", module=mod)
        assert results == [chars("3")]


# ══════════════════════════════════════════════════════════════════════════════
# TIER 6: replace and split
# ══════════════════════════════════════════════════════════════════════════════

class TestReplace:
    """replace/4: Pattern, Replacement, String, Result."""

    def test_simple_replace(self, tmp_path):
        # nv
        mod = _load("rep1", r"""
clean_spaces(S, R) <- replace(r"\s+", " ", S, R)
""", tmp_path)
        assert _first("clean_spaces", chars("hello   world  foo"), module=mod) == chars("hello world foo")

    def test_replace_remove(self, tmp_path):
        # nv
        mod = _load("rep2", r"""
strip_digits(S, R) <- replace(r"\d+", "", S, R)
""", tmp_path)
        assert _first("strip_digits", chars("a1b2c3"), module=mod) == chars("abc")

    def test_replace_backreference(self, tmp_path):
        r"""Replacement can use \1 backreferences."""
        # nv
        mod = _load("rep3", r"""
wrap_words(S, R) <- replace(r"(\w+)", r"[\1]", S, R)
""", tmp_path)
        assert _first("wrap_words", chars("hello world"), module=mod) == chars("[hello] [world]")

    def test_replace_chain(self, tmp_path):
        # nv
        mod = _load("rep4", r"""
normalize(S, R) <- (
    replace(r"\s+", " ", S, T) and
    replace(r"^ | $", "", T, R)
)
""", tmp_path)
        assert _first("normalize", chars("  hello   world  "), module=mod) == chars("hello world")


class TestSplit:
    """split/3: Pattern, String, Parts."""

    def test_split_comma(self, tmp_path):
        # nv
        mod = _load("sp1", r"""
csv_fields(S, F) <- split(r",\s*", S, F)
""", tmp_path)
        assert _first("csv_fields", chars("a, b, c"), module=mod) == [chars("a"), chars("b"), chars("c")]

    def test_split_whitespace(self, tmp_path):
        # nv
        mod = _load("sp2", r"""
words(S, W) <- split(r"\s+", S, W)
""", tmp_path)
        assert _first("words", chars("hello world foo"), module=mod) == [chars("hello"), chars("world"), chars("foo")]


# ══════════════════════════════════════════════════════════════════════════════
# TIER 7: Dynamic patterns (f-strings) — runtime compilation
# ══════════════════════════════════════════════════════════════════════════════

class TestDynamicPattern:
    """f-string patterns compiled at runtime.
    Auto-binding NOT available — use match/3 explicitly."""

    def test_dynamic_match(self, tmp_path):
        # nv
        mod = _load("rd1", """
starts_with(PREFIX, S) <- match(f"^{PREFIX}", S)
""", tmp_path)
        assert _succeeds("starts_with", chars("hello"), chars("hello world"), module=mod)
        assert not _succeeds("starts_with", chars("goodbye"), chars("hello world"), module=mod)

    def test_dynamic_with_explicit_groups(self, tmp_path):
        # nv
        mod = _load("rd2", r"""
after_prefix(PREFIX, S, REST) <- (
    search(f"{PREFIX}(?P<rest>.*)", S, G) and
    REST is ++G["rest"]
)
""", tmp_path)
        assert _first("after_prefix", chars("key="), chars("key=value"), module=mod) == chars("value")

    def test_dynamic_pattern_variable(self, tmp_path):
        """Pattern passed as a plain variable."""
        # nv
        mod = _load("rd3", r"""
try_match(PAT, S) <- match(PAT, S)
""", tmp_path)
        assert _succeeds("try_match", chars(r"\d+"), chars("123"), module=mod)
        assert not _succeeds("try_match", chars(r"\d+"), chars("abc"), module=mod)


# ══════════════════════════════════════════════════════════════════════════════
# TIER 8: Goal expansion behavior — pre-compilation + validation
# ══════════════════════════════════════════════════════════════════════════════

class TestGoalExpansion:
    """Verify that goal expansion correctly pre-compiles static patterns
    and produces equivalent results to runtime compilation."""

    def test_static_precompiled(self, tmp_path):
        # nv
        mod = _load("ge1", r"""
is_hex(S) <- match(r"^[0-9a-fA-F]+$", S)
""", tmp_path)
        assert _succeeds("is_hex", chars("deadBEEF"), module=mod)
        assert not _succeeds("is_hex", chars("xyz"), module=mod)

    def test_multiple_patterns_in_module(self, tmp_path):
        """Each static pattern gets its own compiled regex."""
        # nv
        mod = _load("ge2", r"""
is_date(S) <- match(r"\d{4}-\d{2}-\d{2}", S)
is_time(S) <- match(r"\d{2}:\d{2}:\d{2}", S)
""", tmp_path)
        assert _succeeds("is_date", chars("2026-03-16"), module=mod)
        assert _succeeds("is_time", chars("14:30:00"), module=mod)
        assert not _succeeds("is_date", chars("14:30:00"), module=mod)

    def test_same_pattern_deduplicated(self, tmp_path):
        """Same literal used twice → could share one compiled object."""
        # nv
        mod = _load("ge3", r"""
valid_id(S) <- match(r"[a-z]\w*", S)
extract_id(S, ID) <- match(r"(?P<ID>[a-z]\w*)", S)
""", tmp_path)
        assert _succeeds("valid_id", chars("foo_bar"), module=mod)
        assert _first("extract_id", chars("foo_bar"), module=mod) == chars("foo_bar")


# ══════════════════════════════════════════════════════════════════════════════
# TIER 9: Practical examples
# ══════════════════════════════════════════════════════════════════════════════

class TestPracticalExamples:

    def test_log_parser_compact(self, tmp_path):
        """Parse log lines using auto-binding — ALLCAPS groups only."""
        # nv
        mod = _load("ex1", r"""
parse_log(LINE, LEVEL, MSG) <- match(r"(?P<LEVEL>INFO|WARN|ERROR):\s*(?P<MSG>.*)", LINE)
""", tmp_path)
        results = _call_multi("parse_log", chars("ERROR: disk full"), module=mod,
                              out_names=["level", "msg"])
        assert results == [{"level": chars("ERROR"), "msg": chars("disk full")}]

    def test_tokenizer(self, tmp_path):
        # nv
        mod = _load("ex2", r"""
token(S, T) <- findall(r"[a-zA-Z_]\w*|\d+|[+\-*/=]", S, T)
""", tmp_path)
        assert _all("token", chars("x = 42 + y"), module=mod) == \
            [chars("x"), chars("="), chars("42"), chars("+"), chars("y")]

    def test_backtracking_regex(self, tmp_path):
        """Regex extraction + Clausal backtracking."""
        # nv
        mod = _load("ex3", r"""
line("2026-03-16 INFO started"),
line("2026-03-16 ERROR disk full"),
line("2026-03-16 INFO stopped"),

error_message(MSG) <- (
    line(L) and
    match(r"\S+ ERROR\s+(?P<MSG>.*)", L)
)
""", tmp_path)
        assert _all("error_message", module=mod) == [chars("disk full")]

    def test_url_parser(self, tmp_path):
        # nv
        mod = _load("ex4", r"""
parse_url(S, SCHEME, HOST, PATH) <- match(r"(?P<SCHEME>https?)://(?P<HOST>[^/]+)(?P<PATH>/.*)?", S)
""", tmp_path)
        results = _call_multi(
            "parse_url", chars("https://example.com/api/v1"), module=mod,
            out_names=["s", "h", "p"])
        assert results == [{"s": chars("https"), "h": chars("example.com"),
                            "p": chars("/api/v1")}]

    def test_csv_parse_and_validate(self, tmp_path):
        """split CSV, then validate each field."""
        # nv
        mod = _load("ex5", r"""
valid_email_in_csv(CSV, EMAIL) <- (
    split(r",\s*", CSV, FIELDS) and
    in_(EMAIL, FIELDS) and
    match(r"[^@]+@[^@]+\.[^@]+$", EMAIL)
)
""", tmp_path)
        results = _all("valid_email_in_csv",
                       chars("alice@ex.com, not-email, bob@ex.com"), module=mod)
        assert results == [chars("alice@ex.com"), chars("bob@ex.com")]


# ══════════════════════════════════════════════════════════════════════════════
# TIER 10: Failure modes and edge cases
# ══════════════════════════════════════════════════════════════════════════════

class TestAutoBindingPitfalls:

    def test_typo_in_group_name(self, tmp_path):
        """Misspelled ALLCAPS group → wrong variable bound, intended stays unbound.
        Goal expansion could warn if generated var doesn't appear in clause head."""
        # nv
        mod = _load("pit1", r"""
parse(S, YEAR) <- match(r"(?P<YAER>\d{4})", S)
""", tmp_path)
        # YAER doesn't match YEAR → YEAR is unbound
        result = _first("parse", chars("2026"), module=mod)
        from clausal.logic.variables import is_var
        assert is_var(result), "YEAR should be unbound due to group name typo"

    def test_optional_group_binds_none(self, tmp_path):
        """Non-participating optional group → variable bound to None."""
        # nv
        mod = _load("pit2", r"""
parse(S, A, B) <- match(r"(?P<A>\d+)(?:-(?P<B>\d+))?", S)
""", tmp_path)
        # With both groups
        results = _call_multi("parse", chars("42-99"), module=mod,
                              out_names=["a", "b"])
        assert results == [{"a": chars("42"), "b": chars("99")}]
        # With only first group — B gets None
        results = _call_multi("parse", chars("42"), module=mod,
                              out_names=["a", "b"])
        assert results == [{"a": chars("42"), "b": None}]

    def test_lowercase_groups_not_auto_bound(self, tmp_path):
        """Lowercase group names are NOT auto-bound — this is the control mechanism."""
        # nv
        mod = _load("pit3", r"""
check(S, RESULT) <- (
    match(r"(?P<internal>\d+)-(?P<RESULT>\w+)", S)
)
""", tmp_path)
        # RESULT is auto-bound (ALLCAPS); internal is not
        assert _first("check", chars("42-hello"), module=mod) == chars("hello")

    def test_no_named_groups_boolean_only(self, tmp_path):
        """Unnamed groups → no auto-binding, match/2 is purely boolean."""
        # nv
        mod = _load("pit4", r"""
check(S) <- match(r"(\d+)-(\d+)", S)
""", tmp_path)
        assert _succeeds("check", chars("42-99"), module=mod)
        assert not _succeeds("check", chars("abc"), module=mod)


class TestEdgeCases:

    def test_empty_string(self, tmp_path):
        # nv
        mod = _load("ec1", r"""
match_empty(S) <- match(r"^$", S)
""", tmp_path)
        assert _succeeds("match_empty", chars(""), module=mod)
        assert not _succeeds("match_empty", chars(" "), module=mod)

    def test_unicode(self, tmp_path):
        # nv
        mod = _load("ec2", r"""
is_word(S) <- match(r"^\w+$", S)
""", tmp_path)
        assert _succeeds("is_word", chars("café"), module=mod)

    def test_special_chars(self, tmp_path):
        # nv
        mod = _load("ec3", r"""
has_parens(S) <- search(r"\(.*?\)", S)
""", tmp_path)
        assert _succeeds("has_parens", chars("foo(bar)"), module=mod)
        assert not _succeeds("has_parens", chars("foobar"), module=mod)

    def test_findall_nonoverlapping(self, tmp_path):
        # nv
        mod = _load("ec4", r"""
find_aa(S, M) <- findall(r"aa", S, M)
""", tmp_path)
        assert _all("find_aa", chars("aaaa"), module=mod) == [chars("aa"), chars("aa")]

    def test_search_vs_match(self, tmp_path):
        """search finds anywhere; match only at start."""
        # nv
        mod = _load("ec5", r"""
try_match(S) <- match(r"\d+", S)
try_search(S) <- search(r"\d+", S)
""", tmp_path)
        assert not _succeeds("try_match", chars("abc123"), module=mod)
        assert _succeeds("try_search", chars("abc123"), module=mod)


# ══════════════════════════════════════════════════════════════════════════════
# FIXTURE INTEGRATION: Load .clausal files and run Test predicates
# ══════════════════════════════════════════════════════════════════════════════

import os

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(name):
    path = seam_path(os.path.join(_FIXTURE_DIR, f"{name}.clausal"))
    mod = _load_module(name, path)
    return mod.__dict__["$module"]


class TestRegexBasicFixture:
    """Run Test predicates from tests/fixtures/regex_basic.seam."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("regex_basic")

    @pytest.mark.parametrize("name", [
        "match digits",
        "match rejects non-digits",
        "match anchored at start",
        "match full via dollar",
        "match email",
        "match named groups",
        "match positional groups",
        "match no match fails",
        "auto-bind YEAR",
        "search finds in middle",
        "search rejects absent pattern",
        "search explicit groups",
        "replace whitespace",
        "replace remove digits",
        "replace backreference",
        "split comma",
        "split whitespace",
        "findall digits",
        "findall no matches fails",
        "match empty string",
        "match unicode",
        "search parens",
        "search vs match",
        "dynamic match",
        "dynamic pattern variable",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", chars(name), module=self.mod)


class TestRegexAutoBindFixture:
    """Run Test predicates from tests/fixtures/regex_autobind.seam."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("regex_autobind")

    @pytest.mark.parametrize("name", [
        "auto-bind date parsing",
        "auto-bind no match fails",
        "auto-bind output",
        "auto-bind constrains correct",
        "auto-bind constrains wrong fails",
        "auto-bind search",
        "auto-bind single group",
        "auto-bind many groups",
        "leading underscore auto-bind",
        "selective binding ALLCAPS only",
        "lowercase groups for backrefs",
        "lowercase groups no repeat fails",
        "optional group both present",
        "optional group absent binds None",
        "log parser compact",
        "backtracking with regex",
        "tokenizer first token",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", chars(name), module=self.mod)


class TestCapitalInitialAutoBinding:
    """Named-group auto-binding follows the VARIABLE rule, whatever it is.

    The gate has always been "the group name is spelled like a Clausal logic
    variable".  On 2026-09-10 a capital initial became one, so TitleCase
    group names auto-bind too.  This is the deliberate reading, not an
    accident of the widening: the alternative -- a group named ``Year``
    NOT binding a clause variable named ``Year`` -- would make the gate
    disagree with the language about what a variable is.

    No existing file can be affected: a TitleCase name was a load-time error
    everywhere before that date, so no clause could name such a variable.
    """

    def test_titlecase_group_auto_binds(self, tmp_path):
        mod = _load("tcab1", r"""
parse_year(S, Year) <- match(r"(?P<Year>\d{4})", S)
""", tmp_path)
        assert _first("parse_year", chars("2026"), module=mod) == chars("2026")

    def test_titlecase_group_constrains_a_bound_input(self, tmp_path):
        """Same two-way behaviour the ALLCAPS groups have."""
        mod = _load("tcab2", r"""
is_year(S, Year) <- match(r"(?P<Year>\d{4})-\d{2}", S)
""", tmp_path)
        assert _succeeds("is_year", chars("2026-03"), chars("2026"), module=mod)
        assert not _succeeds("is_year", chars("2026-03"), chars("1999"), module=mod)

    def test_lowercase_group_still_does_not_bind(self, tmp_path):
        """The gate still EXCLUDES lowercase: it is the variable rule, not
        "any name".  ``year`` is an atom spelling, so the group stays
        regex-only and the clause variable is left untouched."""
        mod = _load("tcab3", r"""
parse_year(S, Out) <- (match(r"(?P<year>\d{4})", S), Out is 0)
""", tmp_path)
        assert _first("parse_year", chars("2026"), module=mod) == 0
