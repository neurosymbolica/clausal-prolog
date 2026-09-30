# toklex Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the toklex compiler (spec → annotated DFA → incremental Python lexer + DCG
renderer), ship the ISO and Clausal dialect spec files, and swap the hand-written
`prolog_tokenizer.py` for the generated lexer behind its existing API.

**Architecture:** A spec file of Prolog terms is parsed with the existing
`prolog_parser.py` (plus a small guarded postfix-operator fallback), compiled to one
annotated DFA over a partitioned alphabet (extend sets, follow constraints, bounded
backup), and executed by a generic incremental driver (`feed`/`next_token` →
`Tok | NEED_MORE | EOF`). A UTF-8 decode stage feeds byte streams. A DCG renderer emits
the same automaton as Prolog, tested against the Scryer binary in this workspace.

**Tech Stack:** Pure Python 3 (stdlib only — `unicodedata`, `dataclasses`, `bisect`),
pytest, the existing `clausal/tools/prolog_parser.py` reader, Scryer Prolog binary for
DCG golden tests.

**Spec:** `implementation_plans/toklex-token-formalism-design.md` (the design doc; §
references below are to it). Background: `implementation_plans/prolog-parser-formalism-handoff.md`.

## Global Constraints

- **CLONE ONLY**: all work in `/workspace/clausal-bug-fix` (or worktrees of it). Never
  touch `/workspace/clausal`.
- Test python: `/workspace/clausal/venv/bin/python`, always invoked **from** the
  worktree/clone directory (cwd wins).
- Full-suite baseline (capture BEFORE Task 1, from the worktree):
  `/workspace/clausal/venv/bin/python -m pytest tests/ -q --tb=no --continue-on-collection-errors`
  — save the failure NAME set; every task compares sets, not counts (~142 pre-existing
  failures expected; verify the run actually executed before trusting a diff).
- **NEVER `git add -A`. NEVER `git stash`.** Stage explicit paths only. Reviewers: check
  `git stash list` is empty after each implementer.
- Commit trailers on every commit:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_01G7xiWqatWtL6zNQDc7nspk`
- No C changes in this plan; fresh worktrees still need
  `/workspace/clausal/venv/bin/python setup.py build_ext --inplace` before running the
  full suite (pre-existing C extensions).
- New runtime dependencies: **none**. Property tests use seeded `random`, not hypothesis.
- Scryer binary for DCG tests: `/workspace/scryer-prolog/target/release/scryer-prolog`
  (tests must `pytest.skip` if absent).
- The toklex operator set (`then`, `but_not`, `followed_by`, `nest`, `value`, `gives`,
  postfix `*`/`+`/`?`) lives in a loader-local `OperatorTable` ONLY. Do not add these to
  any default dialect table.
- Per-task review + final whole-branch review (roborev binary:
  `/workspace/roborev/roborev`, not on PATH).

## File Structure

```
clausal/tools/toklex/__init__.py      public API: load_lexer(), NEED_MORE, EOF, Tok
clausal/tools/toklex/charset.py      CharSet interval algebra + Partition
clausal/tools/toklex/spec.py         RE IR + spec loader (uses prolog_parser)
clausal/tools/toklex/automaton.py    RE→NFA→DFA, but_not, labeled union
clausal/tools/toklex/annotate.py     extend sets, follow, backup bound, Lexer, dump
clausal/tools/toklex/builders.py     ISO value builders (lexeme → value)
clausal/tools/toklex/driver.py       IncrementalLexer (chars mode), trivia/glue/nest
clausal/tools/toklex/decode.py       incremental UTF-8 decode stage (byte mode)
clausal/tools/toklex/dcg.py          DCG renderer (Prolog output)
clausal/tools/toklex/specs/iso.toklex.pl       ISO dialect spec
clausal/tools/toklex/specs/clausal.toklex.pl   Clausal dialect spec
clausal/tools/prolog_parser.py       MODIFY: guarded postfix fallback, BAR-as-op
clausal/tools/prolog_tokenizer.py    MODIFY (Task 10): tokenize() becomes toklex shim
tests/toklex/                         all new tests (package with __init__.py)
```

Design decisions locked here (deviations from the design doc's letter, all consistent
with its spirit — flag to the user in the final report):
1. **Compile at import, no generated tables module.** `load_lexer(...)` compiles the
   spec on first call and caches (`functools.lru_cache`). Subset construction over a
   ~60-symbol partition is milliseconds; a checked-in generated file is machinery we
   don't need (YAGNI). The design's "regenerating the tables is the only effect of a
   spec edit" holds trivially.
2. **`def/2` macro declarations** are added to the notation (named sub-expressions,
   inlined at load). The design's fragment examples imply shared sub-rules; `def/2` is
   the minimal way to write them. `fragment/3` declarations are parsed and stored for
   the DCG target/documentation but have no Python-target semantics: Python values come
   from named builders over the whole lexeme (§3.4's "decode loop over the pending
   buffer").
3. **No DFA minimization** in v1. Tables are tiny; minimization adds risk for zero
   observable benefit.
4. ~~**Lenient nest-at-EOF**: an unterminated block comment at true EOF ends the trivia
   silently (parity with the current tokenizer's documented behavior).~~
   **REVERSED — ruled 2026-09-30: an unterminated block comment is a syntax error.**
   At `close()` with nest depth > 0 both drivers (`IncrementalLexer`, `RegexLexer`)
   emit ONE `error` Tok `('unterminated', <comment text>)` spanning the comment from
   its outermost opener; the reader turns it into a `resumable=False` `SyntaxIssue`
   (Scryer's formal: `syntax_error(incomplete_reduction)`), `tokenize()` raises
   `TokenizeError` at the opener, and a `.pl` file ending in one fails to load. The
   silent exit had hidden whole files (a stray `/*` inside a comment, read with
   nesting on, swallowed everything after it). The frozen `_bootstrap` spec reader
   keeps the old behavior; it reads only the in-repo `.toklex.pl` specs.

---

### Task 1: Parser accommodations for toklex spec files

The Pratt parser tries infix before postfix unconditionally (`prolog_parser.py:170-178`),
so `alnum*` before `)` is today a hard ParseError when `*` has both entries. Add a
guarded fallback. Also make the BAR token (`|`) usable as an infix operator when the
table defines one (needed for `(capital | '_')` outside list context).

**Files:**
- Modify: `clausal/tools/prolog_parser.py` (~lines 160-205 `_parse_term`, and
  `_operator_name_from_token`)
- Test: `tests/toklex/__init__.py` (empty), `tests/toklex/test_parser_postfix.py`

**Interfaces:**
- Consumes: existing `parse_term(source, op_table=...)`, `OperatorTable.define`.
- Produces: with a table where an atom has BOTH infix and postfix entries, the parser
  picks postfix iff the token after the operator cannot start a term. "Cannot start a
  term" = token type in {RPAREN, RBRACKET, RCURLY, BAR, COMMA, DOT, END} or an ATOM
  that has an infix or postfix entry but **no** prefix entry. With no postfix entry,
  behavior is bit-for-bit unchanged (default tables define no postfix operators, so the
  existing suite cannot be affected on default paths).

- [ ] **Step 0: Capture the full-suite baseline** (Global Constraints command) to
  `/tmp/claude-1000/-workspace-clausal-bug-fix/*/scratchpad/baseline_names.txt` (grep
  `FAILED`/`ERROR` lines, sort). Confirm the run executed (non-empty output, pass count
  printed).

- [ ] **Step 1: Write the failing tests**

```python
# tests/toklex/test_parser_postfix.py
"""Guarded postfix fallback + BAR-as-operator (toklex spec reading)."""
import pytest
from clausal.tools.prolog_parser import parse_term, ParseError
from clausal.tools.prolog_operators import OperatorTable
from clausal.tools.prolog_ast import PAtom, PCompound


def toklex_table():
    t = OperatorTable.iso_default()
    t.define(200, "xf", "*")
    t.define(200, "xf", "+")
    t.define(200, "xf", "?")
    t.define(600, "xfy", "then")
    t.define(700, "xfx", "but_not")
    t.define(700, "xfx", "followed_by")
    t.define(1100, "xfy", "|")
    return t


class TestPostfixFallback:
    def test_postfix_before_rparen(self):
        t = toklex_table()
        term = parse_term("f(a*)", op_table=t)
        assert term == PCompound("f", (PCompound("*", (PAtom("a"),)),))

    def test_postfix_before_infix_only_atom(self):
        # `graphic+ but_not x` — `but_not` is infix-only, so `+` is postfix
        t = toklex_table()
        term = parse_term("g+ but_not x", op_table=t)
        assert term == PCompound("but_not", (PCompound("+", (PAtom("g"),)), PAtom("x")))

    def test_infix_still_wins_when_term_follows(self):
        t = toklex_table()
        term = parse_term("a * b", op_table=t)
        assert term == PCompound("*", (PAtom("a"), PAtom("b")))

    def test_postfix_at_end_of_input(self):
        t = toklex_table()
        term = parse_term("a?", op_table=t)
        assert term == PCompound("?", (PAtom("a"),))

    def test_no_postfix_entry_unchanged_error(self):
        # default table: `a *` stays a parse error, proving no default-path change
        with pytest.raises(ParseError):
            parse_term("a *")


class TestBarOperator:
    def test_bar_infix_in_parens(self):
        t = toklex_table()
        term = parse_term("a | b | c", op_table=t)
        assert term == PCompound("|", (PAtom("a"), PCompound("|", (PAtom("b"), PAtom("c")))))

    def test_bar_without_table_entry_unchanged(self):
        # ISO default has no infix '|' in our table: still an error outside lists
        with pytest.raises(ParseError):
            parse_term("a | b", op_table=OperatorTable.iso_default())
