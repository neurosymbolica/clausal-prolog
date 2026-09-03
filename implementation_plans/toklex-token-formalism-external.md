# toklex: a token-layer formalism for Prolog readers

*Draft for discussion — Clausal project, September 2026.*

## 1. Problem

Prolog term syntax needs no grammar formalism: its variable part is precedence-shaped,
`op/3` *is* the grammar, and a runtime-mutable Pratt/precedence-climbing core handles it.
The **token layer** is where an actual open problem lives. The requirements (Markus
Triska, September 2026, on what a Prolog-in-Prolog reader needs):

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
  characters, like entities that are not valid UTF-8" (follow-up requirement). Bytes
  that decode to no character must surface as ordinary, positioned lexical errors —
  never crashes — and a multi-byte character split across a chunk boundary must read
  as *pending input*, not as invalid (§6.1).

A fifth requirement comes from experience with hand-written lexers (including the one
this formalism replaces in our own system): **R5 (derivability):** R2 and R3 must be
*derived from the token definitions by the compiler*, not hand-maintained.
Hand-maintained peek logic is where lexer bugs live.

## 2. Design overview

**toklex** is a token-definition language with:

- a **surface notation that is Prolog terms** — a spec file is read with an ordinary
  Prolog reader (bootstrapping: an existing batch reader reads the spec that generates
  its own replacement);
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
  (§6) — an explicit-state `NEED_MORE` contract and a Prolog `freeze/2`-on-the-tail
  implementation are two operationalizations of the same definition;
- a **fixed decode stage** in front of the automaton for byte input, making invalidly
  encoded entities ordinary lexical errors and split multi-byte characters pending
  input (§6.1);
