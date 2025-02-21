from unittest import TestCase

from funcnodes_core import testing, FUNCNODES_LOGGER


class TestTesting(TestCase):
    def test_setup(self):
        pass

    def test_teardown(self):
        testing.setup()
        self.assertGreaterEqual(len(FUNCNODES_LOGGER.handlers), 0)
        for handler in FUNCNODES_LOGGER.handlers:
            self.assertFalse(handler._closed)
        testing.teardown()
        # check all handler are closed

        for handler in FUNCNODES_LOGGER.handlers:
            self.assertTrue(handler._closed)
