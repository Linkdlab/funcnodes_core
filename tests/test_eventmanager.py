import asyncio
from unittest.mock import MagicMock

import pytest

from funcnodes_core.eventmanager import (
    AsyncEventManager,
    EventEmitterMixin,
    MessageInArgs,
    emit_after,
    emit_before,
)
from pytest_funcnodes import funcnodes_test


class DummyObject:
    pass


@pytest.fixture
def event_manager():
    return AsyncEventManager(DummyObject())


@pytest.fixture
def emitter():
    return EventEmitterMixin()


@funcnodes_test
async def test_set_event(event_manager):
    event_name = "test_event"
    assert not event_manager._async_events.get(event_name, asyncio.Event()).is_set()

    await event_manager.set(event_name)
    assert event_manager._async_events[event_name].is_set()


@funcnodes_test
async def test_wait_event(event_manager):
    event_name = "test_event"

    async def setter():
        await asyncio.sleep(0.1)
        await event_manager.set(event_name)

    assert len(event_manager._async_events) == 0
    for i in range(2):
        assert len(event_manager._async_events) == i
        await asyncio.gather(event_manager.wait(event_name), setter())
        assert len(event_manager._async_events) == 1
        assert event_manager._async_events[event_name].is_set()


@funcnodes_test
async def test_clear_event(event_manager):
    event_name = "test_event"
    await event_manager.set(event_name)
    assert event_manager._async_events[event_name].is_set()

    await event_manager.clear(event_name)
    assert not event_manager._async_events[event_name].is_set()

    await event_manager.clear("unknwon")
    assert "unknwon" in event_manager._async_events


@funcnodes_test
async def test_set_and_clear_event(event_manager):
    event_name = "test_event"
    await event_manager.set_and_clear(event_name, delta=0.1)

    assert not event_manager._async_events[event_name].is_set()

    waiter_task = asyncio.create_task(event_manager.wait(event_name))
    await asyncio.sleep(0)
    await event_manager.set(event_name)
    await waiter_task

    assert waiter_task.done()
    assert event_manager._async_events[event_name].is_set()


@funcnodes_test
async def test_event_manager_stress(event_manager):
    num_coroutines = 1000
    event_name = "stress_test_event"
    timeout = 5

    async def waiter():
        await event_manager.wait(event_name)

    async def setter_and_clearer():
        await event_manager.set(event_name)
        await asyncio.sleep(0)
        await event_manager.clear(event_name)

    waiters = [asyncio.create_task(waiter()) for _ in range(num_coroutines)]
    setters_and_clearers = [
        asyncio.create_task(setter_and_clearer()) for _ in range(num_coroutines)
    ]

    all_tasks = waiters + setters_and_clearers
    done, pending = await asyncio.wait(all_tasks, timeout=timeout)

    assert not pending, f"Test timed out with {len(pending)} pending tasks."

    for task in done:
        if task.exception():
            raise task.exception()

    assert not event_manager._async_events[event_name].is_set()


@funcnodes_test
async def test_high_concurrency(event_manager):
    num_events = 1000

    async def waiter(event_name):
        await event_manager.wait(event_name)
        return event_name

    waiter_tasks = [
        asyncio.create_task(waiter(f"event_{i}"), name=f"event_{i}")
        for i in range(num_events)
    ]

    async def setter(event_name):
        await event_manager.set(event_name)

    for i in range(num_events):
        await setter(f"event_{i}")

    done, pending = await asyncio.wait(waiter_tasks, return_when=asyncio.ALL_COMPLETED)

    assert not pending, f"Not all waiter tasks completed: {len(pending)} tasks pending."
    for task in done:
        assert task.result() == task.get_name()


@funcnodes_test
async def test_set_and_clear_under_load(event_manager):
    num_events = 1000

    async def set_and_clear(event_name):
        await event_manager.set_and_clear(event_name, delta=0.001)

    set_and_clear_tasks = [
        asyncio.create_task(set_and_clear(f"event_{i}")) for i in range(num_events)
    ]

    done, pending = await asyncio.wait(
        set_and_clear_tasks, return_when=asyncio.ALL_COMPLETED
    )

    assert not pending, (
        f"Not all set_and_clear tasks completed: {len(pending)} tasks pending."
    )


