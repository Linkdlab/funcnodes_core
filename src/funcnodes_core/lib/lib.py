"""Shelf management utilities for the funcnodes node registry.

The module stores shelves in a flat structure for efficiency while exposing a
tree-based API. It also provides helpers for serializing the structure or
linking externally owned shelves via weak references.
"""

from __future__ import annotations
from typing import List, Optional, TypedDict, Dict, Type, Tuple, Sequence, Union
from funcnodes_core.node import (
    Node,
    SerializedNodeClass,
    REGISTERED_NODES,
    register_node,
)
from funcnodes_core.utils.serialization import JSONEncoder, Encdata
from dataclasses import dataclass, field
import weakref
from ..eventmanager import EventEmitterMixin, emit_after


class NodeClassNotFoundError(ValueError):
    """Raised when a requested node class cannot be found."""


class ShelfError(ValueError):
    """Base class for structured shelf errors."""


class ShelfPathError(ShelfError):
    """Raised when a shelf path is malformed or empty."""


class ShelfExistsError(ShelfError):
    """Raised when attempting to create a shelf that already exists."""


class ShelfNotFoundError(ShelfError):
    """Raised when a requested shelf path cannot be resolved."""


class ShelfTypeError(ShelfError):
    """Raised when an API receives an unexpected shelf type."""


class ShelfNameError(ShelfError):
    """Raised when shelf names or aliases are invalid."""


@dataclass
class Shelf:
    """Tree node containing nodes and optional nested subshelves."""

    name: str
    description: str = ""
    nodes: List[Type[Node]] = field(default_factory=list)
    subshelves: List[Shelf] = field(default_factory=list)
    shelf_id: Optional[str] = None
    parent_shelf: Optional[Shelf] = None

    def __post_init__(self):
        # make nodes unique
        self.nodes = list({id(node): node for node in self.nodes}.values())

        # make subshelves unique by object reference without changing the order
        self.subshelves = list(
            {id(subshelf): subshelf for subshelf in self.subshelves}.values()
        )

    @classmethod
    def from_dict(cls, data: Dict) -> Shelf:
        if isinstance(data, Shelf):
            return data
        if "name" not in data:
            raise ShelfError("name must be present")

        shelf = cls(
            nodes=data.get("nodes", []),
            subshelves=[
                cls.from_dict(subshelf) for subshelf in data.get("subshelves", [])
            ],
            name=data["name"],
            description=data.get("description", ""),
        )
        for subshelf in shelf.subshelves:
            subshelf.parent_shelf = shelf
        return shelf

    def __eq__(self, value: object) -> bool:
        if not isinstance(value, Shelf):
            return False

        if self.name != value.name:
            return False
        if self.description != value.description:
            return False

        if len(self.nodes) != len(value.nodes):
            return False

        if len(self.subshelves) != len(value.subshelves):
            return False

        for i, node in enumerate(self.nodes):
            if node != value.nodes[i]:
                return False

        for i, subshelf in enumerate(self.subshelves):
            if subshelf != value.subshelves[i]:
                return False

        return True


class SerializedShelf(TypedDict):
    nodes: List[SerializedNodeClass]
    subshelves: List[SerializedShelf]
    name: str
    description: str


class FullLibJSON(TypedDict):
    """
    FullLibJSON for a full serilization including temporary properties
    """

    shelves: List[SerializedShelf]


@dataclass
class _ShelfRecord:
    """
    Flat, GC-friendly shelf record:
      - NO strong references to Node classes; only node IDs are stored.
      - Path is maintained externally as the dictionary key.
    """

    name: str
    description: str = ""
    nodes_ref: List[str] = field(default_factory=list)  # node IDs only


def _norm_path(path_like: str | List[str]) -> Tuple[str, ...]:
    """Return a tuple path from user input, rejecting empty elements."""
    if isinstance(path_like, str):
        if not path_like:
            raise ShelfPathError("shelf path must not be empty")
        return (path_like,)
    if not path_like:
        raise ShelfPathError("shelf path must not be empty")
    return tuple(path_like)


def _unique_push(lst: List[str], value: str) -> None:
    """Append ``value`` preserving order if it is not already present."""
    if value not in lst:
        lst.append(value)


