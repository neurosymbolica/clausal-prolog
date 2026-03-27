"""clausal.modules — standard library modules for Clausal.

This package acts as the top-level search path for Clausal module imports.
when a .clausal file uses ``-import_from(py.re, [Match, ...])`` or
``-import_module(py.re)``, the import machinery looks here (as
``clausal.modules.py.re``) if the bare module name is not found.

Canonical modules (``py.*`` subpackage):

- ``py.re``       — Match, Search, Replace, Split, findall
- ``py.logging``  — GetLogger, Debug, Info, Warning, Error, Critical, ...
- ``py.datetime`` — Now, Today, Date, Time, DateTime, TimeDelta, ...
- ``py.yaml``     — Read, write, ReadAll, WriteAll, ReadFile, WriteFile, Get
- ``py.sympy``    — Sym, Simplify, Expand, Factor, Solve, SolveAll, Diff, Integrate, Limit, Series, Subs, FreeVars, ToSympy, FromSympy
- ``py.uuid``     — UUIDv4, UUIDv1, UUIDv3, UUIDv5, UUIDStr, UUIDHex, ...
- ``py.sqlite``   — SQLiteConnect, SQLiteQuery, SQLiteExec, SQLiteTable, ...
- ``py.spacy``    — LoadModel, UnloadModel, CurrentModel, Process, Token, TokenText, TokenList, Pos, Tag, Lemma, Dep, Head, Shape, IsAlpha, IsStop, Entity, EntityList, Sentence, SentenceList, Similarity, NounChunk
- ``py.units``    — SI base/derived unit predicates, SI prefix constants, has_units, StripUnits (canonical: ``units``)
- ``py.imperial`` — imperial and non-SI unit vectors (inch, foot, pound_mass, mph, …) (canonical: ``imperial``)
- ``py.random``   — Random, RandomFloat, RandomInteger, RandomMember, RandomPermutation, RandomSample, RandomSeed, Maybe
- ``py.json``     — Parse, Generate, PrettyGenerate, Get, ReadFile, WriteFile
- ``py.csv``      — Parse, ParseRow, ParseRecords, Generate, GenerateRecords, ReadFile, ReadRecords, WriteFile
- ``py.os``       — EnvironmentVariable, SetEnvironmentVariable, UnsetEnvironmentVariable, WorkingDirectory, ChangeDirectory, Pid, Argv, Platform, CPUCount
- ``py.files``    — FileExists, DirectoryExists, PathExists, DirectoryFiles, DirectoryEntries, FileSize, FileModificationTime, DeleteFile, DeleteDirectory, RenameFile, CopyFile, MakeDirectory, MakeDirectoryPath, ReadFileToString, WriteStringToFile, AppendStringToFile, AbsolutePath, JoinPath, SplitPath, FileExtension, TempFile, TempDirectory
- ``py.process``  — Shell, ShellOutput, ProcessCreate, Sleep

Legacy aliases (backward compatibility shims — re-export from ``py.*``):

- ``regex``       → ``py.re``
- ``log``         → ``py.logging``
- ``date_time``   → ``py.datetime``
- ``yaml_module`` → ``py.yaml``
- ``sympy_module``→ ``py.sympy``
- ``uuid_mod``    → ``py.uuid``
- ``sqlite``      → ``py.sqlite``
- ``spacy_module``→ ``py.spacy``
- ``random_mod``  → ``py.random``
- ``json_mod``    → ``py.json``
- ``csv_mod``     → ``py.csv``
- ``os_mod``      → ``py.os``
- ``files_mod``   → ``py.files``
- ``process_mod`` → ``py.process``
"""
