# fix(A10-F010): .clausal/.pl files shadow not-yet-imported stdlib modules; import.md claims otherwise

**Problem.** `sys.meta_path[:] = [PredicateFinder(), PrologFinder(),
ModulesFinder(), *sys.meta_path]` (import_hook.py:594) puts the extension
finders ahead of PathFinder. Any `wave.clausal` / `colorsys.pl` on sys.path
(cwd included) is imported AS the stdlib module for names not already in
sys.modules. `docs/import.md` §Caveats states: "A file like os.pl or re.pl on
sys.path will not shadow the Python standard library" — true only for modules
clausal itself has already imported.

**Repro/test.** test_10_rewriting_import.py::test_F010_stdlib_not_shadowed_by_clausal_file
(xfail, subprocess).

**Fix.**
1. Docs: correct the caveat (the Perl-file caveat two lines up already
   implies the finders see everything).
2. Guard (recommended per A10-D002, parked): in `_ExtensionFinder.find_spec`,
   if `tail in sys.stdlib_module_names` emit a loud
   `ClausalLintWarning` (or refuse unless an env var / explicit registration
   opts in). A `.pl`/`.clausal` file named after a stdlib module is almost
   always an accident.

**Design ref.** A10-D002 (parked).
