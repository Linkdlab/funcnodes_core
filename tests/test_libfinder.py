"""Tests for funcnodes_core.lib.libfinder."""

from __future__ import annotations

import os
import sys
import textwrap

import pytest

from funcnodes_core.lib.libfinder import find_shelf_from_path


MODULE_SOURCE = """
from funcnodes_core.nodemaker import NodeDecorator


@NodeDecorator(node_id="tmp_libfinder_node", name="Tmp Finder Node")
def tmp_node(value: int = 1) -> int:
    '''Simple node definition for libfinder tests.'''
    return value
"""


def _write_module(tmp_path):
    module_dir = tmp_path / "libfinder_module"
    module_dir.mkdir()
    module_file = module_dir / "demo_module.py"
    module_file.write_text(textwrap.dedent(MODULE_SOURCE))
    return module_dir, module_file


def test_find_shelf_from_path_reads_pyproject_dependencies(tmp_path, monkeypatch):
    module_dir, module_file = _write_module(tmp_path)
    pyproject = module_dir / "pyproject.toml"
    pyproject.write_text(
        textwrap.dedent(
            """
            [tool.poetry.dependencies]
            python = "^3.12"
            pendulum = "^2.1"

            [project]
            dependencies = [
                "httpx>=0.24"
            ]
            """
        ).strip()
    )

    captured_commands: list[str] = []

    def _fake_system(command: str) -> int:
        captured_commands.append(command)
        return 0

    monkeypatch.setattr(os, "system", _fake_system)

    module_path = module_dir.resolve().as_posix()
    try:
        shelf, metadata = find_shelf_from_path(
            {
                "path": module_path,
                "module": module_file.stem,
                "skip_requirements": False,
            }
        )
    finally:
        if module_path in sys.path:
            sys.path.remove(module_path)

    assert metadata["module"] == module_file.stem
    assert metadata["path"] == module_path
    assert shelf.nodes, "generated shelf should contain collected nodes"
    assert shelf.nodes[0].node_id == "tmp_libfinder_node"

    requirements = (module_dir / "requirements.txt").read_text().splitlines()
    assert "pendulum==^2.1" in requirements
    assert "httpx>=0.24" in requirements
    assert captured_commands, (
        "pip install should be triggered for generated requirements"
    )
    assert "-m pip install -r" in captured_commands[0]


def test_find_shelf_from_path_raises_for_missing_directory(tmp_path):
    missing_dir = tmp_path / "does-not-exist"

    with pytest.raises(FileNotFoundError):
        find_shelf_from_path(
            {
                "path": missing_dir.as_posix(),
                "module": "ghost_module",
                "skip_requirements": True,
            }
        )
