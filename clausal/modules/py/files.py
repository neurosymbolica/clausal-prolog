"""clausal.modules.py.files — File system predicates for Clausal.

Provides relational predicates for file and directory operations:
existence checks, listing, metadata, CRUD, path manipulation, and
temporary files.  Import via::

    -import_from(py.files, [FileExists, DirectoryFiles, ReadFileToString,
                            WriteStringToFile, JoinPath])

Or via module import::

    -import_module(py.files)
    # then use py.files.FileExists("data.csv"), py.files.JoinPath(A_, B_, P_), etc.
"""

from __future__ import annotations

from clausal.modules.py import _import_stdlib
_os = _import_stdlib("os")
_shutil = _import_stdlib("shutil")
_tempfile = _import_stdlib("tempfile")

import pathlib
from typing import Callable

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.trampoline import DONE


# ── Dispatch adapter ────────────────────────────────────────────────────


class _FilesPredicate:
    """Adapter with ``_get_dispatch()`` for a files predicate."""

    __slots__ = ("_name", "_dispatch_fns")

    def __init__(self, name: str) -> None:
        self._name = name
        self._dispatch_fns: dict[int, Callable] = {}

    def _register(self, arity: int, fn: Callable) -> None:
        self._dispatch_fns[arity] = fn

    def _get_dispatch(self) -> Callable:
        if len(self._dispatch_fns) == 1:
            return next(iter(self._dispatch_fns.values()))
        return self._multi_dispatch

    def _multi_dispatch(self, this_generator, parent, *args):
        arity = len(args) - 1  # exclude trail
        fn = self._dispatch_fns.get(arity)
        if fn is None:
            yield (parent, DONE)
            return
        yield from fn(this_generator, parent, *args)

    def __repr__(self) -> str:
        arities = sorted(self._dispatch_fns)
        return f"files.{self._name}/{arities}"


# ── Simple-mode wrapper ─────────────────────────────────────────────────


def _simple_to_trampoline(simple_fn):
    """Wrap a simple-mode fn(*args, trail, k) → trampoline protocol."""
    def trampoline_fn(this_generator, parent, *args):
        for _ in simple_fn(*args, None):
            yield (parent, None)
        yield (parent, DONE)
    return trampoline_fn


# ── Helper ──────────────────────────────────────────────────────────────


def _require_ground_str(val, label="argument"):
    """Deref and validate a ground string argument. Returns str or None."""
    val = deref(val)
    if is_var(val) or not isinstance(val, str):
        return None
    return val


# ── Existence predicates ────────────────────────────────────────────────


def _file_exists_1(path, trail, k):
    """FileExists/1: succeeds if Path is a regular file."""
    path = _require_ground_str(path)
    if path is None:
        return
    if pathlib.Path(path).is_file():
        yield None


def _directory_exists_1(path, trail, k):
    """DirectoryExists/1: succeeds if Path is a directory."""
    path = _require_ground_str(path)
    if path is None:
        return
    if pathlib.Path(path).is_dir():
        yield None


def _path_exists_1(path, trail, k):
    """PathExists/1: succeeds if Path exists (file, directory, or other)."""
    path = _require_ground_str(path)
    if path is None:
        return
    if pathlib.Path(path).exists():
        yield None


# ── Directory listing ───────────────────────────────────────────────────


def _directory_files_2(dir_path, files, trail, k):
    """DirectoryFiles/2: unify Files with list of filenames in Dir."""
    dir_path = _require_ground_str(dir_path)
    if dir_path is None:
        return
    p = pathlib.Path(dir_path)
    if not p.is_dir():
        return
    try:
        entries = sorted(e.name for e in p.iterdir())
    except OSError:
        return
    if unify(files, entries, trail):
        yield None


def _directory_entries_2(dir_path, entry, trail, k):
    """DirectoryEntries/2: enumerate directory entries via backtracking."""
    dir_path = _require_ground_str(dir_path)
    if dir_path is None:
        return
    p = pathlib.Path(dir_path)
    if not p.is_dir():
        return
    try:
        entries = sorted(e.name for e in p.iterdir())
    except OSError:
        return
    for name in entries:
        mark = trail.mark()
        if unify(entry, name, trail):
            yield None
        trail.undo(mark)


