"""
Helper functions for testing.
"""

import logging

from .config import set_in_test, get_in_test
from ._logging import FUNCNODES_LOGGER, _update_logger_handlers


def setup():
    if not get_in_test():
        set_in_test()
    logging.basicConfig(level=logging.DEBUG)
    _update_logger_handlers(FUNCNODES_LOGGER)


def teardown():
    """This can be called after each test, which will do a little cleanup."""

    # remove all from the "funcnodes" logger

    # get all logger that start with "funcnodes."

    loggers = [
        name
        for name in logging.root.manager.loggerDict
        if name.startswith("funcnodes.")
    ] + ["funcnodes"]

    loggers = [logging.getLogger(name) for name in loggers]

    for logger in loggers:
        # handlers have to be accessed as a list,
        # because they are removed during iteration
        for handler in list(logger.handlers):
            handler.close()

    # remove all registered nodes
    from funcnodes_core.node import REGISTERED_NODES

    REGISTERED_NODES.clear()

    # remove all registered shelves
    from funcnodes_core.lib import SHELFE_REGISTRY

    SHELFE_REGISTRY.clear()
