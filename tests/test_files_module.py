"""Tests for clausal.modules.py.files — File system predicates."""

from __future__ import annotations

import os
import pathlib

import pytest

from clausal.logic.variables import Var, Trail, deref, unify
from clausal.modules.py.files import (
    FileExists, DirectoryExists, PathExists,
    DirectoryFiles, DirectoryEntries,
    FileSize, FileModificationTime,
    DeleteFile, DeleteDirectory, RenameFile, CopyFile,
    MakeDirectory, MakeDirectoryPath,
    ReadFileToString, WriteStringToFile, AppendStringToFile,
    AbsolutePath, JoinPath, SplitPath, FileExtension,
    TempFile, TempDirectory,
    _file_exists_1, _directory_exists_1, _path_exists_1,
    _directory_files_2, _directory_entries_2,
    _file_size_2, _file_modification_time_2,
    _delete_file_1, _delete_directory_1, _rename_file_2, _copy_file_2,
    _make_directory_1, _make_directory_path_1,
    _read_file_to_string_2, _write_string_to_file_2, _append_string_to_file_2,
    _absolute_path_2, _join_path_3, _split_path_3, _file_extension_2,
    _temp_file_1, _temp_directory_1,
)
from clausal.logic.trampoline import DONE


# ── Helpers ──────────────────────────────────────────────────────────────


def simple_solutions(fn, *args):
    """Run a simple-mode builtin and collect solutions."""
    trail = Trail()
    results = list(fn(*args, trail, None))
    return results, trail


def trampoline_solutions(pred, *args):
    """Run a trampoline-protocol predicate and collect solution snapshots."""
    trail = Trail()
    dispatch = pred._get_dispatch()
    gen = dispatch(None, None, None, None, *args, trail)
    solutions = []
    for parent, value in gen:
        if value is DONE:
            break
        solutions.append(value)
    return solutions, trail


# ── FileExists/1 ───────────────────────────────────────────────────────


class TestFileExists:
    def test_existing_file(self, tmp_path):
        # nv
        f = tmp_path / "test.txt"
        f.write_text("hello")
        sols, _ = simple_solutions(_file_exists_1, str(f))
        assert len(sols) == 1

    def test_nonexistent_fails(self):
        # nv
        sols, _ = simple_solutions(_file_exists_1, "/nonexistent_file_xyz")
        assert len(sols) == 0

    def test_directory_fails(self, tmp_path):
        # nv
        sols, _ = simple_solutions(_file_exists_1, str(tmp_path))
        assert len(sols) == 0

    def test_unbound_fails(self):
        # nv
        sols, _ = simple_solutions(_file_exists_1, Var())
        assert len(sols) == 0

    def test_trampoline(self, tmp_path):
        # nv
        f = tmp_path / "test.txt"
        f.write_text("hello")
        sols, _ = trampoline_solutions(FileExists, str(f))
        assert len(sols) == 1


# ── DirectoryExists/1 ─────────────────────────────────────────────────


class TestDirectoryExists:
    def test_existing_dir(self, tmp_path):
        # nv
        sols, _ = simple_solutions(_directory_exists_1, str(tmp_path))
        assert len(sols) == 1

    def test_file_fails(self, tmp_path):
        # nv
        f = tmp_path / "test.txt"
        f.write_text("hello")
        sols, _ = simple_solutions(_directory_exists_1, str(f))
        assert len(sols) == 0

    def test_nonexistent_fails(self):
        # nv
        sols, _ = simple_solutions(_directory_exists_1, "/nonexistent_dir_xyz")
        assert len(sols) == 0


# ── PathExists/1 ──────────────────────────────────────────────────────


class TestPathExists:
    def test_file_exists(self, tmp_path):
        # nv
        f = tmp_path / "test.txt"
        f.write_text("hello")
        sols, _ = simple_solutions(_path_exists_1, str(f))
        assert len(sols) == 1

    def test_dir_exists(self, tmp_path):
        # nv
        sols, _ = simple_solutions(_path_exists_1, str(tmp_path))
        assert len(sols) == 1

    def test_nonexistent_fails(self):
        # nv
        sols, _ = simple_solutions(_path_exists_1, "/nonexistent_xyz")
        assert len(sols) == 0


# ── DirectoryFiles/2 ──────────────────────────────────────────────────


