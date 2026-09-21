# Strings were lost in the atom pivot: `"hello"` must be a char list again, `'hello'` an atom

**Type:** engine semantics regression (P3-1 fallout) — BLOCKING for the ISO
export's credibility and for the Prolog-reader surface. **Owner:** the
`clausal-bug-fix` instance (the P3 refactoring lane whose pivot introduced
it). **Reporter:** the ISO-export lane (executor-train session), 2026-09-06.
**Operator rulings in this file were taken 2026-09-06 with Mike and are
final unless he reopens them; the OPEN QUESTIONS section is what is not yet
ruled.** Trigger: Markus Triska asked what `write_canonical("hello")` prints
in Clausal. Mike's words: strings not unifying with lists of chars is
"perhaps Markus's biggest pet peeve, and rightly so."

Move this file to `todo/done/` on completion.

---

## 1. The problem, precisely

Before P3-1, Clausal HAD a string type: a Python `str` (or a `SegString` for
strings with holes), and the C unifier's str~char-list cons rule made
`"hello"` unify with `['h','e','l','l','o']`. Atoms were something else
(zero-arity classes).

P3-1 (`28f93bd6`, "atoms are global strings by spelling") made every atom a
plain interned `str` and — correctly, given that — RETIRED the cons rule
(§1b: with str = atom, the rule would have made `'abc'` unify with `"abc"`,
which ISO forbids). The Python-surface parser was left lowering `"..."` to
that same plain str, so a double-quoted literal now denotes an ATOM. The ISO
translator followed (`bda6b039`, "a str literal denotes an ATOM, not a char
list"), and the corpus's literal migration (2026-09-05) was built on it.

Net effect, measured live on canonical `ccdb78d7` (2026-09-06):

| Clausal today | result | Scryer (reference, measured same day) |
|---|---|---|
| `"hello" == hello` | **succeeds** | `'hello' == hello` yes; `"hello" == hello` NO |
| `atom("hello")` | **succeeds** | fails (`atom/1` false on a string) |
| `string("hello")` | succeeds (alias, co-extensional) | no `string/1`; `"hello"` is a list |
| `X is "hello", Y is ['h','e','l','l','o'], X == Y` | **FAILS** | `"hello" == [h,e,l,l,o]` yes |
| `"hello" is [h,e,l,l,o]` (unify) | **FAILS** | `"hello" = [h,e,l,l,o]` yes |
| `[H\|T] is "hello"` | **FAILS** | `H = h, T = [e,l,l,o]` |
| `is_list("hello")` | succeeds | (n/a in Scryer core) — list, yes |
| `length("hello", N)` | N = 5 | 5 |
| `atom_chars(hello, C)` | `['h','e','l','l','o']` (1-char strs) | `C == "hello"` yes |
| `atom_chars("hello", C)` | succeeds (it is an atom) | type_error(atom, [h,e,l,l,o]) |
| `atom_length("hello", N)` | N = 5 | type_error(atom, [h,e,l,l,o]) |
| `write("hello")` | `hello` | `[h,e,l,l,o]` |
| `print_term("hello")` | `'hello'` (Python repr; no writeq/write_canonical exist) | `writeq` → `[h,e,l,l,o]`; `write_canonical` → `'.'(h,'.'(e,'.'(l,'.'(l,'.'(o,[])))))` |
| `"" == []` | fails | yes |

**Clausal has no string type at all right now, only quoted atoms.** The
engine literally cannot tell `"hello"` from `hello`: they are the same
interned object. `is_list/length` succeeding on it while `[H|T]` fails is the
inconsistency showing through.

## 2. The ruling was already on record — this is the unexecuted half

`implementation_plans/tagged-tuple-term-representation.md` §1b, **Surface
literal rulings (user, 2026-09-04, re-confirmed during P3-2 ruling
review):** "SINGLE quotes are quoted atoms (`'abc'`, `'hello world'`), as in
Prolog; DOUBLE quotes are strings-as-char-lists: `"abc"` … unifies with
`['a','b','c']`" and, just above it: "Double-quoted strings lower to char
LISTS (ISO `double_quotes=chars`, Scryer-compatible), and the C cons rule
retires … SegString remains the char-list optimisation."

That ruling was scoped to the FUTURE Prolog reader surface. The Python
surface's `"..."` was left as an atom in the meantime, and nothing else in
the engine can represent a string. This todo executes the ruling on the
Python surface too, with the amendments below.

## 3. Operator rulings taken 2026-09-06 (Mike)

**R-S1. Target semantics = Scryer's.** `"hello"` is a string that unifies
with `['h','e','l','l','o']` AND with `[h,e,l,l,o]` (a char is an atom whose
spelling is one character; post-R2 the two spellings are the same atom).
`'hello'` is a quoted atom and unifies with bare `hello`. `atom("hello")`
is false. Every row of the Scryer column above is the acceptance test.

**R-S2. Do NOT materialize strings to lists.** "It already had a mature
representation system: it was a Python str or a SegString. Do not
materialize, it's highly inefficient." A ground string is a Python `str`;
a string with holes is a `SegString`. Char-list behavior comes from
unification/inspection rules, not from storage. (This AMENDS the
2026-09-04 wording "tokenizes AS `['a','b','c']`" — same semantics,
compact representation.)

**R-S3. Discrimination: TAG THE ATOMS, not the strings.** The real
question is: if atoms are `str`, how do we tell a str meant as an atom
from a str meant as a string? Ruled: atoms are `str` **tagged with an
unused low-ASCII control code as their first character**; plain `str` is a
string again. Rationale:
- Plain str = string restores the mature machinery (SegString, DCG,
  `chars.py`, regex, most of the ~163 str-typed sites in
  `logic/runtime`, `logic/builtins`, `terms.py`) to the meaning it was
  built for. The atom pivot is one week old; its footprint (17 files in
  `28f93bd6`'s stat) is the bounded blast radius.
- Text entering from Python or JSON is a STRING by default (ISO-friendly);
  atoms exist only where the compiler, the reader, or an atom builtin
  mints one.
- Precedent: atoms already carry a control code (R1 ⟨SEP⟩ = US 0x1F inside
  `-hide`-mangled names), the reader already refuses it inside any token,
  and the writer already renders the human form (`atoms.py`:
  `mangle`/`is_mangled`/`demangle`/`demangle_for_display`). A leading tag
  generalizes that one module into the single home for atom identity:
  `mint(spelling) -> atom`, `is_atom(x)`, `spelling(atom) -> str`.
- R1's storage argument transfers: any C0 control keeps ASCII atoms in
  Latin-1 storage and on CPython's compact compare/hash fast paths.
- REJECTED: an empty `str` subclass `atom` — breaks marshalling, values
  passed to subinterpreters, `PyUnicode_CheckExact` fast paths and
  interning in the C unifier. REJECTED (mirror option): tagging strings
  instead — contained, but every string op would have to add/strip the
  tag, disturbing exactly the mature machinery R-S2 protects, and foreign
  text would keep arriving as atoms.
- Proposed tag (NOT yet ruled, see §7): RS, 0x1E, adjacent to R1's US;
  NUL excluded for the C-string reason; same reader refusal rule as R1
  (never legal inside any token, quoted or not); runtime forging via
  `atom_chars/2` out-of-warranty exactly as for ⟨SEP⟩.

**R-S4. `double_quotes/1` is a migration RATCHET, not a compatibility
flag.** Default is `chars` (Scryer). An unmigrated module declares
`-double_quotes(atom)` and keeps today's meaning while it is migrated.
Mike: "ISO Prolog has this flag for backward compatibility … are we being
backward compatible with something? Clausal is very new, there are no
legacy systems written in it. If we want to support Prologs with strings,
I'd prefer a translation system. So if we have double_quotes/1 then it
should be a ratchet, migrate, and remove it, not deprecate." So: insert
the directive mechanically into every existing corpus/library module, migrate
domain by domain with the suites + G4 as oracle, DELETE the directive from
the engine when the last module drops it, and pin a test that REFUSES the
directive afterwards. Support for string-bearing Prologs is a
translation-layer concern, never an engine flag.

**R-S3′ (2026-09-06, later the same day — SUPERSEDES R-S3's mechanism).
Atoms are arity-0 cells; plain `str` is a string.** An atom is the 1-tuple
`("bar",)` — the shape P3-2 gave every compound, at arity 0. Functor slot
0 of a cell stays the plain spelling `str`; a plain `str` anywhere else is
a string. `foo(bar, "baz")` is `("foo", ("bar",), "baz")`. Ruled "D" by
Mike on the design note
`implementation_plans/strings-representation-options-2026-09-06.md`
(clausal-bug-fix, `feat/double-quotes-ratchet`, `0a1881f8`/`bec5ab4f`),
which measured four options (A = R-S3's C0 tag, B = atoms as `bytes`,
C = class-tag the strings, D = this). What R-S3 was *for* is unchanged:
plain `str` = string restores the mature machinery, foreign text is a
string, `mint`/`is_atom`/`spelling` live in `atoms.py`. What changes:
- No tag character, so §7 Q1 is moot: no reader refusal rule, no forging
  path. §7 Q2 is answered by construction (slot 0 = spelling, atom = the
  1-tuple, `functor/3` and `=..` convert at the edge).
- `atom ≠ string` comes from the existing tuple-vs-str guard in the C
  unifier; §4's `_list_unify.c` str arms become CORRECT (plain `str` is a
  char sequence) instead of needing the fix; the retired `str↔list` cons
  rule returns for plain `str` with chars as interned 1-tuples `("h",)`.
- The arg-index key of an atom is `(name, 0)`, i.e. what the cell branch
  already computes — the `(name, 0)`-vs-resolved-value bug class of
  `d0f2bad5` dissolves.
- Measured on the tree: a `("qux",)` head argument already compiles and
  solves; unify 73 ns vs 75 ns for `str`; dict lookup 21.7 vs 21.1 ns
  (29.5 ns for a non-canonical equal tuple — interning discipline is the
  one load-bearing requirement; `mint()` returns the canonical object and
  the loader canonicalises literal 1-tuples in bytecode constants).
- Cost profile: item B's atom sweep stands (every minting site →
  `mint`, every spelling consumer → `[0]`, atoms unwrap at the Python
  wrappers; strings pass unchanged). `mod.atom` module attributes change
  type from `"bar"` to `("bar",)` — a loud downstream break to be
  announced with the flip. JSON needs the atom codec item H already lists.
  Downstream migration profile is exactly R-S3's.
- Design note §5 has the plan shape; §7 there has the per-boundary
  table (bytecode cache, Python callees, JSON, dict keys, threads,
  subinterpreters, ISO translator).

## 4. Facts the implementer needs (all measured 2026-09-06)

- **Corpus census** (`<downstream-corpus>`, comments stripped):
  **15,849 double-quoted literals** — 6,580 identifier-shaped (used as
  atoms today: test names, profile keys, verdict values), 8,303 free text
  (verbatim legal text, labels), 966 empty; single-quoted: 199, ALL
  apostrophes inside text/comments (effectively zero real quoted atoms).
  Library (`downstream-trunk/library`): 427 double-quoted, 0 single. The library
  has consumers in six corpus repos — migrate it first and carefully.
- **The Python AST discards quote style.** `ast.Constant(value='hello')`
  is identical for `'hello'` and `"hello"`. Quote kind must come from the
  source text at the node's `(lineno, col_offset)` — `source_lines` is
  already threaded through `import_hook.py` → `term_rewriting.py` for the
  arrow-adjacency check (`_is_arrow_adjacent`), which is the precedent —
  or from a one-pass `tokenize` position→quote-kind map (robust to
  prefixes, triple quotes, implicit concatenation; f-strings are
  `JoinedStr`, not `Constant`). Both the compiler AND the ISO translator
  (`clausal_to_prolog.py::_convert_constant`) need it.
- **Cons rule state:** `_variables.c`'s str↔list arm is gone;
  `SegString.__unify__` against a `list` materialises `list(walked)` and
  unifies list-vs-list; against a `str` compares walked-str == other (which
  today makes a ground SegString unify with the same-spelled ATOM — wrong
  post-R-S3, right again once plain str = string). `VarSeg`s bind to str.
- `type_checks.py`: `atom/1` "true for every str" (R2), `string/1` a
  retained alias; `_helpers` must_be/can_be "list" accept str (A09-F016);
  `same_length/2`, `list_unify.py` destructure str as a char sequence.
  Under R-S3 these are RIGHT for plain str (= string) and must become
  false/typed for tagged atoms.
- `atom_chars/2` chars→atom direction already emits plain strs
  (`chars.py:386`, the "existing blur" R2 noted) — post-R-S3 the chars
  are 1-char ATOMS (tagged) and the atom result is tagged.
- Writers: `write/1`, `writeln/1`, `write_to_string/2`, `print_term/1`
  (`terms.py::term_str`, Python `repr` quoting) — no `writeq/1`, no
  `write_canonical/1` today.
- The `.venv` `.pth` makes every trunk/corpus run use canonical
  `/workspace/clausal` LIVE (memory: "<harness-library> hardcode defeats the
  seal"). An engine flip is instantly visible to every lane.
- Two stale-doc todos fold into this:
  `todo/docs-strings-as-lists-md-stale-after-cons-rule-retirement-2026-09-04.md`,
  `todo/docs-syntax-md-atom-sections-stale-after-atom-pivot-2026-09-04.md`.

## 5. Work items (design sketch — spec + plan to be written under the
brainstorming/writing-plans flow before code; each item TDD, watched red)

A. **`atoms.py` becomes the atom-identity home:** `ATOM_TAG`, `mint`,
   `is_atom`, `spelling`; `mangle`/`demangle` compose with it (mangled =
   TAG + module ⟨SEP⟩ name). Reader/parser refuses TAG inside any token.
B. **Minting sites** (start from `28f93bd6`'s 17-file stat): bare
   identifiers and strict-atom declarations (`compiler_v2.py`,
   `predicate.py`, `terms_to_ast.py`), module names, `-module`/`-private`
   export lists, `-import_from` names, K3 constants (`undefined`, and
   whatever `[]`/`true`/`false` are), functor names surfaced by
   `functor/3` and `=..` (DECIDE: is the tagged-tuple slot-0 functor str
   tagged, or does `functor/3` tag on the way out? — §7), arg-index keys
   (`arg_index.py`), `atom_chars/atom_codes/atom_concat/sub_atom/
   atom_length/char_code/number_codes` results, `global_atom/2`.
C. **Python-surface literals:** `'...'` → `mint(text)`; `"..."` → plain
   str (string) under `double_quotes=chars`, `mint(text)` under
   `-double_quotes(atom)` (R-S4 ratchet); `b"..."` unchanged (codes list,
   ruling already on record); `b'...'` rejected (on record).
D. **Unification:** str~str by equality (unchanged; tagged vs untagged
   differ by content, so `"hello"` vs `hello` fails for free); REINSTATE
   the cons rule for PLAIN str vs list (string ↔ list of 1-char atoms,
   binding unbound elements/tails), C twin + Python shadow in lockstep,
   NEVER for a tagged str; SegString arms follow (ground walk → plain str
   = string, fine). Empty string `""` ≡ `[]`.
E. **Standard order:** a string orders as the compound list it denotes
   (Scryer: `Var < Number < Atom < Compound`; `"abc"` is Compound); atoms
   compare by spelling (strip tag or compare with tag — tag is common
   prefix, so raw compare is fine).
F. **Type checks & builtins:** `atom/1` true iff tagged; `string/1` true
   for plain str / ground SegString (keep or retire — §7); `atomic/1`
   false for strings; `is_list/1`, `length/2`, `nth`, `append`, `member`
   etc. work on strings via the cons rule; `atom_length/atom_chars` on a
   string → `type_error(atom, …)` (Scryer) — corpus uses of these on
   `"..."` migrate to `'...'` or to list ops.
G. **Writers:** `write/1` of an atom prints spelling (strip tag; reuse the
   demangle-for-display path); of a string prints `[h,e,l,l,o]` (Scryer
   does — decide whether Clausal's `write` may print text; §7). Add
   `writeq/1` and `write_canonical/1` (Markus's question is literally
   `write_canonical("hello")` → `'.'(h,'.'(e,…))`). `print_term/1` /
   `term_str` render atoms bare-or-quoted by ISO rules, strings as
   `"hello"` or `[h,e,l,l,o]` (§7).
H. **Boundaries:** Python interop (`++`, `py.*` modules) — text in = string,
   text out = spelling for atoms / str for strings; JSON oracle/profile
   loader — keys → atoms (schema position), values → atoms only where the
   domain's declared vocabulary says so (the `CachedRunner._declares_atom`
   precedent in `auto/decision`), else strings; marshalling/pickling
   unchanged (tag is content); Scryer codec: tagged atom → atom, plain
   str → string.
I. **`double_quotes/1` ratchet (R-S4):** per-module directive; default
   `chars`; mechanical insertion of `-double_quotes(atom)` into every
   existing corpus + library module BEFORE the engine flip lands on canonical
   (the `.pth` makes it live at once); a census tool that lists modules
   still carrying it; removal + refusal test at the end.
J. **ISO translator (`clausal_to_prolog.py`):** `'x'`/tagged atom →
   quoted-as-needed atom (the `_quote_atom` path, keep); `"..."` string →
   double-quoted Prolog string with the escaping class-G fixed (the
   PString branch, currently bypassed by `bda6b039`'s blanket rule —
   narrow that rule to atoms); execution-harness agreement pins
   (`tests/test_prolog_execution.py`) for every Scryer-table row, both
   engines; re-run the ISO export gates on the 8 publishable domains.
K. **Corpus + library migration:** tool that rewrites identifier-shaped `"x"`
   used as an atom to `'x'` and leaves text as `"..."`, per module, gated
   by that module's suite + G4 + (where armed) G5; drop the directive as
   each module goes green; library first; every score unchanged.
L. **Docs:** fold the two stale-doc todos; user docs for `'…'` vs `"…"`,
   the tag (out-of-warranty forging), the ratchet's lifetime.

## 6. Acceptance

1. Every row of the Scryer column in §1 holds in Clausal (pinned tests),
   including `write_canonical("hello")`.
2. Same rows hold in the ISO export of a fixture domain, both engines
   (execution harness).
3. Corpus: all suites green, G4 green on all 74 roster domains, the 8
   publishable domains still clear all five gates, scores unchanged.
4. `grep -r "double_quotes" corpus library` → 0; the directive is deleted from
   the engine; a test asserts it is refused. Only then move this todo to
   `done/`.

## 7. OPEN QUESTIONS (need a ruling from Mike or the implementer's proposal)

1. ~~Tag character: RS 0x1E proposed (§3 R-S3). Confirm or pick.~~ MOOT
   under R-S3′ (no tag).
2. ~~Tagged-tuple functor slot 0: tagged or untagged with
   `functor/3`/`=..` tagging at the edge?~~ ANSWERED by R-S3′: slot 0 is
   the plain spelling; the atom is `(name,)`; `functor/3`/`=..` convert at
   the edge.
3. `write/1` of a string: Scryer prints `[h,e,l,l,o]`; SWI prints text.
   Which does Clausal's `write/1` do? (`writeq`/`write_canonical` are not
   in question.)
4. `string/1`: keep as "plain str or ground SegString" or retire now that
   `atom/1`/`string/1` are disjoint again?
5. Foreign-text default (Python/JSON in = string): confirm; and the JSON
   profile loader's atom-by-vocabulary rule.
6. `-double_quotes(atom)` mass insertion: one commit per repo by the lane
   that owns it (corpus: executor-train lanes; library: trunk) — coordinate
   so it lands BEFORE the engine flip reaches canonical.
7. Whether the reverse translator (`prolog_to_clausal`) and the Prolog
   reader (`prolog_reader.py`) already emit `'x'` vs `"x"` correctly — the
   reader ruling says yes; verify.

## 8. Coordination

- Owner: `clausal-bug-fix` instance (P3 lane). Reporter/consumer: ISO
  export lane (executor-train), which will re-run the export gates and
  owns items J/K's export side; library/corpus migration is the corpus lanes'.
- Engine-main hold rules unchanged (hold canonical commits only during
  P3-3's announced landing sync). The flip must not reach canonical before
  the ratchet directive is in every corpus/library module (item I) — the
  `.pth` makes it live instantly for every lane.
- Markus Triska's question is the external clock; the honest interim
  answer given to him (2026-09-06): Clausal has no `write_canonical`,
  `"hello"` currently denotes the atom `hello`, and this is being fixed.