```

(If `OperatorTable.iso_default()` DOES define `'|'`, adjust the last test to use a fresh
`OperatorTable()` — check `prolog_operators.py:116` `_load_iso` first and keep whichever
table genuinely lacks the entry.)

- [ ] **Step 2: Run tests, verify they fail**
  `/workspace/clausal/venv/bin/python -m pytest tests/toklex/test_parser_postfix.py -v`
  Expected: the postfix and bar tests FAIL with ParseError; the two "unchanged" tests pass.

- [ ] **Step 3: Implement.** In `_parse_term`, replace the entry-selection block:

```python
            infix_entry = self._ops.lookup_infix(name)
            postfix_entry = self._ops.lookup_postfix(name)

            entry = None
            if infix_entry and infix_entry.precedence <= max_prec:
                entry = infix_entry
                if postfix_entry and postfix_entry.precedence <= max_prec \
                        and not self._can_start_term(self._peek(1)):
                    entry = postfix_entry
            elif postfix_entry and postfix_entry.precedence <= max_prec:
                entry = postfix_entry
```

Add the helper (near `_adjacent`):

```python
    _CLOSER_TYPES = frozenset({
        TokenType.RPAREN, TokenType.RBRACKET, TokenType.RCURLY,
        TokenType.BAR, TokenType.COMMA, TokenType.DOT, TokenType.END,
    })

    def _can_start_term(self, tok: Token) -> bool:
        """Conservative: can *tok* begin a term? Used only to disambiguate an
        atom that is declared both infix and postfix (never true of default
        tables). An infix/postfix-only operator atom is treated as unable to
        start a term (`a* then b`), at the cost of requiring parens for the
        rare `a * (then)`."""
        if tok.type in self._CLOSER_TYPES:
            return False
        if tok.type == TokenType.ATOM:
            name = tok.value
            if (self._ops.lookup_infix(name) or self._ops.lookup_postfix(name)) \
                    and not self._ops.lookup_prefix(name):
                return False
        return True
```

`self._peek(1)` must return the token after the operator; if the parser's `_peek` only
takes no argument, add an offset parameter defaulting to 0 (it holds a token list — use
index arithmetic, clamped to the final END token).

For BAR: in `_operator_name_from_token`, map `TokenType.BAR` to the name `"|"` (so the
table lookup decides; with no `'|'` entry the loop breaks exactly as before). Check how
list parsing consumes BAR first — the change must only affect the operator loop, not
`[H|T]` parsing (list parsing matches `TokenType.BAR` directly before any operator
logic runs; confirm by reading `_parse_list` and leave it untouched).

- [ ] **Step 4: Run tests, verify all pass**; then run the parser's own suite:
  `/workspace/clausal/venv/bin/python -m pytest tests/test_prolog_parse.py tests/toklex/ -v`
  Expected: all pass.

- [ ] **Step 5: Full-suite name-diff vs baseline** (Global Constraints). Expected: empty diff.

- [ ] **Step 6: Commit**

```bash
git add clausal/tools/prolog_parser.py tests/toklex/__init__.py tests/toklex/test_parser_postfix.py
git commit -m "toklex Task 1: guarded postfix fallback + BAR-as-operator in Pratt parser"
```

---

### Task 2: CharSet interval algebra + alphabet partition

**Files:**
- Create: `clausal/tools/toklex/__init__.py` (empty for now), `clausal/tools/toklex/charset.py`
- Test: `tests/toklex/test_charset.py`

**Interfaces:**
- Produces:
  - `CharSet` — frozen; `ivs: tuple[tuple[int, int], ...]` sorted disjoint inclusive
    codepoint intervals. Constructors: `CharSet.from_chars(iterable_of_1char_str)`,
    `CharSet.from_ranges(list[tuple[str, str]])`, `CharSet.from_unicode_category(cat: str)`
    (e.g. `'Ll'`; lazy module-level cache — sweeps `range(0x110000)` once per category),
    `CharSet.full()`, `CharSet.empty()`. Operators: `a | b`, `a - b`, `a & b`;
    `contains(ch: str) -> bool`; `is_empty() -> bool`.
  - `Partition` — `Partition.build(sets: list[CharSet]) -> Partition`;
    `n: int` (symbol count, covering ALL of U+0000..U+10FFFF);
    `symbol_of(ch: str) -> int`; `symbols_of(cs: CharSet) -> frozenset[int]`
    (exact — every partition cell is entirely inside or outside every input set);
    `sample(sym: int) -> str` (a representative char, for tests/DCG comments).

- [ ] **Step 1: Write the failing tests**

```python
# tests/toklex/test_charset.py
from clausal.tools.toklex.charset import CharSet, Partition


class TestCharSet:
    def test_from_chars_and_contains(self):
        cs = CharSet.from_chars("abz")
        assert cs.contains("a") and cs.contains("z") and not cs.contains("c")
        assert cs.ivs == ((97, 98), (122, 122))  # 'ab' merged, 'z' separate

    def test_ranges_union_difference_intersection(self):
        digit = CharSet.from_ranges([("0", "9")])
        low = CharSet.from_ranges([("a", "z")])
        alnum = digit | low
        assert alnum.contains("5") and alnum.contains("m")
        assert (alnum - digit).contains("m") and not (alnum - digit).contains("5")
        assert (alnum & digit).ivs == digit.ivs

    def test_full_minus_char(self):
        hole = CharSet.full() - CharSet.from_chars("\x00")
        assert not hole.contains("\x00") and hole.contains("a")

    def test_unicode_category(self):
        ll = CharSet.from_unicode_category("Ll")
        assert ll.contains("a") and ll.contains("é") and not ll.contains("A")


class TestPartition:
    def test_partition_is_exact_and_total(self):
        digit = CharSet.from_ranges([("0", "9")])
        hexletters = CharSet.from_ranges([("a", "f"), ("A", "F")])
        p = Partition.build([digit, hexletters])
        # totality: every char has a symbol
        for ch in "0a fzé\x00":
            assert 0 <= p.symbol_of(ch) < p.n
        # exactness: a cell never straddles a set boundary
        assert p.symbol_of("0") == p.symbol_of("9")
        assert p.symbol_of("a") != p.symbol_of("g")
        assert p.symbols_of(digit) == {p.symbol_of("0")} | set()
        # symbols_of covers exactly the set
        syms = p.symbols_of(hexletters)
        assert p.symbol_of("b") in syms and p.symbol_of("B") in syms
        assert p.symbol_of("g") not in syms

    def test_sample_roundtrip(self):
        p = Partition.build([CharSet.from_chars("x")])
        s = p.symbol_of("x")
        assert p.symbol_of(p.sample(s)) == s
```

- [ ] **Step 2: Run tests, verify they fail** (ModuleNotFoundError).

- [ ] **Step 3: Implement `charset.py`.** Core representation and the boundary-sweep:

```python
"""Codepoint interval sets and alphabet partitioning for toklex."""
from __future__ import annotations
import bisect
import unicodedata
from dataclasses import dataclass

_MAX = 0x10FFFF
_CATEGORY_CACHE: dict[str, "CharSet"] = {}


def _normalize(ivs):
    """Sort, merge overlapping/adjacent inclusive intervals."""
    out = []
    for lo, hi in sorted(ivs):
        if out and lo <= out[-1][1] + 1:
            out[-1] = (out[-1][0], max(out[-1][1], hi))
        else:
            out.append((lo, hi))
    return tuple(out)


@dataclass(frozen=True)
class CharSet:
    ivs: tuple[tuple[int, int], ...]

    @classmethod
    def from_chars(cls, chars):
        return cls(_normalize([(ord(c), ord(c)) for c in chars]))

    @classmethod
    def from_ranges(cls, ranges):
        return cls(_normalize([(ord(a), ord(b)) for a, b in ranges]))

    @classmethod
    def from_unicode_category(cls, cat):
        if cat not in _CATEGORY_CACHE:
            ivs, run = [], None
            for cp in range(_MAX + 1):
                if unicodedata.category(chr(cp)) == cat:
                    if run and cp == run[1] + 1:
                        run = (run[0], cp)
                    else:
                        if run:
                            ivs.append(run)
                        run = (cp, cp)
            if run:
                ivs.append(run)
            _CATEGORY_CACHE[cat] = cls(tuple(ivs))
        return _CATEGORY_CACHE[cat]

    @classmethod
    def full(cls):
        return cls(((0, _MAX),))

    @classmethod
    def empty(cls):
        return cls(())

    def contains(self, ch):
        cp = ord(ch)
        i = bisect.bisect_right(self.ivs, (cp, _MAX)) - 1
        return i >= 0 and self.ivs[i][0] <= cp <= self.ivs[i][1]

    def is_empty(self):
        return not self.ivs

    def __or__(self, other):
        return CharSet(_normalize(list(self.ivs) + list(other.ivs)))

    def __and__(self, other):
        out, j = [], 0
        for lo, hi in self.ivs:
            for olo, ohi in other.ivs:
                s, e = max(lo, olo), min(hi, ohi)
                if s <= e:
                    out.append((s, e))
        return CharSet(_normalize(out))

    def __sub__(self, other):
        comp, prev = [], 0
        for lo, hi in other.ivs:
            if prev <= lo - 1:
                comp.append((prev, lo - 1))
            prev = hi + 1
        if prev <= _MAX:
            comp.append((prev, _MAX))
        return self & CharSet(tuple(comp))
