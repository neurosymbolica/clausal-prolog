# Diagnostics and CLI help name only `.clausal`, never the `.seam` alias

**Filed** 2026-09-10, engine lane, at 820dc66f. **Severity Low** — every one of these
BEHAVES correctly on either suffix; they INSTRUCT as though only one exists.
**Not committed when filed:** written during a landing hold for another lane's sweep.

## The class

the harness lane found the shape in their tooling and named it well: *the tool behaves
right and instructs wrong*. A refusal message synthesises a filename with one suffix into
the sentence telling a human which file to open, while the code beside it resolved the real
path correctly. iso-export-lane found it in five of their messages, where it is worse: the
repair such a message invites creates a file that SHADOWS the real module, because the
finder takes the first suffix.

**The engine does NOT have the dangerous variant.** No engine message synthesises a filename
to open, and the diagnostic that comes closest — the missing-module report in
`import_diagnostics.py` — ends with "fix the module path ..., or create that module", naming
no suffix at all. What the engine has is the milder form: messages that ENUMERATE the file
kinds it accepts and omit the alias.

## Measured, not recalled

Instrument: parse every tracked `clausal/*.py` with `ast`; take every non-docstring string
constant containing the first suffix; keep those WITH whitespace (a path or glob has none —
those were fixed in 820dc66f; prose is the class here); report whether the string also names
the alias. Positive control: a synthetic message naming only the old suffix is caught.

    strings naming the old suffix       20
    of which also name the alias         8
    naming ONLY the old suffix          12   <- 11 real, 1 false positive

**False positive, recorded so nobody "fixes" it:** `clausal/terms.py:3225` is a CSS rule,
`.clausal-output { ... }`, inside an HTML style block. A suffix-shaped token is not always a
suffix.

**The eleven, in the order they should be judged.**

Instructs the reader where to put code — closest to the dangerous shape:

- `clausal/logic/seam.py:312` — "host this code in a `.clausal` file". Implicitly
  concatenated: 312 is the node's first line (what the sweep reports); the suffix is on 314. A `.seam` file works
  identically today, and after the extension flip `.clausal` becomes the ISO-like surface
  where this code would NOT work, so this message becomes actively wrong rather than merely
  incomplete. Fix this one first.
- `clausal/templating/term_rewriting.py:6451` — "declare constants in a `.clausal` module".

Enumerates what was searched, so the reader concludes the alias was not:

- `clausal/import_diagnostics.py:482` and `:485` — "No .clausal file, .pl file or Python
  module called 'X' is on the import path". The search itself is suffix-correct.
- `clausal/logic/solve.py:734` — "Expected a clausal Module or an imported .clausal module".
- `clausal/logic/solve.py:814` — the module-designator existence error.

States a restriction that applies to both spellings:

- `clausal/templating/term_rewriting.py:2027` — "Python 'lambda' syntax is not supported in
  .clausal files".

CLI help. The tools ACCEPT the alias — verified by running each on a `.seam` input, all
producing the same output as for the `.clausal` twin — so the defect is the sentence:

- `clausal/tools/clausal_to_prolog.py:2926`, `:2930`
- `clausal/tools/prolog_to_clausal.py:1167`, `:1170`

`clausal/tools/translate.py:92` already reads "(.clausal, its alias .seam, or .pl)" and is
the model to copy.

## Why the earlier sweep missed it

The exit check added in 820dc66f (`tests/rewrite/test_cli.py`) deliberately SKIPS strings
containing whitespace, because it hunts path construction and a path has no spaces. Correct
for its job and structurally blind to this one. Two defects, two instruments — the lesson
iso-export-lane drew after seven sites across three trees: a prerequisite verified by one
instrument should not be recorded as met.

## Exit criterion

Every message naming the source suffix names both spellings, or names neither. Re-run the
sweep; expect the CSS false positive and nothing else.

Consider whether the enumerating messages should name suffixes at all. "No module called 'X'
is on the import path" is shorter, needs no maintenance at the next rename, and loses
nothing a reader wanted.

## The sweep

Run from the repo root, feeding this to python on stdin so cwd is on the path:

    import ast, pathlib, subprocess, sys
    sys.path.insert(0, ".")
    from clausal._suffixes import CLAUSAL_SUFFIXES
    OLD, NEW = CLAUSAL_SUFFIXES[0], CLAUSAL_SUFFIXES[1]
    listing = subprocess.run(["git", "ls-files", "-z", "clausal/*.py"],
                             capture_output=True, text=True).stdout
    files = [f for f in listing.split(chr(0)) if f]

    def docstrings(tree):
        out = set()
        kinds = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        for n in ast.walk(tree):
            if isinstance(n, kinds):
                b = getattr(n, "body", None)
                if (b and isinstance(b[0], ast.Expr)
                        and isinstance(b[0].value, ast.Constant)
                        and isinstance(b[0].value.value, str)):
                    out.add(id(b[0].value))
        return out

    ctl = ast.parse('raise ValueError("no .clausal file called x")')
    assert any(OLD in n.value for n in ast.walk(ctl)
               if isinstance(n, ast.Constant) and isinstance(n.value, str)), "CONTROL FAILED"

    for f in files:
        tree = ast.parse(pathlib.Path(f).read_text())
        ds = docstrings(tree)
        for n in ast.walk(tree):
            if (isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and id(n) not in ds and OLD in n.value
                    and any(c.isspace() for c in n.value)):
                tag = "both" if NEW in n.value else "OLD ONLY"
                print(f"[{tag}] {f}:{n.lineno}", n.value.strip()[:80])
