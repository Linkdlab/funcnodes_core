from __future__ import annotations
from typing import (
    Dict,
    Optional,
    TypedDict,
    List,
    TYPE_CHECKING,
    Type,
    Any,
    TypeVar,
    Generic,
    Union,
    Tuple,
    Required,
)
from collections.abc import Callable
from uuid import uuid4
from exposedfunctionality import FunctionInputParam, FunctionOutputParam
from exposedfunctionality.function_parser.types import (
    string_to_type,
    SerializedType,
    EnumOf,
)
from exposedfunctionality import serialize_type
from .eventmanager import (
    AsyncEventManager,
    MessageInArgs,
    emit_before,
    emit_after,
    EventEmitterMixin,
    EventCallback,
)
from .triggerstack import TriggerStack
from .utils.data import deep_fill_dict, deep_remove_dict_on_equal
from .datapath import DataPath

from .utils.serialization import JSONEncoder, JSONDecoder, Encdata
import json
import weakref

if TYPE_CHECKING:
    # Avoid circular import
    from .node import Node


class NodeIOSerialization(
    TypedDict,
    total=False,
):
    """Typing definition for serialized Node Input/Output serialization."""

    name: str
    description: str
    type: Required[SerializedType]
    allow_multiple: bool
    id: Required[str]
    value: Required[Any]
    is_input: Required[bool]
    render_options: IORenderOptions
    value_options: ValueOptions
    hidden: bool
    emit_value_set: bool


class NodeInputSerialization(NodeIOSerialization, total=False):
    """Typing definition for serialized Node Input serialization."""

    required: bool
    does_trigger: bool
    default: Any


class NodeOutputSerialization(NodeIOSerialization):
    """Typing definition for serialized Node Output serialization."""


class NodeIOClassSerialization(TypedDict, total=False):
    """Typing definition for serialized Node Input/Output class."""

    name: str
    description: Optional[str]
    type: SerializedType
    allow_multiple: Optional[bool]
    uuid: Required[str]


class FullNodeIOJSON(TypedDict):
    """Full JSON representation of a NodeIO."""

    id: str
    full_id: str | None
    name: str
    type: SerializedType
    is_input: bool
    connected: bool
    node: str | None
    value: Any
    does_trigger: bool
    render_options: IORenderOptions
    value_options: ValueOptions
    hidden: bool
    emit_value_set: bool


class FullNodeInputJSON(FullNodeIOJSON):
    """Full JSON representation of a NodeInput."""

    default: Any
    required: bool


