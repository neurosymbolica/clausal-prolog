# Move string/atom predicates to C

## Context

`clausal/logic/builtins/chars.py` (501 lines) implements 11 ISO Prolog string
and atom predicates: `atom_chars/2`, `atom_codes/2`, `atom_concat/3`,
`atom_length/2`, `char_code/2`, `char_type/2`, `upcase_atom/2`,
`downcase_atom/2`, `sub_atom/5`, `number_chars/2`, `number_codes/2`.

These are standard operations used in any string-processing Prolog program.
`sub_atom/5` is particularly interesting — it's non-deterministic and generates
all substrings matching a pattern.

## What to move

```python
atom_chars/2       # atom ↔ list of chars (bidirectional)
atom_codes/2       # atom ↔ list of char codes (bidirectional)
atom_concat/3      # concatenation (3 modes)
atom_length/2      # string length
char_code/2        # char ↔ integer code
char_type/2        # character classification
upcase_atom/2      # uppercase conversion
downcase_atom/2    # lowercase conversion
sub_atom/5         # substring search (non-deterministic)
number_chars/2     # number ↔ list of chars
number_codes/2     # number ↔ list of codes
```

## Gotchas

1. **`sub_atom/5` is non-deterministic** with 5 arguments:
   `sub_atom(Atom, Before, Length, After, SubAtom)`.  It generates all
   combinations of Before/Length/After that produce SubAtom from Atom.
   Needs trampoline protocol support.

2. **`atom_concat/3` has multiple modes** including the generate mode
   `atom_concat(X, Y, "abc")` which produces all splits.  Non-deterministic.

3. **Unicode**: Python strings are Unicode.  `char_code/2` should use Unicode
   code points, not bytes.  C implementation should use Python's Unicode API
   (`PyUnicode_*` functions).

4. **`atom_chars/2` bidirectionality**: `atom_chars("hello", X)` → X=["h","e","l","l","o"]
   and `atom_chars(X, ["h","e","l","l","o"])` → X="hello".

## Overlaps

None with existing todos.

## How to verify

```bash
python -m pytest tests/ -k "chars or atom or string" -x -q
python -m pytest tests/conformity/ -x -q
python -m pytest tests/ --ignore=tests/test_trealla_backend.py -x -q
```
