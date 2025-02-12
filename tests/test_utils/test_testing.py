from unittest import TestCase

from funcnodes_core import testing, FUNCNODES_LOGGER


class TestTesting(TestCase):
    def test_setup(self):
        pass

    def test_teardown(self):
        self.assertGreaterEqual(len(FUNCNODES_LOGGER.handlers), 0)
        testing.teardown()
        self.assertEqual(len(FUNCNODES_LOGGER.handlers), 0)
