import json
from pathlib import Path

import pytest

from funcnodes_core.utils.files import write_json_secure


def _read_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_write_json_secure_writes_data(tmp_path: Path):
    target = tmp_path / "configs" / "test.json"
    target.parent.mkdir()

    payload = {"foo": "bar", "numbers": [1, 2, 3]}

    write_json_secure(payload, target)

    assert target.exists()
    assert _read_json(target) == payload
    assert list(target.parent.iterdir()) == [target]


def test_write_json_secure_cleans_up_on_failure(tmp_path: Path):
    target = tmp_path / "broken.json"

    class Boom:
        pass

    class ExplodingEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, Boom):
                raise RuntimeError("cannot encode")
            return super().default(obj)

    with pytest.raises(RuntimeError):
        write_json_secure({"bad": Boom()}, target, cls=ExplodingEncoder)

    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_write_json_secure_accepts_custom_encoder(tmp_path: Path):
    target = tmp_path / "custom.json"

    class Sample:
        def __init__(self, value: int):
            self.value = value

    class SampleEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, Sample):
                return {"value": obj.value}
            return super().default(obj)

    write_json_secure({"payload": Sample(7)}, target, cls=SampleEncoder, indent=0)

    assert _read_json(target) == {"payload": {"value": 7}}


def test_write_json_secure_creates_parent_directories(tmp_path: Path):
    target = tmp_path / "configs" / "deep" / "file.json"
    payload = {"status": "ok"}

    write_json_secure(payload, target)

    assert target.exists()
    assert _read_json(target) == payload
    # ensure only the final file lives in the nested directory
    assert list(target.parent.iterdir()) == [target]
