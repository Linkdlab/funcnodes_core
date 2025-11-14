"""
Helper functions for testing.
"""

from .utils.deprecations import method_deprecated_decorator


def setup():
    from pytest_funcnodes import setup

    return setup()


setup = method_deprecated_decorator(alternative="pytest_funcnodes.setup")(setup)


def teardown():
    from pytest_funcnodes import teardown

    return teardown()


teardown = method_deprecated_decorator(alternative="pytest_funcnodes.teardown")(
    teardown
)
