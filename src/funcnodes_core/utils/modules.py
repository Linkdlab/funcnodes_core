def resolve(dotted_name: str):
    """
    Resolve a fully qualified (dotted) name to a global Python object.

    This function takes a string representing a fully qualified name of an object,
    such as a module, class, function, or attribute (e.g., 'os.path.join' or
    'package.module.ClassName'), and returns the corresponding object. It does this
    by:

      1. Splitting the dotted name into its component parts.
      2. Importing the base module.
      3. Iteratively retrieving each attribute specified in the remaining parts.
         If an attribute is not found, it attempts to import the module corresponding
         to the current dotted path and then retries the attribute lookup.

    Parameters:
        dotted_name (str): The fully qualified name of the target object.

    Returns:
        object: The Python object corresponding to the given dotted name.

    Raises:
        ImportError: If the initial module or any subsequent module cannot be imported.
        AttributeError: If an attribute does not exist in the module after import.
    """
    parts = dotted_name.split(".")
    module_name = parts.pop(0)
    current_object = __import__(module_name)
    for part in parts:
        module_name = f"{module_name}.{part}"
        try:
            current_object = getattr(current_object, part)
        except AttributeError:
            __import__(module_name)
            current_object = getattr(current_object, part)
    return current_object
