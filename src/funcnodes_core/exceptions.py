class NodeError(Exception):
    """
    Base class for all node exceptions.
    """

    pass


class NodeIdAlreadyExistsError(NodeError):
    """
    Exception raised when a node ID already exists.
    """

    pass


class NodeReadyError(NodeError):
    """
    Exception raised when a node is already ready.
    """

    pass


class NodeKeyError(KeyError, NodeError):
    """Exception raised when a node with a given id is not registered."""


class IONotFoundError(KeyError, NodeError):
    pass


class InTriggerError(NodeError):
    """Exception raised when attempting to trigger a node that is already in trigger."""
