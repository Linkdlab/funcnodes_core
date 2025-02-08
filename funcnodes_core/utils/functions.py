from typing import Generic, Callable, TypeVar, ParamSpec, Awaitable, Union, Type
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import wraps


try:
    from multiprocessing import get_context
    from concurrent.futures import ProcessPoolExecutor
    import dill

    MULTIPROCESSING = True
except (ImportError, ModuleNotFoundError):
    MULTIPROCESSING = False

MULTIPROCESSING = False
P = ParamSpec("P")
R = TypeVar("R")


def _make_async(func: Callable[P, R]) -> Callable[P, Awaitable[R]]:
    """
    Converts a synchronous function into an asynchronous function.

    This function wraps a given synchronous function (`func`) in an asynchronous
    function that can be awaited. This is useful when you need to integrate
    synchronous functions into an asynchronous codebase.

    Args:
        func (Callable[P, R]): A synchronous function to be wrapped.

    Returns:
        Callable[P, Awaitable[R]]: An asynchronous version of the given function.

    Example:
        >>> def sync_function(x: int) -> int:
        ...     return x * 2
        ...
        >>> async_function = _make_async(sync_function)
        >>> result = await async_function(5)
        >>> print(result)
        10
    """

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        res = func(*args, **kwargs)
        if asyncio.iscoroutine(res) or asyncio.isfuture(res):
            return await res
        else:
            return res

    return wrapper


def _make_sync(func: Callable[P, Awaitable[R]]) -> Callable[P, R]:
    """
    Converts an asynchronous function into a synchronous function.

    This function wraps a given asynchronous function (`func`) so that it can be
    called synchronously. The asynchronous function will be executed within an
    event loop, and the result will be returned synchronously.

    If the function is called from within an already running event loop, it will
    use `asyncio.ensure_future` and `loop.run_until_complete` to execute the coroutine
    and wait for the result.

    Args:
        func (Callable[P, Awaitable[R]]): An asynchronous function to be wrapped.

    Returns:
        Callable[P, R]: A synchronous version of the given function.

    Example:
        >>> async def async_function(x: int) -> int:
        ...     await asyncio.sleep(1)
        ...     return x * 2
        ...
        >>> sync_function = _make_sync(async_function)
        >>> result = sync_function(5)
        >>> print(result)
        10
    """

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # No running event loop
            loop = None

        # check if this function is running in the event loop

        if loop and loop.is_running():
            # damn you make a async function sync but run it from an async context, why?
            # I cannot solve this problem (yet):
            # Attemptss:
            # task = asyncio.create_task(func(*args, **kwargs))
            # return task.result()  # Directly await the task
            # # asyncio.exceptions.InvalidStateError: Result is not set.

            # future = asyncio.run_coroutine_threadsafe(func(*args, **kwargs), loop)
            # return future.result()
            # # runs forever

            # future = asyncio.ensure_future(func(*args, **kwargs))
            # return asyncio.run_coroutine_threadsafe(future, loop).result()
            # # TypeError: A coroutine object is required

            # task = loop.create_task(func(*args, **kwargs))
            # return loop.run_until_complete(task)
            # RuntimeError: This event loop is already running

            # so our last chance is to run the dunction in a new thread
            # and wait for the result
            executor = ThreadPoolExecutor()
            future = executor.submit(asyncio.run, func(*args, **kwargs))
            return future.result()

        else:
            # No event loop running, use asyncio.run
            return asyncio.run(func(*args, **kwargs))

    return wrapper


