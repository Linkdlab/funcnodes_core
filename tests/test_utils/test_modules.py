import importlib
import sys

import pytest

from funcnodes_core.utils import modules


def test_resolve_existing_function():
    import math

    resolved = modules.resolve("math.sqrt")
    assert resolved is math.sqrt


def test_resolve_lazy_loaded_submodule():
    import email

    if hasattr(email, "mime"):
        delattr(email, "mime")

    sys.modules.pop("email.mime", None)
    sys.modules.pop("email.mime.text", None)

    resolved = modules.resolve("email.mime.text.MIMEText")
    MIMEText = importlib.import_module("email.mime.text").MIMEText

    assert resolved is MIMEText


def test_resolve_invalid_module():
    with pytest.raises(ImportError):
        modules.resolve("funcnodes_core.this_does_not_exist")