- **two thin targets** rendered from the same annotated DFA: a DCG (for a Prolog-hosted
  reader) and a table-driven step function (for a host-language implementation; in our
  case, Clausal's Python reader).

The formalism deliberately does **not** include: lexer modes/start conditions (nesting +
subtraction + follow constraints cover Prolog without them), general semantic actions
(value builders are total functions over captures, §3.4), or anything context-free
beyond trivia nesting.

## 3. Notation

A spec is a list of Prolog terms (read with any conforming reader). Four kinds of
declarations.

### 3.1 Character classes

```prolog
class(layout,     [' ', '\t', '\n', '\r']).          % explicit chars
class(small,      unicode(ll) + ['_']).               % Unicode categories
class(capital,    unicode(lu)).
class(digit,      range('0','9')).
class(graphic,    ['#','$','&','*','+','-','.','/',':','<','=','>','?','@','\\','^','~']).
class(solo,       ['!',',',';','|','%']).
class(hexdigit,   range('0','9') + range('a','f') + range('A','F')).
class(quoted_ok,  any - class(reserved)).             % subtraction on classes
class(reserved,   ['\x0\']).                          % embedder-reserved chars, see §9
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
token(graphic_tok, graphic+  but_not  ('/' then '*' then any*)).   % ISO: no graphic token starts /*
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
the DCG, a decode loop over the pending buffer in a host-language lexer. No general user
code runs inside the lexer; the analyzability of the kernel is preserved.

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

   > **Boundedness check:** the compiler verifies that no cycle lies on any
   > accepting→accepting path through non-accepting states, and reports the maximal
   > backup distance `B`. A spec with unbounded backup is rejected at compile time.

   For the ISO token set, `B = 2` (worst case `1.0e+` followed by a non-digit: emit
   float `1.0`, return `e+`). Pushback is therefore a fixed two-cell affair, not a
   general rewind — which is exactly why R4's no-seeking is satisfiable.
4. Emits the **annotated DFA**: transitions, accept labels, extend sets, follow checks,
   backup actions, builder attachments. Both targets are mechanical renderings of this
   object; the object itself (a Prolog term) is a legitimate interchange format between
   independent implementations.

Lexical errors are part of the semantics, not exceptions: a character with no transition
from the start state, or a failure with no accepting state behind it, yields an
`error(Span, Culprit)` token consuming one character; recovery policy above that (e.g.
resync to `.`) belongs to the term layer.

## 5. Peek and pushback, precisely

The generated lexer needs exactly two stream capabilities, both cheap and both
seek-free:

- **peek(1):** inspect the next character without consuming it — for the emission
  condition and follow constraints. (Scryer Prolog's `CharReader` exposes precisely
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
- **Explicit-state host (a host-language lexer, or a freeze-less Prolog):** the same
  DFA renders as a **step function** — `lex_step(State0, Event, State, Out)` with
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
`0'''` → 39 via the `qq` fragment. `0'\n` escapes via the shared `esc` fragment map.
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

## 9. Example: an embedder's dialect deltas (Clausal)

The formalism is dialect-free; a dialect is a *spec file*. As a concreteness check,
here is what Clausal (a Prolog system embedded in Python) needs as deltas on the ISO
base spec — each one a data change, none a formalism change:

- **A reserved codepoint.** Clausal renames module-hidden atoms internally with a
  separator character that must be *unwritable from source*. In toklex this is one
  fact: the character appears in **no character class at all**, so it is a lexical
  error anywhere — inside quoted atoms, strings, comments, everywhere. Zero special
  cases.
- **Double-quoted tokens** are `string` tokens at the lexer level; lowering to char
  lists (ISO `double_quotes = chars`) is the reader's term-construction policy, not
  the lexer's.
- **Directive surface** `-module(...)`-style (rather than `:- module(...)`) is
  lexically nothing — graphic token `-`, name atom, punctuation.
- **No clause terminators.** Clausal's own surface has no end dots at all (with
  optional commas between items at module level), so the Clausal dialect spec simply
  *omits the `end` token* — it exists only in the ISO dialect file, used for reading
  `.pl` sources. Item boundaries become the term layer's job, decided structurally
  with §8's `Glue`/span data available; error recovery resyncs to a fresh-line item
  start instead of to `.`. The token layer is identical in shape across both
  dialects; only the spec files differ — which is the dialect story working as
  intended.
- Deliberate dialect choices in Clausal's current hand-written tokenizer — `_` digit
  separators, lenient unknown escapes, nested comments — are each one line of spec.

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

**Step-function target (host language).** Tables: `delta[state][class] → state`,
`accept[state]`, `extend[state]` (bitset), `follow[rule]`, `backup[state]`; a ~100-line
generic driver implements `feed`/`next_token` per §6 and never changes; regenerating the
tables is the only effect of a spec edit. In Clausal this replaces a ~500-line
hand-written tokenizer behind the same (now incremental) interface.

## 11. Implementations and conformance

- **The spec files are the shared artifact**: an `iso.toklex.pl` dialect base plus
  per-dialect delta files (§9), plain Prolog term files meaningful to any
  implementation. The annotated-DFA dump (§4.4) is a secondary interchange format.
- Clausal will host the first compiler (spec loader, automaton construction and
  checks, both renderers); the DCG renderer is cheap to build from the same DFA and is
  the concrete contribution to a Prolog-hosted reader.
- A Prolog-hosted compiler can be reimplemented from §4 of this document against the
  same spec files. The conformance suite between independent implementations is the
  chunk-boundary property test (§6) plus a token-stream diff on a shared corpus.

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
  constraints, and trivia nesting exist — and every dropped feature keeps the DCG
  rendering honest.

## 13. Questions for discussion

1. Is the Prolog-terms surface notation right, and are the operator spellings
   agreeable? We currently spell sequence with the word operator `then` — longer to
   type, but it reads naturally and is unambiguous (`·` is untypeable in practice; `,`
   at argument positions forces parentheses everywhere and fails silently by arity
   change when they are forgotten — see the note in §3.2).
2. Is the annotated-DFA dump (§4.4) worth standardizing as an interchange format, so a
   Prolog-hosted reader could consume a DFA compiled elsewhere before a full
   Prolog-hosted compiler exists?
3. For the DCG rendering: is `freeze/2`-on-the-tail acceptable as the primary
   suspension mechanism, or should the pure step-function rendering (explicit state,
   no coroutining) be the reference form, with freeze as sugar?
4. Does the ISO token inventory hide any case that breaks the one-character-peek /
   bounded-backup analysis? (`B = 2` is our computed claim; a counterexample would be
   very interesting.)