class TestDirectoryFiles:
    def test_lists_files(self, tmp_path):
        # nv
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        files = Var()
        sols, trail = simple_solutions(_directory_files_2, str(tmp_path), files)
        assert len(sols) == 1
        result = deref(files)
        assert isinstance(result, list)
        assert "a.txt" in result
        assert "b.txt" in result

    def test_nonexistent_dir_fails(self):
        # nv
        sols, _ = simple_solutions(_directory_files_2, "/nonexistent_dir", Var())
        assert len(sols) == 0

    def test_unbound_dir_fails(self):
        # nv
        sols, _ = simple_solutions(_directory_files_2, Var(), Var())
        assert len(sols) == 0

    def test_trampoline(self, tmp_path):
        # nv
        (tmp_path / "x.txt").write_text("x")
        files = Var()
        sols, trail = trampoline_solutions(DirectoryFiles, str(tmp_path), files)
        assert len(sols) == 1
        assert "x.txt" in deref(files)


# ── DirectoryEntries/2 ────────────────────────────────────────────────


class TestDirectoryEntries:
    def test_enumerates_entries(self, tmp_path):
        # nv
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        entry = Var()
        trail = Trail()
        count = 0
        for _ in _directory_entries_2(str(tmp_path), entry, trail, None):
            count += 1
        assert count == 2

    def test_matches_directory_files(self, tmp_path):
        # nv
        (tmp_path / "x.txt").write_text("x")
        (tmp_path / "y.txt").write_text("y")
        # Collect via DirectoryFiles
        files_var = Var()
        simple_solutions(_directory_files_2, str(tmp_path), files_var)
        files_list = deref(files_var)
        # Count via DirectoryEntries
        entry = Var()
        trail = Trail()
        count = 0
        for _ in _directory_entries_2(str(tmp_path), entry, trail, None):
            count += 1
        assert count == len(files_list)


# ── FileSize/2 ────────────────────────────────────────────────────────


class TestFileSize:
    def test_returns_size(self, tmp_path):
        # nv
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        size = Var()
        sols, trail = simple_solutions(_file_size_2, str(f), size)
        assert len(sols) == 1
        result = deref(size)
        assert isinstance(result, int)
        assert result == len("hello world")

    def test_nonexistent_fails(self):
        # nv
        sols, _ = simple_solutions(_file_size_2, "/nonexistent_xyz", Var())
        assert len(sols) == 0


# ── FileModificationTime/2 ───────────────────────────────────────────


class TestFileModificationTime:
    def test_returns_float(self, tmp_path):
        # nv
        f = tmp_path / "test.txt"
        f.write_text("hello")
        time_var = Var()
        sols, trail = simple_solutions(_file_modification_time_2, str(f), time_var)
        assert len(sols) == 1
        result = deref(time_var)
        assert isinstance(result, float)
        assert result > 0

    def test_nonexistent_fails(self):
        # nv
        sols, _ = simple_solutions(
            _file_modification_time_2, "/nonexistent_xyz", Var()
        )
        assert len(sols) == 0


# ── DeleteFile/1 ─────────────────────────────────────────────────────


class TestDeleteFile:
    def test_deletes_file(self, tmp_path):
        # nv
        f = tmp_path / "test.txt"
        f.write_text("hello")
        assert f.exists()
        sols, _ = simple_solutions(_delete_file_1, str(f))
        assert len(sols) == 1
        assert not f.exists()

    def test_nonexistent_fails(self):
        # nv
        sols, _ = simple_solutions(_delete_file_1, "/nonexistent_xyz")
        assert len(sols) == 0

    def test_unbound_fails(self):
        # nv
        sols, _ = simple_solutions(_delete_file_1, Var())
        assert len(sols) == 0


# ── DeleteDirectory/1 ────────────────────────────────────────────────


class TestDeleteDirectory:
    def test_deletes_empty_dir(self, tmp_path):
        # nv
        d = tmp_path / "subdir"
        d.mkdir()
        assert d.exists()
        sols, _ = simple_solutions(_delete_directory_1, str(d))
        assert len(sols) == 1
        assert not d.exists()

    def test_nonempty_fails(self, tmp_path):
        # nv
        d = tmp_path / "subdir"
        d.mkdir()
        (d / "file.txt").write_text("x")
        sols, _ = simple_solutions(_delete_directory_1, str(d))
        assert len(sols) == 0


# ── RenameFile/2 ─────────────────────────────────────────────────────