def call_sync(
    func: Callable[P, Union[R, Awaitable[R]]], *args: P.args, **kwargs: P.kwargs
) -> R:
    """
    Calls a function (synchronous or asynchronous) and returns the result synchronously.

    This function calls the provided function (`func`) with the given arguments and keyword arguments.
    If the function is asynchronous, it is wrapped in a synchronous function using `_make_sync`.
    The result of the function is returned synchronously.

    Args:
        func (Callable[P, Union[R, Awaitable[R]]]): The function to be called, which can be synchronous or asynchronous.
        *args: Positional arguments to pass to the function.
        **kwargs: Keyword arguments to pass to the function.

    Returns:
        R: The result of the function call.

    Example:
        >>> async def async_function(x: int) -> int:
        ...     await asyncio.sleep(1)
        ...     return x * 2
        ...
        >>> result = _call_sync(async_function, 5)
        >>> print(result)
        10
    """

    return make_sync_if_needed(func)(*args, **kwargs)


def make_async_if_needed(
    func: Callable[P, Union[R, Awaitable[R]]],
) -> Callable[P, Awaitable[R]]:
    """
    Ensures that a given function is asynchronous.

    If the provided function is already asynchronous, it is returned as is.
    If the function is synchronous, it is wrapped in an asynchronous function
    using `_make_async`.

    Args:
        func (Callable[P, Union[R, Awaitable[R]]]): A synchronous or asynchronous function.

    Returns:
        Callable[P, Awaitable[R]]: An asynchronous function.

    Example:
        >>> def sync_function(x: int) -> int:
        ...     return x * 2
        ...
        >>> async_function = make_async_if_needed(sync_function)
        >>> result = await async_function(5)
        >>> print(result)
        10

        >>> async def already_async_function(x: int) -> int:
        ...     return x * 2
        ...
        >>> same_function = make_async_if_needed(already_async_function)
        >>> result = await same_function(5)
        >>> print(result)
        10
    """

    if asyncio.iscoroutinefunction(func):
        return func
    else:
        return _make_async(func)


def make_sync_if_needed(func: Callable[P, Union[R, Awaitable[R]]]) -> Callable[P, R]:
    """
    Ensures that a given function is synchronous.

    If the provided function is asynchronous, it is wrapped in a synchronous
    function using `_make_sync`. If the function is already synchronous, it
    is returned as is.

    Args:
        func (Callable[P, Union[R, Awaitable[R]]]): A synchronous or asynchronous function.

    Returns:
        Callable[P, R]: A synchronous function.

    Example:
        >>> async def async_function(x: int) -> int:
        ...     await asyncio.sleep(1)
        ...     return x * 2
        ...
        >>> sync_function = make_sync_if_needed(async_function)
        >>> result = sync_function(5)
        >>> print(result)
        10

        >>> def already_sync_function(x: int) -> int:
        ...     return x * 2
        ...
        >>> same_function = make_sync_if_needed(already_sync_function)
        >>> result = same_function(5)
        >>> print(result)
        10
    """

    if asyncio.iscoroutinefunction(func):
        return _make_sync(func)
    else:
        return func


if MULTIPROCESSING:
    executor_class_type = Union[Type[ThreadPoolExecutor], Type[ProcessPoolExecutor]]
else:
    executor_class_type = Type[ThreadPoolExecutor]


