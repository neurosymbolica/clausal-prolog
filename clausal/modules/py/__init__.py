"""clausal.modules.py — Python-named wrapper modules for Clausal.

This subpackage mirrors Python library names so that Clausal imports
read naturally::

    -import_from(py.sympy, [Simplify, Solve, Diff, sin, cos])
    -import_from(py.uuid, [UUIDv4, UUIDStr, IsUUID])
    -import_from(py.yaml, [Read, Write, Get])
    -import_from(py.sqlite, [SQLiteConnect, SQLiteQuery])
    -import_from(py.datetime, [Now, Today, Date, TimeDelta])
    -import_from(py.re, [Match, Search, Replace, Split, FindAll])
    -import_from(py.logging, [GetLogger, Info, Debug, Warning, Error])

Each module re-exports predicates from its parent
``clausal.modules.*`` implementation, avoiding the name-collision
workarounds (``sympy_module``, ``uuid_mod``, ``yaml_module``, etc.).
"""
