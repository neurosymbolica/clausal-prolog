# Prolog Reader L1/L2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the §1c L1 term reader and L2 item classification: a resumable
`PrologReader` over the toklex L0 that emits `ReaderItem`s — pure cell trees, `VarRef` +
`var_names`, structure-isomorphic span trees — ready for the Phase 3 compiler to consume.

**Architecture:** The existing Pratt core (`prolog_parser.py`) stays the single term
parser — L1 wraps it per item: toklex tokens are buffered until an `end` token, parsed
with a persistent reader-owned `OperatorTable` (op/3 auto-application comes free from
`_classify_item`), and the resulting P-tree is transformed into (cell tree, span tree,
var_names). Spans flow token→P-node→cell via two additive field pluggings (Token gains
character offsets; P-nodes gain a compare-excluded `span`). Item-granular resumability:
`read_term()` returns `NEED_MORE` until a full item is buffered; `SyntaxIssue` +
resync-to-`end` for recovery. ISO (dot-terminated) surface only — the no-dots clausal
item policy stays parked with its open rulings.

**Tech Stack:** Pure Python 3 stdlib; existing `clausal/tools/` modules (toklex L0,
prolog_parser, prolog_ast, prolog_operators); pytest.

**Spec:** `implementation_plans/tagged-tuple-term-representation.md` §1c (the contract;
user-approved 2026-09-03) and §1b (cons-cell ruling for partial/improper lists).
Background: §1a, the toklex design doc §8 (token output).

## Global Constraints

- **CLONE ONLY**: all work in a worktree of `/workspace/clausal-bug-fix`. Never touch
  `/workspace/clausal`.
- Test python: `/workspace/clausal/venv/bin/python`, invoked FROM the worktree.
- Full-suite baseline: reuse
  `/tmp/claude-1000/-workspace-clausal-bug-fix/1b55f45b-63fb-4ad0-b271-2e4afd8b1e55/scratchpad/baseline_names_242cc8db.txt`
  (146 names; every full-suite gate since has been an empty diff against it). Compare
  failure NAME sets, never counts.
- **NEVER `git add -A`. NEVER `git stash`.** Stage explicit paths. Check `git stash list`
  after implementers.
- Commit trailers on every commit:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_01G7xiWqatWtL6zNQDc7nspk`
- No new dependencies. No C changes (fresh worktrees still need
  `setup.py build_ext --inplace` before full-suite runs).
- Existing P-node equality semantics MUST NOT change (span fields are
  `compare=False`); `tests/test_prolog_parse.py` and the toklex suites stay green
  throughout.
- §1c contract wording is binding; concrete realizations locked below (span-tree shape,
  `Clause.term` = whole item term). One recorded contract caveat: §1c calls parser
  output "hashable", but the proper-list ruling (Python lists) makes cell trees
  containing lists unhashable — follow the LIST ruling, document the caveat, do not
  convert lists to tuples.

## File Structure

```
clausal/tools/prolog_tokenizer.py   MODIFY: Token gains offset/end_offset (compare=False);
                                    shim fills them from Tok.start[0]/end[0]
clausal/tools/prolog_ast.py         MODIFY: every P-term node gains
                                    span: tuple | None = field(default=None, compare=False)
clausal/tools/prolog_parser.py      MODIFY: record spans at every node construction site
clausal/tools/prolog_reader.py      CREATE: VarRef, ReaderItem types, the P->cell
                                    transformer, PrologReader (L1+L2), read_module()