class ExecutorWrapper(Generic[P, R]):
    """
    A wrapper that runs a function (synchronous or asynchronous) in a new thread or process
    with its own ThreadPoolExecutor or ProcessPoolExecutor.

    The `ExecutorWrapper` class wraps a function and ensures that it runs in a new thread
    or process managed by a specific executor. The class allows the wrapped function to be called
    asynchronously and handles the lifecycle of the thread or process pool.

    Attributes:
        syncfunc (Callable[P, R]): The synchronous version of the wrapped function.
        executor (Union[ThreadPoolExecutor, ProcessPoolExecutor]): The executor managing the threads or processes.

    Methods:
        __init__(func: Callable[P, R]):
            Initializes the wrapper with the given function and creates the appropriate executor.
        __del__():
            Cleans up the executor when the wrapper is destroyed.
        shutdown():
            Shuts down the executor manually.
        run_in_thread(*args: P.args, **kwargs: P.kwargs) -> Awaitable[R]:
            Runs the wrapped function in a new thread or process and returns an awaitable result.
        __call__(*args: P.args, **kwargs: P.kwargs) -> Awaitable[R]:
            Calls the `run_in_thread` method, allowing the wrapper to be invoked like a function.
    """

    executor_class: executor_class_type = ThreadPoolExecutor

    def __new__(cls, func, *args, **kwargs):
        res = super().__new__(
            cls,
        )

        return wraps(func)(res)

    def __init__(self, func: Callable[P, R]):
        """
        Initializes the ExecutorWrapper with the given function.

        Args:
            func (Callable[P, R]): The function to be wrapped, which can be synchronous or asynchronous.

        The function is converted to a synchronous version if necessary using `make_sync_if_needed`,
        and a new executor (ThreadPoolExecutor or ProcessPoolExecutor) is created to manage the execution
        of the function in a separate thread or process.
        """

        while isinstance(func, ExecutorWrapper):
            func = func.func

        # check if callable
        if not callable(func):
            raise TypeError("The provided function is not callable")

        self.func = func
        self.syncfunc = make_sync_if_needed(func)
        self.executor = self.executor_class()

    def __del__(self):
        """
        Cleans up the ThreadPoolExecutor when the ExecutorWrapper is destroyed.

        This method ensures that the executor is properly shut down when the `ExecutorWrapper`
        object is garbage collected, preventing resource leaks.
        """
        if hasattr(self, "executor"):
            self.executor.shutdown(wait=True)

    def shutdown(self):
        """
        Manually shuts down the ThreadPoolExecutor.

        This method allows explicit control over the lifecycle of the executor. It should be called
        when the wrapper is no longer needed to ensure that all threads are properly cleaned up.
        """
        self.executor.shutdown(wait=True)

    def run_in_executor(self, *args: P.args, **kwargs: P.kwargs) -> Awaitable[R]:
        """
        Runs the wrapped function in a new thread or process and returns an awaitable result.

        This method submits the wrapped function to the executor and returns a
        future that can be awaited. The function is executed in a separate thread or process, allowing
        it to run concurrently with other operations.

        Args:
            *args: Positional arguments to pass to the wrapped function.
            **kwargs: Keyword arguments to pass to the wrapped function.

        Returns:
            Awaitable[R]: An awaitable result of the wrapped function's execution.

        Example:
            >>> result = await wrapper.run_in_thread(5)
            >>> print(result)  # Output: 10
        """

        future = self.executor.submit(self.syncfunc, *args, **kwargs)
        return asyncio.wrap_future(future)

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> Awaitable[R]:
        """
        Allows the wrapper to be called like a function.

        This method redirects the call to `run_in_thread`, making the `ExecutorWrapper` object
        callable. It simplifies the usage by allowing the wrapper to be used as if it were
        the original function, but with the added behavior of running in a new thread or process.

        Args:
            *args: Positional arguments to pass to the wrapped function.
            **kwargs: Keyword arguments to pass to the wrapped function.

        Returns:
            Awaitable[R]: An awaitable result of the wrapped function's execution.

        Example:
            >>> result = await wrapper(5)
            >>> print(result)  # Output: 10
        """
        return self.run_in_executor(*args, **kwargs)


class ThreadExecutorWrapper(ExecutorWrapper[P, R]):
    """
    A wrapper that runs a function (synchronous or asynchronous) in a new thread with a ThreadPoolExecutor.

    This class is a subclass of `ExecutorWrapper` that specifically uses a `ThreadPoolExecutor`
    to run the wrapped function in a separate thread.
    """

    executor_class = ThreadPoolExecutor