```

`Partition.build`: collect every interval boundary from all input sets
(`lo` and `hi+1` for each interval), plus 0 and `_MAX+1`; sort/dedupe into cut points;
each adjacent pair `[cut[i], cut[i+1]-1]` is one cell; store `starts` list for
`bisect`-based `symbol_of`; precompute nothing else. `symbols_of(cs)`: a cell belongs
iff its start codepoint is in `cs` (exactness follows from using all boundaries).
`sample(sym)`: `chr(starts[sym])`.

- [ ] **Step 4: Run tests, verify pass.** (The `Ll` sweep takes ~1-2 s once; that's fine.)

- [ ] **Step 5: Commit**

```bash
git add clausal/tools/toklex/__init__.py clausal/tools/toklex/charset.py tests/toklex/test_charset.py
git commit -m "toklex Task 2: CharSet interval algebra + exact alphabet partition"
```

---

### Task 3: Spec IR + loader

**Files:**
- Create: `clausal/tools/toklex/spec.py`
- Test: `tests/toklex/test_spec_loader.py`

**Interfaces:**
- Consumes: `parse(source, op_table=...)` from `prolog_parser` (Task 1 semantics),
  `CharSet` (Task 2), P-node AST classes from `prolog_ast`.
- Produces (all frozen dataclasses in `spec.py`):
  - RE nodes: `Lit(cs: CharSet)`, `Seq(parts: tuple)`, `Alt(parts: tuple)`,
    `Star(x)`, `Plus(x)`, `Opt(x)`, `ButNot(a, b)`.
  - `TokenRule(name: str, expr, follow: CharSet | None, follow_eof: bool,
    builder: str | None, prio: int)`
  - `TriviaRule(name: str, expr, nest_close, prio: int)` — `nest_close` is an RE or
    None; when set, `expr` is the OPEN expression only (the `body(...)` part stripped).
  - `Spec(classes: dict[str, CharSet], tokens: tuple[TokenRule, ...],
    trivia: tuple[TriviaRule, ...], encoding: str)`  (`encoding` ∈ {'chars','utf8'}).
  - `load_spec(path: str) -> Spec`; `parse_spec_text(text: str) -> Spec`;
    `SpecError(Exception)` with message naming the offending declaration.
  - `toklex_op_table() -> OperatorTable` (the Task 1 test's table + `nest` 1150 xfx,
    `value` 1150 xfx, `gives` 100 fy).

Declaration forms accepted (from design §3, plus locked decision #2):
`encoding(E).` `class(Name, ClassExpr).` `def(Name, RE).` `token(Name, RE).`
`token(Name, RE) value Builder.` `trivia(Name, RE).` `trivia(Name, RE) nest self.`
`fragment(F, RE, gives V).` (stored in `Spec.fragments: tuple`, otherwise inert).
ClassExpr: char list `['a','b']`, `range(Lo, Hi)`, `unicode(Cat)`, `any`,
`class(Name)` or bare Name reference, `+` union, `-` difference. RE: single-char quoted
atoms → `Lit(singleton)`, class names / inline ClassExpr → `Lit`, `then`, `|`, postfix
`* + ?`, `but_not`, `X followed_by C` (only at top level of a token RE; `C` may include
`eof` as an `Alt` member — split it out into `follow_eof`), `body(RE)` (only as final
`then`-element of a nest trivia rule). `def` names are inlined recursively (cycle →
`SpecError`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/toklex/test_spec_loader.py
import pytest
from clausal.tools.toklex.spec import (
    parse_spec_text, SpecError, Lit, Seq, Alt, Star, Plus, Opt, ButNot,
)

MINI = """
encoding(chars).
class(digit, range('0', '9')).
class(small, range(a, z)).
class(nl, ['\\n']).
def(udigits, digit then (digit | '_')*).
token(integer, udigits).
token(name_atom, small then (small | digit)*).
token(end, '.' followed_by (nl | eof)).
token(weird, small+ but_not ('/' then '*' then any*)).
trivia(line_comment, '%' then (any - nl)*).
trivia(block_comment, '/' then '*' then body('*' then '/')) nest self.
token(quoted, q_ then (any - q_)* then q_) value quoted_atom_val.
class(q_, ['''']).
"""


def test_loads_and_shapes():
    spec = parse_spec_text(MINI)
    assert spec.encoding == "chars"
    assert set(spec.classes) >= {"digit", "small", "nl", "q_"}
    names = [t.name for t in spec.tokens]
    assert names == ["integer", "name_atom", "end", "weird", "quoted"]
    integer = spec.tokens[0]
    # def-inlining: udigits became Seq(Lit(digit), Star(Alt(Lit(digit), Lit('_'))))
    assert isinstance(integer.expr, Seq) and isinstance(integer.expr.parts[1], Star)
    end = spec.tokens[2]
    assert end.follow is not None and end.follow_eof is True
    assert end.follow.contains("\n") and not end.follow.contains("x")
    weird = spec.tokens[3]
    assert isinstance(weird.expr, ButNot) and isinstance(weird.expr.a, Plus)
    assert spec.tokens[4].builder == "quoted_atom_val"
    assert spec.tokens[1].builder is None


def test_trivia_and_nest():
    spec = parse_spec_text(MINI)
    line, block = spec.trivia
    assert line.nest_close is None
    assert block.nest_close is not None            # ('*','/') close expr
    assert isinstance(block.expr, Seq)              # open expr: '/' then '*'
    assert len(block.expr.parts) == 2


def test_priorities_are_declaration_order():
    spec = parse_spec_text(MINI)
    assert [t.prio for t in spec.tokens] == [0, 1, 2, 3, 4]


def test_unknown_class_reference_raises():
    with pytest.raises(SpecError):
        parse_spec_text("token(x, nosuchclass).")


def test_def_cycle_raises():
    with pytest.raises(SpecError):
        parse_spec_text("def(a, b then 'x'). def(b, a). token(t, a).")


def test_multichar_literal_raises():
    with pytest.raises(SpecError):
        parse_spec_text("token(x, 'ab').")
```

- [ ] **Step 2: Run tests, verify they fail.**

- [ ] **Step 3: Implement `spec.py`.** Structure:

```python
def toklex_op_table():
    t = OperatorTable.iso_default()
    for prec, kind, name in [
        (200, "xf", "*"), (200, "xf", "+"), (200, "xf", "?"),
        (600, "xfy", "then"), (700, "xfx", "but_not"), (700, "xfx", "followed_by"),
        (1100, "xfy", "|"), (1150, "xfx", "nest"), (1150, "xfx", "value"),
        (100, "fy", "gives"),
    ]:
        t.define(prec, kind, name)
    return t
```

`parse_spec_text`: `module = parse(text, op_table=toklex_op_table())`; walk
`module.items`; each item is a `PClause`-less fact — its `term` is a `PCompound`
(`class/2`, `token/2`, `def/2`, `trivia/2`, `encoding/1`, `fragment/3`) or the infix
wrappers `value(TokenDecl, Builder)`, `nest(TriviaDecl, self)`.

Two-pass: first collect `class` and `def` raw terms (order-independent references),
then translate `token`/`trivia` in declaration order. Class-expression evaluator
(P-nodes → CharSet): `PList` of 1-char atoms → `from_chars`; `range(A,B)`;
`unicode(Cat)`; `any` → `CharSet.full()`; `+`/`-` PCompounds recurse; `class(N)` or
bare `PAtom` name → lookup (raise `SpecError` if missing). RE translator (P-nodes →
RE IR): `then` → `Seq` (flatten right-nesting), `|` → `Alt` (flatten), postfix
compounds → `Star/Plus/Opt`, `but_not` → `ButNot`, quoted 1-char atoms → `Lit`, names:
try class table → `Lit`; then def table → inline (with an in-progress set for cycle
detection); else `SpecError`. `followed_by`: only accepted as the token RE root —
split RHS alternation members: `eof` atom → `follow_eof=True`, rest evaluated as a
ClassExpr union → `follow`. `body(X)`: only as the last element of the root `Seq` of a
nest trivia rule; strip into `nest_close`.

- [ ] **Step 4: Run tests, verify pass.**

- [ ] **Step 5: Commit**

```bash
git add clausal/tools/toklex/spec.py tests/toklex/test_spec_loader.py
git commit -m "toklex Task 3: spec IR + Prolog-term loader with def-inlining"
```

---

### Task 4: Automaton construction

**Files:**
- Create: `clausal/tools/toklex/automaton.py`
- Test: `tests/toklex/test_automaton.py`

**Interfaces:**
- Consumes: RE IR + `Spec` (Task 3), `Partition` (Task 2).
- Produces:
  - `DFA(start: int, delta: tuple[dict[int, int], ...], accepts: tuple[tuple[str, ...], ...])`
    — `delta[q][sym]` absent = no transition; `accepts[q]` = priority-ordered rule
    names (empty tuple = non-accepting).
  - `build_partition(spec) -> Partition` (every `Lit` CharSet + every follow CharSet
    collected from tokens, trivia, and nest_close exprs).
  - `compile_expr(expr, partition, label="x") -> DFA` (single-rule).
  - `compile_spec(spec, partition) -> DFA` (all token + trivia rules unioned; labels
    are rule names; ties resolved by `prio`).

Algorithm: Thompson NFA over partition symbols (`Lit` expands via
`partition.symbols_of`); `ButNot(a, b)`: compile both sides to DFAs, complete them with
a sink over all `partition.n` symbols, product construction with accept =
`accept_a and not accept_b`, then strip unreachable/dead states and re-embed as an NFA
fragment. Union: fresh start with ε to each rule's NFA start. Subset construction;
per-DFA-state accept list = all constituent rule labels sorted by `prio`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/toklex/test_automaton.py
from clausal.tools.toklex.charset import CharSet, Partition
from clausal.tools.toklex.spec import parse_spec_text, Lit, Seq, Star, ButNot, Plus
from clausal.tools.toklex.automaton import build_partition, compile_expr, compile_spec


def run(dfa, partition, s):
    """Longest accepted prefix's labels, or None."""
    q, best = dfa.start, None
    for i, ch in enumerate(s):
        q = dfa.delta[q].get(partition.symbol_of(ch))
        if q is None:
            break
        if dfa.accepts[q]:
            best = (i + 1, dfa.accepts[q])
    return best


SPEC = parse_spec_text("""
encoding(chars).
class(digit, range('0','9')).
class(small, range(a, z)).
class(graphic, ['*','/','+','=','.']).
token(integer, digit then digit*).
token(name, small then small*).
token(graphic_tok, graphic+ but_not ('/' then '*' then any*)).
""")