# ── File metadata ──────────────────────────────────────────────────────


def _file_size_2(path, size, trail, k):
    """FileSize/2: unify Size with file size in bytes."""
    path = _require_ground_str(path)
    if path is None:
        return
    try:
        st = pathlib.Path(path).stat()
    except OSError:
        return
    if unify(size, st.st_size, trail):
        yield None


def _file_modification_time_2(path, time, trail, k):
    """FileModificationTime/2: unify Time with modification timestamp."""
    path = _require_ground_str(path)
    if path is None:
        return
    try:
        st = pathlib.Path(path).stat()
    except OSError:
        return
    if unify(time, st.st_mtime, trail):
        yield None


# ── Destructive operations ─────────────────────────────────────────────


def _delete_file_1(path, trail, k):
    """DeleteFile/1: delete a file."""
    path = _require_ground_str(path)
    if path is None:
        return
    try:
        pathlib.Path(path).unlink()
    except OSError:
        return
    yield None


def _delete_directory_1(path, trail, k):
    """DeleteDirectory/1: delete an empty directory."""
    path = _require_ground_str(path)
    if path is None:
        return
    try:
        pathlib.Path(path).rmdir()
    except OSError:
        return
    yield None


def _rename_file_2(old, new, trail, k):
    """RenameFile/2: rename/move a file or directory."""
    old = _require_ground_str(old)
    new = _require_ground_str(new)
    if old is None or new is None:
        return
    try:
        pathlib.Path(old).rename(new)
    except OSError:
        return
    yield None


def _copy_file_2(source, destination, trail, k):
    """CopyFile/2: copy a file (not directory)."""
    source = _require_ground_str(source)
    destination = _require_ground_str(destination)
    if source is None or destination is None:
        return
    try:
        _shutil.copy2(source, destination)
    except OSError:
        return
    yield None


# ── Directory creation ─────────────────────────────────────────────────


def _make_directory_1(path, trail, k):
    """MakeDirectory/1: create a directory. Fails if it already exists."""
    path = _require_ground_str(path)
    if path is None:
        return
    try:
        pathlib.Path(path).mkdir()
    except OSError:
        return
    yield None


def _make_directory_path_1(path, trail, k):
    """MakeDirectoryPath/1: create a directory and all parents (mkdir -p)."""
    path = _require_ground_str(path)
    if path is None:
        return
    try:
        pathlib.Path(path).mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    yield None


# ── File I/O ───────────────────────────────────────────────────────────


def _read_file_to_string_2(path, contents, trail, k):
    """ReadFileToString/2: read entire file as a string."""
    path = _require_ground_str(path)
    if path is None:
        return
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    if unify(contents, text, trail):
        yield None


def _write_string_to_file_2(path, contents, trail, k):
    """WriteStringToFile/2: write a string to a file (overwrite)."""
    path = _require_ground_str(path)
    if path is None:
        return
    contents = deref(contents)
    if is_var(contents) or not isinstance(contents, str):
        return
    try:
        pathlib.Path(path).write_text(contents, encoding="utf-8")
    except OSError:
        return
    yield None


def _append_string_to_file_2(path, contents, trail, k):
    """AppendStringToFile/2: append a string to a file."""
    path = _require_ground_str(path)
    if path is None:
        return
    contents = deref(contents)
    if is_var(contents) or not isinstance(contents, str):
        return
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(contents)
    except OSError:
        return
    yield None


# ── Path manipulation ──────────────────────────────────────────────────


def _absolute_path_2(relative, absolute, trail, k):
    """AbsolutePath/2: resolve relative path to absolute."""
    relative = _require_ground_str(relative)
    if relative is None:
        return
    resolved = str(pathlib.Path(relative).resolve())
    if unify(absolute, resolved, trail):
        yield None


def _join_path_3(base, relative, joined, trail, k):
    """JoinPath/3: join two path components."""
    base = _require_ground_str(base)
    relative = _require_ground_str(relative)
    if base is None or relative is None:
        return
    result = str(pathlib.Path(base) / relative)
    if unify(joined, result, trail):
        yield None


def _split_path_3(path, directory, filename, trail, k):
    """SplitPath/3: split path into directory and filename."""
    path = _require_ground_str(path)
    if path is None:
        return
    p = pathlib.Path(path)
    dir_part = str(p.parent)
    name_part = p.name
    if unify(directory, dir_part, trail) and unify(filename, name_part, trail):
        yield None