class TestRenameFile:
    def test_renames(self, tmp_path):
        # nv
        old = tmp_path / "old.txt"
        new = tmp_path / "new.txt"
        old.write_text("content")
        sols, _ = simple_solutions(_rename_file_2, str(old), str(new))
        assert len(sols) == 1
        assert not old.exists()
        assert new.exists()
        assert new.read_text() == "content"

    def test_nonexistent_fails(self, tmp_path):
        # nv
        sols, _ = simple_solutions(
            _rename_file_2, "/nonexistent_xyz", str(tmp_path / "new.txt")
        )
        assert len(sols) == 0


# ── CopyFile/2 ───────────────────────────────────────────────────────


class TestCopyFile:
    def test_copies(self, tmp_path):
        # nv
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("hello")
        sols, _ = simple_solutions(_copy_file_2, str(src), str(dst))
        assert len(sols) == 1
        assert src.exists()
        assert dst.exists()
        assert dst.read_text() == "hello"

    def test_nonexistent_source_fails(self, tmp_path):
        # nv
        sols, _ = simple_solutions(
            _copy_file_2, "/nonexistent_xyz", str(tmp_path / "dst.txt")
        )
        assert len(sols) == 0


# ── MakeDirectory/1 ─────────────────────────────────────────────────


class TestMakeDirectory:
    def test_creates_dir(self, tmp_path):
        # nv
        d = tmp_path / "newdir"
        assert not d.exists()
        sols, _ = simple_solutions(_make_directory_1, str(d))
        assert len(sols) == 1
        assert d.is_dir()

    def test_already_exists_fails(self, tmp_path):
        # nv
        sols, _ = simple_solutions(_make_directory_1, str(tmp_path))
        assert len(sols) == 0


# ── MakeDirectoryPath/1 ─────────────────────────────────────────────


class TestMakeDirectoryPath:
    def test_creates_nested(self, tmp_path):
        # nv
        d = tmp_path / "a" / "b" / "c"
        assert not d.exists()
        sols, _ = simple_solutions(_make_directory_path_1, str(d))
        assert len(sols) == 1
        assert d.is_dir()

    def test_already_exists_succeeds(self, tmp_path):
        # nv
        sols, _ = simple_solutions(_make_directory_path_1, str(tmp_path))
        assert len(sols) == 1


# ── ReadFileToString/2 ──────────────────────────────────────────────


class TestReadFileToString:
    def test_reads_file(self, tmp_path):
        # nv
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        contents = Var()
        sols, trail = simple_solutions(_read_file_to_string_2, str(f), contents)
        assert len(sols) == 1
        assert deref(contents) == "hello world"

    def test_nonexistent_fails(self):
        # nv
        sols, _ = simple_solutions(
            _read_file_to_string_2, "/nonexistent_xyz", Var()
        )
        assert len(sols) == 0

    def test_unbound_path_fails(self):
        # nv
        sols, _ = simple_solutions(_read_file_to_string_2, Var(), Var())
        assert len(sols) == 0

    def test_trampoline(self, tmp_path):
        # nv
        f = tmp_path / "test.txt"
        f.write_text("trampoline test")
        contents = Var()
        sols, trail = trampoline_solutions(ReadFileToString, str(f), contents)
        assert len(sols) == 1
        assert deref(contents) == "trampoline test"


# ── WriteStringToFile/2 ────────────────────────────────────────────


class TestWriteStringToFile:
    def test_writes_file(self, tmp_path):
        # nv
        f = tmp_path / "out.txt"
        sols, _ = simple_solutions(_write_string_to_file_2, str(f), "hello")
        assert len(sols) == 1
        assert f.read_text() == "hello"

    def test_overwrites(self, tmp_path):
        # nv
        f = tmp_path / "out.txt"
        f.write_text("old")
        simple_solutions(_write_string_to_file_2, str(f), "new")
        assert f.read_text() == "new"

    def test_unbound_contents_fails(self, tmp_path):
        # nv
        sols, _ = simple_solutions(
            _write_string_to_file_2, str(tmp_path / "out.txt"), Var()
        )
        assert len(sols) == 0


# ── AppendStringToFile/2 ───────────────────────────────────────────


