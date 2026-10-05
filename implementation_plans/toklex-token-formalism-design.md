# toklex: a token-layer formalism for Prolog readers

**Status: IMPLEMENTED 2026-09-04 — branch feat/toklex (f4316f36..HEAD), per
`implementation_plans/toklex-implementation-plan.md`. The generated tokenizer replaced
`prolog_tokenizer.py`'s hand-written scanner with an EMPTY full-suite failure-name
diff; the DCG rendering runs under Scryer and agrees with the Python driver. §4.3 was
REVISED during implementation (commit regions — see the amendment in that section):
real ISO tokens falsified the original unconditional-rejection rule exactly as §13's
external question 4 invited.**

This document is written to be readable outside the Clausal codebase. Clausal-specific
material is confined to §9 and the appendix; everything before it describes a formalism
any Prolog reader could adopt.

## 1. Problem

Prolog term syntax needs no grammar formalism: its variable part is precedence-shaped,
`op/3` *is* the grammar, and a runtime-mutable Pratt/precedence-climbing core handles it.
The **token layer** is where an actual open problem lives. The requirements (Markus
Triska, 2026-09-03, on what a Prolog-in-Prolog reader needs):

> "we need to find a good formalism to write it, something that is then compiled to a
> DCG. it must be able to 'peek ahead' to see whether the current token will be extended,
> and be able to push characters to the stream, or remember that they were present, for
> the next token. it must be able to be used from streams that are not repositionable,
> like user input: in this case, it must be able to wait for more input."

Unpacked, that is four requirements:

- **R1 (formalism, DCG target):** the tokenizer is *written in* something declarative and
  *compiled to* a DCG — not hand-written as one.
- **R2 (peek):** never emit a token that unseen input could still extend (`=` vs `=..`,
  `1` vs `1.5` vs `1.0e7`, `0'c`, quoted atoms with escapes, `.` as end vs graphic char).
- **R3 (pushback):** reading `1.` and then seeing a space means *two* tokens (integer
  `1`, end `.`) — characters consumed on a wrong path must be returnable to the stream,
  or remembered for the next token.
- **R4 (non-repositionable streams):** works on pipes and user input. No seeking, ever.
  When input is exhausted mid-token, the lexer *waits* — it does not fail, guess, or
  demand a rewindable source.
- **R6 (robust to invalid encodings):** "it also needs to handle invalidly encoded
  characters, like entities that are not valid UTF-8" (Markus Triska, follow-up 2026-09-04). Bytes
  that decode to no character must surface as ordinary, positioned lexical errors —
  never crashes — and a multi-byte character split across a chunk boundary must read
  as *pending input*, not as invalid (§6.1).

A fifth requirement comes from experience with hand-written lexers (including the one
this formalism replaces): **R5 (derivability):** R2 and R3 must be *derived from the
token definitions by the compiler*, not hand-maintained. Hand-maintained peek logic is
where lexer bugs live.

## 2. Design overview

**toklex** is a token-definition language with:

- a **surface notation that is Prolog terms** — a spec file is read with an ordinary
  Prolog reader (bootstrapping: the existing batch tokenizer/parser reads the spec that
  generates its own replacement);
- a **regular kernel**: token rules are named regular expressions over declared
  character classes, closed under sequence, alternation, repetition, option, and
  **subtraction** (set difference of regular languages);
- exactly **two extensions** beyond regular: *follow constraints* (a one-character
  lookahead predicate attached to a token rule, e.g. the ISO end token) and *nesting*
  (self-embedding allowed only in trivia rules, for nested block comments);
