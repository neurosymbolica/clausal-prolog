"""clausal.modules.py — Python-named module implementations for Clausal.

This subpackage contains the canonical implementations of Clausal's
Python library wrappers, using the same names as the libraries they
wrap::

    -import_from(py.sympy, [Simplify, Solve, Diff, sin, cos])
    -import_from(py.uuid, [UUIDv4, UUIDStr, IsUUID])
    -import_from(py.yaml, [Read, Write, Get])
    -import_from(py.sqlite, [SQLiteConnect, SQLiteQuery])
    -import_from(py.datetime, [Now, Today, Date, TimeDelta])
    -import_from(py.re, [Match, Search, Replace, Split, FindAll])
    -import_from(py.logging, [GetLogger, Info, Debug, Warning, Error])
    -import_from(py.random, [Random, RandomInteger, RandomMember, Maybe])
    -import_from(py.json, [Parse, Generate, Get, ReadFile])
    -import_from(py.csv, [Parse, ParseRow, ReadFile, ReadRecords])
    -import_from(py.os, [EnvironmentVariable, WorkingDirectory, Pid, Platform])
    -import_from(py.files, [FileExists, DirectoryFiles, ReadFileToString, JoinPath])
    -import_from(py.process, [Shell, ShellOutput, ProcessCreate, Sleep])

The legacy names (``sympy_module``, ``uuid_mod``, ``yaml_module``,
``regex``, ``log``, ``date_time``, ``sqlite``) are compatibility shims
that re-export from here.
"""


def _import_stdlib(name):
    """Import a stdlib/third-party module, bypassing clausal's ModulesFinder.

    Prevents circular imports when a ``py/*.py`` implementation file has
    the same name as the Python module it wraps (e.g. ``py/uuid.py``
    wrapping stdlib ``uuid``).
    """
    import importlib
    from clausal.import_hook import ModulesFinder

    ModulesFinder._resolving.add(name)
    try:
        return importlib.import_module(name)
    finally:
        ModulesFinder._resolving.discard(name)
