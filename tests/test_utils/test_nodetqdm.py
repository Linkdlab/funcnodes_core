import asyncio
import inspect
import io

import pytest

from funcnodes_core.utils.deprecations import FuncNodesDeprecationWarning
from funcnodes_core.utils.nodetqdm import NodeTqdm


def test_node_tqdm_broadcasts_progress():
    captured = []

    def capture(state):
        captured.append(state.copy())

    output = io.StringIO()
    bar = NodeTqdm(
        total=2,
        broadcast_func=capture,
        disable=False,
        leave=False,
        file=output,
    )
    try:
        bar.update(1)
        bar._broadcast_state()
    finally:
        bar.close()
        output.close()

    assert captured, "the broadcast callback should have been invoked"
    assert bar.n == 1
    assert captured[0]["total"] == 2
    assert captured[0]["n"] == bar.last_print_n


def test_node_tqdm_schedules_coroutine_broadcast(monkeypatch):
    scheduled = []

    def fake_create_task(coro):
        scheduled.append(coro)
        coro.close()
        return object()

    monkeypatch.setattr(asyncio, "create_task", fake_create_task)

    async def broadcast(state):
        return state["n"]

    bar = NodeTqdm(
        total=1,
        broadcast_func=broadcast,
        disable=True,
        leave=False,
    )
    try:
        bar.update(1)
        bar.display()
    finally:
        bar.close()

    assert len(scheduled) == 1
    assert inspect.iscoroutine(scheduled[0])


def test_node_tqdm_default_display_flag():
    bar_without_callback = NodeTqdm(total=1, disable=True, leave=False)
    bar_with_callback = NodeTqdm(
        total=1,
        broadcast_func=lambda state: state,
        disable=True,
        leave=False,
    )
    bar_forced_display = NodeTqdm(
        total=1,
        broadcast_func=lambda state: state,
        default_display=True,
        disable=True,
        leave=False,
    )

    try:
        assert bar_without_callback.default_display is True
        assert bar_with_callback.default_display is False
        assert bar_forced_display.default_display is True
    finally:
        bar_without_callback.close()
        bar_with_callback.close()
        bar_forced_display.close()


def test_node_tqdm_reset_warns_deprecation():
    bar = NodeTqdm(total=1, disable=True, leave=False)
    try:
        with pytest.warns(FuncNodesDeprecationWarning):
            bar.reset()
    finally:
        bar.close()
