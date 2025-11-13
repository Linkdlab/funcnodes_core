import pytest

import funcnodes_core.exceptions as exceptions


def test_node_error_inheritance():
    assert issubclass(exceptions.NodeError, Exception)


def test_child_exceptions_extend_node_error():
    assert issubclass(exceptions.NodeIdAlreadyExistsError, exceptions.NodeError)
    assert issubclass(exceptions.NodeReadyError, exceptions.NodeError)
    assert issubclass(exceptions.NodeKeyError, exceptions.NodeError)
    assert issubclass(exceptions.IONotFoundError, exceptions.NodeError)
    assert issubclass(exceptions.InTriggerError, exceptions.NodeError)


def test_node_key_error_behaves_like_key_error():
    with pytest.raises(KeyError) as exc_info:
        raise exceptions.NodeKeyError("missing-node")

    assert isinstance(exc_info.value, exceptions.NodeError)
    assert exc_info.value.args == ("missing-node",)


def test_io_not_found_error_behaves_like_key_error():
    with pytest.raises(KeyError) as exc_info:
        raise exceptions.IONotFoundError("missing-io")

    assert isinstance(exc_info.value, exceptions.NodeError)
    assert exc_info.value.args == ("missing-io",)


def test_in_trigger_error_preserves_message():
    err = exceptions.InTriggerError("already-triggered")
    assert str(err) == "already-triggered"