@funcnodes_test
async def test_remove_event(event_manager):
    event_name = "test_event"
    assert len(event_manager._async_events) == 0

    await event_manager.set_and_clear(event_name)
    assert event_name in event_manager._async_events
    assert len(event_manager._async_events) == 1

    await event_manager.remove_event(event_name)
    assert event_name not in event_manager._async_events
    assert len(event_manager._async_events) == 0

    await event_manager.remove_event(event_name)
    assert event_name not in event_manager._async_events
    assert len(event_manager._async_events) == 0


@funcnodes_test
def test_init_with_src_sets_src():
    mock_src = MagicMock(EventEmitterMixin)
    msg_args = MessageInArgs(src=mock_src)
    assert msg_args.src == mock_src


@funcnodes_test
def test_set_src_to_invalid_type_raises_type_error():
    msg_args = MessageInArgs(src=MagicMock(EventEmitterMixin))
    with pytest.raises(TypeError):
        msg_args.src = "not an EventEmitterMixin"


@funcnodes_test
def test_set_src_to_valid_type_sets_src():
    mock_src1 = MagicMock(EventEmitterMixin)
    mock_src2 = MagicMock(EventEmitterMixin)
    msg_args = MessageInArgs(src=mock_src1)
    msg_args.src = mock_src2
    assert msg_args.src == mock_src2


@funcnodes_test
def test_init_with_arbitrary_keywords():
    msg_args = MessageInArgs(src=MagicMock(EventEmitterMixin), foo="bar", number=42)
    assert msg_args["foo"] == "bar"
    assert msg_args["number"] == 42


@funcnodes_test
def test_on_adds_callback(emitter):
    callback = MagicMock()
    emitter.on("test_event", callback)
    assert callback in emitter._events["test_event"]


@funcnodes_test
def test_double_on_adds_callback_twice(emitter):
    callback = MagicMock()
    emitter.on("test_event", callback)
    emitter.on("test_event", callback)
    assert callback in emitter._events["test_event"]
    assert len(emitter._events["test_event"]) == 1


@funcnodes_test
def test_on_error_adds_error_callback(emitter):
    error_callback = MagicMock()
    emitter.on_error(error_callback)
    assert error_callback in emitter._error_events


@funcnodes_test
def test_double_on_error_adds_error_callback_twice(emitter):
    error_callback = MagicMock()
    emitter.on_error(error_callback)
    emitter.on_error(error_callback)
    assert error_callback in emitter._error_events
    assert len(emitter._error_events) == 1


@funcnodes_test
def test_off_removes_callback(emitter):
    callback = MagicMock()
    emitter.on("test_event", callback)
    callback2 = MagicMock()
    emitter.on("test_event", callback2)
    emitter.off("test_event", callback)
    assert "test_event" in emitter._events
    assert callback2 in emitter._events["test_event"]
    assert callback not in emitter._events["test_event"]


@funcnodes_test
def test_off_removes_all_callbacks(emitter):
    callback = MagicMock()
    emitter.on("test_event", callback)
    emitter.off("test_event")
    assert len(emitter._events) == 0


@funcnodes_test
def test_off_removes_unknown_callback(emitter):
    callback = MagicMock()
    emitter.on("test_event", callback)
    callback2 = MagicMock()
    emitter.off("test_event", callback2)
    assert callback2 not in emitter._events["test_event"]
    assert callback in emitter._events["test_event"]
    assert len(emitter._events["test_event"]) == 1

    emitter.off("test_event", callback)
    assert "test_event" not in emitter._events

    emitter.off("test_event", callback)


@funcnodes_test
def test_off_error_removes_error_callback(emitter):
    error_callback = MagicMock()
    emitter.on_error(error_callback)
    emitter.off_error(error_callback)
    assert error_callback not in emitter._error_events


@funcnodes_test
def test_off_error_removes_all_error_callback(emitter):
    error_callback = MagicMock()
    emitter.on_error(error_callback)
    emitter.off_error()
    assert len(emitter._error_events) == 0


@funcnodes_test
def test_off_error_removes_unknown_error_callback(emitter):
    error_callback = MagicMock()
    emitter.off_error(error_callback)
    assert error_callback not in emitter._error_events


@funcnodes_test
def test_once_registers_callback_once(emitter):
    callback = MagicMock()
    emitter.once("test_event", callback)
    emitter.emit("test_event", MessageInArgs(src=emitter))
    emitter.emit("test_event", MessageInArgs(src=emitter))
    callback.assert_called_once()


