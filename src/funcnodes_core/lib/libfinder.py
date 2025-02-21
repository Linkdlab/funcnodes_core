import importlib
from typing import Tuple, TypedDict, Union, List, Optional
from .lib import Shelf
from .libparser import module_to_shelf
import os
import sys
import funcnodes_core as fn
import argparse
from pathlib import Path


class BaseShelfDict(TypedDict):
    """
    TypedDict for a base shelf dictionary.

    Attributes:
      module (str): The name of the module.
    """

    module: str


class PackageShelfDict(BaseShelfDict):
    """
    TypedDict for a package shelf dictionary.

    Attributes:
      package (str): The name of the package.
      version (str): The version of the package.
      module (str): The name of the module.
    """

    package: str
    version: str


class PathShelfDict(BaseShelfDict):
    """
    TypedDict for a path shelf dictionary.

    Attributes:
      path (str): The path to the module.
      module (str): The name of the module.
    """

    path: str
    skip_requirements: bool


ShelfDict = Union[BaseShelfDict, PackageShelfDict, PathShelfDict]


def find_shelf_from_module(
    mod: Union[str, BaseShelfDict],
    args: Optional[List[str]] = None,
) -> Union[Tuple[Shelf, BaseShelfDict], None]:
    """
    Finds a shelf from a module.

    Args:
      mod (Union[str, BaseShelfDict]): The module to find the shelf for.

    Returns:
      Union[Tuple[Shelf, BaseShelfDict], None]: The shelf and the shelf dictionary if found, None otherwise.
    """

    try:
        strmod: str
        if isinstance(mod, dict):
            dat = mod
            strmod = mod["module"]
        else:
            strmod = mod
            dat = BaseShelfDict(module=strmod)

        # submodules = strmod.split(".")

        module = importlib.import_module(
            strmod.replace("-", "_")
        )  # replace - with _ to avoid import errors
        # reload module to get the latest version
        try:
            importlib.reload(module)
        except Exception:
            pass
        # for submod in submodules[1:]:
        #     mod = getattr(mod, submod)

        return module_to_shelf(module), dat

    except (ModuleNotFoundError, KeyError) as e:
        fn.FUNCNODES_LOGGER.exception(e)
        return None


def find_shelf_from_package(
    pgk: Union[str, PackageShelfDict],
    update: bool = False,
    args: Optional[List[str]] = None,
) -> Union[Tuple[Shelf, PackageShelfDict], None]:
    """
    Finds a shelf from a package.

    Args:
      pgk (Union[str, PackageShelfDict]): The package to find the shelf for.

    Returns:
      Union[Tuple[Shelf, PackageShelfDict], None]: The shelf and the shelf dictionary if found, None otherwise.
    """
    data = {}
    if isinstance(pgk, str):
        # remove possible version specifier
        stripped_src = pgk.split("=", 1)[0]
        stripped_src = pgk.split(">", 1)[0]
        stripped_src = pgk.split("<", 1)[0]
        stripped_src = pgk.split("~", 1)[0]
        stripped_src = pgk.split("!", 1)[0]
        stripped_src = pgk.split("@", 1)[0]

        data["package"] = stripped_src
        if "/" in pgk:
            data["module"] = pgk.rsplit("/", 1)[-1]
            basesrc = pgk.rsplit("/", 1)[0]
        else:
            data["module"] = data["package"]
            basesrc = pgk
        data["version"] = basesrc.replace(data["package"], "")
        data = PackageShelfDict(**data)
        call = f"{sys.executable} -m pip install {data['package']}{data['version']} -q"
        if update:
            call += " --upgrade"
        try:
            os.system(call)
            if update:  # if we updated the package we might need to call it again if the update is new
                os.system(call)
        except Exception as e:
            fn.FUNCNODES_LOGGER.exception(e)
            return None
    else:
        data = pgk

    ndata = find_shelf_from_module(data)
    if ndata is not None:
        ndata[1].update(data)
        return ndata


