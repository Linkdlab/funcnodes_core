import logging.config
from typing import Optional
import logging


from .utils.modules import resolve
from .config import _CONFIG_DIR, get_config
from pathlib import Path
import os

LOGGINGDIR = _CONFIG_DIR / "logs"
if not LOGGINGDIR.exists():
    LOGGINGDIR.mkdir(parents=True)

DEFAULT_MAX_FORMAT_LENGTH = int(os.environ.get("FUNCNODES_LOG_MAX_FORMAT_LENGTH", 5000))
DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


class NotTooLongStringFormatter(logging.Formatter):
    """
    A custom logging formatter that truncates log messages if they exceed a specified maximum length.

    Attributes:
        max_length (int): The maximum length of the log message.
          If the message exceeds this length, it will be truncated.
    """

    def __init__(self, *args, max_length: Optional[int] = None, **kwargs):
        if max_length is None:
            max_length = os.environ.get(
                "FUNCNODES_LOG_MAX_FORMAT_LENGTH", DEFAULT_MAX_FORMAT_LENGTH
            )
        super(NotTooLongStringFormatter, self).__init__(*args, **kwargs)
        self.max_length = max(max_length - 3, 0)

    def format(self, record):
        """
        Formats the specified log record as text. If the log message exceeds the maximum length, it is truncated.

        Args:
            record (logging.LogRecord): The log record to be formatted.

        Returns:
            str: The formatted log message.
        """
        s = super().format(record)

        # Do not truncate if there's exception information (traceback)
        if record.exc_info:
            return s

        if len(s) > self.max_length:
            s = s[: self.max_length] + "..."
        return s


_formatter = NotTooLongStringFormatter(
    DEFAULT_FORMAT, max_length=DEFAULT_MAX_FORMAT_LENGTH
)

# Add the handler to the logger


def _overwrite_add_handler(logger: logging.Logger):
    """
    Overwrites the addHandler method of the given logger to ensure handlers are added with a formatter
    and prevent duplicate handlers from being added.

    Args:
      logger (logging.Logger): The logger whose addHandler method will be overwritten.

    Returns:
      None

    Example:
      >>> _overwrite_add_handler(FUNCNODES_LOGGER)
    """
    _old_add_handler = logger.addHandler

    def _new_add_handler(hdlr):
        """
        Adds a handler to the given logger if it's not already added,
        and sets the formatter for the handler.

        Args:
          hdlr (logging.Handler): The handler to add to the logger.

        Returns:
          None
        """
        hdlr.setFormatter(_formatter)
        if hdlr not in logger.handlers:
            _old_add_handler(hdlr)

    logger.addHandler = _new_add_handler


def getChildren(logger: logging.Logger):
    """
    Retrieves all child loggers of a given logger.

    Args:
      logger (logging.Logger): The logger for which to retrieve the child loggers.

    Returns:
      set: A set of child loggers of the given logger.

    Example:
      >>> getChildren(FUNCNODES_LOGGER)
    """

    def _hierlevel(_logger: logging.Logger):
        """
        Helper function to determine the hierarchy level of a logger.

        Args:
          _logger (logging.Logger): The logger whose hierarchy level is to be determined.

        Returns:
          int: The hierarchy level of the logger.
        """
        if _logger is _logger.manager.root:
            return 0
        return 1 + _logger.name.count(".")

    d = dict(logger.manager.loggerDict)
    children = set()
    for item in list(d.values()):
        try:
            # catch Exception because ne cannot aquire the logger _lock
            if (
                isinstance(item, logging.Logger)
                and item.parent is logger
                and _hierlevel(  # needed to chack the logger is really a direct child
                    item
                )
                == 1 + _hierlevel(item.parent)
            ):
                children.add(item)
        except Exception:
            pass

    return children