@funcnodes_test
def test_once_error_registers_error_callback_once(emitter):
    error_callback = MagicMock()
    emitter.once_error(error_callback)
    emitter.error(Exception("test"))
    with pytest.raises(Exception):
        emitter.error(Exception("test"))
    error_callback.assert_called_once()


@funcnodes_test
def test_emit_triggers_callbacks(emitter):
    callback = MagicMock()
    emitter.on("test_event", callback)
    emitter.emit("test_event", MessageInArgs(src=emitter))
    callback.assert_called()


@funcnodes_test
def test_emit_with_no_listeners_returns_false(emitter):
    result = emitter.emit("test_event", MessageInArgs(src=emitter))
    assert result is False


@funcnodes_test
def test_error_raises_if_no_listeners(emitter):
    with pytest.raises(Exception) as context:
        emitter.error(Exception("test error"))
    assert str(context.value) == "test error"


@funcnodes_test
def test_error_calls_listeners(emitter):
    error_callback = MagicMock()
    emitter.on_error(error_callback)
    emitter.error(Exception("test error"))
    error_callback.assert_called()


@funcnodes_test
def test_emit_without_message(emitter):
    callback = MagicMock()
    emitter.on("test_event", callback)
    emitter.emit("test_event")
    callback.assert_called_with(src=emitter)


@funcnodes_test
def test_emit_with_false_src(emitter):
    callback = MagicMock()
    emitter.on("test_event", callback)
    with pytest.raises(ValueError):
        emitter.emit("test_event", MessageInArgs(src=EventEmitterMixin()))


@funcnodes_test
def test_on_all_events(emitter):
    callback = MagicMock()
    emitter.on("*", callback)
    emitter.emit("test_event")
    callback.assert_called_with(event="test_event", src=emitter)


@funcnodes_test
def test_default_listener():
    class Emiterclass(EventEmitterMixin):
        test_event = MagicMock()
        test_event2 = MagicMock()
        default_listeners = {
            "test_event": [test_event],
        }

        def __init__(self, *args, **kwargs):
            self.default_listeners = {
                "test_event2": [self.test_event2],
                **self.default_listeners,
            }
            super().__init__(*args, **kwargs)

    emitter = Emiterclass()

    assert "test_event" in emitter._events
    assert "test_event2" in emitter._events
    assert len(emitter._events["test_event"]) == 1
    assert len(emitter._events["test_event2"]) == 1
    assert emitter._events["test_event"][0] == Emiterclass.test_event
    assert emitter._events["test_event2"][0] == emitter.test_event2

    emitter.emit("test_event")
    emitter.test_event.assert_called_with(src=emitter)
    emitter.emit("test_event2")
    emitter.test_event2.assert_called_with(src=emitter)


@funcnodes_test
def test_default_error_listener():
    class Emiterclass(EventEmitterMixin):
        test_event = MagicMock()
        test_event2 = MagicMock()
        default_error_listeners = [test_event]

        def __init__(self, *args, **kwargs):
            self.default_error_listeners.append(self.test_event2)
            super().__init__(*args, **kwargs)

    emitter = Emiterclass()
    assert emitter.test_event in emitter._error_events
    assert emitter.test_event2 in emitter._error_events
    assert len(emitter._error_events) == 2

    exc = Exception("test error")
    emitter.error(exc)
    emitter.test_event.assert_called_with(src=emitter, error=exc)
    emitter.test_event2.assert_called_with(src=emitter, error=exc)


@funcnodes_test
def test_emit_before_decorator_emits_event_before_function():
    emitter = MagicMock(EventEmitterMixin)
    emitter.emit = MagicMock()

    @emit_before()
    def test_function(self):
        return "function_result"

    wrapped_function = test_function(emitter)
    emitter.emit.assert_called_with("before_test_function", {"src": emitter})
    assert wrapped_function == "function_result"


@funcnodes_test
def test_emit_after_decorator_emits_event_after_function():
    emitter = MagicMock(EventEmitterMixin)
    emitter.emit = MagicMock()

    @emit_after()
    def test_function(self):
        return "function_result"

    wrapped_function = test_function(emitter)
    emitter.emit.assert_called_with(
        "after_test_function", {"src": emitter, "result": "function_result"}
    )
    assert wrapped_function == "function_result"


