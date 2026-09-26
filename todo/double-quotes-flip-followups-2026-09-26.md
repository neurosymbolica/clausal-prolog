# Follow-ups from the `-double_quotes` default flip (atom -> chars), 2026-09-26

The engine default is now `chars`: a `"..."` literal in a module that declares
nothing is a STRING (the chars carrier, unifying with its char list), as in
Scryer and Trealla.  `-double_quotes(atom)` is the opt-out.  Every in-tree
source that relied on the atom reading was pinned by `tools/double_quotes_pin.py`
(245 `.clausal`/`.seam` files, 371 embedded test sources); `clausal/examples`
and `docs/tutorial.md` were migrated properly (`"x"` -> `'x'`).

## Out-of-tree sources

Downstream trees that relied on the atom reading must ADD
`-double_quotes(atom)` (their owners' call; ADD instructions, not
replacements) or convert.  The measured file list went to the owners in the
handoff report for this flip; it is deliberately not in this repository.
`tools/double_quotes_pin.py pin <paths>` does the ADD mechanically (one
`-double_quotes(atom)` line after the leading comment block), and `pin-py`
covers Clausal source embedded in Python test strings.

## Docs pass

About 1,100 lines inside ```clausal fences across `docs/*.md` still write
`"..."` where an atom is meant (builtins.md 237, regex.md 74, type_checking.md
54, syntax.md 47, io.md 39, ...).  `docs/tutorial.md` is migrated; the other
snippets that tests execute (metainterpreters.md) run against the migrated
`clausal/examples`.  The rest reads wrong now: `parent("alice", "bob")` is a
fact about strings.  Migrate to `'alice'` / bare declared atoms, or say where
a string is meant.

## The cross-mode literal lint's gap

`ClausalCrossModeLiteralWarning` fires at load for a goal-position seam
literal whose callee is statically known (an `-import_from` name, or
`--m.pred(...)` over an `-import_module`'d base).  A base bound at RUN time
(`module = _RULE.get()` inside a function; `seam.with_bases`) has no module
at load, and a first-call check was declined: by then the argument is a
term, and a chars carrier reaching an atom-mode module is not evidence of a
written `"..."`.  If the hazard bites a real caller, a `-double_quotes`-aware
`with_bases` that knows the LITERAL positions of the goal is the shape.

## Visible behaviour

* `writeln("hi")` in a default-mode module prints `[h,i]` (the char list), as
  Scryer's `write` does; `writeln('hi')` prints `hi`.
* A Python `solve(("greeting", "hello"), module=m)` no longer matches a fact
  `greeting("hello"),` -- the Python str is an atom, the fact holds a string.
  Pass `chars("hello")`, or write the fact `greeting('hello')`.
* `atom("x")` is false and `string("x")` true; `"abc"` unifies with
  `['a', 'b', 'c']`.
* The Prolog exporter emits a default-mode `"x"` as the Prolog string `"x"`
  with no `set_prolog_flag(double_quotes, ...)`: both target engines default
  to chars.  An atom-mode module's literals are emitted as atoms, as before.