tests/toklex/test_reader_transform.py   CREATE (transformer unit tests)
tests/toklex/test_reader_incremental.py CREATE (PrologReader feed/NEED_MORE/EOF/ops)
tests/toklex/test_reader_recovery.py    CREATE (SyntaxIssue + resync)
tests/toklex/test_reader_corpus.py      CREATE (scryer corpus end-to-end)
tests/test_prolog_parse.py          MODIFY (Task 2 only): span-recording assertions appended
```

Locked design decisions (deviations need a controller ruling):
1. **Spans are character-offset pairs** `(start, end)` (end exclusive), from toklex
   `Tok.start[0]`/`Tok.end[0]`. Line/col live on tokens for diagnostics; the span tree
   carries offsets only.
2. **Span-tree realization of §1c.3** (structure-isomorphic, leaves `(start, end)`):
   - leaf cells (atom str, number, `VarRef`, char list from a double-quoted token):
     `(start, end)`
   - compound cell `(f, a1..aN)`: `((start, end), span(a1), ..., span(aN))` — a tuple of
     N+1 entries whose head is the whole-term span
   - Python-list cell `[e1..eN]`: `((start, end), [span(e1), ..., span(eN)])`
   - cons cell `('.', H, T)` (improper/partial lists): compound shape, synthesized spans
     for the nested tails reuse the source extent of the remaining-list region
   - curly `('{}', B)`: compound shape.
3. **`Clause.term` is the whole item term as read**: for a rule, the cell
   `(':-', Head, Body)`; for a fact, the head cell itself. `Directive.term`/`Query.term`
   are the body cell (matching `PDirective`/`PQuery`); `DCGRule.term` is
   `('-->', Head, Body)`. The dataclass type IS the L2 classification; the compiler
   destructures.
4. **`var_names` on ALL item kinds** (directives and queries bind variables too);
   `VarRef` indices are first-occurrence order within the item; each anonymous `_`
   occurrence gets a fresh index with name `"_"`.
5. **L0 driver**: `RegexLexer` by default with the `SpecError`-fallback to
   `IncrementalLexer` (same policy as the shim); `PrologReader(lexer=...)` accepts an
   injected L0 for tests.
6. **Resumability is item-granular**: tokens buffer until an `end` token; `NEED_MORE`
   until then. This satisfies §1c (`read_term() -> ReaderItem | NEED_MORE | EOF`; no
   seeking) without making the Pratt core incremental.
7. **Recovery**: an L0 `error` token or a `ParseError` inside an item yields
   `SyntaxIssue(span, message, resumable=True)` and resyncs to the next `end` token
   (§1c's resync-to-`.`). At EOF with a non-empty partial item: one
   `SyntaxIssue(..., resumable=False)`, then `EOF`.

---

### Task 1: Token character offsets

**Files:**
- Modify: `clausal/tools/prolog_tokenizer.py` (Token dataclass + the shim's Token
  construction; also the END-token append)
- Test: `tests/toklex/test_parity.py` (append one test class)

**Interfaces:**
- Produces: `Token.offset: int` and `Token.end_offset: int`, both
  `field(default=-1, compare=False, repr=False)` — additive, equality/repr unchanged.
  The shim fills them from `Tok.start[0]`/`Tok.end[0]`; the synthetic END token gets
  `offset = end_offset = len(source)`. `_bootstrap.py`'s Token constructions are NOT
  touched (bootstrap-read spec files never need spans; their tokens keep -1).

- [ ] **Step 1: Write the failing test** (append to `tests/toklex/test_parity.py`):

```python
class TestTokenOffsets:
    def test_offsets_populated_by_shim(self):
        toks = tokenize("foo( X , 12 ).\n")
        assert [(t.type.value, t.offset, t.end_offset) for t in toks] == [
            ("atom", 0, 3), ("(", 3, 4), ("var", 5, 6), (",", 7, 8),
            ("integer", 9, 11), (")", 12, 13), (".", 13, 14), ("end", 15, 15),
        ]

    def test_offsets_excluded_from_equality(self):
        a = Token(TokenType.ATOM, "x", 1, 1)
        b = Token(TokenType.ATOM, "x", 1, 1, offset=5, end_offset=6)
        assert a == b