@funcnodes_test
def test_emit_after_decorator_emits_event_after_function_wo_result():
    emitter = MagicMock(EventEmitterMixin)
    emitter.emit = MagicMock()

    @emit_after(include_result=False)
    def test_function(self):
        return "function_result"

    wrapped_function = test_function(emitter)
    emitter.emit.assert_called_with("after_test_function", {"src": emitter})
    assert wrapped_function == "function_result"


@funcnodes_test
def test_emit_before_decorator_with_specific_kwargs():
    emitter = MagicMock(EventEmitterMixin)
    emitter.emit = MagicMock()

    @emit_before(include_kwargs=["foo"])
    def test_function(self, foo, bar):
        return "function_result"

    wrapped_function = test_function(emitter, foo="foo_value", bar="bar_value")
    emitter.emit.assert_called_with(
        "before_test_function", {"src": emitter, "foo": "foo_value"}
    )
    assert wrapped_function == "function_result"


@funcnodes_test
def test_emit_after_decorator_with_specific_kwargs():
    emitter = MagicMock(EventEmitterMixin)
    emitter.emit = MagicMock()

    @emit_after(include_kwargs=["foo"])
    def test_function(self, foo, bar):
        return "function_result"

    wrapped_function = test_function(emitter, foo="foo_value", bar="bar_value")
    emitter.emit.assert_called_with(
        "after_test_function",
        {"src": emitter, "foo": "foo_value", "result": "function_result"},
    )
    assert wrapped_function == "function_result"


@funcnodes_test
def test_emit_before_decorator_with_all_kwargs():
    emitter = MagicMock(EventEmitterMixin)
    emitter.emit = MagicMock()

    @emit_before(include_kwargs="all")
    def test_function(self, **kwargs):
        return "function_result"

    wrapped_function = test_function(emitter, foo="foo_value", bar="bar_value")
    emitter.emit.assert_called_with(
        "before_test_function",
        {"src": emitter, "foo": "foo_value", "bar": "bar_value"},
    )
    assert wrapped_function == "function_result"


@funcnodes_test
def test_emit_after_decorator_with_all_kwargs():
    emitter = MagicMock(EventEmitterMixin)
    emitter.emit = MagicMock()

    @emit_after(include_kwargs="all")
    def test_function(self, **kwargs):
        return "function_result"

    wrapped_function = test_function(emitter, foo="foo_value", bar="bar_value")
    emitter.emit.assert_called_with(
        "after_test_function",
        {
            "src": emitter,
            "foo": "foo_value",
            "bar": "bar_value",
            "result": "function_result",
        },
    )
    assert wrapped_function == "function_result"


@funcnodes_test
def test_emit_before_decorator_with_none_kwargs():
    emitter = MagicMock(EventEmitterMixin)
    emitter.emit = MagicMock()

    @emit_before(include_kwargs="none")
    def test_function(self, **kwargs):
        return "function_result"

    wrapped_function = test_function(emitter, foo="foo_value", bar="bar_value")
    emitter.emit.assert_called_with("before_test_function", {"src": emitter})
    assert wrapped_function == "function_result"


@funcnodes_test
def test_emit_after_decorator_with_none_kwargs():
    emitter = MagicMock(EventEmitterMixin)
    emitter.emit = MagicMock()

    @emit_after(include_kwargs="none")
    def test_function(self, **kwargs):
        return "function_result"

    wrapped_function = test_function(emitter, foo="foo_value", bar="bar_value")
    emitter.emit.assert_called_with(
        "after_test_function", {"src": emitter, "result": "function_result"}
    )
    assert wrapped_function == "function_result"


@funcnodes_test
def test_emit_before_decorator_async_function():
    emitter = MagicMock(EventEmitterMixin)
    emitter.emit = MagicMock()

    @emit_before()
    async def async_test_function(self):
        return "async_function_result"

    result = asyncio.run(async_test_function(emitter))
    emitter.emit.assert_called_with("before_async_test_function", {"src": emitter})
    assert result == "async_function_result"


@funcnodes_test
def test_emit_after_decorator_async_function():
    emitter = MagicMock(EventEmitterMixin)
    emitter.emit = MagicMock()

    @emit_after()
    async def async_test_function(self):
        return "async_function_result"

    result = asyncio.run(async_test_function(emitter))
    emitter.emit.assert_called_with(
        "after_async_test_function",
        {"src": emitter, "result": "async_function_result"},
    )
    assert result == "async_function_result"
