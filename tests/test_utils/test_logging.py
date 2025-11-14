import logging
from io import StringIO

import pytest

from funcnodes_core import get_logger, set_log_format
from pytest_funcnodes import funcnodes_test


@pytest.fixture
def configured_logger():
    from pytest_funcnodes import get_in_test

    assert get_in_test(), "Expected to be in test mode"
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    set_log_format(fmt=None, max_length=20)
    logger = get_logger("TestLogger")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)

    yield logger, stream

    logger.removeHandler(handler)
    stream.close()


@funcnodes_test
def test_truncate_long_message(configured_logger):
    logger, stream = configured_logger

    logger.info("This is a very long message that should be truncated.")
    output = stream.getvalue().strip()

    assert output == "This is a very lo..."


@funcnodes_test
def test_no_truncate_short_message(configured_logger):
    logger, stream = configured_logger

    logger.info("Short message.")
    output = stream.getvalue().strip()

    assert output == "Short message."


@funcnodes_test
def test_no_truncate_exception(configured_logger):
    logger, stream = configured_logger

    try:
        raise ValueError("An example exception with a lot of text.")
    except ValueError:
        logger.exception("Exception occurred")

    output = stream.getvalue()

    assert "Exception occurred" in output
    assert "Traceback" in output
    assert "ValueError: An example exception with a lot of text." in output


@funcnodes_test
def test_handler():
    from funcnodes_core import FUNCNODES_LOGGER, config

    handler_names = [handler.name for handler in FUNCNODES_LOGGER.handlers]

    assert len(FUNCNODES_LOGGER.handlers) == 1, config.get_config().get("logging", {})
    assert handler_names == ["console"]


@funcnodes_test
def test_patch():
    from funcnodes_core.config import get_config_dir, update_config, get_config
    from tempfile import gettempdir
    from funcnodes_core import FUNCNODES_LOGGER
    from funcnodes_core._logging import _update_logger_handlers

    assert get_config_dir().is_relative_to(gettempdir()), get_config_dir()

    logger_config = get_config().get("logging", {})

    try:
        update_config({"logging": {"handler": {"console": False}}})
        _update_logger_handlers(FUNCNODES_LOGGER)

        handler_names = [handler.name for handler in FUNCNODES_LOGGER.handlers]
        assert handler_names == []
    finally:
        update_config({"logging": logger_config})
        _update_logger_handlers(FUNCNODES_LOGGER)