def serialize_shelf(shelf: Shelf) -> SerializedShelf:
    """Return a JSON-ready representation of ``shelf``."""
    return {
        "nodes": [node.serialize_cls() for node in shelf.nodes],
        "subshelves": [serialize_shelf(sub) for sub in shelf.subshelves],
        "name": shelf.name,
        "description": shelf.description,
    }


class Library(EventEmitterMixin):
    """Mutable registry of shelves backed by a flat dictionary.

    The library stores the path of each internal shelf as a tuple whose value is
    a ``_ShelfRecord`` containing only node IDs. Complete ``Shelf`` trees are
    materialized on demand which keeps the long-lived structure friendly to the
    garbage collector. External shelves can be mounted through weak references
    so they automatically disappear once the owner drops the reference.
    """

    def __init__(self) -> None:
        # Flat store: key is a path tuple ("Top", "Child", ...)
        self._records: Dict[Tuple[str, ...], _ShelfRecord] = {}
        self._external: weakref.WeakValueDictionary[Tuple[str, ...], Shelf] = (
            weakref.WeakValueDictionary()
        )
        super().__init__()

    def _live_external_shelves(self) -> List[Shelf]:
        """Return alive external shelves and prune dead refs."""
        alive_refs: List[weakref.ref[Shelf]] = []
        shelves: List[Shelf] = []
        for r in self._external_shelf_refs:
            s = r()
            if s is not None:
                shelves.append(s)
                alive_refs.append(r)
        if len(alive_refs) != len(self._external_shelf_refs):
            self._external_shelf_refs = alive_refs
        return shelves

    # -------- materialization helpers (private) --------

    def _ensure_path_exists(self, path: Tuple[str, ...]) -> None:
        """Create placeholder records for each prefix of ``path`` if missing."""
        if not path:
            raise ShelfPathError("shelf path must not be empty")

        # Walk from root to path, creating missing records with default description.
        for i in range(1, len(path) + 1):
            key = path[:i]
            if key not in self._records:
                self._records[key] = _ShelfRecord(
                    name=key[-1], description="", nodes_ref=[]
                )

    def _child_names(self, parent: Tuple[str, ...]) -> List[str]:
        """Return unique child names under ``parent`` (order not guaranteed)."""
        n = len(parent)
        names: List[str] = []

        # internal children
        for key in self._records.keys():
            if len(key) == n + 1 and key[:n] == parent:
                nm = key[-1]
                if nm not in names:
                    names.append(nm)

        # external children
        for key in list(self._external.keys()):
            if len(key) == n + 1 and key[:n] == parent:
                nm = key[-1]
                if nm not in names:
                    names.append(nm)

        return names

    def _build_shelf(self, path: Tuple[str, ...]) -> Shelf:
        """Rehydrate a ``Shelf`` tree rooted at ``path``."""
        rec = self._records.get(path)
        if rec is None:
            raise ShelfNotFoundError(f"shelf {'/'.join(path)} does not exist")

        # Resolve nodes lazily via REGISTERED_NODES; drop missing classes.
        nodes: List[Type[Node]] = []
        for nid in rec.nodes_ref:
            node_cls = REGISTERED_NODES.get(nid)
            if node_cls is not None:
                nodes.append(node_cls)

        # Build children: internal (recursively) + external (weak)
        subshelves: List[Shelf] = []
        for child_name in self._child_names(path):
            child_path = path + (child_name,)

            # external child?
            ext = self._external.get(child_path)
            if ext is not None:
                subshelves.append(
                    ext
                )  # do NOT set parent; avoid mutating external object
                continue

            # internal child (must exist if not external)
            if child_path in self._records:
                child = self._build_shelf(child_path)
                # set parent only for internal children we constructed
                child.parent_shelf = None  # avoid stale parent
                subshelves.append(child)
                continue

            # Shouldn't happen (name came from union of internal/external)
            # Skip silently to be defensive.

        shelf = Shelf(
            name=rec.name,
            description=rec.description,
            nodes=nodes,
            subshelves=subshelves,
        )
        # Set parent for internal children only (those we created above)
        for sub in shelf.subshelves:
            if (path + (sub.name,)) not in self._external:
                sub.parent_shelf = shelf
        return shelf

    def _top_paths(self) -> List[Tuple[str, ...]]:
        """Top-level shelf paths (length == 1)."""
        return [k for k in self._records.keys() if len(k) == 1]

    def _add_shelf_tree(self, src: Shelf, parent: Tuple[str, ...] = ()) -> None:
        """Merge/insert a Shelf tree into flat storage (node IDs only)."""
        path = parent + (src.name,)
        self._ensure_path_exists(path)
        rec = self._records[path]

        # Update description (latest wins)
        if src.description != rec.description:
            rec.description = src.description

        # Merge node IDs (no duplicates)
        for node_cls in src.nodes:
            _unique_push(rec.nodes_ref, node_cls.node_id)

        # Recurse
        for sub in src.subshelves:
            self._add_shelf_tree(sub, path)

    def _remove_subtree(self, path: Tuple[str, ...]) -> None:
        """Remove the shelf at `path` and all its descendants."""
        exists = any(k[: len(path)] == path for k in self._records.keys())
        if not exists:
            raise ShelfNotFoundError(f"shelf {'/'.join(path)} does not exist")

        for k in list(self._records.keys()):
            if k[: len(path)] == path:
                del self._records[k]

    def _register_shelf_nodes(self, shelf: Shelf) -> None:
        """Ensure all nodes reachable from ``shelf`` are registered."""
        nodes, _ = flatten_shelf(shelf)
        for node in nodes:
            if node.node_id not in REGISTERED_NODES:
                register_node(node)

    # -------- required public API --------

    @property
    def shelves(self) -> List[Shelf]:
        # Rebuild complete trees for all top-level shelves (snapshots).
        internal_shelves = [self._build_shelf(p) for p in self._top_paths()]
        external_shelves = [s for (p, s) in list(self._external.items()) if len(p) == 1]
        return internal_shelves + external_shelves

    @emit_after()
    def add_shelf(self, shelf: Shelf) -> Shelf:
        """
        Merge or insert a complete Shelf tree.
        Top-level uniqueness is by name; children uniqueness is by (parent path, name).
        Returns a materialized snapshot of the top-level shelf after merge.
        """
        if not isinstance(shelf, Shelf):
            raise ShelfTypeError("shelf must be a Shelf")
        self._add_shelf_tree(shelf, ())
        return self._build_shelf((shelf.name,))

    @emit_after()
    def remove_shelf(self, shelf: Union[Shelf, weakref.ref[Shelf]]):
        """
        Remove a top-level shelf by name (and all its descendants).
        Mirrors previous behavior where top-level shelves are keyed by name.
        """
        if isinstance(shelf, weakref.ref):
            shelf = shelf()
        if shelf is None:
            return  # shelf is already garbage-collected
        if not isinstance(shelf, Shelf):
            raise ShelfTypeError("shelf must be a Shelf or a weak reference to a Shelf")
        top = (shelf.name,)
        if top in self._records:
            self._remove_subtree(top)
            return
        if top in self._external:
            try:
                del self._external[top]
            except KeyError:
                pass
            return
        raise ShelfNotFoundError("Shelf does not exist")

    @emit_after()
    def remove_shelf_path(self, path: List[str]):
        """Remove the shelf (and its subtree) at an explicit path."""
        path_t = _norm_path(path)
        # unmount weak shelf if present (works for top-level or nested)
        if path_t in self._external:
            try:
                del self._external[path_t]
            except KeyError:
                pass
            return
        # otherwise remove internal subtree
        self._remove_subtree(path_t)

    def full_serialize(self) -> FullLibJSON:
        """Serialize the entire library into a JSON-friendly structure."""
        internals = [self._build_shelf(p) for p in self._top_paths()]
        externals = [s for (p, s) in list(self._external.items()) if len(p) == 1]
        return {"shelves": [serialize_shelf(s) for s in internals + externals]}

    def _repr_json_(self) -> FullLibJSON:
        return self.full_serialize()

    @emit_after()
    def add_nodes(
        self,
        nodes: Sequence[Type[Node]],
        shelf: str | List[str],
    ):
        """
        Register ``nodes`` under ``shelf`` creating shelves as needed.

        Only the ``node_id`` is stored to keep the records compact; resolving the
        actual class is deferred until materialization time.
        """
        path = _norm_path(shelf)
        self._ensure_path_exists(path)
        rec = self._records[path]
        # Only store IDs; do not retain class references
        for node_cls in nodes:
            _unique_push(rec.nodes_ref, node_cls.node_id)

    def add_node(self, node: Type[Node], shelf: str | List[str]):
        self.add_nodes([node], shelf)

    # Search APIs filter by CURRENTLY registered nodes: if a node ID is
    # not in REGISTERED_NODES, it is treated as absent for these queries.

    def find_nodeid(self, nodeid: str, all: bool = True) -> List[List[str]]:
        """Return shelf paths containing ``nodeid`` (restricted to registered nodes)."""
        if REGISTERED_NODES.get(nodeid) is None:
            return []
        hits: List[List[str]] = []
        # internal
        for key, rec in self._records.items():
            if nodeid in rec.nodes_ref:
                hits.append(list(key))
                if not all:
                    return hits
        # all weak mounts
        for path, shelf in list(self._external.items()):
            subpaths = deep_find_node(shelf, nodeid, all=all)
            for sp in subpaths:
                # Replace the external shelf's own root with the mount alias (path[-1])
                hits.append(list(path) + sp[1:])
                if not all:
                    return hits
        return hits

    def has_node_id(self, nodeid: str) -> bool:
        return len(self.find_nodeid(nodeid, all=False)) > 0

    def find_nodeclass(self, node: Type[Node], all: bool = True) -> List[List[str]]:
        """Convenience wrapper returning shelves that currently expose ``node``."""
        return self.find_nodeid(node.node_id, all=all)

    @emit_after()
    def remove_nodeclass(self, node: Type[Node]):
        """
        Remove ``node`` references from all shelves where the ID is present.

        Only shelves backed by internal records are mutated; weak shelves are
        expected to update themselves when their owner changes.
        """
        paths = self.find_nodeclass(node)
        nodeid = node.node_id
        for path in paths:
            key = tuple(path)
            rec = self._records.get(key)
            if rec is None:
                continue
            # Remove all occurrences of this ID in-place
            rec.nodes_ref[:] = [nid for nid in rec.nodes_ref if nid != nodeid]

    def remove_nodeclasses(self, nodes: Sequence[Type[Node]]):
        for node in nodes:
            self.remove_nodeclass(node)

    def get_node_by_id(self, nodeid: str) -> Type[Node]:
        """
        Return the registered ``Node`` class if it is visible in any shelf.

        The lookup mirrors previous semantics: the node must both be registered
        and referenced at least once; otherwise ``NodeClassNotFoundError`` is
        raised to signal that the entry is no longer usable.
        """
        # Must appear in at least one shelf (as a currently registered node)
        if not self.has_node_id(nodeid):
            raise NodeClassNotFoundError(f"Node with id '{nodeid}' not found")
        node_cls = REGISTERED_NODES.get(nodeid)
        if node_cls is None:
            # Not registered anymore — treat as not found.
            raise NodeClassNotFoundError(f"Node with id '{nodeid}' not found")
        return node_cls

    @emit_after()
    def add_external_shelf(
        self,
        shelf: Union[Shelf, weakref.ref[Shelf]],
        mount: Optional[str] = None,
    ):
        """
        Register an externally owned shelf as a top-level entry.

        The shelf is stored through a weak reference so it automatically
        disappears when its owner releases it. ``mount`` may rename the shelf at
        the root level but it must be a *single* shelf name; nested mounts are
        intentionally rejected to avoid ambiguity with ``add_subshelf_weak``.
        """

        if isinstance(shelf, weakref.ref):
            shelf = shelf()
        if shelf is None:
            return  # shelf is already garbage-collected
        if not isinstance(shelf, Shelf):
            raise ShelfTypeError("shelf must be a Shelf or a weak reference to a Shelf")

        name = mount if mount is not None else shelf.name
        if not isinstance(name, str) or not name:
            raise ShelfPathError(
                "mount must be a single shelf name string; use add_subshelf_weak(...) "
                "to mount under a parent path"
            )

        path = (name,)

        if path in self._external or path in self._records:
            raise ShelfExistsError(f"top-level shelf '{path[0]}' already exists")

        self._register_shelf_nodes(shelf)
        self._external[path] = shelf
        return shelf

    @emit_after()
    def add_subshelf_weak(
        self,
        shelf: Union[Shelf, weakref.ref[Shelf]],
        parent: str | List[str],
        alias: Optional[str] = None,
    ):
        """
        Mount an external shelf underneath an existing *internal* shelf.

        The child name will be ``alias`` if provided, else ``shelf.name``.
        The full mount path is ``tuple(parent) + (child_name,)``.

        Notes:
        - ``parent`` must exist as an internal shelf (``_records`` entry)
        - The final path must not collide with any internal or weak shelf
        """
        if isinstance(shelf, weakref.ref):
            shelf = shelf()
        if shelf is None:
            return  # shelf is already garbage-collected
        if not isinstance(shelf, Shelf):
            raise ShelfTypeError("shelf must be a Shelf or a weak reference to a Shelf")

        parent_t = _norm_path(parent)
        if parent_t not in self._records:
            raise ShelfNotFoundError(
                "parent path must refer to an existing internal shelf"
            )

        child_name = alias if alias is not None else shelf.name
        if not child_name:
            raise ShelfNameError("alias/name must be non-empty")

        path = parent_t + (child_name,)
        if path in self._records or path in self._external:
            raise ShelfExistsError(
                f"child '{child_name}' already exists under {'/'.join(parent_t)}"
            )

        self._register_shelf_nodes(shelf)
        self._external[path] = shelf
        return shelf


