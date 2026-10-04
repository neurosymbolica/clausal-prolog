# Adapter free-form outputs as strings (U2 b): needs a ruling (2026-10-04)

The 2026-10-04 ruling (D11, U2 b) asked for one Breaking commit per package to
make free-form adapter OUTPUTS strings `('$chars', s)`. It came with a
condition: check first for a conflict with the 2026-09-21 Python-boundary spec
("atom out / text in"), and build nothing if there is any conflict or
ambiguity. There is an ambiguity, so (b) was NOT built. The input-side bugs
(U2 a) were fixed, one commit per package.

## The spec lines that disagree

**For "a Python str becomes an ATOM by default":**

- `docs/superpowers/specs/2026-09-18-atoms-as-str-design.md` §3, line 90:
  > **A Python str crossing the seam (`++`, `--`, a goal argument, a dict
  > key) is an ATOM** (§8 Q1). This matches the engine and downstream code's
  > actual use (identifiers, labels, dict keys); an opaque text payload as an
  > atom is legal Prolog (`'a b c'`) ...

  §8 line 192: "**Q1.** A Python str crossing the seam is an ATOM. **Yes.**"
- `docs/superpowers/specs/2026-09-21-python-boundary-atom-and-string-design.md`,
  the dumb-seam table that superseded it (line 139):
  > | **atom** | the plain `str` — no tag | a plain `str` is the atom (main's meaning, kept) |
- `clausal/logic/to_python.py:296` (`wrap_text`, the `++`/thunk door):
  `return val  # STAGE 2: a str a thunk hands back IS the atom (identity)`.

**For "free-form text an adapter returns is a STRING":**

- `docs/superpowers/specs/2026-09-06-atoms-as-cells-strings-design.md` §9.4,
  line 643:
  > Every wrapper that documents "returns an atom" for text (file lines, env
  > values, header names, regex groups, …) now returns a **string** ...
- The 2026-10-04 adapter ruling (T2, `94815dbd`): "a symbolic identifier an
  adapter returns crosses as an atom; free-form strings stay text".
- `clausal/modules/py/__init__.py:232` (`symbol`): "Free-form strings
  (contents, paths, printed representations, user data) stay untagged and
  cross as text." `text_result` makes an untagged `str` the carrier.

## The two readings

**Reading A (doors differ).** The atom default covers the seam's own doors
(`++`, `--`, a `solve()` argument, a dict key). A `py.*` adapter is its own
door, governed by §9.4 + T2: free-form text is a string. Then (b) is a plain
consistency fix and every census item becomes a string.

**Reading B (one rule for Python strs).** The atom default is the rule for any
Python `str` that becomes a term ("a goal argument" includes an adapter's
output argument), and §9.4 + T2 are exceptions for the adapters that ALREADY
convert. Then (b) widens the exception, and the census question "should these
become text, or is free-form-stays-text only a rule for NEW adapters?" is
still open.

The two readings already give different answers for the same Python value
today:

```
X is ++(str(expr))               % X = 'x + 1'   (atom: the ++ door)
sym_str(X + 1, S)                % S = 'x + 1'   (atom: adapter, today, verified)
read_file('/etc/hostname', T)    % T = "box\n"   (string: a §9.4 adapter)
```

Under A, (b) moves the middle line to `S = "x + 1"`; under B it stays.

## What each package's outputs would become under A

| package | output | today | under A |
|---|---|---|---|
| clausal-sympy | `sym_str/2`, `latex/2`, `pretty/2`, `math_ml/2` | atom `'x + 1'` | `"x + 1"` |
| clausal-sympy | `_from_sympy_ctx` `str(expr)` fallback (an object with no term form) | atom | string -- **but** `sym/2` / `_to_sympy_ctx` read it back: the round trip `sym(T, E)` must then accept the string (it is an input, so U2 a already makes it accept both) |
| clausal-spacy | token `text`, `head_text`, `lemma`, entity/chunk `text`, `sentence/2`, `sentence_list/2` | atom | string (POS/tag/dep/label stay atoms) -- **ambiguous**: `lemma(T, run)` is the idiomatic check; a lemma reads as a symbol |
| clausal-yaml | `write/2`, `write_all/2` (a YAML document) | atom | string |
| clausal-yaml | scalars read in (`read/2`, `read_all/2`, `read_file/2`) | atom | string VALUES -- **ambiguous**: mapping KEYS stay atoms (`text_result` leaves dict keys alone), so `{name: "x"}` reads as a DictTerm with an atom key and a string value |
| clausal-scipy | `scipy_integrate` `message` | atom | string |
| clausal-scipy | `scipy_constants` unit strings (`'m s^-1'`) and constant names (`'speed of light in vacuum'`) | atom | string -- **ambiguous**: a constant name is also the KEY `lookup/4` takes |
| clausal-opencv | `haar_cascade_path/2` (a path) | atom | string |
| clausal-torch | `named_*` names (`'0.weight'`) | atom | string -- **ambiguous**: the census itself calls them "arguably symbolic" (a parameter path used as a key) |

Each would be one Breaking commit per package with a CHANGELOG entry:
`text_result` at the unify, tests and docs that compare against the atom move
to the string, and check mode keeps accepting the atom (`unify_result`
already accepts the text spelling of a tagged symbol; the mirror -- an atom
accepted where text comes back -- would need adding, or the change breaks
every `sym_str(E, 'x + 1')`).

## Questions

1. Does the "Python str is an ATOM" default (09-18 §3 Q1, dumb seam `++`)
   govern `py.*` adapter OUTPUTS, or only the seam's own doors (Reading A vs B)?
2. If A: the four **ambiguous** rows -- spacy `lemma`/`text`, yaml mapping
   keys vs values, scipy constant names, torch `named_*` -- symbol or text?
3. If A: should a check-mode argument still accept the ATOM spelling of a
   free-form result (`sym_str(E, 'x + 1')`), as it accepts the text spelling
   of a symbol today?

Blocks: U2 (b) only. U2 (a), U1, U3 and U4 do not depend on it.