def _update_logger_handlers(
    logger: logging.Logger,
    #  prev_dir: Optional[Path] = None
):
    """
    Updates the handlers for the given logger, ensuring it has a StreamHandler and a RotatingFileHandler.
    The log files are stored in the logs directory, and the log formatting is set correctly.
    Also updates the handlers for all child loggers.

    Args:
      logger (logging.Logger): The logger to update handlers for.

    Returns:
      None

    Example:
      >>> _update_logger_handlers(FUNCNODES_LOGGER)
    """
    # if prev_dir is None:
    #     prev_dir = LOGGINGDIR
    # prev_dir = Path(prev_dir)
    handler_config = get_config().get("logging", {}).get("handler", {})
    found = set()
    for hdlr in list(logger.handlers):
        # check if the handler is closed

        if not hasattr(hdlr, "name"):
            # skip handlers that don't have a name attribute since they are not ours
            continue
        if hasattr(hdlr, "_closed") and hdlr._closed:
            logger.removeHandler(hdlr)
            continue
        # rotating file handler cannot be changed(?) so we need to remove it and add a new one
        if isinstance(hdlr, logging.FileHandler):
            if hdlr.baseFilename != LOGGINGDIR / f"{logger.name}.log":
                hdlr.close()
                logger.removeHandler(hdlr)
                continue
        if hdlr.name not in handler_config or not handler_config[hdlr.name]:
            logger.removeHandler(hdlr)
            continue

        hdlr.setFormatter(_formatter)
        found.add(hdlr.name)

    for name, data in handler_config.items():
        if data is False:
            continue

        if name not in found:
            classstring = data["handlerclass"]
            cls = resolve(classstring)
            handler_kwargs = data.get("options", {})
            if issubclass(cls, logging.FileHandler):
                handler_kwargs["filename"] = LOGGINGDIR / f"{logger.name}.log"
            hdlr = cls(**handler_kwargs)
            hdlr.name = name
            hdlr.setFormatter(_formatter)
            logger.addHandler(hdlr)

            if data.get("level", None):
                hdlr.setLevel(data["level"])

    for child in getChildren(logger):
        _update_logger_handlers(
            child,
            # prev_dir=prev_dir
        )


def _update_logger_level(logger: logging.Logger):
    level = get_config().get("logging", {}).get("level", "INFO")
    logger.setLevel(level)
    for child in getChildren(logger):
        _update_logger_level(child)


def _update_logger(logger: logging.Logger):
    _update_logger_level(logger)
    _update_logger_handlers(logger)


def get_logger(name: str, propagate: bool = True):
    """
    Returns a logger with the given name as a child of FUNCNODES_LOGGER,
    and ensures the logger is set up with appropriate handlers.

    Args:
      name (str): The name of the logger to retrieve.
      propagate (bool): Whether to propagate the logger's messages to its parent logger.

    Returns:
      logging.Logger: The logger with the given name, configured with appropriate handlers.

    Example:
      >>> get_logger("foo")
    """
    sublogger = FUNCNODES_LOGGER.getChild(name)
    _overwrite_add_handler(sublogger)
    sublogger.propagate = propagate
    _update_logger(sublogger)

    return sublogger


def set_logging_dir(path: Path):
    """
    Sets a custom directory path for storing log files. If the directory does not exist, it will be created.
    After updating the directory, the logger's handlers will be updated accordingly.

    Args:
      path (str): The directory path where log files should be stored.

    Returns:
      None

    Example:
      >>> set_logging_dir("/path/to/custom/logs")
    """
    global LOGGINGDIR
    # prev_dir = LOGGINGDIR
    LOGGINGDIR = Path(path)
    LOGGINGDIR.mkdir(parents=True, exist_ok=True)
    _update_logger_handlers(
        FUNCNODES_LOGGER,
        #  prev_dir=prev_dir
    )


def set_log_format(fmt: str = DEFAULT_FORMAT, max_length: Optional[int] = None):
    """
    Sets the log formatting string. The format string will be used for all log handlers.

    Args:
      fmt (str): The format string for log messages.
      max_length (Optional[int]): The maximum length of the log message.
        If the message exceeds this length, it will be truncated.

    Returns:
      None

    Example:
      >>> set_format("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    """

    global _formatter
    if max_length is None:
        max_length = os.environ.get(
            "FUNCNODES_LOG_MAX_FORMAT_LENGTH", DEFAULT_MAX_FORMAT_LENGTH
        )
    _formatter = NotTooLongStringFormatter(fmt, max_length=max_length)
    _update_logger_handlers(FUNCNODES_LOGGER)


FUNCNODES_LOGGER = logging.getLogger("funcnodes")
_overwrite_add_handler(FUNCNODES_LOGGER)
_update_logger(FUNCNODES_LOGGER)
set_logging_dir(LOGGINGDIR)


__all__ = ["FUNCNODES_LOGGER", "get_logger", "set_logging_dir", "set_log_format"]