```

- [ ] **Step 2: Run, verify fail** (`TypeError: unexpected keyword` / attribute missing).
- [ ] **Step 3: Implement**: add the two fields after `end_col` in the Token dataclass
  (same `compare=False, repr=False` style); in the shim's token loop pass
  `offset=t.start[0], end_offset=t.end[0]`; for the END token compute
  `offset=end_offset=len(source)`.
- [ ] **Step 4: Run** `tests/toklex/ tests/test_prolog_parse.py` — all green.
- [ ] **Step 5: Commit** (stage exactly the two files).

---

### Task 2: P-node spans + parser span recording

The invasive task: every P-term node gains a compare-excluded `span`, and
`prolog_parser.py` populates it at every construction site. Existing equality-based
tests must be provably unaffected.

**Files:**
- Modify: `clausal/tools/prolog_ast.py` (7 term dataclasses), `clausal/tools/prolog_parser.py`
- Test: `tests/test_prolog_parse.py` (append a span test class)

**Interfaces:**
- Produces: `PAtom/PVar/PNumber/PString/PCompound/PList/PCurly` each gain
  `span: tuple | None = field(default=None, compare=False)` (keep `slots=True`; the
  field must be LAST so positional construction stays valid). Parser guarantee: when
  input tokens carry offsets (>= 0), every node's `span=(start_offset, end_offset)`
  covers the node's full source extent, including parens around a parenthesized term
  being ATTRIBUTED TO THE INNER TERM'S span? NO — locked: a parenthesized term's span
  covers the parens (`(a)` spans the '(' through ')'), an operator compound spans from
  its leftmost operand token to its rightmost, a compound f(...) spans functor through
  ')', a list '[' through ']', curly '{' through '}'. When offsets are -1 (bootstrap
  tokens), spans come out as garbage negative tuples — acceptable; document that spans
  are meaningful only via the shim path.

- [ ] **Step 1: Write failing tests** (append to `tests/test_prolog_parse.py`):

```python
class TestSpans:
    def _term(self, src):
        from clausal.tools.prolog_parser import parse_term
        return parse_term(src)

    def test_atom_number_var_spans(self):
        t = self._term("foo")
        assert t.span == (0, 3)
        assert self._term("42").span == (0, 2)
        assert self._term("Xyz").span == (0, 3)

    def test_compound_and_arg_spans(self):
        t = self._term("foo(bar, 12)")
        assert t.span == (0, 12)
        assert t.args[0].span == (4, 7)
        assert t.args[1].span == (9, 11)

    def test_operator_compound_spans(self):
        t = self._term("a + b * c")
        assert t.span == (0, 9)          # the whole +
        assert t.args[0].span == (0, 1)  # a
        assert t.args[1].span == (4, 9)  # b * c

    def test_list_and_curly_spans(self):
        t = self._term("[a, b | T]")
        assert t.span == (0, 10)
        assert t.elements[1].span == (4, 5)
        assert t.tail.span == (8, 9)
        assert self._term("{x}").span == (0, 3)

    def test_parenthesized_span_covers_parens(self):
        t = self._term("( a )")
        assert t.span == (0, 5)

    def test_quoted_atom_span(self):
        t = self._term("'a b'")
        assert t.span == (0, 5)

    def test_equality_unaffected(self):
        from clausal.tools.prolog_ast import PAtom
        assert self._term("foo") == PAtom("foo")
