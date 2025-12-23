import pytest
from funcnodes_core.eventmanager import EventEmitterMixin

class EmitterTest(EventEmitterMixin):
    pass

@pytest.mark.asyncio
async def test_event_manager_modification_during_emit():
    """
    Test that modifying the event listener list (e.g., via once()) during
    event emission does not cause listeners to be skipped.
    """
    emitter = EmitterTest()
    called = []

    def cb1(**kwargs):
        called.append(1)

    def cb2(**kwargs):
        called.append(2)

    def cb3(**kwargs):
        called.append(3)

    # Scenario: cb1 is 'once', cb2 is normal.
    # When event fires:
    # 1. cb1 is called. It calls 'off' which removes itself from the list.
    # 2. cb2 should still be called.

    emitter.once("test", cb1)
    emitter.on("test", cb2)
    emitter.emit("test")

    assert 1 in called
    assert 2 in called

    called.clear()
    emitter.off("test")

    # Scenario: cb1 is normal, cb2 is once, cb3 is normal.
    emitter.on("test", cb1)
    emitter.once("test", cb2)
    emitter.on("test", cb3)

    emitter.emit("test")

    assert 1 in called
    assert 2 in called
    assert 3 in called
