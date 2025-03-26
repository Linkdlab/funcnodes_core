from typing import Callable, Any, Union, Tuple, List, Dict, Optional
import json
import base64
import weakref
import struct

import dataclasses

VALID_JSON_TYPE = Union[int, float, str, bool, list, dict, type(None)]


class JSONDecoder(json.JSONDecoder):
    """
    Custom JSON decoder that uses a list of decoders to decode JSON objects.

    Args:
      object_hook (Callable): A function that will be called with the result of any object literal decoded (a dict).
        The return value of object_hook will be used instead of the dict. This feature can be used to implement
        custom decoders (e.g. JSON-RPC class hinting).

    Examples:
      >>> JSONDecoder().decode('{"__complex__": true}', object_hook=complex_decoder)
      (1+2j)
    """

    decoder: List[Callable[[VALID_JSON_TYPE], tuple[Any, bool]]] = []

    def __init__(self, *args, **kwargs) -> None:
        """
        Initializes a new JSONDecoder object.
        """
        kwargs["object_hook"] = JSONDecoder._object_hook
        super().__init__(*args, **kwargs)

    @classmethod
    def add_decoder(cls, dec: Callable[[VALID_JSON_TYPE], tuple[Any, bool]]):
        """
        Adds a new decoder to the list of decoders.

        Args:
          dec (Callable[[VALID_JSON_TYPE], tuple[Any, bool]]): A function that takes in a valid JSON type and
            returns a tuple containing the decoded object and a boolean indicating whether
            or not the object was decoded.

        Examples:
          >>> JSONDecoder.add_decoder(complex_decoder)
        """
        cls.decoder.append(dec)

    @classmethod
    def _object_hook(cls, obj: VALID_JSON_TYPE):
        """"""
        if isinstance(obj, dict):
            for key in list(obj.keys()):
                obj[key] = cls._object_hook(obj[key])
            return obj
        elif isinstance(obj, list):
            obj = [cls._object_hook(item) for item in obj]
            return obj

        for dec in JSONDecoder.decoder:
            res, handled = dec(obj)
            if handled:
                return res
        return obj


@dataclasses.dataclass
class Encdata:
    data: Any
    done: bool = False
    handeled: bool = False
    continue_preview: Optional[bool] = None


encodertype = Callable[
    [Any, bool],
    Union[tuple[Any, bool], Encdata],
]


