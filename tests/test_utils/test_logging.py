import unittest
import logging
from io import StringIO

from funcnodes_core import get_logger, set_log_format


class TestNotTooLongStringFormatter(unittest.TestCase):
    def setUp(self):
        self.stream = StringIO()
        self.handler = logging.StreamHandler(self.stream)
        set_log_format(fmt=None, max_length=20)
        self.logger = get_logger("TestLogger")
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(self.handler)

    def tearDown(self):
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
