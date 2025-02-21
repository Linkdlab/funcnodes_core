from functools import wraps
import inspect


def signaturewrapper(func):
    def funcwrapper(innerfunc):
        _innerfunc = wraps(func)(innerfunc)
        _innerfunc = innerfunc
        _innerfunc.__signature__ = inspect.signature(func)
        return _innerfunc

    return funcwrapper
