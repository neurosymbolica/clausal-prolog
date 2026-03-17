"""clausal.modules — standard library modules for Clausal.

This package acts as the top-level search path for Clausal module imports.
When a .clausal file uses ``-import_from(py.re, [Match, ...])`` or
``-import_module(py.re)``, the import machinery looks here (as
``clausal.modules.py.re``) if the bare module name is not found.

Canonical modules (``py.*`` subpackage):

- ``py.re``       — Match, Search, Replace, Split, FindAll
- ``py.logging``  — GetLogger, Debug, Info, Warning, Error, Critical, ...
- ``py.datetime`` — Now, Today, Date, Time, DateTime, TimeDelta, ...
- ``py.yaml``     — Read, Write, ReadAll, WriteAll, ReadFile, WriteFile, Get
- ``py.sympy``    — Sym, Simplify, Expand, Factor, Solve, SolveAll, Diff, Integrate, Limit, Series, Subs, FreeVars, ToSympy, FromSympy
- ``py.uuid``     — UUIDv4, UUIDv1, UUIDv3, UUIDv5, UUIDStr, UUIDHex, ...
- ``py.sqlite``   — SQLiteConnect, SQLiteQuery, SQLiteExec, SQLiteTable, ...

Legacy aliases (backward compatibility shims — re-export from ``py.*``):

- ``regex``       → ``py.re``
- ``log``         → ``py.logging``
- ``date_time``   → ``py.datetime``
- ``yaml_module`` → ``py.yaml``
- ``sympy_module``→ ``py.sympy``
- ``uuid_mod``    → ``py.uuid``
- ``sqlite``      → ``py.sqlite``
"""