def test_single_rule_longest_match():
    p = build_partition(SPEC)
    dfa = compile_expr(SPEC.tokens[0].expr, p, label="integer")
    assert run(dfa, p, "123x") == (3, ("integer",))
    assert run(dfa, p, "x1") is None


def test_but_not_subtraction():
    p = build_partition(SPEC)
    dfa = compile_expr(SPEC.tokens[2].expr, p, label="g")
    assert run(dfa, p, "=..") == (3, ("g",))
    assert run(dfa, p, "/") == (1, ("g",))
    # anything starting /* never accepts, at any length
    assert run(dfa, p, "/*") is None
    assert run(dfa, p, "/**/") is None
    # but a '/' followed later by '*' via another char is fine
    assert run(dfa, p, "/+*") == (3, ("g",))


def test_union_labels_and_priority():
    p = build_partition(SPEC)
    dfa = compile_spec(SPEC, p)
    assert run(dfa, p, "12 ") == (2, ("integer",))
    assert run(dfa, p, "ab1") == (2, ("name",))
    assert run(dfa, p, "==") == (2, ("graphic_tok",))
```

- [ ] **Step 2: Run, verify fail.**

- [ ] **Step 3: Implement.** NFA representation:
`nfa = {n_states, start, accept_state, eps: list[set[int]], trans: list[dict[int, set[int]]]}`
built recursively (one accept per fragment). Subset construction with frozenset keys.
For `ButNot`: `dfa_a = _determinize(_to_nfa(a))`, `dfa_b` likewise; `_complete(dfa, n_syms)`
adds a sink state and fills every missing symbol; product states `(qa, qb)`, accept iff
`qa` accepting and `qb` not; `_dfa_to_nfa` re-embeds (add a fresh accept state with ε
from every accepting product state). Keep every helper ≤ 40 lines; module ≤ ~250 lines.

- [ ] **Step 4: Run, verify pass. Step 5: Commit**

```bash
git add clausal/tools/toklex/automaton.py tests/toklex/test_automaton.py
git commit -m "toklex Task 4: RE->NFA->DFA with language subtraction and labeled union"
```

---

### Task 5: Annotations, backup bound, dump

**Files:**
- Create: `clausal/tools/toklex/annotate.py`
- Test: `tests/toklex/test_annotate.py`

**Interfaces:**
- Consumes: `Spec`, `DFA`, `Partition`, `compile_spec`, `compile_expr`, `build_partition`.
- Produces:
  - `Lexer(spec, partition, dfa, extend: tuple[frozenset[int], ...],
    follow: dict[str, tuple[frozenset[int] | None, bool]],
    kind: dict[str, str],                      # 'token' | 'trivia'
    nest: dict[str, tuple[DFA, DFA]],          # rule -> (open_dfa, close_dfa)
    builder: dict[str, str | None],
    max_backup: int)`
  - `annotate(spec) -> Lexer` — the one-call compiler front door.
  - `UnboundedBackupError(SpecError)` raised when a cycle of non-accepting states is
    reachable from an accepting state (design §4.3).
  - `dump_term(lexer) -> str` — the annotated-DFA interchange dump, a readable Prolog
    term: `toklex_dfa(start(S), states([q(Id, Accepts, Extend, [t(Sym, Dest), ...]), ...])).`

Definitions (design §4): `live` = states from which some accepting state is reachable.
`extend[q]` = symbols σ with `delta[q][σ]` defined and live. Backup: build the directed
graph on **non-accepting** states; find those reachable from any accepting state
(crossing one edge out of the accepting state, then staying within non-accepting
states); a cycle there = `UnboundedBackupError`; otherwise `max_backup` = the longest
such path length (DAG longest-path).

- [ ] **Step 1: Write the failing tests**

```python
# tests/toklex/test_annotate.py
import pytest
from clausal.tools.toklex.spec import parse_spec_text
from clausal.tools.toklex.annotate import annotate, UnboundedBackupError, dump_term

NUM = """
encoding(chars).
class(digit, range('0','9')).
class(layout, [' ']).
def(exp, 'e' then ('+' | '-')? then digit then digit*).
token(integer, digit then digit*).
token(float_num, digit then digit* then '.' then digit then digit* then exp?).
trivia(ws, layout then layout*).
"""


def test_extend_sets_drive_emission():
    lx = annotate(parse_spec_text(NUM))
    p = lx.partition
    # after '1' the state accepts integer; '.' extends (float path), ' ' does not
    q = lx.dfa.delta[lx.dfa.start][p.symbol_of("1")]
    assert lx.dfa.accepts[q] == ("integer",)
    assert p.symbol_of(".") in lx.extend[q]
    assert p.symbol_of(" ") not in lx.extend[q]


def test_backup_bound_is_two():
    lx = annotate(parse_spec_text(NUM))
    # worst case: '1.2e+' then non-digit -> emit float '1.2', return 'e+'
    assert lx.max_backup == 2


def test_unbounded_backup_rejected():
    bad = """
    encoding(chars).
    class(a_, [a]). class(b_, [b]).
    token(t, a_ then (b_ then b_)* then a_ then a_).
    """
    # after accepting is impossible here; craft a real cycle-after-accept:
    bad = """
    encoding(chars).
    class(a_, [a]). class(b_, [b]).
    token(short, a_).
    token(long, a_ then b_ then b_ then (b_ then b_)* then a_).
    """
    with pytest.raises(UnboundedBackupError):
        annotate(parse_spec_text(bad))


def test_follow_and_kind_maps():
    spec = parse_spec_text(NUM + "token(end, '.' followed_by (layout | eof)).")
    lx = annotate(spec)
    syms, eof_ok = lx.follow["end"]
    assert eof_ok and lx.partition.symbol_of(" ") in syms
    assert lx.kind["ws"] == "trivia" and lx.kind["integer"] == "token"


def test_dump_is_prolog_readable():
    from clausal.tools.prolog_parser import parse_term
    lx = annotate(parse_spec_text(NUM))
    term = parse_term(dump_term(lx).rstrip(". \n"))  # parses as a term
    assert term is not None
```

- [ ] **Step 2: Run, verify fail. Step 3: Implement** (`annotate` orchestrates:
`build_partition` → `compile_spec` → liveness (reverse BFS from accepting states) →
extend sets → backup graph analysis (Tarjan or iterative DFS cycle check + topo
longest-path) → nest DFAs via `compile_expr` on `TriviaRule.expr`/`nest_close`).
`dump_term` renders symbols as ints with a `symbols([s(Sym, Lo, Hi), ...])` legend from
partition cells.

- [ ] **Step 4: Run, verify pass. Step 5: Commit**

```bash
git add clausal/tools/toklex/annotate.py tests/toklex/test_annotate.py
git commit -m "toklex Task 5: extend sets, follow maps, bounded-backup proof, term dump"
```

---

### Task 6: Builders + the incremental driver (chars mode)

The heart. Implements design §5–§6 chars-mode exactly: maximal munch with derived
emission, follow-disqualification, bounded backup, trivia recording with `Glue`,
nesting, error tokens, `NEED_MORE` on exhausted input, positions.

**Files:**
- Create: `clausal/tools/toklex/builders.py`, `clausal/tools/toklex/driver.py`
- Modify: `clausal/tools/toklex/__init__.py` (export `NEED_MORE`, `EOF`, `Tok`,
  `IncrementalLexer`, `load_lexer` — `load_lexer` arrives Task 8; export what exists)
- Test: `tests/toklex/test_driver.py`

**Interfaces:**
- Consumes: `Lexer` from Task 5.
- Produces:
  - `builders.ISO_BUILDERS: dict[str, Callable[[str], object]]` with entries:
    `quoted_atom_val`, `string_val` (strip delimiters, decode ISO 6.4.2 escapes:
    simple map exactly as `prolog_tokenizer._SIMPLE_ESCAPES`, `\x…\`/octal…`\`
    (closing backslash optional), doubled-quote, `\<newline>` → removed, unknown
    escape kept verbatim as backslash+char — bit-parity with the current
    `_read_escape`), `int_10` (strip `_`), `int_16`/`int_8`/`int_2` (strip prefix and
    `_`), `float_of` (strip `_`), `char_code` (decode the char after `0'`, incl. `0'''`
    → 39 and escapes), `lexeme` (identity, the default).
  - `driver.NEED_MORE`, `driver.EOF` — unique sentinels.
  - `driver.Tok(kind: str, value, lexeme: str, start: tuple[int, int, int],
    end: tuple[int, int, int], glue: str)` — positions are (offset, line, col),
    line/col 1-based; `glue` ∈ {'glued', 'spaced'}; error tokens have
    `kind='error'`, `value=(reason: str, culprit: str)`.
  - `driver.IncrementalLexer(lexer, builders=ISO_BUILDERS, nested_comments=True)`
    with `.feed(text: str)`, `.close()`, `.next_token() -> Tok | NEED_MORE | EOF`.
    After `close()`, `next_token` never returns NEED_MORE. EOF is returned forever
    once reached. Batch helper: `.run(text: str) -> list[Tok]` (feed, close, drain).

Driver algorithm (write it exactly like this; it is the specification of §5–§6):

```python
# per token attempt, kept as instance state so NEED_MORE can resume anywhere:
#   self._q          current DFA state
#   self._pending    chars consumed this attempt (list)
#   self._accepts    list of (length, labels) recorded at each accepting state
#   self._glue       'glued'/'spaced' for the token being attempted
#   self._nest       (rule, depth, sub-state) when inside nested trivia, else None
#
# next_token():
#   loop:
#     ev = self._peek_event()          # ('char', c) | ('eof',) | ('wait',)
#     if wait: return NEED_MORE
#     if in nest mode: run _nest_step(ev); continue
#     if ev is char c:
#         t = delta[q].get(symbol_of(c))
#         if t is not None:
#             consume c; q = t
#             if accepts[q]: record (len(pending), accepts[q])
#             continue
#     # stuck (no transition, or eof): resolve the attempt
#     nxt = c if ev is char else EOF_MARK
#     for (length, labels) in reversed(self._accepts):
#         # follow check uses the char *right after* that prefix:
#         after = pending[length] if length < len(pending) else nxt
#         for label in labels:
#             if self._follow_ok(label, after):
#                 pushback = pending[length:]      # ≤ max_backup, guaranteed
#                 self._unread(pushback)
#                 return self._emit(label, pending[:length])  # trivia loops internally
#     # no accept survives:
#     if not pending and ev is eof: return EOF
#     if not pending: consume c; return error_tok('no_token', c)
#     if ev is eof and self._in_quote_like(): return error_tok('unterminated', pending)
#     self._unread(pending[1:]); return error_tok('no_token', pending[0])
```

Notes that MUST hold in the implementation:
- `_peek_event` looks at the internal buffer (fed text minus consumed); returns
  `('wait',)` iff buffer exhausted and not closed. **No seeking**: `_unread` prepends to
  the buffer (chars already have recorded positions — keep a parallel position stack so
  line/col stay exact after pushback; simplest correct approach: buffer holds
  `(ch, offset, line, col)` tuples computed once at feed time).
- The follow check when `after is EOF_MARK` uses `follow[label][1]` (eof_ok); a rule
  with no follow entry always passes.
- `_emit` on a trivia label: record `self._glue = 'spaced'`, reset the attempt, and
  **continue the loop** (emit nothing). On a nest-rule label: enter nest mode with
  depth 1. On a token label: build value via `builders.get(builder_name, lexeme)`,
  reset `self._glue = 'glued'` for the next attempt, return the Tok.
- `_nest_step`: greedily try to match the close DFA from the current buffer (char by
  char; if the buffer runs out mid-match and not closed → NEED_MORE); on close match,
  depth -= 1 (depth 0 → leave nest mode as trivia consumed, glue = spaced); else try
  the open DFA (only when `nested_comments`) → depth += 1; else consume one char; at
  eof with depth > 0 → leave nest mode silently (locked decision #4).
- `_in_quote_like`: pending non-empty and no accept recorded → 'unterminated' reason
  (gives the shim its "Unterminated quoted atom" class of errors).

- [ ] **Step 1: Write the failing tests**

```python
# tests/toklex/test_driver.py
from clausal.tools.toklex.spec import parse_spec_text
from clausal.tools.toklex.annotate import annotate
from clausal.tools.toklex.driver import IncrementalLexer, NEED_MORE, EOF

