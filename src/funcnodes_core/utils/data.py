from typing import Any, MutableMapping, Dict, TypeVar, Optional
from copy import deepcopy
import warnings

from .deprecations import SpellingDeprecationWarning

T = TypeVar("T", bound=MutableMapping[Any, Any])


def deep_fill_dict(
    target_dict: T,
    source_dict: T,
    overwrite_existing: bool = False,
    inplace: bool = True,
    merge_lists: bool = False,
    unify_lists: bool = False,
    unfify_lists: Optional[bool] = None,
) -> T:
    """
    deep_fill_dict
    A target dict is filled with the values of a source dict recursively
    if the key does not exist in the target dict

    Parameters
    ----------
    target_dict : Dict[Any, Any]
        The dict to be filled
    source_dict : dict
        The dict to be used as a source
    overwrite_existing : bool, optional
        If true, existing values in the target dict will be overwritten, by default False
    inplace : bool, optional
        If true, the target dict is modified in place, by default True

    Returns
    -------
    Dict[Any, Any]
        The filled dict
    """

    if unfify_lists is not None:
        warnings.warn(
            "unfify_lists is deprecated, use unify_lists instead.",
            SpellingDeprecationWarning,
        )
        unify_lists = unfify_lists

    if not inplace:
        target_dict = deepcopy(target_dict)

    for key, value in source_dict.items():
        if isinstance(value, dict):
            # get node or create one
            if key not in target_dict:
                target_dict[key] = dict()
            node = target_dict[key]
            if isinstance(node, dict):
                deep_fill_dict(
                    target_dict=node,
                    source_dict=value,
                    overwrite_existing=overwrite_existing,
                    inplace=True,  # always inplace for nested dicts
                )
                continue
        if overwrite_existing or (key not in target_dict):
            if (
                merge_lists
                and isinstance(value, list)
                and isinstance(target_dict.get(key), list)
            ):
                target_dict[key].extend(value)
                if unify_lists:
                    target_dict[key] = list(set(target_dict[key]))
            else:
                target_dict[key] = value

    return target_dict


def deep_update_dict(target_dict: T, source_dict: T, inplace: bool = True) -> T:
    return deep_fill_dict(
        target_dict=target_dict,
        source_dict=source_dict,
        overwrite_existing=True,
        inplace=inplace,
        unify_lists=False,
        merge_lists=False,
    )


def deep_remove_dict_on_equal(
    target_dict: Dict[Any, Any], remove_dict: Dict[Any, Any], inplace: bool = True
) -> Dict[Any, Any]:
    """
    deep_remove_dict_on_equal
    All keys in a dict that have the same value as the value of the key
    in theremove dict are removed

    Parameters
    ----------
    target_dict : dict
        The dict to be cleaned
    remove_dict : dict
        The dict to be used as a source
    inplace : bool, optional
        If true, the target dict is modified in place, by default True

    Returns
    -------
    Dict[Any, Any]
        The cleaned dict
    """
    if not inplace:
        target_dict = target_dict.copy()

    for key, value in remove_dict.items():
        if key in target_dict:
            if isinstance(value, dict):
                if isinstance(target_dict[key], dict):
                    node: dict = target_dict[key]
                    deep_remove_dict_on_equal(node, value, inplace=inplace)
                    continue
            if target_dict[key] == value:
                del target_dict[key]

    return target_dict
