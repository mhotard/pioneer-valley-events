"""Tests for the shared JSON persistence boundary."""

import json
from pathlib import Path

import pytest

import json_storage
from json_storage import JsonStorageError, read_json, write_json_atomic


def temporary_siblings(path):
    return list(path.parent.glob(f".{path.name}.*.tmp"))


def test_missing_optional_file_gets_a_fresh_default(tmp_path):
    path = tmp_path / "missing.json"

    first = read_json(path, default_factory=lambda: {"items": []})
    second = read_json(path, default_factory=lambda: {"items": []})
    first["items"].append("changed")

    assert second == {"items": []}


def test_missing_required_file_propagates_path(tmp_path):
    path = tmp_path / "required.json"

    with pytest.raises(FileNotFoundError) as exc_info:
        read_json(path)

    assert str(path) in str(exc_info.value)


@pytest.mark.parametrize("contents", [b"{broken", b'{"name":"\xff"}'])
def test_invalid_json_or_utf8_fails_with_path_and_preserves_file(tmp_path, contents):
    path = tmp_path / "stored.json"
    path.write_bytes(contents)

    with pytest.raises(JsonStorageError, match=str(path)):
        read_json(path, default_factory=dict)

    assert path.read_bytes() == contents


def test_non_missing_read_error_does_not_use_default(monkeypatch, tmp_path):
    path = tmp_path / "stored.json"

    def deny_open(self, *args, **kwargs):
        raise PermissionError("permission denied")

    monkeypatch.setattr(Path, "open", deny_open)
    with pytest.raises(JsonStorageError, match=str(path)) as exc_info:
        read_json(path, default_factory=dict)
    assert isinstance(exc_info.value.__cause__, PermissionError)


def test_successful_replacement_preserves_unicode_and_formatting(tmp_path):
    path = tmp_path / "stored.json"
    path.write_text("old bytes", encoding="utf-8")

    write_json_atomic(path, {"name": "Café", "items": [1]}, indent=2)

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "name": "Café",
        "items": [1],
    }
    assert "Café" in path.read_text(encoding="utf-8")
    assert '\n  "items": [' in path.read_text(encoding="utf-8")
    assert not path.read_bytes().endswith(b"\n")
    assert temporary_siblings(path) == []


def test_first_write_creates_complete_compact_json(tmp_path):
    path = tmp_path / "new.json"

    write_json_atomic(path, {"name": "Café"}, separators=(",", ":"))

    assert path.read_text(encoding="utf-8") == '{"name":"Café"}'
    assert temporary_siblings(path) == []


@pytest.mark.parametrize("destination_exists", [False, True])
def test_partial_serialization_failure_never_changes_destination(
    tmp_path, destination_exists
):
    path = tmp_path / "stored.json"
    if destination_exists:
        path.write_bytes(b"original")

    with pytest.raises(TypeError):
        write_json_atomic(path, {"written": [1, object()]})

    if destination_exists:
        assert path.read_bytes() == b"original"
    else:
        assert not path.exists()
    assert temporary_siblings(path) == []


def test_fsync_failure_preserves_destination_and_cleans_temp(monkeypatch, tmp_path):
    path = tmp_path / "stored.json"
    path.write_bytes(b"original")

    def fail_fsync(_fileno):
        raise OSError("sync failed")

    monkeypatch.setattr(json_storage.os, "fsync", fail_fsync)
    with pytest.raises(OSError, match="sync failed"):
        write_json_atomic(path, {"new": True})

    assert path.read_bytes() == b"original"
    assert temporary_siblings(path) == []


def test_flush_failure_preserves_destination_and_cleans_temp(monkeypatch, tmp_path):
    path = tmp_path / "stored.json"
    path.write_bytes(b"original")
    real_named_temporary_file = json_storage.tempfile.NamedTemporaryFile

    class FlushFailure:
        def __init__(self, wrapped):
            self.wrapped = wrapped
            self.name = wrapped.name

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.wrapped.close()

        def write(self, value):
            return self.wrapped.write(value)

        def flush(self):
            raise OSError("flush failed")

        def fileno(self):
            return self.wrapped.fileno()

    def failing_temporary_file(*args, **kwargs):
        return FlushFailure(real_named_temporary_file(*args, **kwargs))

    monkeypatch.setattr(
        json_storage.tempfile, "NamedTemporaryFile", failing_temporary_file
    )
    with pytest.raises(OSError, match="flush failed"):
        write_json_atomic(path, {"new": True})

    assert path.read_bytes() == b"original"
    assert temporary_siblings(path) == []


def test_replace_sees_complete_sibling_then_failure_preserves_old_file(
    monkeypatch, tmp_path
):
    path = tmp_path / "stored.json"
    path.write_bytes(b"original")
    observed = {}

    def fail_replace(source, destination):
        source = Path(source)
        observed["source"] = source
        observed["value"] = json.loads(source.read_text(encoding="utf-8"))
        observed["old"] = Path(destination).read_bytes()
        raise OSError("replace failed")

    monkeypatch.setattr(json_storage.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        write_json_atomic(path, {"new": True})

    assert observed["source"].parent == path.parent
    assert observed["source"] != path.with_suffix(".tmp")
    assert observed["value"] == {"new": True}
    assert observed["old"] == b"original"
    assert path.read_bytes() == b"original"
    assert temporary_siblings(path) == []


def test_temporary_names_are_unique_siblings(monkeypatch, tmp_path):
    path = tmp_path / "stored.json"
    real_replace = json_storage.os.replace
    sources = []

    def record_replace(source, destination):
        sources.append(Path(source))
        real_replace(source, destination)

    monkeypatch.setattr(json_storage.os, "replace", record_replace)
    write_json_atomic(path, {"version": 1})
    write_json_atomic(path, {"version": 2})

    assert len(set(sources)) == 2
    assert all(source.parent == path.parent for source in sources)
    assert temporary_siblings(path) == []


def test_cleanup_error_does_not_hide_primary_write_error(monkeypatch, tmp_path):
    path = tmp_path / "stored.json"

    def fail_cleanup(self, *args, **kwargs):
        raise OSError("cleanup failed")

    monkeypatch.setattr(Path, "unlink", fail_cleanup)
    with pytest.raises(TypeError):
        write_json_atomic(path, {"bad": object()})


def test_missing_parent_fails_without_creating_directories(tmp_path):
    parent = tmp_path / "not-created"

    with pytest.raises(FileNotFoundError):
        write_json_atomic(parent / "stored.json", {"new": True})

    assert not parent.exists()