# A unique object that represents the absence of a value
class NoValueType:
    """A unique object that represents the absence of a value."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(NoValueType, cls).__new__(cls)
        return cls._instance

    def __repr__(self):
        return "<NoValue>"

    def __str__(self):
        return "<NoValue>"

    def __reduce__(self):
        return (NoValueType, ())


NoValue: NoValueType = NoValueType()


class IOReadyState(TypedDict):
    """Typing definition for Node Input/Output ready state."""

    node: bool


class InputReadyState(IOReadyState):
    """Typing definition for Node Input ready state."""

    value: bool


def novalue_endocer(obj, preview=False):
    """Encodes NoValue objects."""
    if obj is NoValue:
        return Encdata(data="<NoValue>", handeled=True, done=True)
    return Encdata(data=obj, handeled=False, done=False)


def novalue_decoder(obj):
    """Decodes NoValue objects."""
    if obj == "<NoValue>":
        return NoValue, True
    return obj, False


JSONDecoder.add_decoder(novalue_decoder)
JSONEncoder.add_encoder(novalue_endocer, enc_cls=[NoValueType])


class NodeIOError(Exception):
    """Base exception for Node Input/Output related errors."""


class NodeAlreadyDefinedError(NodeIOError):
    """Exception raised when a node is already defined for an NodeIO instance."""


class NodeConnectionError(NodeIOError):
    """Exception raised when an invalid connection is attempted."""


class SameNodeConnectionError(NodeConnectionError):
    """Exception raised when attempting to connect an IO to its own node."""


class MultipleConnectionsError(NodeConnectionError):
    """
    Exception raised when attempting to connect an IO that does not allow
    multiple connections.
    """


class NodeIOStatus(TypedDict):
    """Typing definition for Node IO status."""

    has_value: bool
    has_node: bool
    ready: bool
    connected: bool


class NodeInputStatus(NodeIOStatus):
    """Typing definition for Node Input status."""

    required: bool


class NodeOutputStatus(NodeIOStatus):
    """Typing definition for Node Output status."""


def raise_allow_connections(src: NodeIO, trg: NodeIO):
    """Checks and raises an exception if a connection between two NodeIO instances is not allowed.

    Args:
        src: The source NodeIO instance.
        trg: The target NodeIO instance.

    Returns:
        True if the connection is allowed, otherwise raises an exception.

    Raises:
        NodeConnectionError: If attempting to connect two outputs or two inputs.
        MultipleConnectionsError: If either the source or target does not allow
            multiple connections.
    """
    # Check if connection is not allowed between two outputs or two inputs
    if isinstance(src, NodeOutput):
        if not isinstance(trg, NodeInput):
            raise NodeConnectionError("Cannot connect two outputs")
    elif isinstance(src, NodeInput):
        if not isinstance(trg, NodeOutput):
            raise NodeConnectionError("Cannot connect two inputs")
    else:
        raise NodeConnectionError("Undefinable connection")

    # Check if connection would exceed allowed connections for source or target
    # the other node has to be removed first since in the connection process
    # a node might be added and then the check would fail in the creation of the reverse connection
    src_connections: List[NodeInput | NodeOutput] = list(src.connections)
    if trg in src_connections:
        src_connections.remove(trg)

    trg_connections: List[NodeInput | NodeOutput] = list(trg.connections)

    if src in trg_connections:
        trg_connections.remove(src)

    if len(src_connections) > 0 and not src.allow_multiple:
        raise MultipleConnectionsError(
            f"Source {src} already connected: {src_connections}"
        )

    if len(trg_connections) > 0 and not trg.allow_multiple:
        raise MultipleConnectionsError(
            f"Target {trg} already connected: {trg_connections}"
        )
    return True


class IORenderOptions(TypedDict, total=False):
    """Typing definition for Node Input/Output render options."""

    set_default: bool
    type: str


class GenericValueOptions(TypedDict, total=False):
    """Typing definition for Node Input/Output generic value options."""


class NumberValueOptions(GenericValueOptions, total=False):
    """Typing definition for Node Input/Output number value options."""

    min: int
    max: int
    step: int


class EnumValueOptions(GenericValueOptions, total=False):
    """Typing definition for Node Input/Output enum value options."""

    options: EnumOf


class LiteralValueOptions(GenericValueOptions, total=False):
    """Typing definition for Node Input/Output literal value options."""

    options: List[Union[str, int, float]]


ValueOptions = Union[
    NumberValueOptions, EnumValueOptions, LiteralValueOptions, GenericValueOptions
]


NodeIOType = TypeVar("NodeIOType")


class IOOptions(NodeIOSerialization, total=False):
    """Typing definition for Node Input/Output options."""

    on: Dict[str, Union[EventCallback, List[EventCallback]]]


class NodeInputOptions(IOOptions, NodeInputSerialization, total=False):
    """Typing definition for Node Input options."""


class NodeOutputOptions(IOOptions, NodeOutputSerialization, total=False):
    """Typing definition for Node Output options."""


def generate_value_options(
    _type: SerializedType, value_options: Optional[GenericValueOptions] = None
) -> ValueOptions:
    """Generates value options for a NodeIO instance based on the type.

    Args:
        _type: The type of the NodeIO instance.
        value_options: Optional value options to update.

    Returns:
        The generated value options.
    """
    if value_options is not None:
        opts = value_options
    else:
        opts = GenericValueOptions()

    if isinstance(_type, dict) and "type" in _type and _type["type"] == "enum":
        opts.update(
            EnumValueOptions(
                options=_type,
            )
        )

    if isinstance(_type, dict) and "anyOf" in _type:
        nopts = GenericValueOptions()
        for _t in _type["anyOf"]:
            nopts.update(generate_value_options(_t, None))
        nopts.update(opts)
        opts = nopts

    if isinstance(_type, str):
        if _type == "int":
            opts.update(
                NumberValueOptions(
                    step=1,
                )
            )

    return opts


class NodeIO(EventEmitterMixin, Generic[NodeIOType]):
    """Abstract base class representing an input or output of a node in a node-based system."""

    default_allow_multiple = False

    def __init__(
        self,
        name: Optional[str] = None,
        type: SerializedType | Type = "Any",
        description: Optional[str] = None,
        allow_multiple: Optional[bool] = None,
        uuid: Optional[str] = None,
        id: Optional[str] = None,  # fallback for uuid
        render_options: Optional[IORenderOptions] = None,
        value_options: Optional[ValueOptions] = None,
        is_input: Optional[bool] = None,  # catch and ignore
        value: Optional[Any] = None,  # catch and ignore
        emit_value_set: bool = True,
        on: Optional[Dict[str, Union[EventCallback, List[EventCallback]]]] = None,
        hidden: bool = False,
        #  **kwargs,
    ) -> None:
        """Initializes a new instance of NodeIO.

        Args:
            name: The name of the NodeIO.
            description: Optional description of the NodeIO.
        """
        super().__init__()

        if uuid is None and id is not None:
            uuid = id
        self._uuid = (uuid or f"_{uuid4().hex}").strip()
        self._name = (name or self._uuid).strip()
        self._description = description
        self._value: Union[NodeIOType, NoValueType] = NoValue

        self._connected: List[NodeIO] = []
        self._allow_multiple: Optional[bool] = allow_multiple
        self._node: Optional[weakref.ref[Node]] = None
        if isinstance(type, str):
            true_type: type = string_to_type(type)
            ser_type = serialize_type(true_type)
        elif isinstance(type, dict):
            ser_type = type
        else:
            ser_type = serialize_type(type)
        if not isinstance(ser_type, (str, dict)):
            raise TypeError(
                f"type must be a string or a dict (exposedfunctionality.SerializedType) or type not {ser_type}"
            )

        self._sertype: SerializedType = ser_type
        self.hidden = hidden

        self.eventmanager = AsyncEventManager(self)
        self._value_options: ValueOptions = GenericValueOptions()
        self._default_render_options = render_options or {}
        self._default_value_options = generate_value_options(
            self._sertype, value_options
        )
        self._emit_value_set = emit_value_set

        if on is not None:
            for event, callback in on.items():
                if isinstance(callback, list):
                    for cb in callback:
                        self.on(event, cb)
                else:
                    self.on(event, callback)

    def deserialize(self, data: NodeIOSerialization) -> None:
        if "name" in data:
            self._name = data["name"].strip() or data.get("id", self._uuid)
        if "description" in data:
            self._description = data["description"]
        if "id" in data:
            self._uuid = data["id"]
        if "value" in data:
            self._value = data["value"]
        if "hidden" in data:
            self.hidden = data["hidden"]

    def serialize(self, drop=True) -> NodeIOSerialization:
        """Serializes the NodeIO instance to a dictionary.

        Returns:
            A dictionary containing the serialized name and description.
        """
        ser = NodeIOSerialization(
            name=self._name,
            type=self._sertype,
            id=self._uuid,
            is_input=self.is_input(),
            render_options=self.render_options,
            value_options=self.value_options,
            value=self.value,
            hidden=self.hidden,
            emit_value_set=self._emit_value_set,
        )
        if self._description is not None:
            ser["description"] = self._description
        if (
            self.allow_multiple is not None
            and self.allow_multiple is not self.default_allow_multiple
        ):
            ser["allow_multiple"] = self.allow_multiple

        if drop:
            if "name" in ser and ser["name"] == ser["id"]:
                del ser["name"]

            if "render_options" in ser and len(ser["render_options"]) == 0:
                del ser["render_options"]

            if "value_options" in ser and len(ser["value_options"]) == 0:
                del ser["value_options"]

            if "hidden" in ser and not ser["hidden"]:
                del ser["hidden"]

        return ser

    @property
    def name(self) -> str:
        """Gets the name of the NodeIO."""
        return self._name

    @name.setter
    def name(self, name: str) -> None:
        # asstert name is a string
        # if None or empty fall back to uuid
        if name is None:
            name = self.uuid
        name = str(name).strip()
        if len(name) == 0:
            name = self.uuid
        self._name = name

    @property
    def uuid(self):
        """The unique identifier of the node."""
        return self._uuid

    @property
    def full_id(self) -> Optional[str]:
        if self.node is None:
            return None
        return f"{self.node.uuid}__{self.uuid}"

    def get_value(self) -> NodeIOType | NoValueType:
        """Gets the current value of the NodeIO."""
        return self._value

    @property
    def value(self) -> NodeIOType | NoValueType:
        """Gets the current value of the NodeIO."""
        return self.get_value()

    @value.setter
    def value(self, value: NodeIOType) -> None:
        """Sets the value of the NodeIO."""
        self.set_value(value)

    @property
    def connections(self) -> List[NodeIO]:
        """Gets a list of NodeIO instances connected to this one."""
        return list(self._connected)

    def set_value(self, value: NodeIOType) -> NodeIOType | NoValueType:
        """Sets the internal value of the NodeIO.

        Args:
            value: The value to set.
        """
        self._value = value

        if self._emit_value_set:
            msg = MessageInArgs(src=self)
            msg["result"] = self.value
            self.emit("after_set_value", msg=msg)
        return self.value

    @emit_before()
    @emit_after()
    def connect(self, other: NodeIO, replace: bool = False):
        """Connects this NodeIO instance to another NodeIO instance.

        Args:
            other: The NodeIO instance to connect to.
            replace: If True, existing connections will be replaced.

        Raises:
            NodeConnectionError: If the connection is not allowed.
        """
        if self.hidden:
            self.hidden = False
        if other in self._connected:
            return
        try:
            raise_allow_connections(self, other)
        except MultipleConnectionsError:
            if not replace:
                raise
            self.disconnect()

        self._connected.append(other)
        other.connect(self, replace=replace)
        self.post_connect(other)
        if self.is_input():
            src = other
            trg = self
        else:
            src = self
            trg = other

        return [
            src.node.uuid if src.node else None,
            src.uuid,
            trg.node.uuid if trg.node else None,
            trg.uuid,
        ]

    def c(self, *args, **kwargs):
        """Alias for connect."""
        return self.connect(*args, **kwargs)

    def __gt__(self, other):
        self.connect(other)

    def __lt__(self, value):
        return self.set_value(value)

    @emit_before()
    @emit_after()
    def disconnect(self, other: Optional[NodeIO] = None):
        """Disconnects this NodeIO instance from another NodeIO instance, or all if no specific one is provided.

        Args:
            other: The NodeIO instance to disconnect from. If None, disconnects from all.
        """
        if other is None:
            for other in self.connections:
                self.disconnect(other)
            return
        if other not in self._connected:
            return
        self._connected.remove(other)
        other.disconnect(self)
        return [
            self.node.uuid if self.node else None,
            self.uuid,
            other.node.uuid if other.node else None,
            other.uuid,
        ]

    def d(self, *args, **kwargs):
        """Alias for disconnect."""
        return self.disconnect(*args, **kwargs)

    def post_connect(self, other: NodeIO):
        """Called after a connection is made.

        Args:
            other: The NodeIO instance that was connected to.
        """
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}({self._name},{self.full_id})>"

    @property
    def node(self) -> Optional[Node]:
        """Gets the Node instance that this NodeIO belongs to."""
        return self._node() if self._node is not None else None

    def set_node(self, node: Node) -> None:
        """Sets the Node instance that this NodeIO belongs to.

        Args:
            node: The Node instance to set.
        """
        if self._node is not None:
            if self._node() is node:
                return
            raise NodeAlreadyDefinedError("NodeIO already belongs to a node")
        if node is not None:
            self._node = weakref.ref(node)
        else:
            self._node = None

    @node.setter
    def node(self, node: Node) -> None:
        self.set_node(node)

    def ready(self) -> bool:
        return self.node is not None

    def ready_state(self) -> IOReadyState:
        return {"node": self.node is not None}

    def status(self) -> NodeIOStatus:
        return NodeIOStatus(
            has_value=self.value is not NoValue,
            has_node=self.node is not None,
            ready=self.ready(),
            connected=len(self.connections) > 0,
        )

    def is_input(self):
        """Returns whether this NodeIO is an input.

        Returns
        -------
        bool:
            whether this NodeIO is an input

        """
        raise NotImplementedError()

    @property
    def does_trigger(self) -> bool:
        return True

    def serialize_class(self) -> NodeIOClassSerialization:
        ser = NodeIOClassSerialization(
            name=self.name,
            type=self._sertype,
            description=self._description,
            uuid=self.uuid,
        )
        if self._allow_multiple is not None:
            ser["allow_multiple"] = self._allow_multiple

        if "name" in ser and ser["name"] == ser["uuid"]:
            del ser["name"]
        return ser

    def full_serialize(self, with_value=False) -> FullNodeIOJSON:
        """Generates a JSON serializable dictionary of the NodeIO.

        Returns
        -------
        FullNodeIOJSON:
            JSON serializable dictionary of the NodeIO
        """
        ser = FullNodeIOJSON(
            id=self.uuid,
            full_id=self.full_id,
            name=self.name,
            type=self._sertype,
            is_input=self.is_input(),
            connected=self.is_connected(),
            node=self.node.uuid if self.node else None,
            does_trigger=self.does_trigger,
            render_options=self.render_options,
            value_options=self.value_options,
            hidden=self.hidden,
            emit_value_set=self._emit_value_set,
        )
        if with_value:
            ser["value"] = self.value

        return ser

    def _repr_json_(self) -> FullNodeIOJSON:
        return JSONEncoder.apply_custom_encoding(
            self.full_serialize(with_value=False), preview=False
        )  # type: ignore

    @property
    def allow_multiple(self) -> bool:
        """
        Indicates whether this NodeInput allows multiple connections.

        Returns:
            A boolean indicating whether multiple connections are allowed.
            Defaults to False if not explicitly set.
        """
        return (
            self._allow_multiple
            if self._allow_multiple is not None
            else self.default_allow_multiple
        )

    @property
    def render_options(self) -> IORenderOptions:
        return self._default_render_options

    @property
    def value_options(self) -> ValueOptions:
        return deep_fill_dict(
            self._default_value_options,  # type: ignore
            self._value_options,  # type: ignore
            inplace=False,
            overwrite_existing=True,
        )

    @value_options.setter
    def value_options(self, value_options: ValueOptions):
        self._value_options = deep_remove_dict_on_equal(
            value_options,  # type: ignore
            self._default_value_options,  # type: ignore
            inplace=False,
        )

    @emit_after()
    def update_value_options(self, **kwargs) -> ValueOptions:
        deep_fill_dict(
            self._value_options,  # type: ignore
            kwargs,  # type: ignore
            inplace=True,
            overwrite_existing=True,
        )

        return self.value_options

    def is_connected(self) -> bool:
        """Returns whether this NodeIO is connected to another NodeIO.

        Returns
        -------
        bool:
            whether this NodeIO is connected to another NodeIO
        """
        return len(self._connected) > 0


class NodeInput(NodeIO, Generic[NodeIOType]):
    """
    Represents an input connection point for a node in a node-based system.
    Inherits from NodeIO and represents a connection that can receive data.
    """

    @staticmethod
    def is_default_factory(obj: Any):
        return hasattr(obj, "_is_default_factory")

    @staticmethod
    def DefaultFactory(
        func: Callable[[NodeInput[NodeIOType]], NodeIOType],
    ) -> Callable[[NodeInput[NodeIOType]], NodeIOType]:
        func._is_default_factory = True
        return func

    default_does_trigger = True
    default_required = True
    default_allow_multiple = False

    def __init__(
        self,
        *args,
        does_trigger: Optional[bool] = None,
        required: Optional[bool] = None,
        default: Union[NodeIOType, NoValueType] = NoValue,
        class_default: Optional[NodeIOType] = NoValue,
        **kwargs,
    ) -> None:
        """
        Initializes a new instance of NodeInput.

        Accepts all arguments that NodeIO does.
        """

        self._does_trigger = (
            self.default_does_trigger if does_trigger is None else does_trigger
        )
        self.required = self.default_required if required is None else required
        super().__init__(
            *args,
            **kwargs,
        )
        self._connected: List[NodeOutput] = self._connected
        self._default = default
        self._class_default = class_default
        self._forwards: weakref.WeakSet[NodeInput] = weakref.WeakSet()
        self._forwards_from: weakref.WeakSet[NodeInput] = weakref.WeakSet()
        self._datapath: Optional[DataPath] = None
        self.set_value(
            self.value,
            does_trigger=False,
        )

    def set_node(self, node):
        super().set_node(node)
        self.set_value(
            self.value,
            does_trigger=False,
        )

    def get_value(self):
        v = super().get_value()
        return v if v is not NoValue else self.default

    def full_serialize(self, with_value=False) -> FullNodeInputJSON:
        return FullNodeInputJSON(
            **super().full_serialize(with_value=with_value),
            default=self.default,
            required=self.required,
        )

    def set_default(self, default: NodeIOType | NoValueType):
        if default == NoValue:
            default = self._class_default
        self._default = default

    @property
    def default(self) -> NodeIOType | NoValueType:
        if NodeInput.is_default_factory(self._default):
            return self._default(self)
        return self._default

    @default.setter
    def default(self, default: NodeIOType | NoValueType):
        self.set_default(default)

    def disconnect(self, other: Optional[Union[NodeInput, NodeOutput]] = None):
        if other is None:
            for other in list(self._forwards_from):
                other.unforward(self)
        else:
            if other in self._forwards_from:
                other.unforward(self)
            if other in self._forwards:
                self.unforward(other)

        super().disconnect(other=other)

        if not self.is_connected():
            self.set_value(self.default, does_trigger=False)

    def is_connected(self):
        return super().is_connected() or len(self._forwards_from) > 0

    @classmethod
    def from_serialized_input(cls, serialized_input: FunctionInputParam) -> NodeInput:
        """
        Creates a NodeInput instance from serialized input data.

        Args:
            serialized_input: A dictionary containing serialized data for the node input.

        Returns:
            An instance of NodeInput initialized with the serialized data.
        """
        return cls(
            uuid=serialized_input.get(
                # overwriting the name attribute losses reference,
                # which is why we use _name (see expose_method if exposedfunctionality)
                "_name",
                serialized_input.get("name"),
            ),
            name=serialized_input.get("name"),
            description=serialized_input.get("description"),
            type=serialized_input["type"],
            allow_multiple=serialized_input.get("allow_multiple"),
            default=serialized_input.get("default", NoValue),
        )

    def serialize(self, drop=True) -> NodeInputSerialization:
        """
        Serializes the NodeInput instance to a dictionary for storage or transmission.

        Returns:
            A dictionary containing the serialized name and description of the node input.
        """
        ser = NodeInputSerialization(
            **super().serialize(drop=drop),
        )
        if self.required is not NodeInput.default_required:
            ser["required"] = self.required
        if self.does_trigger is not NodeInput.default_does_trigger:
            ser["does_trigger"] = self.does_trigger
        if self.default is not NoValue:
            ser["default"] = self.default
        v, d = self.value, self.default
        if not self.is_connected():  # check same type
            comp = v != d
            if not isinstance(comp, bool):
                # other comaring results are handled by the encoder
                comp = json.dumps(v, cls=JSONEncoder) != json.dumps(d, cls=JSONEncoder)
            if comp:
                ser["value"] = self.value

        return ser

    def to_dict(self) -> NodeInputOptions:
        ser: IOOptions = NodeInputOptions(
            **self.serialize(drop=False),
        )
        if NodeInput.is_default_factory(self._default):
            ser["default"] = self._default
        return ser

    def deserialize(self, data: NodeInputSerialization) -> None:
        super().deserialize(data)
        if "required" in data:
            self.required = data["required"]
        if "does_trigger" in data:
            self._does_trigger = data["does_trigger"]
        if "default" in data:
            self._default = data["default"]

    @classmethod
    def from_serialized_nodeio(
        cls, serialized_nodeio: NodeInputSerialization
    ) -> NodeInput:
        """
        Creates a NodeInput instance from serialized input data.

        Args:
            serialized_nodeio: A dictionary containing serialized data for the node input.

        Returns:
            An instance of NodeInput initialized with the serialized data.
        """

        ins = cls(**serialized_nodeio)
        ins.deserialize(serialized_nodeio)
        return ins

    @property
    def datapath(self) -> Optional[DataPath]:
        """Gets the DataPath associated with this NodeInput."""
        return self._datapath

    @datapath.setter
    def datapath(self, datapath: DataPath) -> None:
        self._datapath = datapath

    def set_value(
        self,
        value: object,
        does_trigger: Optional[bool] = None,
        datapath: Optional[DataPath] = None,
    ) -> None:
        super().set_value(value)
        if self.node is not None:
            new_datapath = DataPath(self.node, self.uuid)
        else:
            new_datapath = None
        if datapath is not None and new_datapath is not None:
            new_datapath.add_src_path(datapath)

        self.datapath = new_datapath

        if self.node is not None:
            if does_trigger is None:
                does_trigger = self.does_trigger
            if does_trigger:
                self.node.request_trigger()

        for other in self._forwards:
            if other.has_forwards_from(self):
                other.set_value(value, does_trigger=does_trigger)
            else:
                self._forwards.remove(other)

    def is_input(self):
        """Returns whether this NodeIO is an input.

        Returns
        -------
        bool:
            whether this NodeIO is an input

        """
        return True

    def ready(self):
        return super().ready() and (self.value is not NoValue or not self.required)

    def ready_state(self) -> InputReadyState:
        return InputReadyState(**super().ready_state(), value=self.value is not NoValue)

    def status(self) -> NodeInputStatus:
        return NodeInputStatus(required=self.required, **super().status())

    @property
    def connections(self) -> List[NodeOutput]:
        """Gets a list of NodeIO instances connected to this one."""
        return list(self._connected)

    @property
    def does_trigger(self) -> bool:
        """
        Indicates whether this NodeInput triggers the node when set.

        Returns:
            A boolean indicating whether the node is triggered when the input is set.
            Defaults to True if not explicitly set.
        """
        return self._does_trigger

    def trigger(self, triggerstack: Optional[TriggerStack] = None) -> TriggerStack:
        if triggerstack is None:
            triggerstack = TriggerStack()
        if not self.does_trigger or self.value is NoValue or self.node is None:
            return triggerstack

        if self.node.ready_to_trigger():
            return self.node.trigger(triggerstack=triggerstack)
        self.node.request_trigger()
        return triggerstack

    def __del__(self):
        self.disconnect()
        self._node = None
        self._value = NoValue

    def has_forwards_from(self, other: NodeInput):
        return other in self._forwards_from

    def has_forward_to(self, other: NodeInput):
        return other in self._forwards

    def forwards_from(self, other: NodeInput, replace=False):
        if other in self._forwards_from:
            return other.forward(self, replace=replace)
        if not other.is_input():
            raise NodeConnectionError("Can only forward from other inputs")

        if other in self._forwards:
            raise NodeConnectionError(
                "cannot get forwards from an input it selfs forwards to"
            )

        if self.is_connected() and not replace:
            raise MultipleConnectionsError("Can only forward to unconnected inputs")

        self._forwards_from.add(other)
        self.set_default(NoValue)  # set default to class default upon connection

        return other.forward(self, replace=replace)

    @emit_before()
    @emit_after()
    def forward(self, other: NodeInput, replace=False):
        if other in self._forwards:
            return [
                self.node.uuid if self.node else None,
                self.uuid,
                other.node.uuid if other.node else None,
                other.uuid,
            ]
        if not other.is_input():
            raise NodeConnectionError("Can only forward to other inputs")

        if other.is_connected():
            if not replace:
                raise MultipleConnectionsError("Can only forward to unconnected inputs")
            else:
                other.disconnect()

        self._forwards.add(other)
        other.forwards_from(self, replace=replace)

        other.set_value(self.value)

        return [
            self.node.uuid if self.node else None,
            self.uuid,
            other.node.uuid if other.node else None,
            other.uuid,
        ]

    def unforward_from(self, other: NodeInput):
        if other in self._forwards_from:
            self._forwards_from.remove(other)
            other.unforward(self)

        if len(self._connected) + len(self._forwards_from) == 0:
            self.set_value(self.default, does_trigger=False)

    @emit_before()
    @emit_after()
    def unforward(self, other: NodeInput):
        if other in self._forwards:
            self._forwards.remove(other)
            other.unforward_from(self)
            return [
                self.node.uuid if self.node else None,
                self.uuid,
                other.node.uuid if other.node else None,
                other.uuid,
            ]

    def get_forward_connections(self) -> List[NodeInput]:
        return list(self._forwards)

    def connect(self, other, replace=False):
        if isinstance(other, NodeInput):
            return self.forward(other, replace=replace)
        self.set_default(NoValue)  # set default to class default upon connection
        con = super().connect(other, replace)
        if con and self._forwards_from:
            for f in list(self._forwards_from):
                self.unforward_from(f)

        return con


class NodeOutput(NodeIO):
    """
    Represents an output connection point for a node in a node-based system.
    Inherits from NodeIO and represents a connection that can send data.
    """

    default_allow_multiple = True

    def __init__(self, *args, **kwargs) -> None:
        """
        Initializes a new instance of NodeOutput.

        Accepts all arguments that NodeIO does.
        """

        super().__init__(*args, **kwargs)

        # self._connected: List[NodeInput] = self._connected

    @classmethod
    def from_serialized_output(
        cls, serialized_output: FunctionOutputParam
    ) -> NodeOutput:
        """
        Creates a NodeOutput instance from serialized output data.

        Args:
            serialized_output: A dictionary containing serialized data for the node output.

        Returns:
            An instance of NodeOutput initialized with the serialized data.
        """
        return cls(
            uuid=serialized_output["name"],
            description=serialized_output.get("description"),
            type=serialized_output["type"],
        )

    def serialize(self, drop: bool = True) -> NodeOutputSerialization:
        """
        Serializes the NodeOutput instance to a dictionary for storage or transmission.

        Returns:
            A dictionary containing the serialized name and description of the node output.
        """
        return NodeOutputSerialization(**super().serialize(drop=drop))

    def to_dict(self) -> NodeOutputOptions:
        ser: IOOptions = NodeOutputOptions(
            **self.serialize(drop=False),
        )
        return ser

    def deserialize(self, data: NodeIOSerialization) -> None:
        return super().deserialize(data)

    @classmethod
    def from_serialized_nodeio(
        cls, serialized_nodeio: NodeOutputSerialization
    ) -> NodeOutput:
        """
        Creates a NodeOutput instance from serialized output data.

        Args:
            serialized_nodeio: A dictionary containing serialized data for the node output.

        Returns:
            An instance of NodeOutput initialized with the serialized data.
        """
        ins = cls(**serialized_nodeio)
        ins.deserialize(serialized_nodeio)
        return ins

    @property
    def connections(self) -> List[NodeInput]:
        """Gets a list of NodeIO instances connected to this one."""
        return list(self._connected)  # type: ignore connected has to be a list of NodeInput since outputs dont connect

    def set_value(
        self,
        value: object,
        does_trigger: Optional[bool] = None,
    ) -> None:
        """Sets the internal value of the NodeIO.

        Args:
            value: The value to set.
        """
        super().set_value(value)

        # input_paths: List[DataPath] = []
        if self.node is not None:
            datapath = DataPath(self.node, self.uuid)
            for ip_name, input in self.node.inputs.items():
                if ip_name == "_triggerinput":
                    continue
                if input.datapath is not None:
                    datapath.add_src_path(input.datapath)
                    # input_paths.append(input.datapath)
        else:
            datapath = None
            # input_paths = []
        for other in self.connections:
            # if self.node is not None:
            #     for input_path in input_paths:
            #         datapath.add_src_path(input_path)
            # else:
            #     datapath = None

            other.set_value(value, does_trigger=does_trigger, datapath=datapath)

    def post_connect(self, other: NodeIO):
        """Called after a connection is made.

        Args:
            other: The NodeIO instance that was connected to.
        """
        if self.value is not NoValue:
            other.set_value(self.value)

    def is_input(self):
        """Returns whether this NodeIO is an input.

        Returns
        -------
        bool:
            whether this NodeIO is an input

        """
        return False

    def status(self) -> NodeOutputStatus:
        return NodeOutputStatus(**super().status())

    def trigger(self, triggerstack: Optional[TriggerStack] = None) -> TriggerStack:
        """Triggers the node connected to this output via the connected inputs.
        First all connected inputs are set to the value of this output and then all connected inputs are triggered.
        """
        if triggerstack is None:
            triggerstack = TriggerStack()
        for connection in self.connections:
            connection.set_value(
                self.value,
                does_trigger=False,  # no triggering since this happens manually in the next line
            )
        for connection in self.connections:
            try:
                # the triggering of the connections should not be hindered by exceptions
                # this can happen e.g. if the outputs connects to two inputs of one node,
                # resulting in a double trigger, which will likely raise an InTriggerError
                connection.trigger(triggerstack=triggerstack)
            except Exception:
                pass
        return triggerstack


def nodeioencoder(obj, preview=False) -> Tuple[Any, bool]:
    """
    Encodes Nodes
    """
    if isinstance(obj, NodeIO):
        return obj.full_serialize(with_value=False), True
    return obj, False


JSONEncoder.prepend_encoder(nodeioencoder)  # prepand to skip __repr_json__ method
