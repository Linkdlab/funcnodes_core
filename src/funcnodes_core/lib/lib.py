from __future__ import annotations
from typing import List, Optional, TypedDict, Dict, Type, Tuple, Sequence
from funcnodes_core.node import Node, SerializedNodeClass, REGISTERED_NODES
from funcnodes_core.utils.serialization import JSONEncoder, Encdata
from dataclasses import dataclass, field
from ..eventmanager import EventEmitterMixin, emit_after


class NodeClassNotFoundError(ValueError):
    pass


class ShelfError(Exception):
    pass


@dataclass
class Shelf:
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
    if isinstance(path_like, str):
        if not path_like:
            raise ValueError("shelf path must not be empty")
        return (path_like,)
    if not path_like:
        raise ValueError("shelf path must not be empty")
    return tuple(path_like)


def _unique_push(lst: List[str], value: str) -> None:
    """Append only if value not present; preserves order."""
    if value not in lst:
        lst.append(value)


def serialize_shelf(shelf: Shelf) -> SerializedShelf:
    return {
        "nodes": [node.serialize_cls() for node in shelf.nodes],
        "subshelves": [serialize_shelf(sub) for sub in shelf.subshelves],
        "name": shelf.name,
        "description": shelf.description,
    }


class Library(EventEmitterMixin):
    """
    Flat shelf store keyed by path tuples. Never stores Node classes; only IDs.
    Reconstructs full `Shelf` trees on demand.
    """

    def __init__(self) -> None:
        # Flat store: key is a path tuple ("Top", "Child", ...)
        self._records: Dict[Tuple[str, ...], _ShelfRecord] = {}
        super().__init__()

    # -------- materialization helpers (private) --------

    def _ensure_path_exists(self, path: Tuple[str, ...]) -> None:
        """Create missing _ShelfRecord entries along the path with empty descriptions."""
        if not path:
            raise ValueError("shelf path must not be empty")

        # Walk from root to path, creating missing records with default description.
        for i in range(1, len(path) + 1):
            key = path[:i]
            if key not in self._records:
                self._records[key] = _ShelfRecord(
                    name=key[-1], description="", nodes_ref=[]
                )

    def _child_names(self, parent: Tuple[str, ...]) -> List[str]:
        """Return direct child names under `parent` (order not guaranteed)."""
        n = len(parent)
        seen: List[str] = []
        for key in self._records.keys():
            if len(key) == n + 1 and key[:n] == parent:
                name = key[-1]
                if name not in seen:
                    seen.append(name)
        return seen

    def _build_shelf(self, path: Tuple[str, ...]) -> Shelf:
        """Reconstruct a Shelf (and its subtree) from flat records and REGISTERED_NODES."""
        rec = self._records.get(path)
        if rec is None:
            raise ValueError(f"shelf {'/'.join(path)} does not exist")

        # Resolve nodes lazily via REGISTERED_NODES; drop missing classes.
        nodes: List[Type[Node]] = []
        for nid in rec.nodes_ref:
            node_cls = REGISTERED_NODES.get(nid)
            if node_cls is not None:
                nodes.append(node_cls)

        # Build children
        subshelves: List[Shelf] = []
        for child_name in self._child_names(path):
            child_path = path + (child_name,)
            subshelves.append(self._build_shelf(child_path))

        shelf = Shelf(
            name=rec.name,
            description=rec.description,
            nodes=nodes,
            subshelves=subshelves,
        )
        # fix parent pointers
        for sub in shelf.subshelves:
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
            raise ValueError(f"shelf {'/'.join(path)} does not exist")

        for k in list(self._records.keys()):
            if k[: len(path)] == path:
                del self._records[k]

    # -------- required public API --------

    @property
    def shelves(self) -> List[Shelf]:
        # Rebuild complete trees for all top-level shelves (snapshots).
        return [self._build_shelf(p) for p in self._top_paths()]

    @emit_after()
    def add_shelf(self, shelf: Shelf):
        """
        Merge or insert a complete Shelf tree.
        Top-level uniqueness is by name; children uniqueness is by (parent path, name).
        Returns a materialized snapshot of the top-level shelf after merge.
        """
        if not isinstance(shelf, Shelf):
            raise ValueError("shelf must be a Shelf")
        self._add_shelf_tree(shelf, ())
        return self._build_shelf((shelf.name,))

    @emit_after()
    def remove_shelf(self, shelf: Shelf):
        """
        Remove a top-level shelf by name (and all its descendants).
        Mirrors previous behavior where top-level shelves are keyed by name.
        """
        if not isinstance(shelf, Shelf):
            raise ValueError("shelf must be a Shelf")
        self._remove_subtree((shelf.name,))

    @emit_after()
    def remove_shelf_path(self, path: List[str]):
        """Remove the shelf (and its subtree) at an explicit path."""
        path_t = _norm_path(path)
        self._remove_subtree(path_t)

    def full_serialize(self) -> FullLibJSON:
        """Serialize the entire library into a JSON-friendly structure."""
        top = [self._build_shelf(p) for p in self._top_paths()]
        return {"shelves": [serialize_shelf(s) for s in top]}

    def _repr_json_(self) -> FullLibJSON:
        return self.full_serialize()

    @emit_after()
    def add_nodes(
        self,
        nodes: Sequence[Type[Node]],
        shelf: str | List[str],
    ):
        """
        Add (or upsert) nodes (by ID) under the given path.
        Creates missing shelves with empty descriptions.
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
        if REGISTERED_NODES.get(nodeid) is None:
            return []
        hits: List[List[str]] = []
        for key, rec in self._records.items():
            if nodeid in rec.nodes_ref:
                hits.append(list(key))
                if not all:
                    break
        return hits

    def has_node_id(self, nodeid: str) -> bool:
        return len(self.find_nodeid(nodeid, all=False)) > 0

    def find_nodeclass(self, node: Type[Node], all: bool = True) -> List[List[str]]:
        return self.find_nodeid(node.node_id, all=all)

    @emit_after()
    def remove_nodeclass(self, node: Type[Node]):
        """
        Remove a node (by ID) from the shelves where it is currently visible
        (i.e., only from shelves where the node is registered).
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
        Return the Node class if it exists in at least one shelf and is registered.
        Mirror previous semantics: not present anywhere => raise.
        """
        # Must appear in at least one shelf (as a currently registered node)
        if not self.has_node_id(nodeid):
            raise NodeClassNotFoundError(f"Node with id '{nodeid}' not found")
        node_cls = REGISTERED_NODES.get(nodeid)
        if node_cls is None:
            # Not registered anymore — treat as not found.
            raise NodeClassNotFoundError(f"Node with id '{nodeid}' not found")
        return node_cls


def check_shelf(shelf: Shelf, parent_id: Optional[str] = None) -> Shelf:
    # make shure required properties are present
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
            raise ValueError(f"Node {node} is not a subclass of Node")

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
    nodes: List[Type[Node]] = []
    flat_shelves: List[Shelf] = []
    for shelf in shelves:
        subnodes, subshelves = flatten_shelf(shelf)
        nodes.extend(subnodes)
        flat_shelves.extend(subshelves)
    return nodes, flat_shelves


def flatten_shelf(shelf: Shelf) -> Tuple[List[Type[Node]], List[Shelf]]:
    nodes: List[Type[Node]] = list(shelf.nodes)
    shelves: List[Shelf] = [shelf]
    for subshelf in shelf.subshelves:
        subnodes, subshelves = flatten_shelf(subshelf)
        nodes.extend(subnodes)
        shelves.extend(subshelves)
    return nodes, shelves


def deep_find_node(shelf: Shelf, nodeid: str, all=True) -> List[List[str]]:
    paths = []
    try:
        i, node = get_node_in_shelf(shelf, nodeid)
        paths.append([shelf.name])
        if not all:
            return paths
    except ValueError:
        pass

    for subshelf in shelf.subshelves:
        path = deep_find_node(subshelf, nodeid)
        if len(path) > 0:
            for p in path:
                p.insert(0, shelf.name)
            paths.extend(path)
            if not all:
                break
    return paths


def get_node_in_shelf(shelf: Shelf, nodeid: str) -> Tuple[int, Type[Node]]:
    """
    Returns the index and the node with the given id
    """
    for i, node in enumerate(shelf.nodes):
        if node.node_id == nodeid:
            return i, node
    raise NodeClassNotFoundError(f"Node with id {nodeid} not found")


# --- JSON serialization ---
def libencode(obj, preview=False):
    if isinstance(obj, Library):
        return Encdata(data=obj.full_serialize(), handeled=True, done=True)
    return Encdata(data=obj, handeled=False)


JSONEncoder.add_encoder(libencode)
