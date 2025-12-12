from __future__ import annotations

import json
import os
import tempfile
import shutil
from pathlib import Path
from typing import Any, Optional

from .. import config as fnconfig
from .files import write_json_secure


def get_cache_dir(subdir: str = "cache") -> Path:
    """
    Return (and ensure) a cache directory under the funcnodes config dir.

    Args:
        subdir: Subdirectory name under the config dir.
    """
    cache_dir = fnconfig.get_config_dir() / subdir
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def get_cache_path(filename: str, subdir: str = "cache") -> Path:
    """Return full path for a cache file within the cache dir."""
    return get_cache_dir(subdir) / filename


def get_cache_meta_path_for(cache_path: Path) -> Path:
    """Return a sidecar meta file path next to a cache file."""
    return cache_path.with_suffix(cache_path.suffix + ".meta.json")


def get_cache_meta_for(cache_path: Path) -> Optional[dict[str, Any]]:
    """Read JSON metadata for a given cache file, if present."""
    meta_path = get_cache_meta_path_for(cache_path)
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def set_cache_meta_for(cache_path: Path, meta: dict[str, Any]):
    """Write JSON metadata for a given cache file (atomic)."""
    if not isinstance(meta, dict):
        raise TypeError("meta must be a dictionary")
    meta_path = get_cache_meta_path_for(cache_path)
    write_json_secure(meta, meta_path, indent=2)


def write_cache_text(cache_path: Path, text: str, encoding: str = "utf-8"):
    """
    Write text to cache_path using a temp file + atomic replace.

    This avoids partially-written cache files if the process crashes mid-write.
    """
    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w+", dir=cache_path.parent, delete=False, encoding=encoding
    ) as temp_file:
        temp_file.write(text)
        temp_file.flush()
        os.fsync(temp_file.fileno())
        temp_path = temp_file.name
    os.replace(temp_path, str(cache_path))


def clear_cache():
    """Clear all cache files."""
    cache_dir = get_cache_dir()
    shutil.rmtree(cache_dir, ignore_errors=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