class JSONEncoder(json.JSONEncoder):
    """
    Custom JSON encoder that uses a list of encoders to encode JSON objects.
    """

    encoder_registry: Dict[type, List[encodertype]] = {}

    default_preview = False

    @classmethod
    def add_encoder(cls, enc: encodertype, enc_cls: Optional[List[type]] = None):
        """
        Adds a new encoder to the list of encoders.

        Args:
          enc (encodertyoe): A function that takes in an object and a boolean indicating whether
            or not to use a default preview and returns a tuple containing the encoded object and a
            boolean indicating whether or not the object was encoded.
          enc_cls (Optional[List[type]]): A list of classes that the encoder should be applied to primarily.
        Examples:
          >>> def complex_encoder(obj, preview=False):
          ...     if isinstance(obj, complex):
          ...         return {"__complex__": True}, True
          ...     return obj, False
          >>> JSONEncoder.add_encoder(complex_encoder)
        """
        if enc_cls is None:
            enc_cls = [object]
        for _enc_cls in enc_cls:
            if _enc_cls not in cls.encoder_registry:
                cls.encoder_registry[_enc_cls] = []
            cls.encoder_registry[_enc_cls].append(enc)

    @classmethod
    def prepend_encoder(cls, enc: encodertype, enc_cls: Optional[List[type]] = None):
        """
        Adds a new encoder to the list of encoders.

        Args:
          enc (encodertyoe): A function that takes in an object and a boolean indicating whether
            or not to use a default preview and returns a tuple containing the encoded object and
            a boolean indicating whether or not the object was encoded.

        Examples:
          >>> def complex_encoder(obj, preview=False):
          ...     if isinstance(obj, complex):
          ...         return {"__complex__": True}, True
          ...     return obj, False
          >>> JSONEncoder.add_encoder(complex_encoder)
        """
        if enc_cls is None:
            enc_cls = [object]
        for _enc_cls in enc_cls:
            if _enc_cls not in cls.encoder_registry:
                cls.encoder_registry[_enc_cls] = []
            cls.encoder_registry[_enc_cls].insert(0, enc)

    @classmethod
    def apply_custom_encoding(cls, obj, preview=False, seen=None):
        """
        Recursively apply custom encoding to an object, using the encoders defined in JSONEncoder.
        """
        if seen is None:
            seen = set()

        obj_id = id(obj)
        if obj_id in seen:
            # Circular reference detected.
            raise ValueError("Circular reference detected.")
        # Mark this object as seen.
        seen.add(obj_id)

        try:
            # Attempt to apply custom encodings
            obj_type = type(obj)
            for base in obj_type.__mro__:
                encoders = cls.encoder_registry.get(base)
                if encoders:
                    for enc in encoders:
                        # try:
                        encres = enc(obj, preview)

                        if not isinstance(encres, Encdata):
                            res, handled = encres
                            encres = Encdata(data=res, handeled=handled)
                        if encres.handeled:
                            if encres.done:
                                return encres.data

                            return cls.apply_custom_encoding(
                                encres.data,
                                preview=(
                                    preview
                                    if encres.continue_preview is None
                                    else encres.continue_preview
                                ),
                                seen=seen,
                            )
                    # except Exception as e:
                    #     pass
            if isinstance(obj, (int, float, bool, type(None))):
                # convert nan to None
                if isinstance(obj, float) and obj != obj:
                    return None
                # Base types
                return obj
            elif isinstance(obj, str):
                if preview and len(obj) > 1000:
                    return obj[:1000] + "..."
                return obj
            elif isinstance(
                obj, (dict, weakref.WeakKeyDictionary, weakref.WeakValueDictionary)
            ):
                # Handle dictionaries
                return {
                    key: cls.apply_custom_encoding(value, preview=preview, seen=seen)
                    for key, value in obj.items()
                }
            elif isinstance(obj, (set, tuple, list, weakref.WeakSet)):
                # Handle lists
                obj = list(obj)
                if preview:
                    return [
                        cls.apply_custom_encoding(item, preview, seen=seen)
                        for item in obj[:10]
                    ]
                return [cls.apply_custom_encoding(item, seen=seen) for item in obj]

            # Fallback to string representation
            return str(obj)
        finally:
            # Remove this object from seen objects
            seen.remove(obj_id)

    def default(self, obj):
        """
        Applies custom encoding to an object.

        Args:
          obj (Any): The object to be encoded.

        Returns:
          Any: The encoded object.

        Examples:
          >>> JSONEncoder.default(obj)
        """
        return self.apply_custom_encoding(obj, self.default_preview)


def _repr_json_(obj, preview=False) -> Tuple[Any, bool]:
    """
    Encodes objects that have a _repr_json_ method.
    """
    if hasattr(obj, "_repr_json_"):
        return Encdata(
            data=obj._repr_json_(), handeled=True, done=True, continue_preview=False
        )
    return Encdata(data=obj, handeled=False)


JSONEncoder.add_encoder(_repr_json_)


def bytes_handler(obj, preview=False):
    """
    Encodes bytes objects to base64 strings.
    """
    if isinstance(obj, bytes):
        # Convert bytes to base64 string
        if preview:
            return Encdata(
                done=True, handeled=True, data=base64.b64encode(obj).decode("utf-8")
            )
        return Encdata(
            done=True, handeled=True, data=base64.b64encode(obj).decode("utf-8")
        )
    return Encdata(data=obj, handeled=False)


JSONEncoder.add_encoder(bytes_handler, enc_cls=[bytes])


def dataclass_handler(obj, preview=False):
    """
    Encodes dataclasses to dictionaries.
    """
    if dataclasses.is_dataclass(obj):
        return Encdata(data=dataclasses.asdict(obj), handeled=True)
    return Encdata(data=obj, handeled=False)


JSONEncoder.add_encoder(dataclass_handler)


@dataclasses.dataclass
class BytesEncdata:
    data: Union[bytes, Any]
    handeled: bool = False
    mime: Optional[str] = None


byteencodertype = Callable[
    [Any, bool],
    BytesEncdata,
]