def check_shelf(shelf: Shelf, parent_id: Optional[str] = None) -> Shelf:
    """Normalize dict-based shelves and validate their contents."""
    if isinstance(shelf, dict):
        if "nodes" not in shelf:
            shelf["nodes"] = []
        if "subshelves" not in shelf:
            shelf["subshelves"] = []
        if "name" not in shelf:
            shelf["name"] = "Unnamed Shelf"
        if "description" not in shelf:
            shelf["description"] = ""

        shelf = Shelf.from_dict(shelf)

    for node in shelf.nodes:
        if not issubclass(node, Node):
            raise ShelfTypeError(f"Node {node} is not a subclass of Node")

    for subshelf in shelf.subshelves:
        subshelf.parent_shelf = shelf

    if shelf.shelf_id is None:
        if parent_id is not None:
            shelf.shelf_id = f"{parent_id}_{shelf.name}"
        else:
            shelf.shelf_id = f"{shelf.name}_{shelf.description}"

    shelf.subshelves = [
        check_shelf(subshelf, parent_id=shelf.shelf_id) for subshelf in shelf.subshelves
    ]

    return shelf


# --- helper functions ---


def flatten_shelves(shelves: List[Shelf]) -> Tuple[List[Type[Node]], List[Shelf]]:
    """Flatten a list of shelves into parallel node and shelf lists."""
    nodes: List[Type[Node]] = []
    flat_shelves: List[Shelf] = []
    for shelf in shelves:
        subnodes, subshelves = flatten_shelf(shelf)
        nodes.extend(subnodes)
        flat_shelves.extend(subshelves)
    return nodes, flat_shelves


