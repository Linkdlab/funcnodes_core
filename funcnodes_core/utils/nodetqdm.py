import asyncio
from tqdm import tqdm


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

    def __init__(self, *args, broadcast_func=None, **kwargs):
        self.broadcast_func = broadcast_func
        super().__init__(*args, **kwargs)

    def reset(self, total=None, desc=None, n=None):
        if desc is not None:
            self.desc = desc

        super().reset(total=total)
        if n is not None:
            self.n = n

    def display(self, msg=None, pos=None):
        # This method is called by tqdm according to its internal logic,
        # respecting mininterval, miniters, etc.
        super().display(msg=msg, pos=pos)
        self._broadcast_state()

    def _broadcast_state(self):
        if self.broadcast_func is None:
            return

        result = self.broadcast_func(self.format_dict)
        if asyncio.iscoroutine(result):
            asyncio.create_task(result)
