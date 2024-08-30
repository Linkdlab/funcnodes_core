from typing import Any, Callable, Optional
import funcnodes_core as fn


def identity(x):
    return x


def update_other_io(trg_io: str, modifier: Optional[Callable[[Any], Any]] = identity):
    """
    Generate a callback function that updates the value options of another io from the same node.

    Args:
        trg_io (str): The name of the target io.
        modifier (Optional[Callable[[Any], Any]], optional): A function that modifies the result before
        updating the value options. Defaults to identity.

    Returns:
        Callable[[fn.NodeIO, Any], None]: A callback function that updates the value options of the target io.
            The first argument is the source io, the second argument is the respective value
            (in most cases the value of the src io).
    """

    def update_value(src: fn.NodeIO, result):
        node = src.node
        if node is None:
            return
        try:
            _trg_io = node[trg_io]
        except fn.IONotFoundError:
            return

        try:
            mod_result = modifier(result)
        except Exception:
            return
        _trg_io.update_value_options(options=mod_result)

    return update_value
