"""clausal.modules — standard library modules for Clausal.

This package acts as the top-level search path for Clausal module imports.
When a .clausal file uses ``-import_from(regex, [Match, ...])`` or
``-import_module(regex)``, the import machinery looks here (as
``clausal.modules.regex``) if the bare module name is not found.

Available modules:

- ``regex``       — Match, Search, Replace, Split, FindAll
- ``log``         — GetLogger, Debug, Info, Warning, Error, Critical, ...
- ``date_time``   — Now, Today, Date, Time, DateTime, TimeDelta, ...
- ``yaml_module`` — Read, Write, ReadAll, WriteAll, ReadFile, WriteFile, Get
- ``sympy_module`` — Sym, Simplify, Expand, Factor, Solve, SolveAll, Diff, Integrate, Limit, Series, Subs, FreeVars, ToSympy, FromSympy

Python-named aliases (``py.*`` subpackage):

- ``py.re``       — same as ``regex``
- ``py.logging``  — same as ``log``
- ``py.datetime`` — same as ``date_time``
- ``py.yaml``     — same as ``yaml_module``
- ``py.sympy``    — same as ``sympy_module``
- ``py.uuid``     — same as ``uuid`` / ``uuid_mod``
- ``py.sqlite``   — same as ``sqlite``
"""
