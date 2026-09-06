# Strings vs atoms: representation options (design note, 2026-09-06)

**Status: RULED — Option D (operator, 2026-09-06).** Atoms are arity-0
cells `("bar",)`; plain `str` is a string; functor slot 0 stays the plain
spelling. This supersedes R-S3 (C0-tag) and answers Q1/Q2 of
`todo/strings-lost-in-the-atom-pivot-double-quotes-are-char-lists-2026-09-06.md`
(canonical); R-S1, R-S2 and R-S4 stand. The note was written as input to
that ruling and is kept as its record; §5's plan shape is the seed of the
implementation plan.
Revision 2 (2026-09-06): adds Option D (atoms as arity-0 cells, the
operator's proposal), measured in F7, and flips the recommendation to D.

The target semantics (R-S1, Scryer's) and the migration ratchet (R-S4,
`-double_quotes/1`, acceptance landed as `a961ef5d`) are **not** in question
here — every option below delivers the same observable rows of the Scryer
table. Only the representation is.

## 1. Facts measured on the tree (`fe09b472` + ratchet), with locations

F1. **The C unifier has no atom-specific fast path.** `str~str` and
`bytes~bytes` both fall through to `PyObject_RichCompareBool(.., Py_EQ)` at
the bottom of `do_unify` (`clausal/logic/variables/_variables.c:1314`).
CPython's rich compare for both `str` and `bytes` checks identity first, so
interned atoms of either type compare at pointer speed. The `str↔list` cons
rule was retired in place (`:1168–1179`, comment block).

F2. **`bytes` already has engine semantics in C.** Two `bytes↔list` codes
arms (`_variables.c:1188`, `:1225`: `b"abc"` unifies element-wise with
`[97,98,99]`), and PyBytes arms in `clausal/logic/runtime/_list_unify.c`
(`:251`, `:268`, `:420`, `:468`). `b"…"` = code list is a live rule, ruled
2026-09-04, not merely a literal lowering.

F3. **`_list_unify.c` treats every `str` as a char sequence** —
`PyUnicode_Check` at `:91`, `:126`, `:241`, `:261`, `:268`, `:403`, `:498`.
This is *why* today `is_list("hello")` and `length("hello", 5)` succeed on
what is an atom while `[H|T] = "hello"` fails (the inconsistency in the
todo's §1 table). **Every option must fix these arms**; they are not a cost
that distinguishes the options.

F4. **`SegString`** (`clausal/terms.py:1002`) is a small `__slots__` Python
class: `__unify__` (`:1149`; a `str` arm and a `list` arm), `__eq__`
(`:1295`), `__hash__` (`:1315`), `__walk__` → plain `str` when ground. The C
unifier reaches it through the generic `__unify__` protocol probe
(`_variables.c:1260–1300`), no type-specific C. Its `str` arm does
`walked == other` for the ground case — under *any* string/atom split that
one line becomes "fail: a string never unifies with an atom".
**Producers outside `terms.py`: six sites** — `runtime/body_star_unify.py:132,
:301`, `builtins/inspection.py:95`, `builtins/dcg.py:220`,
`builtins/lists.py:942, :944`.

F5. **The builtin families are already split the ISO way.**
`builtins/chars.py` is entirely the ATOM family (`char_code`, `upcase_atom`,
`downcase_atom`, `atom_length`, `atom_chars`, `atom_codes`, `atom_concat`,
`sub_atom`, `number_chars`, `number_codes`, `char_type`) and operates on plain
`str`. The STRING-producing surface today is small: `write_to_string/2`,
`term_to_string/2`, `string/1`/`is_str/1`, the in-body `*` star patterns
(`body_star_unify.py` → `SegString`), DCG `phrase` over `SegString`, the Z3
string theory (`z3.string*`, `z3_str_*`, Python `str` in and out), and
Python interop (`++`, `py.*`, JSON loaders). There is no
`sub_string/5`, `string_concat/3`, `split_string/4` or `string_chars/2` to
retarget — they would be NEW builtins under every option.

F6. **`("point", 1, 2)` is the public Python term representation** (P3-2
coordination note to the downstream lanes: "build tuples directly"). Python
code constructs cells with a plain-`str` functor in slot 0.

F7. **The engine already accepts an atom spelled as a 0-arity cell.** A
head `probe(("qux",), 2)` compiles and solves on the tree today (one
answer); `compiler/arg_index.py:64` keys the argument as `("qux", 0)` (the
cell branch); P3-3 already wraps a bare-`str` goal as the 0-arity cell and
calls `("true",)` / `("!",)`. Micro-benchmarks (CPython 3.13, warm,
`min` of 5×1M): `unify(("bar",), ("bar",))` 73 ns vs `unify("bar", "bar")`
75 ns (call-overhead dominated; the tuple arm is a size check plus one
element compare on an interned `str`); dict lookup keyed by the canonical
1-tuple 21.7 ns vs 21.1 ns for the `str`, **29.5 ns for a distinct but
equal tuple** (hash recompute + element compare) — interning discipline
matters for the arg index, nothing else.

## 2. The four candidates

### Option A — tag the atoms with a leading C0 control (R-S3 as ruled)

Atom = `str` whose first character is an unused control (RS 0x1E proposed);
plain `str` = string. Everything in the todo's §3/§5 applies.

### Option B — atoms are `bytes` (UTF-8 spelling); the class is the tag

Atom = interned `bytes`; plain `str` = string. Compared with A:

- *Better:* no forbidden character → no reader-refusal rule, no forging path,
  no "what if a tag appears in data" tests. UTF-8 byte order = code-point
  order, so atom standard order is free. Builtin type: pickling, marshalling
  and subinterpreter channels are fine (the todo's objections to a `str`
  subclass do not apply). Leaks are **loud**: `b'foo'` in a traceback, a
  `TypeError` from `getattr`/`%s`/`json.dumps` — where a C0-tagged `str`
  leaks invisibly.
- *Same as A:* the whole of item B (re-mint every atom site: the 17-file
  P3-1 footprint, `PredRow`/`$disp_`/`arg_index` keys, module names, every
  `chars.py` builtin, K3 constants, `functor/3`, `=..`) and every
  atom→Python-identifier crossing (`module_dict` keys, dot-attribute access,
  kwargs, exception text, JSON keys) — a `.decode()` per crossing instead of
  a strip. Memoise both directions in `atoms.py` or pay an allocation each.
  `atom_length`/`sub_atom` must count code points, not bytes.
- *Worse:* **displaces `bytes`.** The F2 arms and the `b"…"` lowering move
  to an internal byte-string/int-list type, and every `bytes` crossing in
  from Python (file reads, hashes, sockets, `struct`) must be converted on
  entry or it is misread as an atom. That is a boundary sweep in **both**
  directions; A only strips on exit.

### Option C — class-tag the STRINGS; atoms stay P3-1 plain `str`

String = a dedicated type; atom = the interned plain `str` P3-1 made it.
This is the "mirror option" the todo rejected; the two rejection reasons do
not survive contact with the code:

- "every string op would have to add/strip the tag, disturbing the mature
  machinery" — with a *class* there is no tag to strip. Ops work on the
  payload and re-wrap the result; the mature `str` machinery is untouched.
- "foreign text would keep arriving as atoms" — true, and a policy choice
  (§4 Q-C1). It is also exactly what the downstream corpus, the JSON loaders
  and every Python-side test rely on today.

What C buys:

- **Atoms untouched.** Everything P3-1 and P3-3 built stays: interned `str`,
  identity by spelling, rows, `$disp_` bake, arg index, module dicts, dot
  access, kwargs, JSON keys, the whole `chars.py` family. Item B vanishes.
  `atom_chars(hello, C)` already yields one-char `str`s, which under C *are*
  one-char atoms — correct for free; under A/B they need tagging.
- **Q2 dissolves** (§3): slot 0 of a cell is an atom because it is a `str`,
  exactly as today; F6's Python-built cells keep working.
- **Near-zero C.** The string cons rule already lives in
  `SegString.__unify__` (F4); the only C work is F3, owed under every option.
- **Migration collapses** to the `"…"` literal lowering (behind the ratchet,
  unchanged plan) plus the string-producing surface in F5, which is small
  and enumerable. Pin `string/1` on every string-builtin result.

Two sub-options for the ground case (`SegString` stays for holes either way):

- **C-seg:** ground string = one-segment `SegString`. Simplest; one Python
  object hop per text op; `__eq__`/`__hash__`/`__walk__` exist.
- **C-sub:** ground string = `Text(str)` subclass. All `str` machinery works
  via `isinstance(x, str)`, slicing/regex/`format` are native speed, pickles
  by class reference. The todo's subclass objections were about ATOMS
  (interning, `PyUnicode_CheckExact` identity paths, subinterpreter sharing)
  and do not bite for strings, which need no interning. Every C arm found is
  `PyUnicode_Check` (subclass-inclusive), so F3's fix must discriminate
  `Text` from plain `str` explicitly there — the same edit F3 needs anyway.

C's honest costs:

- The **silent-leak direction flips**: a string op that returns a bare `str`
  has produced an atom. Same bug class as an A leak, mirror direction, needs
  the same pins — but the producing surface (F5) is far smaller than A/B's
  atom-minting surface.
- `""` ≡ `[]` and "a string orders as the compound list it denotes" go into
  `__eq__`/standard-order compare — small, but must not make a ground
  `Text` hash-equal to an atom of the same spelling.
- The Z3 string theory and Python interop need an explicit rule (§4 Q-C1).

### Option D — atoms ARE arity-0 cells; plain `str` = string

Atom = the 1-tuple `("bar",)` — the same shape P3-2 gave every compound,
at arity 0. Functor slot 0 stays the plain spelling `str`; a plain `str`
anywhere else is a *string*. `foo(bar, "baz")` is `("foo", ("bar",), "baz")`.
The canonical object per spelling comes from `mint()` (an interned `str`
inside an interned 1-tuple), so identity by spelling is preserved.

What D gets for free (F7):

- **atom ≠ string with no new unifier arm** — tuple vs `str` hits the
  existing guard just above `_variables.c:1314` and fails.
- **F3 stops being a bug.** Plain `str` *is* the string, so
  `_list_unify.c` treating `str` as a char sequence is now *correct*, the
  `SegString` `str` arm (F4) is correct, and the retired cons rule
  (`:1168–1179`) comes back for plain `str` with no "unless tagged"
  condition. A, B and C all owe the F3 fix; D does not.
- **Q2 resolved by construction.** Slot 0 = spelling; the atom as a term =
  the 1-tuple; `functor/3` and `=..` convert at the edge
  (`functor(("foo", X), F, 2)` → `F = ("foo",)`). F6's Python-built cells
  are unchanged.
- **The `(name, 0)`-vs-resolved-value hazard disappears** — the bug class
  behind the corpus atom-index regression (`d0f2bad5`). The atom's index key
  *is* `("bar", 0)` because the atom *is* the 0-arity cell.
- **One term model:** Var | number | `str` = string | list | cell, with
  `call(X)` of an atom being the 0-arity goal without wrapping — the
  direction P3-3 already took. ISO standard order ("compounds by arity, then
  name") puts atoms first with no special case.
- **Boundaries:** the bytecode cache marshals a constant tuple (no
  construction call at load, unlike C); raw-shareable across
  subinterpreters; pickles; no forbidden character; `bytes` untouched;
  strings cross into Python callees unchanged (C-sub's best property).
  Leaks are **loud** — `getattr`, `re`, `open`, `%s`-into-an-identifier all
  raise on a tuple (B's best property).
- **No measurable unifier or index cost** (F7 numbers).

D's honest costs:

- **The full atom sweep (item B), as under A/B:** every minting site →
  `mint(name)`; every consumer of a spelling → `[0]`; atoms crossing into
  Python wrappers unwrap on the way in (strings need nothing). Module
  attributes change type — `mod.bar` is `"bar"` today and becomes
  `("bar",)` — a loud downstream break class that must be announced.
- **Migration profile is R-S3's, not C's:** foreign text arrives as a
  string, so identifier-shaped `"x"` literals and JSON values used as atoms
  downstream migrate (todo items H/K). This is the policy the operator
  already ruled on 2026-09-06, so it is a cost relative to C only.
- **Chars are 1-tuples:** `atom_chars(("hello",), C)` → `[("h",), ("e",),
  …]`. Needs an interned single-char atom table so the reinstated cons rule
  compares and binds `(c,)` without allocating per character. This is the
  one real C change beyond F3-as-correct.
- JSON: an atom dumps as `["bar"]` unless the codec maps it — the codec is
  owed under A/B too; only C avoids it.
- Sweep items to enumerate in the plan: K3 `true`/`false`/`undefined`, the
  module argument of `(":", Module, Goal)`, `resolve_module`, `listing/1`'s
  indicator forms, `DictTerm` atom keys, the renderer (arity-0 cells already
  print as the bare name, so `write/1` is largely free; `writeq` quotes by
  the ISO rules).
- Interning discipline is load-bearing for index speed (the 29.5 ns
  distinct-tuple case): `mint()` returns the canonical object; the loader
  canonicalises literal tuples in bytecode constants at module load.

## 3. Q2 (functor slot 0) — revised in every option

The todo's §7 Q2 asks whether the functor `str` in `("point", 1, 2)` is
tagged. F6 answers it for A and B: **slot 0 stays the plain spelling `str`**,
and `functor/3` / `=..` tag on the way out — otherwise every Python-built
cell carries a *string* functor and breaks. (The controller's earlier
"tagged slot 0" default is withdrawn.) Under C the question does not arise;
under D it is answered by construction (slot 0 = spelling, atom = 1-tuple).
Corollary for A/B: the engine then holds atoms in two spellings (tagged in
terms, bare in functor slots and keys), which is a second identity to keep
straight in `resolve_module`, `listing/1`, arg-index keys and `PredRow`.
D has the same two spellings but not a second *identity*: the 1-tuple's
identity is its spelling, and `(name, 0)` is already what the index keys.

## 4. Comparison

| criterion | A: C0-tag atoms | B: bytes atoms | C: class-tag strings | D: atoms = 0-arity cells |
|---|---|---|---|---|
| atom re-mint sweep (item B) | full | full | none | full |
| P3-3 row/key/bake surfaces touched | yes | yes | no | keys already `(name, 0)`; rows/bake re-mint |
| F3 (`_list_unify.c` str arms) | fix | fix | fix | **already correct** |
| C changes beyond F3 | reader guard only | bytes arms → new type | none | cons rule back + 1-char atom table |
| forbidden character / forging tests | yes | no | no | no |
| leak visibility | invisible | loud | invisible (atom where string meant) | loud |
| Python boundary work | strip on exit | decode on exit + convert bytes on entry | wrap text on entry (policy Q-C1) or none | unwrap atoms on exit; strings none |
| displaces an existing type | no | `bytes` | no | no |
| Q2 second atom spelling | yes | yes | no | by construction |
| string-op re-wrap surface | none | none | F5 (small) | none |
| `atom_chars`/one-char atoms | tag needed | tag needed | free | interned 1-tuple table |
| bytecode-cache constants | str | bytes | construction call per string | constant tuple |
| `mod.atom` attribute type | tagged str | bytes | unchanged | `("atom",)` (loud break) |
| downstream migration | literal flip + JSON/interop rules | same + bytes rules | literal flip only | literal flip + JSON/interop rules |

## 5. Recommendation

**Option D.** It dominates A and B on every axis — the same sweep, none of
their mechanical costs (no tag character, no `bytes` displacement, no
decode), and it *removes* two problems the others merely avoid: F3 becomes
correct instead of needing a fix, and the `(name, 0)` hazard goes away.

Against C the trade is unchanged in kind — C is the cheaper **path** (no
atom sweep, no downstream literal/JSON migration; but keeps F3, the string
re-wrap surface, the silent atom-where-string leak and the bytecode
construction calls); D is the cleaner **end state** (one term model,
consistent with P3-3, atoms loud when they leak). Because the operator has
already ruled R-S3's migration policy (foreign text = string), C's
migration advantage no longer counts, and what remains — a bounded,
mechanical atom sweep versus a string re-wrap surface plus F3 — favours D.

Plan shape (supersedes the C spike):

1. `mint()` returns the canonical `(name,)`; interned 1-char table; the
   loader canonicalises literal 1-tuples in bytecode constants.
2. Atom sweep (item B) over the P3-1 footprint, `chars.py`, K3 constants,
   `functor/3`, `=..`, `resolve_module`, `listing/1`, `DictTerm` keys,
   renderer/`writeq`; atoms unwrap at the Python wrappers.
3. Reinstate the `str↔list` cons rule for plain `str` (chars as 1-tuples);
   confirm the F3 arms are string-only by construction; pin the Scryer
   table.
4. Perf gate as usual (interleaved A/B, not saved baselines) — the index
   and unifier are measured neutral (F7); the sweep's risk is a
   non-canonical tuple reaching the index.
5. Announce the `mod.atom` type change to the downstream lanes together
   with the `-double_quotes` flip.

Fallbacks, in order: **C** if the operator wants the atom sweep avoided
(sub-option by the one-day spike described in the previous revision of this
note); **B over A** if atoms must stay `str`-shaped with a tag.

Design-neutral and already landed: the `-double_quotes/1` ratchet
(`a961ef5d`). Design-neutral and still required: the downstream insertion of
`-double_quotes(atom)` before any literal flip reaches canonical.

## 6. Rulings needed

- **Q-C0.** Option: **D (recommended)** / C-seg / C-sub / B / A.
- **Q-C1** (C only; A, B and D take R-S3 as ruled — foreign text is a
  string). Foreign text: does a Python/JSON `str` crossing into the
  engine arrive as an atom (today's behaviour; downstream-compatible; the
  todo's R-S3 said string) or as a string (ISO-friendly; every interop site
  and JSON loader gets a rule, as the todo's item H describes)? Recommended
  default: atom on entry, with explicit `text/1`-style conversion and a
  per-loader "values are strings" switch — revisitable once the string
  family exists.
- **Q-C2.** `write/1` of a string: text (SWI) or `[h,e,l,l,o]` (Scryer)?
  `writeq` → `"hello"`, `write_canonical` → `'.'(h,'.'(e,…))` in all cases.
- **Q-C3.** `string/1`: keep (true for the string type) — recommended.
- **Q-D1** (D only). Python-side atom construction: the `("bar",)` literal
  *is* the representation and needs no helper; recommend exporting `mint()`
  for code that wants the canonical object. A bare `"bar"` from Python is a
  string.
- **Q-D2** (D only). `write/1` of an atom prints the bare spelling (as
  arity-0 cells already render); `writeq` quotes by the ISO rules — confirm.
- Superseded by this note if C or D is chosen: todo §7 Q1 (tag character)
  and Q2 (functor slot).

## 7. Appendix — what each boundary does, per option

Boundaries that exist on the tree (the engine uses no pickle,
multiprocessing or subinterpreters; venv CPython 3.13):

| boundary | where | A: C0-tag | B: bytes | C: class strings | D: 0-arity cells |
|---|---|---|---|---|---|
| bytecode cache (marshal) | `import_hook.py:396–480`, `CLAUSAL_BYTECODE_TAG = 8` | str constant | bytes constant | subclass / `SegString` **not marshallable** → a construction call per string literal; bump the tag | tuple constant; bump the tag |
| Python callees / `py.*` | `modules/py/_helpers.py::_deep_deref` (str passes through) | strip on exit | decode on exit; convert `bytes` on entry | pass the payload `str` (C-sub: is-a `str`, free) | unwrap `[0]` on exit for atoms; strings pass |
| JSON | `modules/py/json.py:46–72` (pass-through) | strip keys/values | decode | strings native; atoms as today | codec: atom ↔ `str` by policy, else dumps as `["bar"]` |
| dict keys / `DictTerm` | atom keys are `str` today | tagged keys | bytes keys | unchanged | 1-tuple keys (21.7 ns canonical) |
| threads | shared heap | nothing | nothing | nothing | nothing |
| subinterpreters (none today) | would need a channel | str shares raw | bytes shares raw | `SegString` / subclass must pickle | tuple-of-str shares raw |
| ISO translator | `clausal_to_prolog.py:723 _convert_constant` (str → PAtom) | strip → PAtom; plain → PString | decode → PAtom | `str` → PAtom; string class → PString | 1-tuple → PAtom; `str` → PString |
