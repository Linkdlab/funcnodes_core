import unittest
import logging
from io import StringIO

from funcnodes_core import get_logger, set_log_format
from funcnodes_core.testing import teardown, setup


class TestNotTooLongStringFormatter(unittest.TestCase):
    def setUp(self):
        setup()
        self.stream = StringIO()
        self.handler = logging.StreamHandler(self.stream)
        set_log_format(fmt=None, max_length=20)
        self.logger = get_logger("TestLogger")
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(self.handler)

    def tearDown(self):
        teardown()
        self.logger.removeHandler(self.handler)
        self.stream.close()

    def test_truncate_long_message(self):
        self.logger.info("This is a very long message that should be truncated.")
        output = self.stream.getvalue().strip()

        self.assertEqual(output, "This is a very lo...")

    def test_no_truncate_short_message(self):
        self.logger.info("Short message.")
        output = self.stream.getvalue().strip()

        self.assertEqual(output, "Short message.")

    def test_no_truncate_exception(self):
        try:
            raise ValueError("An example exception with a lot of text.")
        except ValueError:
            self.logger.exception("Exception occurred")

        output = self.stream.getvalue()

        self.assertIn("Exception occurred", output)
        self.assertIn("Traceback", output)
        self.assertIn("ValueError: An example exception with a lot of text.", output)


class TestFuncnodesLogger(unittest.TestCase):
    def setUp(self):
        setup()

    def tearDown(self):
        teardown()

    def test_handler(self):
        from funcnodes_core import FUNCNODES_LOGGER, config

        handler_names = []
        self.assertEqual(
            len(FUNCNODES_LOGGER.handlers), 1, config.get_config().get("logging", {})
        )
        for handler in FUNCNODES_LOGGER.handlers:
            handler_names.append(handler.name)
        self.assertEqual(handler_names, ["console"])

    def test_patch(self):
        from funcnodes_core.config import get_config_dir, update_config, get_config
        from tempfile import gettempdir
        from funcnodes_core import FUNCNODES_LOGGER
        from funcnodes_core._logging import _update_logger_handlers

        self.assertTrue(get_config_dir().is_relative_to(gettempdir()), get_config_dir())

        logger_config = get_config().get("logging", {})

        update_config({"logging": {"handler": {"console": False}}})
        _update_logger_handlers(FUNCNODES_LOGGER)

        handler_names = []
        for handler in FUNCNODES_LOGGER.handlers:
            handler_names.append(handler.name)
        self.assertEqual(handler_names, [])

        update_config({"logging": logger_config})
        _update_logger_handlers(FUNCNODES_LOGGER)