SPEC = parse_spec_text("""
encoding(chars).
class(digit, range('0','9')).
class(small, range(a, z)).
class(layout, [' ', '\\n']).
class(graphic, ['=','.','/','*','+']).
def(exp, 'e' then ('+' | '-')? then digit then digit*).
token(integer, digit then (digit | '_')*).
token(float_num, digit then digit* then '.' then digit then digit* then exp?).
token(name, small then (small | digit)*).
token(end, '.' followed_by (layout | '%' | eof)).
token(graphic_tok, graphic+ but_not ('/' then '*' then any*)).
token(lparen, '(').
trivia(ws, layout then layout*).
trivia(block, '/' then '*' then body('*' then '/')) nest self.
""")


def lex(text):
    return IncrementalLexer(annotate(SPEC)).run(text)


def kinds(text):
    return [(t.kind, t.lexeme) for t in lex(text)]


class TestMaximalMunch:
    def test_graphic_extension(self):
        assert kinds("=.. ") == [("graphic_tok", "=..")]
        assert kinds("= x") == [("graphic_tok", "="), ("name", "x")]

    def test_numbers_and_backup(self):
        assert kinds("1.5 ") == [("float_num", "1.5")]
        assert kinds("1. ") == [("integer", "1"), ("end", ".")]
        assert kinds("1.2e7 ") == [("float_num", "1.2e7")]
        # the B=2 witness: emit 1.2, push back 'e+', relex as name then graphic
        assert kinds("1.2e+ ")[0] == ("float_num", "1.2")
        assert [k for k, _ in kinds("1.2e+ ")] == ["float_num", "name", "graphic_tok"]

    def test_dot_cases(self):
        assert kinds(".( ") == [("graphic_tok", "."), ("lparen", "(")]
        assert kinds(". ") == [("end", ".")]


class TestIncrementality:
    def test_need_more_mid_token(self):
        lx = IncrementalLexer(annotate(SPEC))
        lx.feed("=")
        assert lx.next_token() is NEED_MORE       # '=' could become '=..'
        lx.feed(". x")
        toks = []
        while (t := lx.next_token()) is not NEED_MORE and t is not EOF:
            toks.append(t)
        lx.close()
        while (t := lx.next_token()) is not EOF:
            toks.append(t)
        assert [t.lexeme for t in toks] == ["=.", "x"]

    def test_eof_resolves_extension(self):
        lx = IncrementalLexer(annotate(SPEC))
        lx.feed("=")
        lx.close()
        assert lx.next_token().lexeme == "="
        assert lx.next_token() is EOF

    def test_end_at_eof(self):
        assert kinds("ab.") == [("name", "ab"), ("end", ".")]


class TestTriviaGlueNest:
    def test_glue(self):
        a, b, c = lex("f( (")
        assert (a.glue, b.glue, c.glue) == ("spaced", "glued", "spaced")

    def test_nested_comment_is_skipped_and_spaces(self):
        toks = lex("f/* x /* y */ z */(")
        assert [(t.kind, t.glue) for t in toks] == [("name", "spaced"), ("lparen", "spaced")]

    def test_slash_before_comment_not_emitted_early(self):
        # '/' must NOT be emitted when '/*' opens a comment (combined-DFA extend)
        assert kinds("/* c */ x") == [("name", "x")]
        assert kinds("/ x") == [("graphic_tok", "/"), ("name", "x")]


class TestErrors:
    def test_unknown_char(self):
        toks = lex("\x01ab")
        assert toks[0].kind == "error" and toks[1] == toks[1]
        assert toks[1].kind == "name"

    def test_positions(self):
        a, b = lex("ab\ncd")
        assert a.start == (0, 1, 1) and a.end == (2, 1, 3)
        assert b.start == (3, 2, 1)
```

Also builder tests:

```python
# appended in tests/toklex/test_driver.py
from clausal.tools.toklex.builders import ISO_BUILDERS

class TestBuilders:
    def test_quoted_atom_escapes(self):
        f = ISO_BUILDERS["quoted_atom_val"]
        assert f("'ab'") == "ab"
        assert f("'a''b'") == "a'b"
        assert f("'a\\nb'") == "a\nb"
        assert f("'a\\\nb'") == "ab"          # line continuation
        assert f("'\\x41\\b'") == "Ab"
        assert f("'\\q'") == "\\q"             # lenient unknown escape

    def test_numbers(self):
        assert ISO_BUILDERS["int_10"]("1_000") == 1000
        assert ISO_BUILDERS["int_16"]("0x1F_f") == 0x1FF
        assert ISO_BUILDERS["float_of"]("1.5e3") == 1500.0
        assert ISO_BUILDERS["char_code"]("0'a") == 97
        assert ISO_BUILDERS["char_code"]("0'''") == 39
        assert ISO_BUILDERS["char_code"]("0'\\n") == 10
```

- [ ] **Step 2: Run, verify fail. Step 3: Implement `builders.py` then `driver.py`**
  per the algorithm block above. Keep `driver.py` under ~300 lines; the attempt state
  is 6 instance fields, `next_token` is one loop with the resolve block factored into
  `_resolve(ev)`.

- [ ] **Step 4: Run, verify pass. Step 5: Commit**

```bash
git add clausal/tools/toklex/builders.py clausal/tools/toklex/driver.py clausal/tools/toklex/__init__.py tests/toklex/test_driver.py
git commit -m "toklex Task 6: incremental driver (munch/backup/follow/trivia/nest) + ISO builders"
```

---

### Task 7: UTF-8 decode stage (byte mode, R6)

**Files:**
- Create: `clausal/tools/toklex/decode.py`
- Modify: `clausal/tools/toklex/driver.py` (accept injected `bad` events)
- Test: `tests/toklex/test_decode.py`

**Interfaces:**
- Consumes: `IncrementalLexer` (Task 6).
- Produces:
  - `decode.Utf8Feeder(lexer: IncrementalLexer)` with `.feed(b: bytes)`, `.close()`;
    delegates `.next_token()` to the wrapped lexer. Valid sequences → `lexer.feed(chars)`;
    invalid sequences (a byte no continuation can repair: stray continuation, overlong,
    > U+10FFFF, 0xFE/0xFF) → `lexer.feed_bad(raw: bytes)`; a valid *prefix* at the end
    of fed bytes is HELD (pending, not invalid) until more bytes or close; at close a
    held prefix becomes one `bad` event then EOF.
  - `IncrementalLexer.feed_bad(raw: bytes)`: enqueue a bad event; when the attempt
    loop meets it: if mid-token, resolve the attempt first (as if stuck); the bad event
    itself becomes `Tok(kind='error', value=('invalid_encoding', raw), ...)` consuming
    zero chars (positions: zero-width at current offset).

Implement the decoder as the standard DFA over UTF-8 byte classes (hand-write the
4-row table: 1-byte, 2-byte lead C2-DF, 3-byte lead E0-EF with the E0/ED special
ranges, 4-byte lead F0-F4 with F0/F4 specials; continuation 80-BF). ~60 lines.

- [ ] **Step 1: Write the failing tests**

```python
# tests/toklex/test_decode.py
from clausal.tools.toklex.annotate import annotate
from clausal.tools.toklex.driver import IncrementalLexer, NEED_MORE, EOF
from clausal.tools.toklex.decode import Utf8Feeder
from tests.toklex.test_driver import SPEC


def blex(data: bytes):
    f = Utf8Feeder(IncrementalLexer(annotate(SPEC)))
    f.feed(data)
    f.close()
    out = []
    while (t := f.next_token()) is not EOF:
        assert t is not NEED_MORE
        out.append(t)
    return out


