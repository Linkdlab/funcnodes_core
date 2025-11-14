import warnings
from unittest import TestCase
from unittest.mock import patch

from funcnodes_core import FUNCNODES_LOGGER
from funcnodes_core.testing import setup as deprecated_setup
from funcnodes_core.testing import teardown as deprecated_teardown
from funcnodes_core.utils.deprecations import FuncNodesDeprecationWarning

import pytest_funcnodes as testing


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

    def test_deprecated_setup_warns_and_calls_pytest_setup(self):
        sentinel = object()
        with patch("pytest_funcnodes.setup", return_value=sentinel) as patched_setup:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", FuncNodesDeprecationWarning)
                result = deprecated_setup()

        self.assertIs(result, sentinel)
        patched_setup.assert_called_once_with()
        self.assertTrue(
            any(
                isinstance(item.message, FuncNodesDeprecationWarning) for item in caught
            )
        )

    def test_deprecated_teardown_warns_and_calls_pytest_teardown(self):
        with patch("pytest_funcnodes.teardown") as patched_teardown:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", FuncNodesDeprecationWarning)
                deprecated_teardown()

        patched_teardown.assert_called_once_with()
        self.assertTrue(
            any(
                isinstance(item.message, FuncNodesDeprecationWarning) for item in caught
            )
        )