def make_run_in_new_thread(
    func: Callable[P, Union[R, Awaitable[R]]],
) -> ThreadExecutorWrapper[P, Awaitable[R]]:
    """
    Wraps a function (synchronous or asynchronous) to run in a new thread with its own ThreadPoolExecutor.

    This function returns an `ThreadExecutorWrapper` object that manages the execution of the provided
    function in a separate thread. The returned wrapper is callable and returns an awaitable result.

    Args:
        func (Callable[P, Union[R, Awaitable[R]]]): The function to be wrapped, which can be synchronous
            or asynchronous.

    Returns:
        ThreadExecutorWrapper[P, Awaitable[R]]: An `ThreadExecutorWrapper` object that runs the function
            in a new thread.

    Example:
        >>> def blocking_function(x: int) -> int:
        ...     import time
        ...     time.sleep(1)
        ...     return x * 2
        ...
        >>> async_function = make_run_in_new_thread(blocking_function)
        >>> result = await async_function(5)
        >>> print(result)  # Output: 10
        ...
        >>> async_function.shutdown()  # Ensure that the executor is properly shut down
    """
    return ThreadExecutorWrapper(func)


if MULTIPROCESSING:

    class DillProcessPoolExecutor(ProcessPoolExecutor):
        """
        A custom ProcessPoolExecutor that uses dill for pickling.
        """

        def __init__(self, *args, **kwargs):
            # Ensure the context is set to 'spawn' to avoid issues with forking and dill
            kwargs["mp_context"] = get_context("spawn")
            super().__init__(*args, **kwargs)

        def _get_function_and_args(
            self, func: Callable[P, R], *args: P.args, **kwargs: P.kwargs
        ):
            """
            Custom serialization using dill.
            """

            func_dill = dill.dumps(func)
            args_dill = dill.dumps((args, kwargs))
            return func_dill, args_dill

        def submit(self, func: Callable[P, R], *args: P.args, **kwargs: P.kwargs):
            func_dill, args_dill = self._get_function_and_args(func, *args, **kwargs)
            return super().submit(self._dill_worker, func_dill, args_dill)

        @staticmethod
        def _dill_worker(func_dill, args_dill):
            """
            A worker function that unpacks dill serialized data.
            """
            func = dill.loads(func_dill)
            args, kwargs = dill.loads(args_dill)
            result = func(*args, **kwargs)
            return dill.dumps(result)

    class ProcessExecutorWrapper(ExecutorWrapper[P, R]):
        """
        A wrapper that runs a function (synchronous or asynchronous) in a new process with a ProcessPoolExecutor.

        This class is a subclass of `ExecutorWrapper` that specifically uses a `ProcessPoolExecutor`
        to run the wrapped function in a separate process.
        """

        executor_class = DillProcessPoolExecutor

        async def run_in_executor(
            self, *args: P.args, **kwargs: P.kwargs
        ) -> Awaitable[R]:
            future = self.executor.submit(call_sync, self.func, *args, **kwargs)

            result = await asyncio.wrap_future(future)
            return dill.loads(result)

    def make_run_in_new_process(
        func: Callable[P, Union[R, Awaitable[R]]],
    ) -> ProcessExecutorWrapper[P, Awaitable[R]]:
        """
        Wraps a function (synchronous or asynchronous) to run in a new process with its own ProcessPoolExecutor.

        This function returns a `ProcessExecutorWrapper` object that manages the execution of the provided
        function in a separate process. The returned wrapper is callable and returns an awaitable result.

        Args:
            func (Callable[P, Union[R, Awaitable[R]]]): The function to be wrapped, which can be synchronous
                or asynchronous.

        Returns:
            ProcessExecutorWrapper[P, Awaitable[R]]: A `ProcessExecutorWrapper` object that runs the function
                in a new process.

        Example:
            >>> def cpu_bound_function(x: int) -> int:
            ...     return sum(i * i for i in range(x))
            ...
            >>> async_function = make_run_in_new_process(cpu_bound_function)
            >>> result = await async_function(1000000)
            >>> print(result)
            ...
            >>> async_function.shutdown()  # Ensure that the executor is properly shut down
        """
        return ProcessExecutorWrapper(func)

else:
    ProcessExecutorWrapper = ThreadExecutorWrapper
    make_run_in_new_process = make_run_in_new_thread