def find_shelf_from_path(
    path: Union[str, PathShelfDict],
    args: Optional[List[str]] = None,
) -> Union[Tuple[Shelf, PathShelfDict], None]:
    """
    Finds a shelf from a path.

    Args:
      path (Union[str, PathShelfDict]): The path to find the shelf for.

    Returns:
      Union[Tuple[Shelf, PathShelfDict], None]: The shelf and the shelf dictionary if found, None otherwise.
    """

    if isinstance(path, str):
        parser = argparse.ArgumentParser(description="Parse a path for Funcnodes.")
        parser.add_argument(
            "path",
            type=str,
            help="The path to parse.",
        )
        parser.add_argument(
            "--skip_requirements",
            action="store_true",
            help="Skip installing requirements",
            default=False,
        )
        if args is None:
            args = []

        args = [Path(path).as_posix()] + args
        args = parser.parse_args(args=args)

        _path = Path(args.path).absolute()
        data = PathShelfDict(
            path=_path.parent.as_posix(),
            module=_path.stem,
            skip_requirements=args.skip_requirements,
        )
    else:
        data = path

    data_path = Path(data["path"]).absolute()

    if not data_path.exists():
        raise FileNotFoundError(f"file {data_path} not found")

    # check if path in sys.path
    if str(data_path) not in sys.path:
        sys.path.insert(0, str(data_path))

    # install requirements
    if not data.get("skip_requirements", False):
        if (data_path / "pyproject.toml").exists():
            fn.FUNCNODES_LOGGER.debug(
                f"pyproject.toml found in {data_path}, generating requirements.txt"
            )
            tomlfile = data_path / "pyproject.toml"

            # TODO: check this, is it really neeed anymore
            import tomllib

            with open(tomlfile, "r") as f:
                content = tomllib.load(f)
            parsed = {}
            poetry_deps = (
                content.get("tool", {}).get("poetry", {}).get("dependencies", {})
            )
            for package, info in poetry_deps.items():
                if package == "python":  # ignore python version
                    continue
                if (
                    isinstance(info, str)
                    and info.startswith("{")
                    and info.endswith("}")
                ):
                    info = tomllib.loads(info)
                    if "extras" in info:
                        extras = ",".join(info["extras"])
                        parsed[f"{package}[{extras}]"] = info["version"].replace(
                            "^=", ">="
                        )
                    elif "version" in info:
                        parsed[package] = (
                            info["version"].strip("^=").replace("^=", ">=")
                        )
                    elif "path" in info:
                        parsed[info["path"]] = ""
                else:
                    parsed[package] = info.replace("^=", ">=")

            pep_deps = content.get("project", {}).get("dependencies", [])
            for package in pep_deps:
                parsed[package] = ""

            with open(data_path / "requirements.txt", "w+") as f:
                for package, version in parsed.items():
                    if version:
                        if version[0] not in "=<>!~":
                            version = f"=={version}"
                        f.write(f"{package}{version}\n")
                    else:
                        f.write(f"{package}\n")

        if "requirements.txt" in os.listdir(data["path"]):
            fn.FUNCNODES_LOGGER.debug(
                f"requirements.txt found in {data['path']}, installing requirements"
            )
            # install pip requirements
            # TODO: installing schould be done via asynctoolkit???
            os.system(
                f"{sys.executable} -m pip install -r {os.path.join(data['path'], 'requirements.txt')}"
            )

    ndata = find_shelf_from_module(data)
    if ndata is not None:
        ndata[1].update(data)
        return ndata


def find_shelf(src: Union[ShelfDict, str]) -> Tuple[Shelf, ShelfDict] | None:
    """
    Finds a shelf from a shelf dictionary or a string.

    Args:
      src (Union[ShelfDict, str]): The shelf dictionary or string to find the shelf for.

    Returns:
      Tuple[Shelf, ShelfDict] | None: The shelf and the shelf dictionary if found, None otherwise.
    """
    if isinstance(src, dict):
        if "path" in src:
            dat = find_shelf_from_path(src)
            if dat is not None:
                dat[1].update(src)
            return dat

        if "module" in src:
            dat = find_shelf_from_module(src)

            if dat is not None:
                dat[1].update(src)
                return dat

        if "package" in src:
            dat = find_shelf_from_package(src)
            if dat is not None:
                dat[1].update(src)
                return dat

        return None

    # check if identifier is a python module e.g. "funcnodes.lib"
    fn.FUNCNODES_LOGGER.debug(f"trying to import {src}")

    args = src.split(" ")
    src = args.pop(0)

    if src.startswith("pip://"):
        src = src[6:]
        return find_shelf_from_package(src, update=True, args=args)

    # check if file path:
    if src.startswith("file://"):
        # unifiy path between windows and linux
        src = src[7:]
        return find_shelf_from_path(src, args=args)

    # try to get via pip
    dat = find_shelf_from_module(src, args=args)
    return dat
