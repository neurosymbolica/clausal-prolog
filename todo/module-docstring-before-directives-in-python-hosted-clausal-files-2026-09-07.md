# A module docstring cannot precede the directives in a `.clausal` file

Found 2026-09-07 during the first migration of a Python program into a
`.clausal` host file (the `--` seam work): a file that starts with a Python
module docstring, as every Python file conventionally does, cannot then carry
`-module(...)`, `-double_quotes(...)` or `-import_from(...)` — the directives
must come first, so the docstring had to become comments.

With the Python-style surface re-assigned as the EMBEDDING language (Python
that speaks terms), Python files are going to be moved into `.clausal` hosts
wholesale, and each will want its docstring. The rewriter should accept a
leading `Expr(Constant(str))` before the directive block and keep it as the
module docstring (`__doc__`), exactly as Python does.

Also from the same migration, worth stating in `docs/python_integration.md`
next to the seam section: a plain `.py` launcher that imports a `.clausal`
module must `import clausal` first, or the import hook is not installed and
the module reads as missing — a confident-looking wrong error.