def _file_extension_2(path, extension, trail, k):
    """FileExtension/2: unify Extension with the file extension (including dot)."""
    path = _require_ground_str(path)
    if path is None:
        return
    ext = pathlib.Path(path).suffix
    if unify(extension, ext, trail):
        yield None


# ── Temporary files ────────────────────────────────────────────────────


def _temp_file_1(path, trail, k):
    """TempFile/1: create a temporary file and unify Path with its path."""
    try:
        fd, tmp_path = _tempfile.mkstemp()
        _os.close(fd)
    except OSError:
        return
    if unify(path, tmp_path, trail):
        yield None


def _temp_directory_1(path, trail, k):
    """TempDirectory/1: create a temporary directory and unify Path with its path."""
    try:
        tmp_path = _tempfile.mkdtemp()
    except OSError:
        return
    if unify(path, tmp_path, trail):
        yield None


# ── Build and export predicate objects ──────────────────────────────────

FileExists = _FilesPredicate("FileExists")
FileExists._register(1, _simple_to_trampoline(_file_exists_1))

DirectoryExists = _FilesPredicate("DirectoryExists")
DirectoryExists._register(1, _simple_to_trampoline(_directory_exists_1))

PathExists = _FilesPredicate("PathExists")
PathExists._register(1, _simple_to_trampoline(_path_exists_1))

DirectoryFiles = _FilesPredicate("DirectoryFiles")
DirectoryFiles._register(2, _simple_to_trampoline(_directory_files_2))

DirectoryEntries = _FilesPredicate("DirectoryEntries")
DirectoryEntries._register(2, _simple_to_trampoline(_directory_entries_2))

FileSize = _FilesPredicate("FileSize")
FileSize._register(2, _simple_to_trampoline(_file_size_2))

FileModificationTime = _FilesPredicate("FileModificationTime")
FileModificationTime._register(2, _simple_to_trampoline(_file_modification_time_2))

DeleteFile = _FilesPredicate("DeleteFile")
DeleteFile._register(1, _simple_to_trampoline(_delete_file_1))

DeleteDirectory = _FilesPredicate("DeleteDirectory")
DeleteDirectory._register(1, _simple_to_trampoline(_delete_directory_1))

RenameFile = _FilesPredicate("RenameFile")
RenameFile._register(2, _simple_to_trampoline(_rename_file_2))

CopyFile = _FilesPredicate("CopyFile")
CopyFile._register(2, _simple_to_trampoline(_copy_file_2))

MakeDirectory = _FilesPredicate("MakeDirectory")
MakeDirectory._register(1, _simple_to_trampoline(_make_directory_1))

MakeDirectoryPath = _FilesPredicate("MakeDirectoryPath")
MakeDirectoryPath._register(1, _simple_to_trampoline(_make_directory_path_1))

ReadFileToString = _FilesPredicate("ReadFileToString")
ReadFileToString._register(2, _simple_to_trampoline(_read_file_to_string_2))

WriteStringToFile = _FilesPredicate("WriteStringToFile")
WriteStringToFile._register(2, _simple_to_trampoline(_write_string_to_file_2))

AppendStringToFile = _FilesPredicate("AppendStringToFile")
AppendStringToFile._register(2, _simple_to_trampoline(_append_string_to_file_2))

AbsolutePath = _FilesPredicate("AbsolutePath")
AbsolutePath._register(2, _simple_to_trampoline(_absolute_path_2))

JoinPath = _FilesPredicate("JoinPath")
JoinPath._register(3, _simple_to_trampoline(_join_path_3))

SplitPath = _FilesPredicate("SplitPath")
SplitPath._register(3, _simple_to_trampoline(_split_path_3))

FileExtension = _FilesPredicate("FileExtension")
FileExtension._register(2, _simple_to_trampoline(_file_extension_2))

TempFile = _FilesPredicate("TempFile")
TempFile._register(1, _simple_to_trampoline(_temp_file_1))

TempDirectory = _FilesPredicate("TempDirectory")
TempDirectory._register(1, _simple_to_trampoline(_temp_directory_1))