- **compiler-derived munch discipline**: the compiler builds one annotated DFA for the
  whole token set and computes, per state, the *extend set* (R2's peek test) and the
  *backup action* (R3's pushback), and it **proves the pushback bounded** or rejects the
  spec;
- **incrementality as semantics, not plumbing**: the input is conceptually a partial
  list of characters; "wait for more input" *is* "demand reached the unbound tail"
  (§6) — the Python `NEED_MORE` contract and the Prolog `freeze/2`-on-the-tail
  implementation are two operationalizations of the same definition;
- a **fixed decode stage** in front of the automaton for byte input, making invalidly
  encoded entities ordinary lexical errors and split multi-byte characters pending
  input (§6.1);
- **two thin targets** rendered from the same annotated DFA: a DCG (for a Prolog-hosted
  reader) and a table-driven step function (Clausal's Python L0).

The formalism deliberately does **not** include: lexer modes/start conditions (nesting +
subtraction + follow constraints cover Prolog without them), general semantic actions
(value builders are total functions over captures, §3.4), or anything context-free
beyond trivia nesting.

## 3. Notation

A spec is a list of Prolog terms (read with any conforming reader; the spec header
declares the handful of operators: `then`, `|`, postfix `*`/`+`/`?`, `but_not`,
`followed_by`, `nest`, `value`, `gives`). Four kinds of declarations.

### 3.1 Character classes

```prolog
class(layout,     [' ', '\t', '\n', '\r']).          % explicit chars
class(small,      unicode(ll) + ['_']).               % Unicode categories… (see note)
class(capital,    unicode(lu)).
class(digit,      range('0','9')).
class(graphic,    ['#','$','&','*','+','-','.','/',':','<','=','>','?','@','\\','^','~']).
class(solo,       ['!',',',';','|','%']).
class(hexdigit,   range('0','9') + range('a','f') + range('A','F')).
class(quoted_ok,  any - class(hidden_sep)).           % subtraction on classes
class(hidden_sep, ['\x0\']).                          % see §9: reader-unwritable char
```

Classes are finite unions/differences of explicit sets, ranges, and named Unicode
categories. (Whether identifiers are ASCII or Unicode is a *spec* decision, not a
formalism decision — the ISO spec ships an ASCII-faithful class file; a dialect swaps
class definitions, nothing else.)

### 3.2 Token rules

```prolog
token(name_atom,  small then alnum*).
token(variable,   (capital | '_') then alnum*).
token(end,        '.'  followed_by  (layout | '%' | eof)).   % declared before graphic_tok
token(graphic_tok, graphic+  but_not  ('/' then '*' then any*)).    % ISO: no graphic token starts /*
token(integer,    digit then (digit | '_')*).                   % '_' separators: dialect choice
```

- `then` sequence — a word operator: longer to type, but it reads naturally and is
  unambiguous (`followed_by` was considered and rejected for sequence: it already names
  the follow-*constraint*, a different thing). `|` alternation, `*`/`+`/`?`
  repetition/option (postfix), literals are quoted atoms/chars, class names denote
  their class.
- *Why not `,` for sequence, DCG-style?* It is terser and familiar, but a comma
  sequence at argument position demands parentheses, and forgetting them fails
  *silently* — by changing arity, not by raising a syntax error:
  `fragment(qitem, (backslash, nl), gives none)` minus its inner parentheses is a
  well-formed `fragment/4`, a different declaration. Nested sequences compound it
  (`body(('*', '/'))` needs the double parentheses or `body` quietly becomes binary).
  `then` makes that mistake unwritable; the verbosity is the price. Where a rule has
  no sequence at all, the two spellings are identical anyway.
- `but_not L` — language subtraction. This replaces every "priority" hack: ISO's rule
  that a graphic token cannot begin `/*` is *subtracted* from the graphic rule rather
  than encoded as comment-beats-graphic ordering. Regular languages are closed under
  difference, so the compiler folds this into the DFA; nothing survives to runtime.
- `followed_by C` — a **follow constraint**: the token matches only if the *next*
  character (not consumed) is in class `C`, or the special `eof`. This is the one place
  ISO genuinely needs lookahead that longest-match cannot express: `.` is the end token
  exactly when followed by layout, `%`, or end of stream (ISO 6.4.8). Follow constraints
  are the *declarative* form of "peek ahead"; the compiler folds them into the same
  one-character peek it already derives for maximal munch (§5).
- Ties after longest match are broken by declaration order (conventional; with
  subtraction available, real specs have almost no ties).

### 3.3 Trivia rules

Trivia are skipped between tokens but are *recorded* (§8: layout adjacency is
semantically load-bearing in Prolog — `f(` vs `f (`).

```prolog
trivia(whitespace,     layout+).
trivia(line_comment,   '%' then (any - '\n')*).
trivia(block_comment,  '/' then '*' then body('*' then '/')  nest  self).
```

`nest self` is the second extension: the rule may contain itself (nested `/* /* */ */`).
Only trivia may nest — trivia produce no value, so nesting never interacts with capture,
and the compiled form is the DFA plus one depth counter (equivalently: a DCG nonterminal
that recurses). Strict-ISO non-nesting is the same rule without `nest self`.

### 3.4 Values (captures and builders)

A token's default value is its lexeme (the exact characters matched). Where the value is
computed — quoted atoms decode escapes, numbers parse digits — the rule names its
fragments and gives a **builder**, a total function over fragment values:

```prolog
token(quoted_atom, q then qitem* then q)  value  atom_from(qitems).

fragment(qitem, qq,            gives  '\'').        % '' → literal quote
fragment(qitem, backslash then nl, gives  none).        % \<newline> line continuation
fragment(qitem, backslash then esc(C), gives  C).       % ISO 6.4.2 escape map
fragment(qitem, quoted_ok_char(C),  gives  C).
```

Builders are pure and total on accepted lexemes (the DFA already guarantees the shape),
so they compile to straight-line code in both targets: difference-list accumulation in
the DCG, a decode loop over the pending buffer in Python. No general user code runs
inside the lexer; the analyzability of the kernel is preserved.

### 3.5 What a rule may not say

No rule can mention: stream positions, peeking, pushback, buffers, or chunk boundaries.
Those are compiler artifacts (§5–§6). This is the enforcement of R5 — if the operational
concepts are inexpressible in the notation, they cannot be hand-maintained wrongly.

## 4. Semantics: the annotated automaton

The compiler:

1. Compiles every token and trivia rule to an NFA over the class alphabet; applies
   subtractions (product with complement DFAs); unions all rules; determinizes and
   minimizes. Accepting states are labeled with the winning rule (longest match, then
   declaration order).
2. Computes per accepting state `s` the **extend set** `extend(s)`: the characters on
   which some path from `s` can reach an accepting state (of any rule). The emission
   condition is:

   > *emit at `s` ⇔ the next character ∉ extend(s); the winning rule at `s` is the
   > highest-priority label whose follow constraint (if any) holds of that next
   > character — a rule whose follow constraint fails is disqualified, and the next
   > label in longest-match/declaration order takes the token.*

   Both conditions inspect exactly **one character beyond the token, without consuming
   it**. This is R2, derived: nobody writes the `=` vs `=..` peek — it falls out of
   `extend(s)` for the graphic-token DFA.
3. Computes **backup actions**. The DFA may pass an accepting state and continue toward
   a longer token that never materializes (`1.` + space: passed accept-at-`1`, consumed
   `.`, failed). The compiler records, for every non-accepting state reachable from an
   accepting one, the distance back to the last accept. On failure the generated code
   emits the last-accepted token and **returns the over-consumed characters to the
   head of the stream** (R3: "push characters to the stream, or remember that they were
   present"). Crucially:

   > **Boundedness check (REVISED 2026-09-04 during implementation):** the original
   > rule — reject any spec with a cycle of non-accepting states reachable from an
   > accept — was falsified by ISO itself: quote-doubling (`"ab""ccc…"`) and the
   > optional escape terminator each create exactly such cycles, and both are
   > load-bearing ISO syntax. The implemented rule derives **commit regions** instead:
   > pending states on or downstream of a cycle are *committed*; the bound `B` is the
   > DAG longest path over the remaining (provably acyclic) pending states. At a
   > failure in a committed state, the lexer backs up normally **iff** the nearest
   > recorded accept lies within `B`; beyond it, it emits one `unterminated` error for
   > the whole pending — which is precisely what hand-written greedy scanners (and
   > SWI) do. Bounded pushback survives as a runtime-checked invariant of that gate.
   > Everything is still derived from the definitions; nothing is hand-annotated (R5).

   For the ISO token set, `B = 2` (worst case `1.0e+` followed by a non-digit: emit
   float `1.0`, return `e+`; the ISO automaton has 28 committed states out of 112 —
   all inside quoted-token bodies). One further lesson landed in the spec rather than
   the engine: the reference scanner's greedy escape-terminator rule ("a backslash
   right after escape digits is always the terminator") is not a longest-match
   property and had to be stated in the token grammar itself — the body-item rules
   restrict what may follow an unterminated digit escape. Both revisions answer §13's
   external question 4: the counterexample exists, and the fix preserves derivability.
4. Emits the **annotated DFA**: transitions, accept labels, extend sets, follow checks,
   backup actions, builder attachments. Both targets are mechanical renderings of this
   object; the object itself (a Prolog term / JSON) is a legitimate interchange format
   between independent implementations.

Lexical errors are part of the semantics, not exceptions: a character with no transition
from the start state, or a failure with no accepting state behind it, yields an
`error(Span, Culprit)` token consuming one character; recovery policy above that (e.g.
resync to `.`) belongs to the term layer.

## 5. Peek and pushback, precisely

The generated lexer needs exactly two stream capabilities, both cheap and both
seek-free:

- **peek(1):** inspect the next character without consuming it — for the emission
  condition and follow constraints. (Scryer's `CharReader` exposes precisely
  `peek_char`/`put_back_char`; every buffered reader can.)
- **unread(≤ B):** return the last `k ≤ B` consumed characters, where `B` is the
  compiler-computed bound. Implemented as a tiny ring/stack in front of the stream —
  "remember that they were present, for the next token."

In the DCG target both collapse into non-consumption: a DCG relation
`token(T, S0, S)` that leaves `S` pointing at the right cell has "pushed back" by
construction — the compiler simply threads the pre-consumption list variable of the
last accept through to the emit site. Peek is head inspection without advancing:

```prolog
peek(C), [C] --> [C].          % standard DCG lookahead idiom
```

## 6. Incrementality: the partial-list semantics

**Definition.** The input is a partial list of characters `S`. Feeding a chunk binds the
tail: `feed("ab")` performs `Tail = [a,b|Tail']`; closing the stream binds `Tail = []`.
The lexer's demand for the next character encounters one of three situations:

| head of rest | meaning | lexer behavior |
|---|---|---|
| bound cell `[C|_]` | character available | consume / peek `C` |
| `[]` | true end of stream | `eof` — resolve follow-`eof`, final emit or error |
| **unbound var** | *stream that can wait* | **suspend: the token is not yet decidable** |

That third row *is* R4. A partial list with an unbound tail is exactly "a stream that
can wait for more input", and the two implementations differ only in who does the
waiting:

- **Coroutining Prolog host:** the compiled DCG wraps its character demand in
  `freeze/2` on the list variable. The lexer *is* a suspended goal; feeding input is
  unification; the scheduler resumes it. Nothing is reified because nothing needs to be
  — the suspended goal's continuation is the lexer state. This is the classically
  elegant answer and the primary DCG rendering.
- **Explicit-state host (Clausal's Python L0, or a freeze-less Prolog):** the same DFA
  renders as a **step function** — `lex_step(State0, Event, State, Out)` with
  `Event ∈ {char(C), eof}` and `Out ∈ {none, tokens([...]), error(...)}` — plus a
  driver exposing `feed(chunk)` / `next_token() → Token | NEED_MORE | EOF`. `NEED_MORE`
  is returned precisely when the semantics above says *suspend*. The reified state is
  small and explicit: DFA state id, pending lexeme, backup buffer (≤ B), position.
  Freezing the lexer between chunks is copying one small record.

**Correctness property (testable): chunk-boundary insensitivity.** For any character
sequence and any partition of it into chunks, the emitted token sequence is identical to
the batch run. This single property test subsumes most incremental-lexer bug classes and
is the acceptance gate for any implementation of the spec.

Note what is *absent*: seeking, repositioning, re-lexing from the token start after a
refill. The pending lexeme lives in the lexer state, never in the stream.

### 6.1 The byte layer: invalid encodings (R6)

Rules are written over characters, but a non-repositionable stream delivers bytes. A
fixed **decode stage** sits in front of the DFA — itself a tiny incremental automaton
(a ≤4-byte window for UTF-8) emitting three events: `char(C)`, `bad(Bytes)`, `eof`.
Two properties matter:

- **Invalid entities are ordinary error tokens.** `bad(_)` belongs to no character
  class, so the existing rule — no class membership ⇒ no transition ⇒ an
  `error(Span, invalid_encoding(Bytes))` token consuming the entity — handles it with
  zero new machinery; recovery is "skip the entity, continue". This is the same
  mechanism as §9's reserved-codepoint exclusion: in toklex, *rejection is absence
  from every class*. A `bad` event is emitted only for byte sequences that no
  continuation can repair — a stray continuation byte, an overlong encoding, `0xFF`.
- **A split multi-byte character is pending, not invalid.** A valid prefix at the end
  of fed input is exactly the unbound-tail situation of §6, one level down:
  suspend/`NEED_MORE`; truncation is only decidable at true EOF. Chunk-boundary
  insensitivity therefore extends through the decoder and remains the single
  conformance property.

A spec declares its input form: `encoding(utf8)` (byte input, decode stage active) or
`encoding(chars)` (the host stream already decodes — e.g. a Prolog whose text streams
deliver chars; what such a host does with invalid bytes is then its stream layer's
affair, upstream of toklex). In the DCG rendering the decode stage is a `decode//1`
nonterminal over a partial list of bytes; hosts that decode natively skip it.

## 7. Worked examples (the nasty cases)

**`=` vs `=..`** — one rule, `token(graphic_tok, graphic+)`. After `=`, state is
accepting with `extend ∋ '.'`; input `=..` keeps consuming to the longer accept; input
`=, ` peeks `,` ∉ extend → emit `=`. With input exhausted after `=`: unbound tail →
suspend (a terminal reader showing `X =` correctly waits — `=` could still become
`=..`). *Nothing was written to achieve this.*

**`1` / `1.5` / `1.0e7` / `1.` as end** — number DFA: after `1`, accepting; consuming
`.` moves to non-accepting (float wants a digit). `1.5` → accept float. `1. ` → fail at
`' '`, backup 1: emit `integer(1)`, return `.` to the stream; next round: `.` with
follow layout → `end`. `1.0e+x` → fail, backup 2 (`B`'s witness): emit `float(1.0)`,
return `e+`; `e` then lexes as a name atom. `1.` + unbound tail → suspend (could be
`1.5`).

**`0'c` family** — `0'a` → 97 (longest match beats "integer 0 then quoted atom").
`0'''` → 39 via the `qq` fragment. `0'\n\` escapes via the shared `esc` fragment map.
`0'` + unbound tail → suspend.

**Quoted atom with continuation** — `'ab\⏎cd'` decodes to `abcd` via the
`gives none` fragment; a doubled `''` gives one quote. Unterminated at true EOF
(`Tail=[]`) → `error(Span, unterminated_quote)`; before that, suspend — on a
non-repositionable stream "unterminated" is only decidable at EOF, and the formalism
makes that fall out rather than be a special case.

**Nested block comment** — `trivia(block_comment, ...) nest self`: depth counter in the
step-function target, recursive nonterminal in the DCG target. `/*` with the tail
unbound → suspend (the entire comment is pending trivia; its span is recorded, its
content dropped).

**The dot, completely.** `.` is: end token (followed by layout/`%`/eof — the follow
constraint on `end`, which outranks `graphic_tok` by declaration order when it holds),
or a graphic char inside a longer graphic token (`=..`, longest match), or a lone
graphic atom when the follow constraint fails and nothing extends it (`.(`
disqualifies `end`, so `graphic_tok` takes the dot), or a float's decimal point
(between digits, inside the number rule). All four read directly off the spec; none is
control flow.

## 8. Token output: what the term layer receives

Each emitted token: `tok(Kind, Value, Span, Glue)` where `Span = (StartPos, EndPos)`
(absolute offsets plus line/col) and `Glue ∈ {glued, spaced}` records whether trivia
preceded the token. `Glue` makes ISO's adjacency distinctions (`f(` compound-open vs
`f (` — "open-ct"; adjacent `-1` negative literals) a fact the lexer states rather than
a reconstruction from positions downstream. Trivia themselves are droppable but
span-recorded (comment-preserving tools may subscribe; the term layer ignores them).

## 9. Clausal instantiation (Phase 3 deltas from the ISO spec file)

The formalism above is dialect-free; Clausal's Phase 3 surface is a *spec file*, an ISO
base with these deltas (rulings from `tagged-tuple-term-representation.md` §1b):

- **`hidden_sep` exclusion:** the `-hide` mangling separator (NUL or a private-use
  codepoint — final char TBD in Phase 3) appears in **no character class at all**, so
  it is a lexical error *anywhere* in source — inside quoted atoms, strings, comments,
  everywhere. Stronger than §1b's minimum ("inside any atom token") and simpler: one
  class-membership fact, zero special cases. The writer renders the human form; only
  the runtime str carries the separator.
- **Double-quoted tokens** are `string` tokens at the lexer level; chars-list lowering
  (ISO `double_quotes = chars`, per §1b) is the reader's term-construction policy, not
  the lexer's.
- **Directive surface `-module(...)`, `-private([...])`, bare `-allow_singletons`:**
  lexically nothing — `-` graphic token, name atom, punctuation.
- **No clause terminators (RULED 2026-09-04, user):** Clausal's surface has *no dots —
  nothing, ideally — with optional commas between items at module level*. So the
  clausal dialect spec simply **omits the `end` token** (it exists only in the ISO
  dialect file, for reading `.pl`); item boundaries are the term layer's job, decided
  structurally (a complete maximal term ends the item) with §8's `Glue`/span data
  available for any layout-sensitive rule, and an optional module-level `,` consumed
  as an item separator. Error recovery follows the dialect: resync-to-`.` in ISO mode,
  resync-to-fresh-line-item-start in clausal mode. Comment syntax (`#` vs `%`) is
  still an open surface choice — one trivia line either way. The token layer is
  identical in shape across both dialects; only the spec files differ.
- The existing `prolog_tokenizer.py` behaviors that are deliberate dialect choices —
  `_` digit separators, lenient unknown escapes, nested comments — are each one line of
  spec, on by default to keep `tests/test_prolog_parse.py` green.

## 10. Compilation targets

**DCG target (Prolog-hosted).** One nonterminal per DFA state, first-argument-indexed
on the peeked character; accepting states carry the emit-vs-extend branch; backup is
list-variable threading (§5); suspension via `freeze/2` on the stream variable, or the
step-function rendering below for freeze-less systems. Sketch of generated code for the
number fragment:

```prolog
% state 12: seen digits — accepting as integer(...)
q12(Pnd, T) --> peek(C), { is_digit(C) }, !, [C], q12([C|Pnd], T).
q12(Pnd, T) --> peek('.'), ['.'], q13(Pnd, T).          % maybe float; q13 non-accepting
q12(Pnd, T) --> emit_integer(Pnd, T).                   % peek ∉ extend(q12)

% state 13: digits '.' — NOT accepting; fail here = backup to q12's accept
q13(Pnd, T) --> peek(C), { is_digit(C) }, !, [C], q14([C, '.'|Pnd], T).
q13(Pnd, T), ['.'] --> emit_integer(Pnd, T).            % pushback via right-hand context
```

(The `q13 … , ['.'] -->` pushback clause is the generated form of a backup action —
DCG's right-hand-side context notation *is* "push characters back to the stream", which
is a pleasing fit: the standard's own notation already contains R3.)

**Step-function target (Python, Clausal L0).** Tables: `delta[state][class] → state`,
`accept[state]`, `extend[state]` (bitset), `follow[rule]`, `backup[state]`; a ~100-line
generic driver implements `feed/next_token` per §6 and never changes; regenerating the
tables is the only effect of a spec edit. This replaces the 487-line hand-written
`prolog_tokenizer.py` behind the same (now incremental) interface.

## 11. Where it lives (deliverable b — recommendation)

- **The spec files and this design are the shared artifact.** `iso.toklex.pl` (dialect
  base) and `clausal_phase3.toklex.pl` (deltas of §9) are plain Prolog term files,
  meaningful to any implementation, suitable to hand to the Prolog-in-Prolog effort
  as-is. The annotated-DFA dump (§4.4) is the secondary interchange format.
- **Clausal hosts the first compiler**: `clausal/tools/toklex/` — spec loader
  (bootstrapped on the *existing* `prolog_parser.py`, which is already capable of
  reading the spec files), automaton construction + checks, and the two renderers. The
  Python renderer is what Clausal runs; the DCG renderer is cheap to build from the
  same DFA and is the concrete contribution back to the Prolog-hosted effort.
- A future Prolog-hosted compiler reimplements §4 from this document against the same
  spec files; the chunk-boundary property test plus a token-stream diff on a shared
  corpus is the conformance suite between implementations.

## 12. Alternatives considered

- **Restricted-DCG style + static checker** (write the tokenizer directly as a DCG in a
  disciplined idiom; a checker enforces peek/munch hygiene). Rejected on R5: maximal
  munch and pushback remain hand-written per token; the checker can flag violations but
  cannot *derive* the discipline, and the incremental transformation of arbitrary DCG
  code is much harder than rendering a DFA.
- **PEG / parser combinators with ordered choice and explicit cut.** Expressive, but
  ordered choice hand-encodes exactly what R5 says must be derived, and general PEG
  backtracking is unbounded — R3's boundedness proof is unavailable.
- **Full lexer-generator with modes (flex-style start conditions).** Modes are the
  traditional escape hatch; Prolog needs them nowhere once `but_not`, follow
  constraints, and trivia nesting exist. YAGNI — and every dropped feature keeps the
  DCG rendering honest.

## 13. Open questions for the user

1. **Notation blessing:** *(RESOLVED 2026-09-04: `but_not` with the underscore; the
   sequence operator is the word operator `then` — verbose but natural and unambiguous.
   `followed_by` was rejected for sequence since it already names the follow
   constraint. Remaining spellings stand unless Markus/Ulrich push back.)*
2. **⟨SEP⟩ strictness:** *(CONFIRMED 2026-09-04: the separator is in no character
   class — a lexical error anywhere in source. Code that legitimately needs the
   character at runtime constructs it via escapes/`char_code` — the documented
   out-of-warranty path.)*
3. **Phase 3 surface:** *(RULED 2026-09-04: no dots — nothing, ideally — with
   optional commas at module level; see the §9 bullet for the consequences. Still
   open within this: `#` vs `%` comments, and the ruling interacts with the parked
   bracketed-clause-bodies idea,
   `todo/rejected/phase3-surface-bracketed-clause-bodies-2026-09-04.md`, rejected 2026-10-05.)*
4. **Sharing:** this document + the two spec files are written to be shareable with
   Markus Triska as the proposal; say the word and nothing Clausal-internal blocks it
   (§9 would travel as "an embedder's dialect deltas" example). *(Answered 2026-09-04:
   yes — sanitized version produced as
   `implementation_plans/toklex-token-formalism-external.md` + PDF, for Markus Triska,
   who also shares with Ulrich Neumerkel.)*

## 14. Implementation notes (2026-09-04, feat/toklex)

- **Extend sets:** the Python driver walks `delta` directly; `extend(s)` is
  observationally equivalent there because every constructed DFA state is live. The
  extend annotation remains the *specification* of the emission rule and drives the
  DCG rendering and the dump; §5's prose stands, with this equivalence noted.
- **Bootstrapping is load-bearing:** the retired hand-written tokenizer lives on as
  `clausal/tools/toklex/_bootstrap.py`, used only to read `.toklex.pl` spec files —
  the public `tokenize()` is generated (the §2 bootstrap sentence, made literal).
- **Known v1 gaps:** (1) the reserved codepoint is not rejected inside *block-comment
  bodies* (the nest sub-scanner consumes chars without class checks — a formalism-level
  gap; fix candidate: a declarable nest-body class, default `any`); (2) generated
  tokenizer is ~2.9x slower per file than the hand scanner (interpreted tables;
  optimization parked); (3) DCG target is chars-mode kinds+lexemes (v1 scope), rendered
  as generated fact tables plus a small generic engine — i.e. the §4.4 dump plus an
  interpreter, a legitimate and readable alternative to unrolled per-state clauses.
- **Ratified surface divergences from the old scanner** (SWI-compatible): `0x`/`0x_`/
  `1.5e`-style digitless radix/exponent tails now lex as number-then-name instead of
  raising; malformed char-codes raise positioned errors with a generic message. Full
  list: `tests/toklex/test_parity.py` `EXPECTED_DIVERGENCES` + `TestMalformedHardening`.