class TestAppendStringToFile:
    def test_appends(self, tmp_path):
        # nv
        f = tmp_path / "out.txt"
        f.write_text("hello")
        sols, _ = simple_solutions(_append_string_to_file_2, str(f), " world")
        assert len(sols) == 1
        assert f.read_text() == "hello world"

    def test_creates_if_missing(self, tmp_path):
        # nv
        f = tmp_path / "new.txt"
        sols, _ = simple_solutions(_append_string_to_file_2, str(f), "first")
        assert len(sols) == 1
        assert f.read_text() == "first"


# ── AbsolutePath/2 ─────────────────────────────────────────────────


class TestAbsolutePath:
    def test_resolves(self):
        # nv
        result = Var()
        sols, trail = simple_solutions(_absolute_path_2, ".", result)
        assert len(sols) == 1
        abs_path = deref(result)
        assert os.path.isabs(abs_path)

    def test_unbound_fails(self):
        # nv
        sols, _ = simple_solutions(_absolute_path_2, Var(), Var())
        assert len(sols) == 0


# ── JoinPath/3 ─────────────────────────────────────────────────────


class TestJoinPath:
    def test_joins(self):
        # nv
        result = Var()
        sols, trail = simple_solutions(_join_path_3, "/home", "user", result)
        assert len(sols) == 1
        assert deref(result) == str(pathlib.Path("/home") / "user")

    def test_unbound_base_fails(self):
        # nv
        sols, _ = simple_solutions(_join_path_3, Var(), "user", Var())
        assert len(sols) == 0

    def test_unbound_relative_fails(self):
        # nv
        sols, _ = simple_solutions(_join_path_3, "/home", Var(), Var())
        assert len(sols) == 0

    def test_trampoline(self):
        # nv
        result = Var()
        sols, trail = trampoline_solutions(JoinPath, "/a", "b", result)
        assert len(sols) == 1
        assert deref(result) == str(pathlib.Path("/a") / "b")


# ── SplitPath/3 ────────────────────────────────────────────────────


class TestSplitPath:
    def test_splits(self):
        # nv
        dir_var, name_var = Var(), Var()
        sols, trail = simple_solutions(
            _split_path_3, "/home/user/file.txt", dir_var, name_var
        )
        assert len(sols) == 1
        assert deref(dir_var) == "/home/user"
        assert deref(name_var) == "file.txt"

    def test_unbound_fails(self):
        # nv
        sols, _ = simple_solutions(_split_path_3, Var(), Var(), Var())
        assert len(sols) == 0


# ── FileExtension/2 ────────────────────────────────────────────────


class TestFileExtension:
    def test_extension(self):
        # nv
        ext = Var()
        sols, trail = simple_solutions(_file_extension_2, "data.csv", ext)
        assert len(sols) == 1
        assert deref(ext) == ".csv"

    def test_no_extension(self):
        # nv
        ext = Var()
        sols, trail = simple_solutions(_file_extension_2, "Makefile", ext)
        assert len(sols) == 1
        assert deref(ext) == ""

    def test_double_extension(self):
        # nv
        ext = Var()
        sols, trail = simple_solutions(_file_extension_2, "archive.tar.gz", ext)
        assert len(sols) == 1
        assert deref(ext) == ".gz"


# ── TempFile/1 ─────────────────────────────────────────────────────


class TestTempFile:
    def test_creates_temp_file(self):
        # nv
        path = Var()
        sols, trail = simple_solutions(_temp_file_1, path)
        assert len(sols) == 1
        result = deref(path)
        assert isinstance(result, str)
        assert os.path.exists(result)
        # Cleanup
        os.unlink(result)

    def test_trampoline(self):
        # nv
        path = Var()
        sols, trail = trampoline_solutions(TempFile, path)
        assert len(sols) == 1
        result = deref(path)
        assert os.path.exists(result)
        os.unlink(result)


# ── TempDirectory/1 ────────────────────────────────────────────────


class TestTempDirectory:
    def test_creates_temp_dir(self):
        # nv
        path = Var()
        sols, trail = simple_solutions(_temp_directory_1, path)
        assert len(sols) == 1
        result = deref(path)
        assert isinstance(result, str)
        assert os.path.isdir(result)
        # Cleanup
        os.rmdir(result)

    def test_trampoline(self):
        # nv
        path = Var()
        sols, trail = trampoline_solutions(TempDirectory, path)
        assert len(sols) == 1
        result = deref(path)
        assert os.path.isdir(result)
        os.rmdir(result)
