import logging
from logging.handlers import RotatingFileHandler
from .config import CONFIG_DIR
import os

LOGGINGDIR = os.path.join(CONFIG_DIR, "logs")
if not os.path.exists(LOGGINGDIR):
    os.makedirs(LOGGINGDIR)


_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# Add the handler to the logger


def _overwrite_add_handler(logger):
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
                and _hierlevel(item) == 1 + _hierlevel(item.parent)
            ):
                children.add(item)
        except Exception:
            pass

    return children


def _update_logger_handlers(logger: logging.Logger, prev_dir=None):
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
    if prev_dir is None:
        prev_dir = LOGGINGDIR
    has_stream_handler = False
    for hdlr in list(logger.handlers):
        if isinstance(hdlr, logging.StreamHandler):
            has_stream_handler = True
            hdlr.setFormatter(_formatter)

        if isinstance(hdlr, RotatingFileHandler):
            if hdlr.baseFilename == os.path.join(prev_dir, f"{logger.name}.log"):
                hdlr.close()
                logger.removeHandler(hdlr)
                continue

        elif isinstance(hdlr, logging.Handler):
            hdlr.setFormatter(_formatter)

    if not has_stream_handler:
        ch = logging.StreamHandler()
        ch.setFormatter(_formatter)
        logger.addHandler(ch)

    fh = RotatingFileHandler(
        os.path.join(LOGGINGDIR, f"{logger.name}.log"),
        maxBytes=1024 * 1024 * 5,
        backupCount=5,
    )
    fh.setFormatter(_formatter)
    logger.addHandler(fh)

    # get child loggers
    for child in getChildren(logger):
        _update_logger_handlers(child, prev_dir=prev_dir)


def get_logger(name, propagate=True):
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
    _update_logger_handlers(sublogger)

    return sublogger


def set_logging_dir(path):
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
    prev_dir = LOGGINGDIR
    LOGGINGDIR = path
    if not os.path.exists(path):
        os.makedirs(path)
    _update_logger_handlers(FUNCNODES_LOGGER, prev_dir=prev_dir)


def set_format(fmt: str):
    """
    Sets the log formatting string. The format string will be used for all log handlers.

    Args:
      fmt (str): The format string for log messages.

    Returns:
      None

    Example:
      >>> set_format("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    """

    global _formatter
    _formatter = logging.Formatter(fmt)
    _update_logger_handlers(FUNCNODES_LOGGER)


FUNCNODES_LOGGER = logging.getLogger("funcnodes")

FUNCNODES_LOGGER.setLevel(logging.INFO)
_overwrite_add_handler(FUNCNODES_LOGGER)
_update_logger_handlers(FUNCNODES_LOGGER)
set_logging_dir(LOGGINGDIR)


__all__ = ["FUNCNODES_LOGGER", "get_logger", "set_logging_dir", "set_format"]
