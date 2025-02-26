from functools import wraps
import inspect


def signaturewrapper(func):
    def funcwrapper(innerfunc):
        _innerfunc = wraps(func)(innerfunc)
        _innerfunc = innerfunc
        _innerfunc.__signature__ = inspect.signature(func)
        return _innerfunc

    return funcwrapper


class saveproperty(property):
    """
    Extended property descriptor that prevents critical properties from being overridden in subclasses.

    This descriptor builds on Python’s built-in property by registering itself on the owner class
    when it is defined. During class creation, the __set_name__ method is automatically invoked,
    storing the property’s name and the owner class. It then records itself in a special dictionary
    (__save_properties__) on the owner class. This registration enables later checks (via a mixin)
    to detect and prevent any subclass from overriding the property.

    Attributes:
        name (str): The name of the property as defined in the class.
        owner (type): The class that originally defined this property.
    """

    def __set_name__(self, owner, name):
        self.name = name
        self.owner = owner
        # Register this property on the owner class in a dedicated dictionary.
        if not hasattr(owner, "__save_properties__"):
            owner.__save_properties__ = {}
        owner.__save_properties__[name] = self


class savemethod:
    """
    Decorator that marks a class method as protected from being overridden in subclasses.

    This decorator wraps the target function in a descriptor that registers itself on the
    owning class via the __set_name__ hook. During class creation, the owner stores a
    reference to this protected method in the __save_methods__ dictionary. When combined with
    a mixin (e.g., NoOverrideMixin), if a subclass attempts to override a method decorated
    with @savemethod, a TypeError will be raised.

    Usage:
        class Base(NoOverrideMixin):
            @savemethod
            def critical_method(self):
                print("Important work")

        # Attempting to override `critical_method` in a subclass will cause a TypeError:
        class Child(Base):
            def critical_method(self):
                print("Override attempt")
    """

    def __init__(self, func):
        self.func = func

    def __set_name__(self, owner, name):
        self.name = name
        self.owner = owner
        # Register this method on the owner class in a dedicated dictionary.
        if not hasattr(owner, "__save_methods__"):
            owner.__save_methods__ = {}
        owner.__save_methods__[name] = self

    def __get__(self, instance, owner):
        # Return the bound method when accessed via an instance.
        if instance is None:
            return self
        return self.func.__get__(instance, owner)


class NoOverrideMixin:
    """
    Mixin that enforces protection of properties defined with saveproperty from being overridden.

    This mixin leverages the __init_subclass__ hook to inspect new subclass definitions. It iterates
    through the method resolution order (MRO) of the new class to check for any attributes that were
    registered as saveproperties in base classes. If the subclass’s own dictionary contains an attribute
    with the same name that is not the same as the registered property, a TypeError is raised,
    preventing the override.

    Usage:
        Inherit from this mixin in your base class to ensure that any properties defined with saveproperty
        are protected against being overwritten in subclasses.
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Iterate over all classes in the method resolution order.
        for base in cls.__mro__:
            # chack all saveprops
            registered = getattr(base, "__save_properties__", {})
            for name, prop in registered.items():
                # If the subclass defines the attribute and it is not the same property object, raise an error.
                if name in cls.__dict__ and cls.__dict__[name] is not prop:
                    raise TypeError(
                        f"Overriding saveproperty '{name}' is forbidden in class '{cls.__name__}'."
                    )

            # check all savemethods
            registered = getattr(base, "__save_methods__", {})
            for name, method in registered.items():
                # If the subclass defines the attribute and it is not the same property object, raise an error.
                if name in cls.__dict__ and cls.__dict__[name] is not method:
                    raise TypeError(
                        f"Overriding savemethod '{name}' is forbidden in class '{cls.__name__}'."
                    )