def flatten_shelf(shelf: Shelf) -> Tuple[List[Type[Node]], List[Shelf]]:
    """Return a flattened view (nodes, shelves) for ``shelf`` and children."""
    nodes: List[Type[Node]] = list(shelf.nodes)
    shelves: List[Shelf] = [shelf]
    for subshelf in shelf.subshelves:
        subnodes, subshelves = flatten_shelf(subshelf)
        nodes.extend(subnodes)
        shelves.extend(subshelves)
    return nodes, shelves


def deep_find_node(shelf: Shelf, nodeid: str, all=True) -> List[List[str]]:
    """Return all relative paths to ``nodeid`` inside ``shelf``."""
    paths: List[List[str]] = []
    try:
        get_node_in_shelf(shelf, nodeid)
        paths.append([shelf.name])
        if not all:
            return paths
    except NodeClassNotFoundError:
        pass

    for subshelf in shelf.subshelves:
        subpaths = deep_find_node(subshelf, nodeid, all=all)
        for p in subpaths:
            p.insert(0, shelf.name)
        if subpaths:
            paths.extend(subpaths)
            if not all:
                return paths[:1]
    return paths


def get_node_in_shelf(shelf: Shelf, nodeid: str) -> Tuple[int, Type[Node]]:
    """Return ``(index, node)`` for ``nodeid`` or raise ``NodeClassNotFoundError``."""
    for i, node in enumerate(shelf.nodes):
        if node.node_id == nodeid:
            return i, node
    raise NodeClassNotFoundError(f"Node with id {nodeid} not found")


# --- JSON serialization ---
def libencode(obj, preview=False):
    """JSON-encoder hook that understands ``Library`` instances."""
    if isinstance(obj, Library):
        return Encdata(data=obj.full_serialize(), handeled=True, done=True)
    return Encdata(data=obj, handeled=False)


JSONEncoder.add_encoder(libencode)
