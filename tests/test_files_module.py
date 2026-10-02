"""Tests for clausal.modules.py.files — File system predicates."""

from __future__ import annotations

import os
import pathlib

import pytest

from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.cells import chars, is_chars, chars_text
from clausal.modules.py.files import (
    file_exists, directory_exists, path_exists,
    directory_files, directory_entries,
    file_size, file_modification_time,
    delete_file, delete_directory, rename_file, copy_file,
    make_directory, make_directory_path,
    read_file_to_string, write_string_to_file, append_string_to_file,
    absolute_path, join_path, split_path, file_extension,
    temp_file, temp_directory,
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


def raised(fn, *args):
    """The error term a simple-mode builtin raises.  RULED 2026-10-02: an
    argument of the wrong type raises type_error, an unbound required one
    instantiation_error -- neither fails the goal."""
    from clausal.logic.exceptions import LogicException
    with pytest.raises(LogicException) as info:
        list(fn(*args, Trail(), None))
    return info.value.term


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


# ── file_exists/1 ───────────────────────────────────────────────────────


class TestFileExists:
    def test_existing_file(self, tmp_path):
        # nv
        f = tmp_path / "test.txt"
        f.write_text("hello")
        sols, _ = simple_solutions(_file_exists_1, chars(str(f)))
        assert len(sols) == 1

    def test_nonexistent_fails(self):
        # nv
        sols, _ = simple_solutions(_file_exists_1, chars("/nonexistent_file_xyz"))
        assert len(sols) == 0

    def test_directory_fails(self, tmp_path):
        # nv
        sols, _ = simple_solutions(_file_exists_1, chars(str(tmp_path)))
        assert len(sols) == 0

    def test_unbound_raises(self):
        # nv
        term = raised(_file_exists_1, Var())
        assert term == ('error', 'instantiation_error', ('/', 'file_exists', 1))

    def test_trampoline(self, tmp_path):
        # nv
        f = tmp_path / "test.txt"
        f.write_text("hello")
        sols, _ = trampoline_solutions(file_exists, chars(str(f)))
        assert len(sols) == 1


# ── directory_exists/1 ─────────────────────────────────────────────────


class TestDirectoryExists:
    def test_existing_dir(self, tmp_path):
        # nv
        sols, _ = simple_solutions(_directory_exists_1, chars(str(tmp_path)))
        assert len(sols) == 1

    def test_file_fails(self, tmp_path):
        # nv
        f = tmp_path / "test.txt"
        f.write_text("hello")
        sols, _ = simple_solutions(_directory_exists_1, chars(str(f)))
        assert len(sols) == 0

    def test_nonexistent_fails(self):
        # nv
        sols, _ = simple_solutions(_directory_exists_1, chars("/nonexistent_dir_xyz"))
        assert len(sols) == 0


# ── path_exists/1 ──────────────────────────────────────────────────────


class TestPathExists:
    def test_file_exists(self, tmp_path):
        # nv
        f = tmp_path / "test.txt"
        f.write_text("hello")
        sols, _ = simple_solutions(_path_exists_1, chars(str(f)))
        assert len(sols) == 1

    def test_dir_exists(self, tmp_path):
        # nv
        sols, _ = simple_solutions(_path_exists_1, chars(str(tmp_path)))
        assert len(sols) == 1

    def test_nonexistent_fails(self):
        # nv
        sols, _ = simple_solutions(_path_exists_1, chars("/nonexistent_xyz"))
        assert len(sols) == 0


# ── directory_files/2 ──────────────────────────────────────────────────


class TestDirectoryFiles:
    def test_lists_files(self, tmp_path):
        # nv
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        files = Var()
        sols, trail = simple_solutions(_directory_files_2, chars(str(tmp_path)), files)
        assert len(sols) == 1
        result = deref(files)
        assert isinstance(result, list)
        assert chars("a.txt") in result
        assert chars("b.txt") in result

    def test_nonexistent_dir_raises_existence_error(self):
        # RULED 2026-10-02: a file-system failure raises (it failed).
        d = chars("/nonexistent_dir")
        term = raised(_directory_files_2, d, Var())
        assert term == ('error', ('existence_error', 'source_sink', d),
                        ('/', 'directory_files', 2))

    def test_unbound_dir_raises(self):
        # nv
        term = raised(_directory_files_2, Var(), Var())
        assert term == ('error', 'instantiation_error', ('/', 'directory_files', 2))

    def test_trampoline(self, tmp_path):
        # nv
        (tmp_path / "x.txt").write_text("x")
        files = Var()
        sols, trail = trampoline_solutions(directory_files, chars(str(tmp_path)), files)
        assert len(sols) == 1
        assert chars("x.txt") in deref(files)


# ── directory_entries/2 ────────────────────────────────────────────────


class TestDirectoryEntries:
    def test_enumerates_entries(self, tmp_path):
        # nv
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        entry = Var()
        trail = Trail()
        count = 0
        for _ in _directory_entries_2(chars(str(tmp_path)), entry, trail, None):
            count += 1
        assert count == 2

    def test_matches_directory_files(self, tmp_path):
        # nv
        (tmp_path / "x.txt").write_text("x")
        (tmp_path / "y.txt").write_text("y")
        # Collect via directory_files
        files_var = Var()
        simple_solutions(_directory_files_2, chars(str(tmp_path)), files_var)
        files_list = deref(files_var)
        # Count via directory_entries
        entry = Var()
        trail = Trail()
        count = 0
        for _ in _directory_entries_2(chars(str(tmp_path)), entry, trail, None):
            count += 1
        assert count == len(files_list)


# ── file_size/2 ────────────────────────────────────────────────────────


class TestFileSize:
    def test_returns_size(self, tmp_path):
        # nv
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        size = Var()
        sols, trail = simple_solutions(_file_size_2, chars(str(f)), size)
        assert len(sols) == 1
        result = deref(size)
        assert isinstance(result, int)
        assert result == len("hello world")

    def test_nonexistent_raises_existence_error(self):
        p = chars("/nonexistent_xyz")
        term = raised(_file_size_2, p, Var())
        assert term == ('error', ('existence_error', 'source_sink', p),
                        ('/', 'file_size', 2))


# ── file_modification_time/2 ───────────────────────────────────────────


class TestFileModificationTime:
    def test_returns_float(self, tmp_path):
        # nv
        f = tmp_path / "test.txt"
        f.write_text("hello")
        time_var = Var()
        sols, trail = simple_solutions(_file_modification_time_2, chars(str(f)), time_var)
        assert len(sols) == 1
        result = deref(time_var)
        assert isinstance(result, float)
        assert result > 0

    def test_nonexistent_raises_existence_error(self):
        p = chars("/nonexistent_xyz")
        term = raised(_file_modification_time_2, p, Var())
        assert term == ('error', ('existence_error', 'source_sink', p),
                        ('/', 'file_modification_time', 2))


# ── delete_file/1 ─────────────────────────────────────────────────────


class TestDeleteFile:
    def test_deletes_file(self, tmp_path):
        # nv
        f = tmp_path / "test.txt"
        f.write_text("hello")
        assert f.exists()
        sols, _ = simple_solutions(_delete_file_1, chars(str(f)))
        assert len(sols) == 1
        assert not f.exists()

    def test_nonexistent_raises_existence_error(self):
        p = chars("/nonexistent_xyz")
        term = raised(_delete_file_1, p)
        assert term == ('error', ('existence_error', 'source_sink', p),
                        ('/', 'delete_file', 1))

    def test_unbound_raises(self):
        # nv
        term = raised(_delete_file_1, Var())
        assert term == ('error', 'instantiation_error', ('/', 'delete_file', 1))


# ── delete_directory/1 ────────────────────────────────────────────────


class TestDeleteDirectory:
    def test_deletes_empty_dir(self, tmp_path):
        # nv
        d = tmp_path / "subdir"
        d.mkdir()
        assert d.exists()
        sols, _ = simple_solutions(_delete_directory_1, chars(str(d)))
        assert len(sols) == 1
        assert not d.exists()

    def test_nonempty_raises_permission_error(self, tmp_path):
        # ENOTEMPTY: the directory exists, removing it is not permitted.
        d = tmp_path / "subdir"
        d.mkdir()
        (d / "file.txt").write_text("x")
        p = chars(str(d))
        term = raised(_delete_directory_1, p)
        assert term == ('error', ('permission_error', 'modify', 'source_sink', p),
                        ('/', 'delete_directory', 1))


# ── rename_file/2 ─────────────────────────────────────────────────────


class TestRenameFile:
    def test_renames(self, tmp_path):
        # nv
        old = tmp_path / "old.txt"
        new = tmp_path / "new.txt"
        old.write_text("content")
        sols, _ = simple_solutions(_rename_file_2, chars(str(old)), chars(str(new)))
        assert len(sols) == 1
        assert not old.exists()
        assert new.exists()
        assert new.read_text() == "content"

    def test_nonexistent_raises_existence_error(self, tmp_path):
        p = chars("/nonexistent_xyz")
        term = raised(_rename_file_2, p, chars(str(tmp_path / "new.txt")))
        assert term == ('error', ('existence_error', 'source_sink', p),
                        ('/', 'rename_file', 2))


# ── copy_file/2 ───────────────────────────────────────────────────────


class TestCopyFile:
    def test_copies(self, tmp_path):
        # nv
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("hello")
        sols, _ = simple_solutions(_copy_file_2, chars(str(src)), chars(str(dst)))
        assert len(sols) == 1
        assert src.exists()
        assert dst.exists()
        assert dst.read_text() == "hello"

    def test_nonexistent_source_raises_existence_error(self, tmp_path):
        p = chars("/nonexistent_xyz")
        term = raised(_copy_file_2, p, chars(str(tmp_path / "dst.txt")))
        assert term == ('error', ('existence_error', 'source_sink', p),
                        ('/', 'copy_file', 2))


# ── make_directory/1 ─────────────────────────────────────────────────


class TestMakeDirectory:
    def test_creates_dir(self, tmp_path):
        # nv
        d = tmp_path / "newdir"
        assert not d.exists()
        sols, _ = simple_solutions(_make_directory_1, chars(str(d)))
        assert len(sols) == 1
        assert d.is_dir()

    def test_already_exists_raises_permission_error(self, tmp_path):
        p = chars(str(tmp_path))
        term = raised(_make_directory_1, p)
        assert term == ('error', ('permission_error', 'create', 'source_sink', p),
                        ('/', 'make_directory', 1))


# ── make_directory_path/1 ─────────────────────────────────────────────


class TestMakeDirectoryPath:
    def test_creates_nested(self, tmp_path):
        # nv
        d = tmp_path / "a" / "b" / "c"
        assert not d.exists()
        sols, _ = simple_solutions(_make_directory_path_1, chars(str(d)))
        assert len(sols) == 1
        assert d.is_dir()

    def test_already_exists_succeeds(self, tmp_path):
        # nv
        sols, _ = simple_solutions(_make_directory_path_1, chars(str(tmp_path)))
        assert len(sols) == 1


# ── read_file_to_string/2 ──────────────────────────────────────────────


class TestReadFileToString:
    def test_reads_file(self, tmp_path):
        # nv
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        contents = Var()
        sols, trail = simple_solutions(_read_file_to_string_2, chars(str(f)), contents)
        assert len(sols) == 1
        assert deref(contents) == chars("hello world")

    def test_nonexistent_raises_existence_error(self):
        p = chars("/nonexistent_xyz")
        term = raised(_read_file_to_string_2, p, Var())
        assert term == ('error', ('existence_error', 'source_sink', p),
                        ('/', 'read_file_to_string', 2))

    def test_unbound_path_raises(self):
        # nv
        term = raised(_read_file_to_string_2, Var(), Var())
        assert term == ('error', 'instantiation_error', ('/', 'read_file_to_string', 2))

    def test_trampoline(self, tmp_path):
        # nv
        f = tmp_path / "test.txt"
        f.write_text("trampoline test")
        contents = Var()
        sols, trail = trampoline_solutions(read_file_to_string, chars(str(f)), contents)
        assert len(sols) == 1
        assert deref(contents) == chars("trampoline test")


# ── write_string_to_file/2 ────────────────────────────────────────────


class TestWriteStringToFile:
    def test_writes_file(self, tmp_path):
        # nv
        f = tmp_path / "out.txt"
        sols, _ = simple_solutions(_write_string_to_file_2, chars(str(f)), chars("hello"))
        assert len(sols) == 1
        assert f.read_text() == "hello"

    def test_overwrites(self, tmp_path):
        # nv
        f = tmp_path / "out.txt"
        f.write_text("old")
        simple_solutions(_write_string_to_file_2, chars(str(f)), chars("new"))
        assert f.read_text() == "new"

    def test_unbound_contents_raises(self, tmp_path):
        # nv
        term = raised(
            _write_string_to_file_2, chars(str(tmp_path / "out.txt")), Var()
        )
        assert term == ('error', 'instantiation_error', ('/', 'write_string_to_file', 2))


# ── append_string_to_file/2 ───────────────────────────────────────────


class TestAppendStringToFile:
    def test_appends(self, tmp_path):
        # nv
        f = tmp_path / "out.txt"
        f.write_text("hello")
        sols, _ = simple_solutions(_append_string_to_file_2, chars(str(f)), chars(" world"))
        assert len(sols) == 1
        assert f.read_text() == "hello world"

    def test_creates_if_missing(self, tmp_path):
        # nv
        f = tmp_path / "new.txt"
        sols, _ = simple_solutions(_append_string_to_file_2, chars(str(f)), chars("first"))
        assert len(sols) == 1
        assert f.read_text() == "first"


# ── absolute_path/2 ─────────────────────────────────────────────────


class TestAbsolutePath:
    def test_resolves(self):
        # nv
        result = Var()
        sols, trail = simple_solutions(_absolute_path_2, chars("."), result)
        assert len(sols) == 1
        abs_path = deref(result)
        assert os.path.isabs(chars_text(abs_path))

    def test_unbound_raises(self):
        # nv
        term = raised(_absolute_path_2, Var(), Var())
        assert term == ('error', 'instantiation_error', ('/', 'absolute_path', 2))


# ── join_path/3 ─────────────────────────────────────────────────────


class TestJoinPath:
    def test_joins(self):
        # nv
        result = Var()
        sols, trail = simple_solutions(_join_path_3, chars("/home"), chars("user"), result)
        assert len(sols) == 1
        assert deref(result) == chars(str(pathlib.Path("/home") / "user"))

    def test_unbound_base_raises(self):
        # nv
        term = raised(_join_path_3, Var(), chars("user"), Var())
        assert term == ('error', 'instantiation_error', ('/', 'join_path', 3))

    def test_unbound_relative_raises(self):
        # nv
        term = raised(_join_path_3, chars("/home"), Var(), Var())
        assert term == ('error', 'instantiation_error', ('/', 'join_path', 3))

    def test_trampoline(self):
        # nv
        result = Var()
        sols, trail = trampoline_solutions(join_path, chars("/a"), chars("b"), result)
        assert len(sols) == 1
        assert deref(result) == chars(str(pathlib.Path("/a") / "b"))


# ── split_path/3 ────────────────────────────────────────────────────


class TestSplitPath:
    def test_splits(self):
        # nv
        dir_var, name_var = Var(), Var()
        sols, trail = simple_solutions(
            _split_path_3, chars("/home/user/file.txt"), dir_var, name_var
        )
        assert len(sols) == 1
        assert deref(dir_var) == chars("/home/user")
        assert deref(name_var) == chars("file.txt")

    def test_unbound_raises(self):
        # nv
        term = raised(_split_path_3, Var(), Var(), Var())
        assert term == ('error', 'instantiation_error', ('/', 'split_path', 3))


# ── file_extension/2 ────────────────────────────────────────────────


class TestFileExtension:
    def test_extension(self):
        # nv
        ext = Var()
        sols, trail = simple_solutions(_file_extension_2, chars("data.csv"), ext)
        assert len(sols) == 1
        assert deref(ext) == chars(".csv")

    def test_no_extension(self):
        # nv
        ext = Var()
        sols, trail = simple_solutions(_file_extension_2, chars("Makefile"), ext)
        assert len(sols) == 1
        assert deref(ext) == chars("")

    def test_double_extension(self):
        # nv
        ext = Var()
        sols, trail = simple_solutions(_file_extension_2, chars("archive.tar.gz"), ext)
        assert len(sols) == 1
        assert deref(ext) == chars(".gz")


# ── temp_file/1 ─────────────────────────────────────────────────────


class TestTempFile:
    def test_creates_temp_file(self):
        # nv
        path = Var()
        sols, trail = simple_solutions(_temp_file_1, path)
        assert len(sols) == 1
        result = deref(path)
        assert is_chars(result)
        assert os.path.exists(chars_text(result))
        # Cleanup
        os.unlink(chars_text(result))

    def test_trampoline(self):
        # nv
        path = Var()
        sols, trail = trampoline_solutions(temp_file, path)
        assert len(sols) == 1
        result = deref(path)
        assert os.path.exists(chars_text(result))
        os.unlink(chars_text(result))


# ── temp_directory/1 ────────────────────────────────────────────────


class TestTempDirectory:
    def test_creates_temp_dir(self):
        # nv
        path = Var()
        sols, trail = simple_solutions(_temp_directory_1, path)
        assert len(sols) == 1
        result = deref(path)
        assert is_chars(result)
        assert os.path.isdir(chars_text(result))
        # Cleanup
        os.rmdir(chars_text(result))

    def test_trampoline(self):
        # nv
        path = Var()
        sols, trail = trampoline_solutions(temp_directory, path)
        assert len(sols) == 1
        result = deref(path)
        assert os.path.isdir(chars_text(result))
        os.rmdir(chars_text(result))
