# Stage-2 pin rewrite brief — an ATOM is a Python str

## What changed in the engine (you do NOT change the engine)

Stage 1 (already on this branch's parents) made every STRING the carrier `('$chars', 'abc')`,
built by `clausal.logic.cells.chars('abc')`. Stage 2 (this branch) makes every ATOM the Python `str`:

| term | before (stage 1) | now (stage 2) |
| --- | --- | --- |
| the atom `foo` | `('foo',)` | `'foo'` — `mint("foo") == "foo"`, `is_atom("foo")` |
| a char atom `a` | `('a',)` | `'a'` — `char_atom("a") == "a"` |
| the string `"abc"` (chars mode) | `('$chars', 'abc')` | UNCHANGED — `chars("abc")` |
| `[]` / `""` (chars) | `[]` / `chars("")` | UNCHANGED (one term, the atom `'[]'`) |
| a bare Python `""` | the empty string | the atom `''` (NOT nil) |
| the 1-tuple `('x',)` | the atom | REFUSED: `TypeError: the 1-tuple ('x',) is reserved ...` |
| a Python str crossing the seam (`++`, `to_term`, a goal argument, a dict key) | the carrier | the ATOM (spec §3 Q1) |
| a thunk's str result (`++"x".upper()`) | the carrier | the ATOM |
| a 0-arity predicate `p` referenced as a VALUE | its class | the atom `'p'` (order: after its first clause) |
| a str in GOAL position (`call("foo")`, `solve("foo")`) | existence_error | the CALL of `foo/0` |
| `unify("ab", [a, b])`, `"ab" == [a, b]` (bare str) | true (text) | FALSE (an atom is not a list); `chars("ab")` still equals `[a, b]` |
| `atom("ab")` / `string("ab")` / `is_list("ab")` for a bare str | no / yes / yes | YES / no / no |
| `write`/`writeq` of a bare str | a string | an ATOM (`'a b'` quoted by writeq) |

Helpers: `mint`, `is_atom`, `spelling`, `char_atom`, `is_char_atom` (`clausal.logic.atoms`); `chars`,
`is_chars`, `chars_text` (`clausal.logic.cells`). `spelling("foo") == "foo"` (identity).

## Your job: make the assigned test files pass, editing ONLY those test files

Run a file like this (from the worktree, this python):

    cd /tmp/claude-1000/-workspace-clausal-bug-fix/1b182390-5717-4b40-933e-c91c748a9079/scratchpad/s2wt
    /workspace/clausal/venv/bin/python -m pytest tests/<file>.py -q -p no:randomly -p no:cacheprovider --tb=short

The three legitimate edits, and nothing else:
1. A literal 1-tuple that is an ATOM becomes the str: `("foo",)` → `"foo"`, `[("a",), ("b",)]` → `["a", "b"]`,
   `== ("yes",)` → `== "yes"`. A 1-tuple that is a Python tuple of NAMES or of anything else
   (`answer_names=("STATUS",)`, `fields=("term",)`, `pytest.param(("x",), ...)`, a `__slots__`) STAYS —
   read the call. When unsure whether a 1-tuple was an atom, look at what the callee does with it.
2. A test that asserted the OLD meaning of a bare str is rewritten to the new one, keeping the assertion
   exactly as strong: a bare-str argument that MEANT a string becomes `chars("...")` (most were converted
   in stage 1; the ones left are the "str means text" rows: `unify("ab", [a, b])`, `is_list("ab")`,
   `length("ab", 2)` written from Python); a test that asserted a str result of a `++` escape/`to_term`
   as the CARRIER now expects the bare str (the atom); `isinstance(x, tuple)`/`type(x) is tuple` for an
   atom becomes `type(x) is str`/`is_atom(x)`; `x[0]` to read an atom's spelling becomes `spelling(x)`.
3. A `.clausal` fixture whose Python-side harness compares against the old shapes: same edits on the Python
   side. The `.clausal` SOURCE needs a change in exactly one case: a `++(...)` escape that yields Python strs
   (`++sorted(["a", "b"])`, `++"x".upper()`, `++str(N)`) now yields ATOMS (spec §3 Q1), so a fixture that
   compared such a result against `"..."` STRINGS under `-double_quotes(chars)` must compare against atoms
   (`['a', 'b']` / `'X'`) or take the string side through `atom_chars`/`chars` -- keep the assertion's
   strength. A harness that calls a fixture test BY NAME with a bare Python str (`_succeeds("test", name)`)
   must pass `chars(name)`: under chars mode the `test("...")` head is a STRING literal.

Forbidden: editing anything under `clausal/`; deleting or skipping/xfailing a test; loosening an
assertion (`==` to `in`, dropping a check, catching the TypeError); changing what a test tests.

## When a row is NOT a pin — stop on that row and report it

If after edits 1–3 a test still fails, or the failure is not one of the shape changes in the table
(a wrong VALUE, a missing solution, a `TypeError: reserved` raised from inside `clausal/` on a term the
test never wrote as a 1-tuple, a bare str the engine hands out where a STRING is meant), leave that test
red and report it with the test id, the assertion/exception line, and your one-line reading of the
cause. Do not paper over it.

## Verify before you report

Run every assigned file and paste the summary line per file. Confirm you edited only your assigned
files: `git -C <worktree> status --short` must show only them. Do not commit. Do not run the whole suite.
Report: per file, rows fixed by edit type (1/2/3), rows left red with shapes, and the summary lines.
