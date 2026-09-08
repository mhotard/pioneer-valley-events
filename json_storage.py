"""Small, reliable boundary for persistent JSON files."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional, Union

PathLike = Union[str, Path]


class JsonStorageError(RuntimeError):
    """A JSON file could not be read or written safely."""


def read_json(
    path: PathLike, *, default_factory: Optional[Callable[[], Any]] = None
) -> Any:
    """Read UTF-8 JSON, using a fresh default only when the file is missing."""
    json_path = Path(path)
    try:
        with json_path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        if default_factory is None:
            raise
        return default_factory()
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise JsonStorageError(f"Could not read JSON from {json_path}: {exc}") from exc


def write_json_atomic(
    path: PathLike,
    value: Any,
    *,
    indent: Optional[int] = None,
    separators: Optional[tuple[str, str]] = None,
) -> None:
    """Serialize, sync, and atomically replace one JSON destination.

    The destination's parent must already exist. Failures before ``os.replace``
    leave any previous destination unchanged.
    """
    json_path = Path(path)
    temporary_path = None
    primary_error = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=json_path.parent,
            prefix=f".{json_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(
                value,
                temporary,
                ensure_ascii=False,
                indent=indent,
                separators=separators,
            )
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, json_path)
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
            except BaseException:
                if primary_error is None:
                    raise
