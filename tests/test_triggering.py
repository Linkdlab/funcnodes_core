import time
import os
import pathlib

import funcnodes_core as fn
from pytest_funcnodes import funcnodes_test

try:
    import yappi
except ImportError:
    yappi = None


class yappicontext:
    def __init__(self, file):
        base_dir = pathlib.Path(
            os.environ.get("TEST_OUTPUT_DIR", "testouts")
        ).absolute()
        if not base_dir.exists():
            base_dir.mkdir(parents=True, exist_ok=True)
        self.file = str(base_dir / file)

    def __enter__(self):
        if yappi is not None:
            yappi.set_clock_type("WALL")
            yappi.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if yappi is not None:
            yappi.stop()
            yappi.get_func_stats().save(self.file, "pstat")
            yappi.clear_stats()


@funcnodes_test
async def test_triggerspeeds():
    @fn.NodeDecorator("TestTriggerSpeed test_triggerspeeds")
    async def _add_one(input: int) -> int:
        return input + 1  # a very simple and fast operation

    async def _a_add_one(input: int) -> int:
        return input + 1  # a very simple and fast operation

    node = _add_one(pretrigger_delay=0.0)

    with yappicontext("test_triggerspeeds_directfunc.pstat"):
        t = time.perf_counter()
        cound_directfunc = 0
        while time.perf_counter() - t < 1:
            cound_directfunc = await node.func(cound_directfunc)

    with yappicontext("test_triggerspeeds_simplefunc.pstat"):
        t = time.perf_counter()
        count_simplefunc = 0
        while time.perf_counter() - t < 1:
            count_simplefunc = await _a_add_one(count_simplefunc)

    assert (
        cound_directfunc >= count_simplefunc / 70
    )  # allow more headroom since asyncio without debug makes plain coroutines far faster

    # disable triggerlogger
    # triggerlogger.disabled = True

    node.inputs["input"].value = 1
    assert node._rolling_tigger_time >= fn.node.NodeConstants.TRIGGER_SPEED_FAST
    t = time.perf_counter()
    called_trigger = 0
    called_triggerfast = 0

    def increase_called_trigger(*args, **kwargs):
        nonlocal called_trigger
        called_trigger += 1

    def increase_called_triggerfast(*args, **kwargs):
        nonlocal called_triggerfast
        called_triggerfast += 1

    node.on("triggerstart", increase_called_trigger)
    node.on("triggerfast", increase_called_triggerfast)
    with yappicontext("test_triggerspeeds_direct_called.pstat"):
        while time.perf_counter() - t < 1:
            await node()
            node.inputs["input"].value = node.outputs["out"].value
    assert node.outputs["out"].value > 10
    assert node._rolling_tigger_time < fn.node.NodeConstants.TRIGGER_SPEED_FAST

    assert called_trigger > 0

    trigger_direct_called = called_triggerfast + called_trigger

    assert (
        trigger_direct_called > cound_directfunc / 5
    )  # overhead due to all the trigger set and clear

    with yappicontext("test_triggerspeeds_called_await.pstat"):
        node.inputs["input"].value = 1

        t = time.perf_counter()
        called_trigger = 0
        called_triggerfast = 0

        while time.perf_counter() - t < 1:
            await node
            node.inputs["input"].value = node.outputs["out"].value
        assert node.outputs["out"].value > 10

        trigger_called_await = called_triggerfast + called_trigger
        assert (
            trigger_called_await > trigger_direct_called / 7
        )  # holy molly thats a lot of overhead,
        # mosttly due to the waiting for the event, which is kinda slow
        # uvloop might help, but this is not yet available under windows
