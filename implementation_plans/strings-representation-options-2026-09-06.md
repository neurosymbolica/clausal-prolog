# Strings vs atoms: representation options (design note, 2026-09-06)

**Status: DECISION PENDING.** Input to the operator's ruling on how Clausal
tells a *string* (`"hello"`, unifies with `['h','e','l','l','o']`) from an
*atom* (`'hello'` / `hello`) now that P3-1 made every atom a plain interned
`str`. Supersedes nothing yet: R-S3 in
`todo/strings-lost-in-the-atom-pivot-double-quotes-are-char-lists-2026-09-06.md`
(canonical) still stands as the ruling of record until the operator rules on
this note. The other engine lanes are HOLDING until it is ruled.

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

## 2. The three candidates

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

## 3. Q2 (functor slot 0) — revised in every option

The todo's §7 Q2 asks whether the functor `str` in `("point", 1, 2)` is
tagged. F6 answers it for A and B: **slot 0 stays the plain spelling `str`**,
and `functor/3` / `=..` tag on the way out — otherwise every Python-built
cell carries a *string* functor and breaks. (The controller's earlier
"tagged slot 0" default is withdrawn.) Under C the question does not arise.
Corollary for A/B: the engine then holds atoms in two spellings (tagged in
terms, bare in functor slots and keys), which is a second identity to keep
straight in `resolve_module`, `listing/1`, arg-index keys and `PredRow`.

## 4. Comparison

| criterion | A: C0-tag atoms | B: bytes atoms | C: class-tag strings |
|---|---|---|---|
| atom re-mint sweep (item B) | full | full | none |
| P3-3 row/key/bake surfaces touched | yes | yes | no |
| C changes beyond F3 | reader guard only | bytes arms → new type | none |
| forbidden character / forging tests | yes | no | no |
| leak visibility | invisible | loud | invisible (atom where string meant) |
| Python boundary work | strip on exit | decode on exit + convert bytes on entry | wrap text on entry (policy Q-C1) or none |
| displaces an existing type | no | `bytes` | no |
| Q2 second atom spelling | yes | yes | no |
| string-op re-wrap surface | none | none | F5 (small) |
| `atom_chars`/one-char atoms | tag needed | tag needed | free |
| downstream migration | literal flip + JSON/interop rules | same + bytes rules | literal flip only |

## 5. Recommendation

**Option C**, sub-option to be settled by a one-day spike:

1. Census: classify every str-typed site in `logic/runtime`,
   `logic/builtins`, `terms.py` as atom-family / string-family / both
   (seeded by F5). Expected result: the string family is a short list.
2. Prototype C-seg and C-sub on `write_to_string/2`, the `*` star patterns
   and DCG `phrase`; micro-benchmark text-heavy paths (regex, `format`,
   slicing) A/B against today's plain `str`.
3. Fix F3 once (the arms become string-only), and pin the Scryer table.

If the operator prefers to keep tagging atoms, **B over A**: same sweep,
no forbidden character, loud leaks — at the price of displacing `bytes`.

Design-neutral and already landed: the `-double_quotes/1` ratchet
(`a961ef5d`). Design-neutral and still required: the downstream insertion of
`-double_quotes(atom)` before any literal flip reaches canonical.

## 6. Rulings needed

- **Q-C0.** Option: A / B / C-seg / C-sub.
- **Q-C1** (C only). Foreign text: does a Python/JSON `str` crossing into the
  engine arrive as an atom (today's behaviour; downstream-compatible; the
  todo's R-S3 said string) or as a string (ISO-friendly; every interop site
  and JSON loader gets a rule, as the todo's item H describes)? Recommended
  default: atom on entry, with explicit `text/1`-style conversion and a
  per-loader "values are strings" switch — revisitable once the string
  family exists.
- **Q-C2.** `write/1` of a string: text (SWI) or `[h,e,l,l,o]` (Scryer)?
  `writeq` → `"hello"`, `write_canonical` → `'.'(h,'.'(e,…))` in all cases.
- **Q-C3.** `string/1`: keep (true for the string type) — recommended.
- Superseded by this note if C is chosen: todo §7 Q1 (tag character) and Q2
  (functor slot).
