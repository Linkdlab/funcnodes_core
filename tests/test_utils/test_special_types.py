from pathlib import Path

from funcnodes_core.utils.serialization import Encdata
from funcnodes_core.utils.special_types import (
    databytes,
    databytes_handler,
    path_hander,
)


def test_databytes_handler_encodes_length_preview():
    payload = databytes(b"super secret payload")

    result = databytes_handler(payload)

    assert isinstance(result, Encdata)
    assert result.handeled is True
    assert result.done is True
    assert result.data == f"databytes({len(payload)})"


def test_databytes_handler_leaves_plain_bytes_untouched():
    payload = b"plain-bytes"

    result = databytes_handler(payload)

    assert result.handeled is False
    assert result.done is False
    assert result.data == payload


def test_path_handler_encodes_path_to_posix_string():
    path = Path("folder") / "sub" / "file.txt"

    result = path_hander(path)

    assert isinstance(result, Encdata)
    assert result.handeled is True
    assert result.done is False
    assert result.data == path.as_posix()


def test_path_handler_passes_through_non_paths():
    value = "folder/sub/file.txt"

    result = path_hander(value)

    assert result.handeled is False
    assert result.data == value
