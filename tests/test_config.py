import os
import warnings

import pytest
import pytest_funcnodes

import funcnodes_core as fn
from funcnodes_core.config import FuncNodesDeprecationWarning


def test_in_node_test_varaset():
    # assert a warning is issued when accessing the deprecated attribute
    with pytest.warns(FuncNodesDeprecationWarning):
        fn.config.set_in_test()

    assert pytest_funcnodes.get_in_test()
    pid = os.getpid()
    assert os.path.basename(fn.config._BASE_CONFIG_DIR) == f"funcnodes_test_{pid}"


def test_config_access_deprecation():
    # make sure a deprecation warning is issued when accessing the deprecated attributes
    with pytest.warns(DeprecationWarning):
        fn.config.CONFIG
    with pytest.warns(DeprecationWarning):
        fn.config.CONFIG_DIR
    with pytest.warns(DeprecationWarning):
        fn.config.BASE_CONFIG_DIR


def test_no_deprecation_warning():
    # make sure no deprecation warning is issued when accessing the new attribute
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)


def test_config_not_laoded():
    assert not fn.config._CONFIG_CHANGED, "Expected _CONFIG_CHANGED to be False"

    pytest_funcnodes.set_in_test()
    assert fn.config._CONFIG_CHANGED, "Expected _CONFIG_CHANGED to be True"
