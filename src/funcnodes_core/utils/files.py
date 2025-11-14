import json
import os
import tempfile
from .serialization import JSONEncoder
from pathlib import Path
from typing import Union


def write_json_secure(data, filepath: Union[Path, str], cls=None, **kwargs):
    """
    Write JSON data to a file securely to avoid corruption.

    :param data: The data to write (dictionary or list).
    :param filepath: The final JSON file path.
    """

    filepath = Path(filepath).absolute()
    directory = filepath.parent
    directory.mkdir(parents=True, exist_ok=True)
    filepath_str = str(filepath)

    cls = cls or JSONEncoder

    # Create a temporary file in the same directory
    try:
        with tempfile.NamedTemporaryFile(
            "w+", dir=directory, delete=False, encoding="utf-8"
        ) as temp_file:
            temp_file_path = temp_file.name
            # Write the JSON data to the temporary file
            json.dump(data, temp_file, cls=cls, **kwargs)
            temp_file.flush()  # Ensure all data is written to disk
            os.fsync(temp_file.fileno())  # Force writing to disk for durability
    except Exception as e:
        # Clean up the temporary file in case of an error
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise e

    # Atomically replace the target file with the temporary file
    try:
        os.replace(temp_file_path, filepath_str)
    except Exception as e:
        # Clean up the temporary file in case of an error
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise e
