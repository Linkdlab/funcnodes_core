from typing import Optional, TypedDict, Union, Dict, Any
from collections.abc import Callable
import asyncio
from tqdm import tqdm
from funcnodes_core.utils.deprecations import method_deprecated_decorator


class TqdmState(TypedDict):
    """
    TypedDict for the dictionary returned by `tqdm.format_dict`.

    Notes on each field:
    - n (int): Current iteration count.
    - total (Optional[int]): Total number of iterations if known, None otherwise.
    - elapsed (float): Time elapsed in seconds since the start of iteration.
    - ncols (Optional[int]): Number of columns for the progress bar. If None, not dynamically determined.
    - nrows (Optional[int]): Number of rows. Usually None as `tqdm` typically focuses on columns.
    - prefix (Optional[str]): Description string provided to `tqdm` via `desc`.
    - ascii (Union[bool, str]): Whether to use ASCII characters for the bar or a custom set of ASCII characters.
                                Can be True/False or a string specifying the characters.
    - unit (str): Iteration unit (e.g., 'it', 'steps', 'items').
    - unit_scale (Union[bool, float]): If True, `tqdm` scales the iteration values.
                                       If float, `tqdm` uses it as a scaling factor.
    - rate (Optional[float]): Current rate of iteration (iterations/second). None if rate cannot be computed.
    - bar_format (Optional[str]): Custom format string for the bar. If None, default format is used.
    - postfix (Optional[Union[str, Dict[str, Any]]]): Additional data appended to the bar.
                                                      Could be a string or a dictionary passed via `set_postfix()`.
    - unit_divisor (float): Divisor used when scaling units (e.g., 1000 or 1024).
    - initial (Optional[int]): Initial counter value if specified, else None.
    - colour (Optional[str]): Colour for the progress bar if supported, else None.
    """

    n: int
    total: Optional[int]
    elapsed: float
    ncols: Optional[int]
    nrows: Optional[int]
    prefix: Optional[str]
    ascii: Union[bool, str]
    unit: str
    unit_scale: Union[bool, float]
    rate: Optional[float]
    bar_format: Optional[str]
    postfix: Optional[Union[str, Dict[str, Any]]]
    unit_divisor: float
    initial: Optional[int]
    colour: Optional[str]


class NodeTqdm(tqdm):
    """
    A custom tqdm class that broadcasts its state to a frontend,
    using the same refresh logic as tqdm's standard output.

    By only broadcasting in `display()`, it matches tqdm's refresh rate logic.
    If tqdm is configured not to refresh on every iteration (e.g., fast updates),
    then broadcasting will also be limited accordingly.

    Parameters
    ----------
    broadcast_func : callable, optional
        A function or coroutine used to broadcast the progress state.
        It should accept a single argument: a dictionary containing
        tqdm's progress state. The dictionary will include keys like:
        - 'n': current iteration count
        - 'total': total iterations (if known)
        - 'desc': description string
        - 'bar_format': custom bar format (if any)
        - 'postfix': postfix dictionary
        - 'format_dict': the internal formatting dictionary that includes
                         timing, rate, remaining time, percentage, etc.
    """

    def __init__(
        self,
        *args,
        broadcast_func: Optional[Callable[[TqdmState], None]] = None,
        default_display: Optional[bool] = False,
        **kwargs,
    ):
        self.broadcast_func = broadcast_func
        self.default_display = default_display or broadcast_func is None
        super().__init__(*args, **kwargs)

    @method_deprecated_decorator()
    def reset(self, *args, **kwargs):
        pass

    def display(self, msg=None, pos=None):
        # This method is called by tqdm according to its internal logic,
        # respecting mininterval, miniters, etc.
        if self.default_display:
            super().display(msg=msg, pos=pos)
        self._broadcast_state()

    def _broadcast_state(self):
        if self.broadcast_func is None:
            return

        result = self.broadcast_func(self.format_dict)
        if asyncio.iscoroutine(result):
            asyncio.create_task(result)