```

- [ ] **Step 2: Run, verify fail** (span is None).
- [ ] **Step 3: Implement.** prolog_ast: add the field to the seven term dataclasses
  (LAST field, default None, `compare=False`). prolog_parser: thread spans —
  * primaries built from one token: `span=(tok.offset, tok.end_offset)`;
  * compounds `f(args)`: `(functor_tok.offset, rparen_tok.end_offset)`;
  * operator compounds (infix/prefix/postfix): combine operand spans and operator token
    (`min(start...), max(end...)`) — a small helper `_span_join(*spans_and_tokens)`;
  * lists/curly: bracket tokens; parenthesized terms: rebuild the inner node with the
    paren span via `dataclasses.replace(node, span=...)`;
  * negative-literal folding and any other node-synthesis sites: preserve/derive spans
    the same way (grep every `PAtom(`/`PVar(`/`PNumber(`/`PString(`/`PCompound(`/
    `PList(`/`PCurly(` construction in the file and handle EACH — list them in your
    report).
- [ ] **Step 4: Run** `tests/test_prolog_parse.py tests/toklex/` — all green. The
  toklex spec loader also runs through this parser (via `_bootstrap` tokens with -1
  offsets): confirm `tests/toklex/test_spec_loader.py` is green (it must be — spans are
  compare-excluded and never read there).
- [ ] **Step 5: Full-suite name-diff vs baseline** (controller runs it too): empty.
- [ ] **Step 6: Commit.**

---

### Task 3: ReaderItem IR + the P→cell transformer

**Files:**
- Create: `clausal/tools/prolog_reader.py` (IR + transformer half)
- Test: `tests/toklex/test_reader_transform.py`

**Interfaces (frozen for Tasks 4-6 and the Phase 3 compiler):**

```python
@dataclass(frozen=True, slots=True)
class VarRef:
    i: int

@dataclass(frozen=True, slots=True)
class Clause:      # fact or rule; term = whole item term as read
    term: object; spans: object; var_names: dict
@dataclass(frozen=True, slots=True)
class Directive:   # term = directive body
    term: object; spans: object; var_names: dict
@dataclass(frozen=True, slots=True)
class DCGRule:     # term = ('-->', H, B)
    term: object; spans: object; var_names: dict
@dataclass(frozen=True, slots=True)
class Query:       # term = query body
    term: object; spans: object; var_names: dict
@dataclass(frozen=True, slots=True)
class SyntaxIssue:
    span: tuple; message: str; resumable: bool

def transform_term(pterm) -> tuple[object, object, dict[int, str]]:
    """P-tree -> (cell, span_tree, var_names) per the locked decisions."""
```

Cell mapping (§1b/§1c, binding): `PAtom` → `name` str (quoted or not — mangling is the
compiler's job); `PNumber` → native value; `PString` → **list of 1-char strings** (char
list; empty string → `[]`); `PCompound(f, args)` → `(f, *cells)`; proper `PList` →
Python list; `PList` with tail → right-nested cons cells `('.', H, T)` ending at the
transformed tail; `PCurly(b)` → `('{}', cell(b))`; `PVar` → `VarRef(i)` with
first-occurrence numbering, fresh index per `_` occurrence. Span tree per locked
decision 2; cons-cell span nodes reuse the remaining-list extent (from the element/tail
spans available on the P-nodes; when a P-node span is None — hand-built trees in tests —
emit `(-1, -1)` leaves rather than crashing).

- [ ] **Step 1: Write the failing tests:**

```python
# tests/toklex/test_reader_transform.py
from clausal.tools.prolog_parser import parse_term
from clausal.tools.prolog_reader import VarRef, transform_term


def tt(src):
    return transform_term(parse_term(src))


class TestCells:
    def test_atoms_numbers(self):
        assert tt("foo")[0] == "foo"
        assert tt("'b ar'")[0] == "b ar"
        assert tt("42")[0] == 42
        assert tt("1.5")[0] == 1.5

    def test_compound_and_nesting(self):
        cell, spans, vn = tt("f(a, g(1), X)")
        assert cell == ("f", "a", ("g", 1), VarRef(0))
        assert vn == {0: "X"}

    def test_proper_list_is_python_list(self):
        assert tt("[a, 1, [b]]")[0] == ["a", 1, ["b"]]

    def test_partial_list_is_cons_cells(self):
        cell, _, vn = tt("[a, b | T]")
        assert cell == (".", "a", (".", "b", VarRef(0)))
        assert vn == {0: "T"}

    def test_double_quoted_is_char_list(self):
        assert tt('"ab"')[0] == ["a", "b"]
        assert tt('""')[0] == []

    def test_curly(self):
        assert tt("{a, b}")[0] == ("{}", (",", "a", "b"))

    def test_var_numbering_first_occurrence_and_anon(self):
        cell, _, vn = tt("f(X, Y, X, _, _)")
        assert cell == ("f", VarRef(0), VarRef(1), VarRef(0), VarRef(2), VarRef(3))
        assert vn == {0: "X", 1: "Y", 2: "_", 3: "_"}

    def test_output_is_ground_data(self):
        cell, _, _ = tt("f(g(h(1)), a)")
        assert hash(cell) is not None  # all-tuple trees hash (list caveat documented)


class TestSpanTrees:
    def test_leaf_and_compound_iso_structure(self):
        cell, spans, _ = tt("f(ab, 12)")
        assert spans[0] == (0, 9)        # whole compound
        assert spans[1] == (2, 4)        # ab
        assert spans[2] == (6, 8)        # 12
        assert len(spans) == 1 + (len(cell) - 1)

    def test_list_span_shape(self):
        cell, spans, _ = tt("[a, b]")
        whole, elems = spans
        assert whole == (0, 6)
        assert elems[0] == (1, 2) and elems[1] == (4, 5)

    def test_charlist_is_leaf_span(self):
        cell, spans, _ = tt('"ab"')
        assert cell == ["a", "b"] and spans == (0, 4)
```

- [ ] **Step 2: Run, verify fail. Step 3: Implement** `prolog_reader.py`'s IR +
  `transform_term` (a recursive walker carrying a mutable var-index dict; ~120 lines).
- [ ] **Step 4: Run, verify pass. Step 5: Commit.**

---

### Task 4: PrologReader — the incremental L1 core

**Files:**
- Modify: `clausal/tools/prolog_reader.py` (add PrologReader + read_module)
- Test: `tests/toklex/test_reader_incremental.py`

**Interfaces:**

```python
from clausal.tools.toklex.driver import NEED_MORE, EOF   # re-exported by the reader

class PrologReader:
    def __init__(self, *, op_table=None, dialect=None, nested_comments=True, lexer=None):
        """op_table precedence: explicit > dialect.operator_table > swi_default().
        The reader OWNS the table for its lifetime; op/3 directives apply to it."""
    def feed(self, text: str) -> None: ...
    def close(self) -> None: ...
    def read_term(self):  # -> ReaderItem | NEED_MORE | EOF
        ...

def read_module(source: str, **kw) -> list:
    """Batch helper: feed+close+drain (SyntaxIssues included in the list)."""
```

Mechanics (binding):
- Internal L0: `RegexLexer(load_lexer(), nested_comments=...)` guarded by the same
  `SpecError` fallback to `IncrementalLexer`; or the injected `lexer`.
- `read_term()` loop: pull L0 tokens; `NEED_MORE` propagates; buffer `Tok`s until one
  with `kind == "end"`; then (a) convert the buffered Toks to compat `Token`s (reuse the
  shim's `_KIND_MAP` — import it — plus offsets/quoted, appending the END sentinel),
  (b) run `PrologParser(tokens, self._op_table)` — call its single-item entry
  (`parse_program()` returns a PModule; with exactly one item's tokens it yields one
  PItem — use that, asserting len==1), (c) `transform_term` the item's P-term(s) into
  the matching ReaderItem type. Classification mapping: `PClause(h, None)` →
  `Clause(term=cell(h))`; `PClause(h, b)` → `Clause(term=(':-', cell(h), cell(b)))`
  with the span tree correspondingly shaped from the two subtree span trees plus the
  item extent; `PDirective(b)` → `Directive(cell(b))`; `PQuery(b)` → `Query(cell(b))`;
  `PDCGRule(h, b)` → `DCGRule(('-->', ...))`. IMPORTANT: run `transform_term` ONCE per
  item on a synthetic whole-item P-term where needed so VarRef numbering is shared
  across head and body (e.g. transform `PCompound(':-', (h, b))` directly).
- op/3 persistence: `_classify_item` already applies op directives to the table the
  parser was constructed with — the reader passes ITS table, so effects persist to
  later items. Test with a custom op used AFTER its directive (and confirm a
  fresh-reader parse of the same later item FAILS without the directive).
- L0 `error` Toks and parse failures are Task 5's scope — in this task, let them raise;
  keep the wiring simple.
- EOF: L0 EOF with an empty buffer → EOF forever. (Non-empty buffer at EOF: Task 5.)

- [ ] **Step 1: Write the failing tests:**

```python
# tests/toklex/test_reader_incremental.py
from clausal.tools.prolog_reader import (
    Clause, DCGRule, Directive, EOF, NEED_MORE, PrologReader, Query, VarRef, read_module,
)


class TestBatch:
    def test_fact_rule_directive_query_dcg(self):
        items = read_module(
            "foo(a).\n"
            "bar(X) :- foo(X).\n"
            ":- dynamic(baz/1).\n"
            "?- foo(a).\n"
            "greet --> [hello].\n")
        kinds = [type(i).__name__ for i in items]
        assert kinds == ["Clause", "Clause", "Directive", "Query", "DCGRule"]
        assert items[0].term == ("foo", "a")
        assert items[1].term == (":-", ("bar", VarRef(0)), ("foo", VarRef(0)))
        assert items[1].var_names == {0: "X"}
        assert items[2].term == ("dynamic", ("/", "baz", 1))
        assert items[4].term == ("-->", "greet", ["hello"])

    def test_shared_var_numbering_across_head_and_body(self):
        (item,) = read_module("p(X, Y) :- q(Y, X).\n")
        assert item.term == (":-", ("p", VarRef(0), VarRef(1)),
                             ("q", VarRef(1), VarRef(0)))

    def test_item_spans_present(self):
        (item,) = read_module("foo(bar).")
        assert item.spans[0] == (0, 8)   # the compound foo(bar)


class TestIncremental:
    def test_need_more_until_end_token(self):
        r = PrologReader()
        r.feed("foo(a)")
        assert r.read_term() is NEED_MORE
        r.feed(". bar")
        item = r.read_term()
        assert isinstance(item, Clause) and item.term == ("foo", "a")
        assert r.read_term() is NEED_MORE   # 'bar' could extend / no end yet
        r.feed("(b).")
        r.close()
        assert r.read_term().term == ("bar", "b")
        assert r.read_term() is EOF
        assert r.read_term() is EOF

    def test_op_directive_applies_to_later_items(self):
        src = ":- op(700, xfx, ===).\na === b.\n"
        items = read_module(src)
        assert items[1].term == ("===", "a", "b")
        # and without the directive the same item does not parse cleanly
        from clausal.tools.prolog_reader import SyntaxIssue
        naked = read_module("a === b.\n")
        assert any(isinstance(i, SyntaxIssue) for i in naked) or \
            naked[0].term != ("===", "a", "b")
```

(The last assertion tolerates Task-5-not-yet-built error behavior: before Task 5 an
unparseable item may raise — wrap that call in `pytest.raises` OR mark the naked-parse
half `xfail(strict=False)` until Task 5, and note it; Task 5 flips it to the
SyntaxIssue assertion.)

- [ ] **Step 2: Run, verify fail. Step 3: Implement** (~150 lines).
- [ ] **Step 4: Run** `tests/toklex/ tests/test_prolog_parse.py` — green.
- [ ] **Step 5: Commit.**

---

### Task 5: SyntaxIssue + resync recovery

**Files:**
- Modify: `clausal/tools/prolog_reader.py`
- Test: `tests/toklex/test_reader_recovery.py` (+ un-xfail the Task 4 note if used)

**Interfaces:** already-frozen `SyntaxIssue(span, message, resumable)`. Behavior
(binding):
- A `ParseError` from the Pratt on a buffered item → `SyntaxIssue(span=(item_start,
  item_end), message=str(exc), resumable=True)`; the buffer for that item is dropped
  (the `end` token was already its boundary — resync is inherent), reading continues.
- An L0 `error` Tok inside an item: buffer it; when the item closes (next `end`) emit
  ONE SyntaxIssue for the item span with the lexical message; if the L0 error is an
  `unterminated` at EOF (no `end` ever comes), fall through to the EOF path.
- EOF with a non-empty buffered partial item → `SyntaxIssue(span=(item_start, eof),
  message="unterminated item (missing end token)" or the lexical error's message,
  resumable=False)`, then `EOF`.
- `read_module` collects SyntaxIssues inline (already specified).

- [ ] **Step 1: Write the failing tests:**

```python
# tests/toklex/test_reader_recovery.py
from clausal.tools.prolog_reader import Clause, SyntaxIssue, read_module


class TestRecovery:
    def test_bad_item_resyncs_to_next_end(self):
        items = read_module("foo(a).\n)(bad syntax.\nbar(b).\n")
        assert [type(i).__name__ for i in items] == ["Clause", "SyntaxIssue", "Clause"]
        assert items[2].term == ("bar", "b")
        assert items[1].resumable is True
        s, e = items[1].span
        assert s >= 8 and e <= 22

    def test_unterminated_final_item(self):
        items = read_module("foo(a).\nbar(b")
        assert [type(i).__name__ for i in items] == ["Clause", "SyntaxIssue"]
        assert items[1].resumable is False

    def test_lexical_error_becomes_issue(self):
        items = read_module("foo(a).\nb\x01ad.\nok(c).\n")
        kinds = [type(i).__name__ for i in items]
        assert kinds == ["Clause", "SyntaxIssue", "Clause"]

    def test_unterminated_quote_at_eof(self):
        items = read_module("foo(a).\n'never closed")
        assert type(items[-1]).__name__ == "SyntaxIssue"
        assert items[-1].resumable is False

    def test_issue_positions_are_offsets(self):
        items = read_module("foo(a).\n)(x.\n")
        s, e = items[1].span
        assert isinstance(s, int) and isinstance(e, int) and 0 <= s < e
```

- [ ] **Step 2: Run, verify fail. Step 3: Implement. Step 4: Green (incl. flipping any
  Task-4 xfail). Step 5: Commit.**

---

### Task 6: Corpus integration + exports + gates

**Files:**
- Modify: `clausal/tools/prolog_reader.py` (only if corpus reveals defects — each fix
  gets a regression test), `clausal/tools/toklex/__init__.py` is NOT touched (reader is
  a sibling module, not part of the toklex package)
- Test: `tests/toklex/test_reader_corpus.py`

- [ ] **Step 1: Write the corpus test:**

```python
# tests/toklex/test_reader_corpus.py
import glob

import pytest

from clausal.tools.prolog_reader import SyntaxIssue, read_module

CORPUS = sorted(glob.glob("/workspace/scryer-prolog/src/lib/**/*.pl", recursive=True))


@pytest.mark.parametrize("path", CORPUS or
    [pytest.param(None, marks=pytest.mark.skip(reason="corpus absent"))])
def test_corpus_reads_with_low_issue_rate(path):
    src = open(path, encoding="utf-8").read()
    items = read_module(src)
    assert items, path
    issues = [i for i in items if isinstance(i, SyntaxIssue)]
    # dialect gaps (0'\ shapes the old tokenizer also rejected, exotic ops)
    # may produce issues; the gate is that the reader RECOVERS and the
    # overwhelming majority of items parse.
    assert len(issues) <= max(2, len(items) // 20), (
        path, len(issues), len(items), issues[:3])


def test_spot_check_known_file():
    src = open("/workspace/scryer-prolog/src/lib/lists.pl", encoding="utf-8").read()
    items = read_module(src)
    from clausal.tools.prolog_reader import Clause, Directive
    assert isinstance(items[0], Directive)          # :- module(...)
    assert any(isinstance(i, Clause) for i in items)
    assert not any(isinstance(i, SyntaxIssue) for i in items)
```

  (If `lists.pl` starts with something other than a module directive, adjust the
  spot-check to the file's real shape — verify by reading the file's head first, and
  say so in the report.)
- [ ] **Step 2: Run; drive any failures to root cause.** A corpus file tripping the
  issue-rate gate means a real reader defect OR a real dialect gap — classify each in
  the report; dialect gaps get the threshold documented, defects get fixed with
  regression tests.
- [ ] **Step 3: Run the full covering set:**
  `tests/toklex/ tests/test_prolog_parse.py tests/audit_2026_07_05/test_11_modules_interop.py` — green.
- [ ] **Step 4: Full-suite name-diff vs baseline (controller gate): empty.**
- [ ] **Step 5: Commit.**

---

### Task 7: Close-out

**Files:**
- Modify: `implementation_plans/tagged-tuple-term-representation.md` (§1c: add a
  STATUS line — L0/L1/L2 implemented, module paths, the hashability caveat, the
  span-tree realization decisions 1-4 from this plan's locked list)
- No code.

- [ ] **Step 1:** Final `git stash list` empty; log shows one commit per task with
  trailers; whole-branch review (controller dispatches); fix wave if findings.
- [ ] **Step 2:** Doc edit + commit.
- [ ] **Step 3:** Controller: memory update + report to user.

## Self-review record

- **Spec coverage:** §1c L1 (`read_term -> ReaderItem | NEED_MORE | EOF`, op-table
  ownership + auto-apply) → Task 4; ReaderItem field shapes + pure cells + VarRef +
  ground data → Task 3; span trees → Tasks 1-3 (plumbing) + locked decision 2;
  cons-cell ruling → Task 3; SyntaxIssue + resync → Task 5; L2 classification → Task 4
  (via `_classify_item` mapping); formalism-agnostic L0 boundary → locked decision 5
  (injected lexer). Hashability caveat recorded rather than resolved (contract tension,
  Global Constraints).
- **Type consistency:** `VarRef(i)`, item dataclass field order `(term, spans,
  var_names)`, `SyntaxIssue(span, message, resumable)` used identically in Tasks 3-6;
  `Token.offset/end_offset` names consistent Tasks 1-2.
- **Placeholder scan:** none; the two adjust-if-reality-differs notes (lists.pl head,
  Task-4 xfail) are explicit contingencies with instructions, not TBDs.