class ByteEncoder:
    encoder_registry: Dict[type, List[byteencodertype]] = {}

    default_preview = False

    class NoEncoderException(Exception):
        pass

    @classmethod
    def add_encoder(cls, enc: byteencodertype, enc_cls: Optional[List[type]] = None):
        """
        Adds a new encoder to the list of encoders.

        Args:
          enc (encodertyoe): A function that takes in an object and a boolean indicating whether
            or not to use a default preview and returns a tuple containing the encoded object and a
            boolean indicating whether or not the object was encoded.
          enc_cls (Optional[List[type]]): A list of classes that the encoder should be applied to primarily.
        Examples:
          >>> def complex_encoder(obj, preview=False):
          ...     if isinstance(obj, complex):
          ...         return {"__complex__": True}, True
          ...     return obj, False
          >>> JSONEncoder.add_encoder(complex_encoder)
        """
        if enc_cls is None:
            enc_cls = [object]
        for _enc_cls in enc_cls:
            if _enc_cls not in cls.encoder_registry:
                cls.encoder_registry[_enc_cls] = []
            cls.encoder_registry[_enc_cls].append(enc)

    @classmethod
    def prepend_encoder(
        cls, enc: byteencodertype, enc_cls: Optional[List[type]] = None
    ):
        """
        Adds a new encoder to the list of encoders.

        Args:
          enc (encodertyoe): A function that takes in an object and a boolean indicating whether
            or not to use a default preview and returns a tuple containing the encoded object and
            a boolean indicating whether or not the object was encoded.

        Examples:
          >>> def complex_encoder(obj, preview=False):
          ...     if isinstance(obj, complex):
          ...         return {"__complex__": True}, True
          ...     return obj, False
          >>> JSONEncoder.add_encoder(complex_encoder)
        """
        if enc_cls is None:
            enc_cls = [object]
        for _enc_cls in enc_cls:
            if _enc_cls not in cls.encoder_registry:
                cls.encoder_registry[_enc_cls] = []
            cls.encoder_registry[_enc_cls].insert(0, enc)

    @classmethod
    def encode(cls, obj, preview=False, seen=None, json_fallback=True) -> BytesEncdata:
        """
        Recursively apply custom encoding to an object, using the encoders defined in JSONEncoder.
        """
        if seen is None:
            seen = set()

        obj_id = id(obj)
        if obj_id in seen:
            # Circular reference detected.
            raise ValueError("Circular reference detected.")
        # Mark this object as seen.
        seen.add(obj_id)

        try:
            # Attempt to apply custom encodings
            obj_type = type(obj)
            for base in obj_type.__mro__:
                encoders = cls.encoder_registry.get(base)
                if encoders:
                    for enc in encoders:
                        # try:
                        encres = enc(obj, preview)
                        if encres.handeled:
                            return encres

            if isinstance(obj, str):
                return BytesEncdata(
                    data=(
                        obj[:1000] + "..." if preview and len(obj) > 1000 else obj
                    ).encode("utf-8", errors="replace"),
                    handeled=True,
                    mime="text/plain",
                )

            if isinstance(obj, bytes):
                return BytesEncdata(
                    data=obj, handeled=True, mime="application/octet-stream"
                )

            if isinstance(obj, int):
                return BytesEncdata(
                    data=struct.pack("!q", obj),
                    handeled=True,
                    mime="application/fn.struct.!q",
                )

            if isinstance(obj, float):
                return BytesEncdata(
                    data=struct.pack("!d", obj),
                    handeled=True,
                    mime="application/fn.struct.!d",
                )

            if isinstance(obj, bool):
                return BytesEncdata(
                    data=struct.pack("?", obj),
                    handeled=True,
                    mime="application/fn.struct.?",
                )

            if obj is None:
                return BytesEncdata(data=b"", handeled=True, mime="application/fn.null")

            # Fallback to JSON representation
            if json_fallback:
                return BytesEncdata(
                    data=json.dumps(
                        JSONEncoder.apply_custom_encoding(obj, preview)
                    ).encode("utf-8", errors="replace"),
                    handeled=True,
                    mime="application/json",
                )
            raise ByteEncoder.NoEncoderException(f"No encoder for {type(obj)}")
        finally:
            # Remove this object from seen objects
            seen.remove(obj_id)


def bytes_bytes_handler(obj, preview=False):
    """
    Encodes bytes objects to base64 strings.
    """
    if isinstance(obj, bytes):
        # Convert bytes to base64 string
        return BytesEncdata(handeled=True, data=obj, mime="application/octet-stream")
    return BytesEncdata(data=obj, handeled=False, mime="application/octet-stream")


ByteEncoder.add_encoder(bytes_bytes_handler, enc_cls=[bytes])
