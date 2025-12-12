import funcnodes_core as fn
from pytest_funcnodes import funcnodes_test
import pytest


@funcnodes_test
def test_get_cache_dir_creates_under_config_dir():
    from funcnodes_core.utils.cache import get_cache_dir

    cache_dir = get_cache_dir()
    assert cache_dir.exists()
    assert cache_dir.is_dir()
    assert fn.config.get_config_dir() in cache_dir.parents


@funcnodes_test
def test_cache_meta_roundtrip():
    from funcnodes_core.utils.cache import (
        get_cache_path,
        get_cache_meta_for,
        set_cache_meta_for,
    )

    cache_path = get_cache_path("example.txt")
    meta = {"foo": "bar", "num": 1}
    set_cache_meta_for(cache_path, meta)

    loaded = get_cache_meta_for(cache_path)
    assert loaded == meta


@funcnodes_test
def test_write_cache_text_writes_file():
    from funcnodes_core.utils.cache import get_cache_path, write_cache_text

    cache_path = get_cache_path("example.txt")
    write_cache_text(cache_path, "hello")

    assert cache_path.exists()
    assert cache_path.read_text(encoding="utf-8") == "hello"


@funcnodes_test
def test_clear_cache_clears_cache():
    from funcnodes_core.utils.cache import clear_cache, get_cache_dir, write_cache_text

    # check that it is empty
    assert len(list(get_cache_dir().glob("*"))) == 0
    # write a file to the cache
    write_cache_text(get_cache_dir() / "test.txt", "hello")
    assert (get_cache_dir() / "test.txt").exists()
    # check that it is not empty
    assert len(list(get_cache_dir().glob("*"))) == 1
    # clear the cache
    clear_cache()

    # check that it is empty
    assert get_cache_dir().exists()
    assert len(list(get_cache_dir().glob("*"))) == 0


@funcnodes_test
def test_cache_meta_exception_handling():
    from funcnodes_core.utils.cache import (
        get_cache_path,
        get_cache_meta_for,
        set_cache_meta_for,
    )

    cache_path = get_cache_path("example.txt")
    with pytest.raises(TypeError):
        set_cache_meta_for(cache_path, "hello world")

    set_cache_meta_for(cache_path, {"hello": "world"})
    assert get_cache_meta_for(cache_path) == {"hello": "world"}

    # write a invalid meta file
    (cache_path.with_suffix(cache_path.suffix + ".meta.json")).write_text("invalid")
    assert get_cache_meta_for(cache_path) is None

    assert get_cache_meta_for(cache_path.with_suffix(cache_path.suffix + ".md")) is None
