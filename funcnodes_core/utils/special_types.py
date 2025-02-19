from pathlib import Path
from .serialization import JSONEncoder, Encdata


class databytes(bytes):
    """
    A subclass of bytes that is not fully encoded in preview.
    """

    pass


def databytes_handler(obj, preview=False):
    """
    Encodes bytes objects to base64 strings.
    """
    if isinstance(obj, databytes):
        # Convert bytes to base64 string
        return Encdata(data=f"databytes({len(obj)})", handeled=True, done=True)
    return Encdata(data=obj, handeled=False)


JSONEncoder.add_encoder(databytes_handler, enc_cls=[databytes])


def path_hander(obj, preview=False):
    """
    Encodes paths to strings.
    """
    if isinstance(obj, Path):
        return Encdata(data=obj.as_posix(), handeled=True)
    return Encdata(data=obj, handeled=False)


JSONEncoder.add_encoder(path_hander)
