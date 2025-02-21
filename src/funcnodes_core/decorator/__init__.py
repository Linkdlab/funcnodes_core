from typing import Any, Callable, Optional, Union, List
import funcnodes_core as fn
import warnings
from funcnodes_core.io import ValueOptions


def identity(x):
    return x


def update_other_io_options(
    trg_io: Union[str, List[str]], modifier: Optional[Callable[[Any], Any]] = identity
):
    """
    Generate a callback function that updates the value options of on ot multiple other ios from the same node.

    Args:
        trg_io (Union[str,List[str]]): The name of the target io or a list of multiple ios.
        modifier (Optional[Callable[[Any], Any]], optional): A function that modifies the result before
        updating the value options. Defaults to identity.

    Returns:
        Callable[[fn.NodeIO, Any], None]: A callback function that updates the value options of the target io.
            The first argument is the source io, the second argument is the respective value
            (in most cases the value of the src io).
    """

    # treat single io as list
    if isinstance(trg_io, str):
        trg_io = [trg_io]

    # convert to string
    trg_ios = [str(io) for io in trg_io]

    def update_value(src: fn.NodeIO, result):
        node = src.node
        if node is None:
            return
        try:
            mod_result = modifier(result)
        except Exception:
            return
        for trg_io in trg_ios:
            try:
                _trg_io = node[trg_io]
                _trg_io.update_value_options(options=mod_result)
            except fn.IONotFoundError:
                pass

    return update_value


def update_other_io(*args, **kwargs):
    warnings.warn(
        "update_other_io is deprecated, use update_other_io_options instead, "
        "this function will be removed in a future release",
        DeprecationWarning,
    )
    return update_other_io_options(*args, **kwargs)


def update_other_io_value_options(
    trg_io: Union[str, List[str]],
    options_generator: Optional[Callable[[Any], ValueOptions]],
):
    """
    Generate a callback function that updates the alue_options of one or multiple other ios from the same node.

    Args:
        trg_io (Union[str,List[str]]): The name of the target io or a list of multiple ios.
        options_generator (Optional[Callable[[Any], ValueOptions]], optional): A function that
            generates the new value options, applied to all trg_ios.

    Returns:
        Callable[[fn.NodeIO, Any], None]: A callback function that updates the value options of the target io.
            The first argument is the source io, the second argument is the respective value
            (in most cases the value of the src io).
    """

    # treat single io as list
    if isinstance(trg_io, str):
        trg_io = [trg_io]

    # convert to string
    trg_ios = [str(io) for io in trg_io]

    def update_value(src: fn.NodeIO, result):
        node = src.node
        if node is None:
            return
        try:
            new_value_options = options_generator(result)
        except Exception:
            return
        for trg_io in trg_ios:
            try:
                _trg_io = node[trg_io]
                _trg_io.update_value_options(**new_value_options)
            except fn.IONotFoundError:
                pass

    return update_value