def test_plain_ascii_roundtrip():
    assert [t.lexeme for t in blex(b"ab 12 ")] == ["ab", "12"]


def test_invalid_byte_is_error_token_and_lexing_continues():
    toks = blex(b"ab \xff cd ")
    assert [t.kind for t in toks] == ["name", "error", "name"]
    assert toks[1].value == ("invalid_encoding", b"\xff")


def test_stray_continuation_and_overlong():
    assert [t.kind for t in blex(b"\x80x ")] == ["error", "name"]
    assert [t.kind for t in blex(b"\xc0\xafx ")][0] == "error"   # overlong '/'


def test_split_multibyte_is_pending_not_invalid():
    f = Utf8Feeder(IncrementalLexer(annotate(SPEC)))
    f.feed(b"ab \xc3")            # first byte of e9 'é'
    toks = [f.next_token()]        # 'ab' emits (space ends it)
    assert toks[0].lexeme == "ab"
    assert f.next_token() is NEED_MORE      # held prefix: waiting
    f.feed(b"\xa9 ")               # completes 'é' (not in any SPEC class -> error tok)
    f.close()
    t = f.next_token()
    assert t.kind == "error" and t.value[1] == "é"


def test_truncated_multibyte_at_close_is_bad():
    f = Utf8Feeder(IncrementalLexer(annotate(SPEC)))
    f.feed(b"x \xe2\x82")          # 2 of 3 bytes of '€'
    f.close()
    kinds = []
    while (t := f.next_token()) is not EOF:
        kinds.append(t.kind)
    assert kinds == ["name", "error"]
```

- [ ] **Step 2: Run, verify fail. Step 3: Implement. Step 4: Run, verify pass.**
- [ ] **Step 5: Commit**

```bash
git add clausal/tools/toklex/decode.py clausal/tools/toklex/driver.py tests/toklex/test_decode.py
git commit -m "toklex Task 7: incremental UTF-8 decode stage; bad bytes are error tokens (R6)"
```

---

### Task 8: The ISO spec file + `load_lexer` + worked-example tests

**Files:**
- Create: `clausal/tools/toklex/specs/iso.toklex.pl`
- Modify: `clausal/tools/toklex/__init__.py` (add `load_lexer`)
- Test: `tests/toklex/test_iso_spec.py`

**Interfaces:**
- Produces: `load_lexer(name: str = "iso") -> Lexer` — resolves
  `clausal/tools/toklex/specs/<name>.toklex.pl` (via `importlib.resources` or
  `os.path.join(os.path.dirname(__file__), "specs", ...)`), `annotate(load_spec(path))`,
  `functools.lru_cache`d.

The ISO spec file, in full (this is the deliverable — copy exactly, then fix what the
tests reveal; keep the parity comments):

```prolog
% iso.toklex.pl — ISO Prolog token layer, matching clausal/tools/prolog_tokenizer.py
% dialect choices: '_' digit separators, lenient unknown escapes, 1e5 floats,
% nested block comments (nesting is a driver flag, not a spec change).
encoding(chars).

class(layout,    [' ', '\t', '\n', '\r', '\f', '\v']).
class(small,     range(a, z)).
class(capital,   range('A', 'Z')).
class(digit,     range('0', '9')).
class(alnum,     class(small) + class(capital) + class(digit) + ['_']).
class(graphic,   ['#','$','&','*','+','-','.','/',':','<','=','>','?','@','\\','^','~']).
class(hexdig,    class(digit) + range(a, f) + range('A', 'F')).
class(octdig,    range('0', '7')).
class(bindig,    ['0', '1']).
class(quote,     ['''']).
class(dquote,    ['"']).
class(bslash,    ['\\']).
class(nl,        ['\n']).
class(sign,      ['+', '-']).

def(escape,   bslash then ( octdig then octdig* then bslash?
                          | 'x' then hexdig then hexdig* then bslash?
                          | any )).
def(qitem,    quote then quote | escape | (any - quote - bslash)).
def(ditem,    dquote then dquote | escape | (any - dquote - bslash)).
def(udigits,  digit then (digit | '_')*).
def(exp,      ('e' | 'E') then sign? then digit then digit*).

token(lparen,   '(').
token(rparen,   ')').
token(lbracket, '[').
token(rbracket, ']').
token(lcurly,   '{').
token(rcurly,   '}').
token(bar,      '|').
token(comma,    ',').
token(cut,      '!').
token(semicolon, ';').
token(end,      '.' followed_by (layout | '%' | eof)).
token(variable, (capital | '_') then alnum*).
token(name_atom, small then alnum*).
token(char_code, '0' then quote then (quote then quote | escape | any)) value char_code.
token(hex_int,  '0' then ('x' | 'X') then (hexdig | '_') then (hexdig | '_')*) value int_16.
token(oct_int,  '0' then ('o' | 'O') then (octdig | '_') then (octdig | '_')*) value int_8.
token(bin_int,  '0' then ('b' | 'B') then (bindig | '_') then (bindig | '_')*) value int_2.
token(float_num, udigits then '.' then udigits then exp?
               | udigits then exp) value float_of.
token(integer,  udigits) value int_10.
token(quoted_atom, quote then qitem* then quote) value quoted_atom_val.
token(string,   dquote then ditem* then dquote) value string_val.
token(graphic_tok, graphic then graphic* but_not ('/' then '*' then any*)).

trivia(whitespace, layout then layout*).
trivia(line_comment, '%' then (any - nl)*).
trivia(block_comment, '/' then '*' then body('*' then '/')) nest self.
```

(Note `graphic then graphic*` rather than `graphic+` in `graphic_tok`: identical
language; use whichever parses cleanly first and simplify after — the postfix ops ARE
expected to work here, this is their acceptance test in anger.)

- [ ] **Step 1: Write the failing tests** — the design §7 worked examples, verbatim:

```python
# tests/toklex/test_iso_spec.py
from clausal.tools.toklex import load_lexer
from clausal.tools.toklex.driver import IncrementalLexer, NEED_MORE, EOF


def lex(text, **kw):
    return IncrementalLexer(load_lexer(), **kw).run(text)


def kv(text):
    return [(t.kind, t.value) for t in lex(text)]


class TestWorkedExamples:
    def test_univ_vs_eq(self):
        assert kv("=..")[0] == ("graphic_tok", "=..")
        assert kv("=, ")[0] == ("graphic_tok", "=")

    def test_number_family(self):
        assert kv("1 ")[0] == ("integer", 1)
        assert kv("1.5 ")[0] == ("float_num", 1.5)
        assert kv("1.0e7 ")[0] == ("float_num", 1.0e7)
        assert [k for k, _ in kv("1. ")] == ["integer", "end"]
        got = kv("1.0e+x ")
        assert got[0] == ("float_num", 1.0)
        assert [k for k, _ in got] == ["float_num", "name_atom", "graphic_tok", "name_atom"]

    def test_char_codes(self):
        assert kv("0'a ")[0] == ("char_code", 97)
        assert kv("0''' ")[0] == ("char_code", 39)
        assert kv("0'\\n ")[0] == ("char_code", 10)

    def test_quoted_atom_continuation_and_doubling(self):
        assert kv("'ab\\\ncd' ")[0] == ("quoted_atom", "abcd")
        assert kv("'a''b' ")[0] == ("quoted_atom", "a'b")

    def test_unterminated_quote_at_eof_is_error(self):
        toks = lex("'abc")
        assert toks[-1].kind == "error"

    def test_nested_comment(self):
        assert [k for k, _ in kv("/* a /* b */ c */ x ")] == ["name_atom"]

    def test_dot_completely(self):
        assert [k for k, _ in kv("a. ")] == ["name_atom", "end"]
        assert kv(".( ")[0] == ("graphic_tok", ".")
        assert kv("a.b ")[:3] == [("name_atom", "a"), ("graphic_tok", "."), ("name_atom", "b")]


class TestSuspension:
    def test_terminal_reader_waits_on_eq(self):
        lx = IncrementalLexer(load_lexer())
        lx.feed("X =")
        assert lx.next_token().kind == "variable"
        assert lx.next_token() is NEED_MORE
        lx.feed(".. Y")
        assert lx.next_token().value == "=.."

    def test_zero_quote_waits(self):
        lx = IncrementalLexer(load_lexer())
        lx.feed("0'")
        assert lx.next_token() is NEED_MORE


class TestCompilerClaims:
    def test_backup_bound_is_exactly_two(self):
        assert load_lexer().max_backup == 2

    def test_strict_iso_comments_flag(self):
        strict = IncrementalLexer(load_lexer(), nested_comments=False)
        toks = strict.run("/* a /* b */ c */ x ")
        # non-nesting: comment closes at first */, then 'c', then '*/' etc.
        assert toks[0].kind == "name_atom" and toks[0].lexeme == "c"
```

- [ ] **Step 2: Run, verify fail** (spec file missing).
- [ ] **Step 3: Write the spec file + `load_lexer`; iterate until green.** Expect the
  iteration to be in the SPEC FILE, not the engine — if an engine bug surfaces, add a
  regression test to the relevant Task-4/5/6 test file in the same commit.
- [ ] **Step 4: Full tests/toklex/ run green. Step 5: Commit**

```bash
git add clausal/tools/toklex/specs/iso.toklex.pl clausal/tools/toklex/__init__.py tests/toklex/test_iso_spec.py
git commit -m "toklex Task 8: ISO spec file; design-doc worked examples green; B=2 verified"
```

---

### Task 9: Chunk-boundary insensitivity (the conformance property)

**Files:**
- Test: `tests/toklex/test_chunking.py`

**Interfaces:** consumes `load_lexer`, `IncrementalLexer`, `Utf8Feeder`.

- [ ] **Step 1: Write the test** (it should PASS immediately if Tasks 6-8 are right —
  a failure here is a real bug; bisect with the printed seed):

```python
# tests/toklex/test_chunking.py
import random
from clausal.tools.toklex import load_lexer
from clausal.tools.toklex.driver import IncrementalLexer, NEED_MORE, EOF
from clausal.tools.toklex.decode import Utf8Feeder

CORPUS = [
    "foo(X) :- bar(X, [1,2|T]), X =.. L, Y is 1.0e7 + 0'a. % done\n",
    "a. 1. 1.5. 'qu''ote'. \"str\\n\". /* c /* n */ c */ end.\n",
    "=.. = . .( 0x1F 0o17 0b101 1_000_000 X_1 _var !;,| {} [] ",
    "'\\x41\\' '\\q' 0''' 1.2e+ 1.2e-3 .\n",
]


def drain(feed_chunks, close, next_token):
    for c in feed_chunks:
        pass
    out = []
    while True:
        t = next_token()
        if t is NEED_MORE:
            continue_feeding = False
            break
    return out  # NOTE: replaced by real helper below


def tokens_batch(text):
    return [(t.kind, t.value, t.lexeme) for t in IncrementalLexer(load_lexer()).run(text)]


def tokens_chunked(text, cuts):
    lx = IncrementalLexer(load_lexer())
    out, pieces = [], [text[a:b] for a, b in zip([0] + cuts, cuts + [len(text)])]
    for piece in pieces:
        lx.feed(piece)
        while (t := lx.next_token()) is not NEED_MORE:
            if t is EOF:
                break
            out.append((t.kind, t.value, t.lexeme))
    lx.close()
    while (t := lx.next_token()) is not EOF:
        assert t is not NEED_MORE
        out.append((t.kind, t.value, t.lexeme))
    return out


def test_chunk_insensitivity_chars():
    rng = random.Random(20260904)
    for text in CORPUS:
        want = tokens_batch(text)
        for trial in range(200):
            k = rng.randrange(0, min(8, len(text)))
            cuts = sorted(rng.sample(range(1, len(text)), k))
            got = tokens_chunked(text, cuts)
            assert got == want, (text, cuts)


def test_chunk_insensitivity_bytes_with_multibyte_splits():
    rng = random.Random(42)
    text = "père(luc). 'é' = X. % café\n".encode("utf-8") + b"a \xff b.\n"
    def run(cuts):
        f = Utf8Feeder(IncrementalLexer(load_lexer()))
        pieces = [text[a:b] for a, b in zip([0] + cuts, cuts + [len(text)])]
        out = []
        for p in pieces:
            f.feed(p)
            while (t := f.next_token()) is not NEED_MORE:
                if t is EOF:
                    break
                out.append((t.kind, t.lexeme))
        f.close()
        while (t := f.next_token()) is not EOF:
            out.append((t.kind, t.lexeme))
        return out
    want = run([])
    for trial in range(200):
        k = rng.randrange(0, 8)
        cuts = sorted(rng.sample(range(1, len(text)), k))
        assert run(cuts) == want, cuts
```

(Delete the dead `drain` sketch before committing — it's shown here only to warn
against writing a helper that swallows NEED_MORE incorrectly; the two real helpers are
the pattern.)

Note: `père` contains `è` which is in no ISO class → each run yields identical error
tokens; that is exactly what the property must preserve. If instead the loader is later
given Unicode classes, this test needs no change.

- [ ] **Step 2: Run.** Expected: PASS. If it fails, minimize (print text+cuts), file the
  bug as a regression test in the owning task's test file, fix, re-run.
- [ ] **Step 3: Commit**

```bash
git add tests/toklex/test_chunking.py
git commit -m "toklex Task 9: chunk-boundary insensitivity property (chars + utf8-split)"
```

---

### Task 10: The tokenizer swap (batch shim + parity)

**Files:**
- Modify: `clausal/tools/prolog_tokenizer.py` — keep `Token`, `TokenType`,
  `TokenizeError` EXACTLY as-is; replace the body of `tokenize()` with the shim; delete
  the `_Tokenizer` class ONLY after parity is proven (same commit, after tests green).
- Test: `tests/toklex/test_parity.py`

**Interfaces:**
- Consumes: `load_lexer`, `IncrementalLexer`.
- Produces: `tokenize(source, *, nested_comments=True) -> list[Token]` — same
  signature, same Token stream, same TokenizeError behavior as today.

Kind→TokenType mapping in the shim:

```python
_KIND_MAP = {
    "lparen": TokenType.LPAREN, "rparen": TokenType.RPAREN,
    "lbracket": TokenType.LBRACKET, "rbracket": TokenType.RBRACKET,
    "lcurly": TokenType.LCURLY, "rcurly": TokenType.RCURLY,
    "bar": TokenType.BAR, "comma": TokenType.COMMA, "end": TokenType.DOT,
    "name_atom": TokenType.ATOM, "graphic_tok": TokenType.ATOM,
    "cut": TokenType.ATOM, "semicolon": TokenType.ATOM,
    "quoted_atom": TokenType.ATOM, "variable": TokenType.VAR,
    "integer": TokenType.INTEGER, "hex_int": TokenType.INTEGER,
    "oct_int": TokenType.INTEGER, "bin_int": TokenType.INTEGER,
    "char_code": TokenType.INTEGER, "float_num": TokenType.FLOAT,
    "string": TokenType.STRING,
}
```

Shim behavior: run the incremental lexer batch; `quoted=True` iff kind == 'quoted_atom';
positions map from Tok.start/end (line/col already 1-based); on an `error` Tok raise
`TokenizeError(reason_message, line, col)` with messages matching the current strings
where tests depend on them (`"Unterminated quoted atom"`, `"Unterminated string"`,
`f"Unexpected character {ch!r}"` — grep `tests/` for asserted message text first and
match ONLY what is asserted); append the END token exactly as today.

**Known divergences** (document in the test file as `EXPECTED_DIVERGENCES` and assert
they behave as described, so they are chosen, not accidental):
- `0x` / `1.5e` with no digits: old raised `TokenizeError("malformed …")`; new lexes
  `0` then `x` (maximal munch + backup — SWI-compatible for `0x`).
- Old accepted `_` inside exponent digits? It did not (`isdigit()` loop) — new spec
  also uses bare `digit` in `exp`; no divergence. Verify with `1e1_0`.

- [ ] **Step 1: Write the parity tests**

```python
# tests/toklex/test_parity.py
"""Old-vs-new tokenizer differential + the swapped tokenize() contract."""
import glob
import pytest
from clausal.tools.prolog_tokenizer import tokenize, Token, TokenType, TokenizeError

NASTY = [
    "foo(X) :- bar(X).", "X =.. L.", "a. ", "1. ", "1.5.", "1.0e7. ", "0'a.",
    "0'''.", "'qu''ote'.", '"str".', "% c\na.", "/* x /* y */ z */a.",
    "[1,2|T].", "{a}.", "a;b.", "!.", "1_000.", "0x1F.", "0o17.", "0b101.",
    "'\\x41\\'.", "'\\q'.", "p :- q, r.", "- 1.", "-1.", "f(-1).",
]


class TestTokenStream:
    @pytest.mark.parametrize("src", NASTY)
    def test_nasty_inputs_produce_expected_shapes(self, src):
        toks = tokenize(src)
        assert toks[-1].type == TokenType.END
        assert all(isinstance(t, Token) for t in toks)

    def test_exact_stream_sample(self):
        toks = tokenize("foo(X) :- 'b ar', 1.5e2. ")
        got = [(t.type, t.value) for t in toks]
        assert got == [
            (TokenType.ATOM, "foo"), (TokenType.LPAREN, "("), (TokenType.VAR, "X"),
            (TokenType.RPAREN, ")"), (TokenType.ATOM, ":-"), (TokenType.ATOM, "b ar"),
            (TokenType.COMMA, ","), (TokenType.FLOAT, 150.0), (TokenType.DOT, "."),
            (TokenType.END, ""),
        ]
        assert toks[5].quoted is True

    def test_errors_still_raise(self):
        with pytest.raises(TokenizeError):
            tokenize("'unterminated")
        with pytest.raises(TokenizeError):
            tokenize('"unterminated')
        with pytest.raises(TokenizeError):
            tokenize("\x01")


SCRYER_LIB = "/workspace/scryer-prolog/src/lib"


class TestScryerCorpus:
    """Differential against the reference corpus: every .pl file the OLD tokenizer
    could tokenize must produce the identical Token list from the NEW one.
    Run BEFORE deleting _Tokenizer; after deletion this class pins the recorded
    token-count snapshot instead (see Step 3)."""

    @pytest.mark.parametrize("path", sorted(glob.glob(SCRYER_LIB + "/*.pl")))
    def test_corpus_file(self, path):
        src = open(path, encoding="utf-8", errors="strict").read()
        try:
            toks = tokenize(src)
        except TokenizeError:
            pytest.skip("file uses syntax outside the dialect (also failed before)")
        assert toks[-1].type == TokenType.END and len(toks) > 1
```

- [ ] **Step 2: BEFORE swapping, capture old-tokenizer output on the corpus**: write a
  scratchpad script that runs current `tokenize()` over every `SCRYER_LIB/*.pl` and
  `NASTY` input, pickling `{path_or_src: [(type.name, value, line, col, quoted)]}` (or
  the raised error type) to the scratchpad. Commit nothing for this step.

- [ ] **Step 3: Implement the shim** in `prolog_tokenizer.py` (old `_Tokenizer` still
  present but unused by `tokenize`). Add a temporary scratchpad differ that replays the
  pickle against the new `tokenize` and prints mismatches. Iterate on the ISO spec /
  shim until the only mismatches are the documented `EXPECTED_DIVERGENCES` (old raised,
  new lexes). Then delete `_Tokenizer` and inline its docstring history into the module
  docstring ("generated behavior; spec: specs/iso.toklex.pl").

- [ ] **Step 4: Full-suite name-diff vs baseline** (Global Constraints). This is the
  gate: `tests/test_prolog_parse.py` and everything else must show an EMPTY name diff.
  Investigate any diff to root cause — no "flake" dismissals without rerunning the
  exact test alone.

- [ ] **Step 5: Commit**

```bash
git add clausal/tools/prolog_tokenizer.py tests/toklex/test_parity.py
git commit -m "toklex Task 10: tokenize() now generated from iso.toklex.pl (parity-proven swap)"
```

---

### Task 11: The Clausal dialect spec

**Files:**
- Create: `clausal/tools/toklex/specs/clausal.toklex.pl`
- Test: `tests/toklex/test_clausal_dialect.py`

**Interfaces:** `load_lexer("clausal") -> Lexer`.

The dialect file = ISO content with these deltas (design §9, rulings of 2026-09-04):
- Add at top: `class(reserved, ['\x1\']).` — **placeholder codepoint U+0001** until the
  Phase 3 ⟨SEP⟩ ruling lands (U+0000 is awkward in a spec file literal; the class is
  one line to change). Subtract it from EVERY class that contains `any`:
  change `def(qitem, ... (any - quote - bslash))` to
  `(any - quote - bslash - reserved)`, same for `ditem`, and for `escape`'s trailing
  `any`, and in `line_comment`'s `(any - nl)` → `(any - nl - reserved)`. The char is
  in no class at all → lexical error ANYWHERE (§9).
- **Delete the `end` token** (no clause terminators — ruling). `.` then lexes as
  `graphic_tok` everywhere.
- Keep `%` line comments until the `#`-vs-`%` ruling (open question; one line later).

- [ ] **Step 1: Write the failing tests**

```python
# tests/toklex/test_clausal_dialect.py
from clausal.tools.toklex import load_lexer
from clausal.tools.toklex.driver import IncrementalLexer


def lex(text):
    return IncrementalLexer(load_lexer("clausal")).run(text)


def test_no_end_token_dot_is_graphic():
    kinds = [t.kind for t in lex("a. ")]
    assert kinds == ["name_atom", "graphic_tok"]      # no 'end' anywhere


def test_directive_surface_tokens():
    toks = lex("-module(m, [f])\n-allow_singletons\n")
    assert [(t.kind, t.lexeme) for t in toks[:3]] == [
        ("graphic_tok", "-"), ("name_atom", "module"), ("lparen", "("),
    ]
    assert toks[2].glue == "glued"                     # -module( is compound-open


def test_reserved_codepoint_rejected_everywhere():
    for src in ["a\x01b ", "'a\x01b' ", '"a\x01b" ', "% c\x01c\na "]:
        kinds = [t.kind for t in lex(src)]
        assert "error" in kinds, src


def test_optional_module_level_comma_is_just_a_token():
    kinds = [t.kind for t in lex("f(a), g(b)\n")]
    assert kinds.count("comma") == 2                   # L1 policy, not lexer's business


def test_iso_lexer_unaffected():
    kinds = [t.kind for t in IncrementalLexer(load_lexer("iso")).run("a. ")]
    assert kinds == ["name_atom", "end"]
```

- [ ] **Step 2: Run, verify fail. Step 3: Write the spec file. Step 4: Run, verify pass.**
- [ ] **Step 5: Commit**

```bash
git add clausal/tools/toklex/specs/clausal.toklex.pl tests/toklex/test_clausal_dialect.py
git commit -m "toklex Task 11: clausal dialect spec (no end token, reserved codepoint everywhere)"
```

---

### Task 12: DCG renderer + Scryer golden test

**Files:**
- Create: `clausal/tools/toklex/dcg.py`
- Test: `tests/toklex/test_dcg.py`

**Interfaces:**
- Consumes: `Lexer` (Task 5).
- Produces: `render_dcg(lexer, module_name="toklex_iso") -> str` — a complete Prolog
  module: one `q<N>//2` nonterminal per DFA state threading `(PendingRev, Result)`,
  `toklex_tokens(Ts)//0` top loop, `toklex_symbol(Char, Sym)` facts generated from the
  partition legend (interval membership via `between/3` on codes), backup rendered as
  DCG right-hand-side pushback (design §10 sketch — the `q13(Pnd, T), ['.']  -->` form),
  follow checks via one-symbol lookahead `peek//1`, trivia skipped, nest via a depth
  argument. **v1 scope:** chars mode, token kinds + lexemes as char lists (NO value
  builders, no glue, no spans) — enough to prove the automaton renders and runs; say so
  in the module header comment.

- [ ] **Step 1: Write the failing tests**

```python
# tests/toklex/test_dcg.py
import os
import subprocess
import pytest
from clausal.tools.toklex import load_lexer
from clausal.tools.toklex.driver import IncrementalLexer
from clausal.tools.toklex.dcg import render_dcg

SCRYER = "/workspace/scryer-prolog/target/release/scryer-prolog"
SAMPLES = ["foo(X, 1). ", "=.. = . ", "1. 1.5 1.0e7 ", "'a''b' \"s\" 0'a ",
           "/* c /* n */ */ x ", "a. "]


def test_render_is_nonempty_and_mentions_every_state():
    lx = load_lexer()
    src = render_dcg(lx)
    assert ":- module(" in src or "% toklex" in src
    for q in range(len(lx.dfa.delta)):
        assert f"q{q}(" in src


@pytest.mark.skipif(not os.path.exists(SCRYER), reason="scryer binary not present")
@pytest.mark.parametrize("sample", SAMPLES)
def test_scryer_agrees_with_python_driver(tmp_path, sample):
    lx = load_lexer()
    pl = tmp_path / "toklex_iso.pl"
    pl.write_text(render_dcg(lx))
    goal = (
        f'consult(\'{pl}\'), toklex_run("{sample}", Ts), '
        f"write_canonical(Ts), nl, halt."
    )
    out = subprocess.run([SCRYER, "-g", goal], capture_output=True, text=True,
                         timeout=60).stdout.strip()
    py = IncrementalLexer(lx).run(sample)
    want = "[" + ",".join(f"tok({t.kind},\"{t.lexeme}\")" for t in py) + "]"
    # normalize scryer's char-list printing before comparing
    assert _normalize(out) == _normalize(want)


def _normalize(s):
    return s.replace(" ", "").replace('"', "").replace("'", "")
```

(`toklex_run/2` is a generated helper: string→chars, phrase the token loop, map to
`tok(Kind, Lexeme)` pairs. The `_normalize` comparison is deliberately blunt — kinds
and lexeme content, not quoting style. If Scryer's `-g` quoting fights back, write the
goal into a second consulted file instead of passing it on the command line.)

- [ ] **Step 2: Run, verify fail. Step 3: Implement `render_dcg`.** Generation order:
  header (module decl + `:- use_module(library(between)).` etc. as needed), symbol
  facts from partition cells, `peek//1` + `at_eof//0` helpers, state nonterminals
  (per state: one clause per outgoing symbol group, then the resolve clause carrying
  the recorded-accept logic — mirror the driver's `_resolve`, simplified: v1 may
  restrict follow handling to the `end` rule shape), nest depth clauses, top loop.
  Keep it boring and explicit; this file is meant to be READ by Prolog people.
- [ ] **Step 4: Run (with Scryer), verify pass. Step 5: Commit**

```bash
git add clausal/tools/toklex/dcg.py tests/toklex/test_dcg.py
git commit -m "toklex Task 12: DCG renderer; Scryer agrees with the Python driver on samples"
```

---

### Task 13: Close-out

**Files:**
- Modify: `implementation_plans/toklex-token-formalism-design.md` (status header →
  implemented, with commit range), `implementation_plans/prolog-parser-formalism-handoff.md`
  (add a one-line "DONE — see toklex-implementation-plan.md" note at top).
- No code.

- [ ] **Step 1:** Final full-suite name-diff vs baseline (empty), `git stash list`
  empty, `git log --oneline` shows one commit per task with trailers.
- [ ] **Step 2:** Whole-branch review (roborev per project practice); fix findings;
  re-run affected tests. Verify any reviewer claim against the code before acting on it.
- [ ] **Step 3:** Update the two docs; commit:

```bash
git add implementation_plans/toklex-token-formalism-design.md implementation_plans/prolog-parser-formalism-handoff.md
git commit -m "toklex Task 13: close-out — design doc status + handoff marked done"
```

- [ ] **Step 4:** Report to the user: divergence list from Task 10, the `def/2`
  notation addition, the U+0001 reserved-codepoint placeholder awaiting the ⟨SEP⟩
  ruling, the `%`-comment placeholder awaiting the `#` ruling, and DCG v1 scope
  (kinds+lexemes only).

## Self-review record

- **Spec coverage:** §3 notation → Tasks 1, 3 (incl. `def/2` deviation, locked
  decision #2); §4 semantics → Tasks 4, 5; §5 peek/pushback → Task 6 (driver `_unread`);
  §6 incrementality + conformance property → Tasks 6, 9; §6.1 R6 → Task 7; §7 worked
  examples → Task 8 tests verbatim; §8 Glue/spans → Task 6; §9 dialect deltas → Task 11;
  §10 targets → Tasks 6 (step function), 12 (DCG); §11 "Clausal hosts first compiler" →
  the whole plan; annotated-DFA dump (§4.4) → Task 5 `dump_term`. Not implemented
  anywhere (deliberate, design-consistent): DCG builders/spans (v1 scope note),
  minimization (locked decision #3).
- **Type consistency:** `Tok(kind, value, lexeme, start, end, glue)` used identically
  in Tasks 6-12; `Lexer` fields fixed in Task 5 and only read afterwards; `DFA.accepts`
  is a tuple of label-tuples everywhere (Task 4 def, Task 5/6 reads).
- **Placeholder scan:** the only intentional placeholders are the two flagged surface
  rulings (⟨SEP⟩ final codepoint, `#` vs `%`), which are USER decisions parked by
  design, with one-line change paths recorded in Task 11.
