from __future__ import annotations
from typing import List, Optional, TypedDict, Dict, Type, Tuple, Set, Sequence
from funcnodes_core.node import Node, SerializedNodeClass, REGISTERED_NODES
from funcnodes_core.utils.serialization import JSONEncoder, Encdata
from dataclasses import dataclass, field
from weakref import WeakValueDictionary
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

    def add_node(self, node: Type[Node]):
        self.nodes.append(node)
        # make nodes unique
        self.nodes = list({id(node): node for node in self.nodes}.values())

    def add_subshelf(self, shelf: Shelf):
        shelf.parent_shelf = self
        self.subshelves.append(shelf)
        # make subshelves unique by object reference without changing the order
        self.subshelves = list(
            {id(subshelf): subshelf for subshelf in self.subshelves}.values()
        )


class ShelfReferenceLost(ReferenceError):
    pass


@dataclass
class _InnerShelf:
    nodes_ref: List[str]
    inner_subshelves: List[_InnerShelf]
    name: str
    description: str
    shelf_id: Optional[str] = None

    @property
    def nodes(self) -> List[Type[Node]]:
        if self.shelf_id is not None:
            return self.to_shelf().nodes
        return [
            node
            for node in [REGISTERED_NODES.get(nodeid) for nodeid in self.nodes_ref]
            if node is not None
        ]

    @property
    def subshelves(self) -> List[Shelf]:
        if self.shelf_id is not None:
            return self.to_shelf().subshelves
        return [subshelf.to_shelf() for subshelf in self.inner_subshelves]
        #     return self.shelf().subshelves
        # return [subshelf.to_shelf() for subshelf in self.inner_subshelves]

    @classmethod
    def from_shelf(cls, shelf: Shelf) -> _InnerShelf:
        if not isinstance(shelf, Shelf):
            raise ValueError("shelf must be of type Shelf")
        check_shelf(shelf)
        return cls(
            nodes_ref=[node.node_id for node in shelf.nodes],
            inner_subshelves=[
                cls.from_shelf(subshelf) for subshelf in shelf.subshelves
            ],
            name=shelf.name,
            description=shelf.description,
            shelf_id=shelf.shelf_id,
        )

    def _check_shelf(self):
        if self.shelf_id is not None:
            if SHELFE_REGISTRY.get(self.shelf_id) is None:
                raise ShelfReferenceLost(
                    "Shelf reference is lost\n"
                    "This could happen if the shelf is not permanently stored e.g. if its added to the library "
                    "as a dictionary and the returned Shelf object is not referenced"
                )

    def to_shelf(self) -> Shelf:
        self._check_shelf()
        if self.shelf_id is not None:
            return SHELFE_REGISTRY.get(self.shelf_id)
        return Shelf(
            nodes=self.nodes,
            subshelves=self.subshelves,
            name=self.name,
            description=self.description,
        )

        # if self.shelf is not None:
        #     return SHELFE_REGISTRY.get(self.shelf)()

    def add_node(self, node: Type[Node]):
        self.nodes_ref.append(node.node_id)

    def add_subshelf(self, shelf: Shelf):
        self._check_shelf()
        self.inner_subshelves.append(_InnerShelf.from_shelf(shelf))

    def update(self, shelf: Shelf):
        for node in shelf.nodes:
            if node not in self.nodes:
                self.add_node(node)

        subshelves = {subshelf.name: subshelf for subshelf in self.inner_subshelves}
        for subshelf in shelf.subshelves:
            if subshelf.name in subshelves:
                subshelves[subshelf.name].update(subshelf)
            else:
                self.add_subshelf(subshelf)


class SerializedShelf(TypedDict):
    nodes: List[SerializedNodeClass]
    subshelves: List[SerializedShelf]
    name: str
    description: str


def serialize_shelfe(shelf: Shelf) -> SerializedShelf:
    """
    Serializes a shelf object into a dictionary.
    """
    return {
        "nodes": [
            node.serialize_cls() for node in shelf.nodes
        ],  # unique nodes, necessary since somtimes nodes are added multiple times if they have aliases
        "subshelves": [serialize_shelfe(shelf) for shelf in shelf.subshelves],
        "name": shelf.name,
        "description": shelf.description,
    }


def get_node_in_shelf(shelf: Shelf, nodeid: str) -> Tuple[int, Type[Node]]:
    """
    Returns the index and the node with the given id
    """
    for i, node in enumerate(shelf.nodes):
        if node.node_id == nodeid:
            return i, node
    raise NodeClassNotFoundError(f"Node with id {nodeid} not found")


def update_nodes_in_shelf(shelf: Shelf, nodes: Sequence[Type[Node]]):
    """
    Adds nodes to a shelf
    """
    for node in nodes:
        try:
            i, _ = get_node_in_shelf(shelf, node.node_id)
            shelf.nodes[i] = node
        except NodeClassNotFoundError:
            shelf.add_node(node)


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


def flatten_shelf(shelf: Shelf) -> Tuple[List[Type[Node]], List[Shelf]]:
    nodes: List[Type[Node]] = list(shelf.nodes)
    shelves: List[Shelf] = [shelf]
    for subshelf in shelf.subshelves:
        subnodes, subshelves = flatten_shelf(subshelf)
        nodes.extend(subnodes)
        shelves.extend(subshelves)
    return nodes, shelves


def flatten_shelves(shelves: List[Shelf]) -> Tuple[List[Type[Node]], List[Shelf]]:
    nodes: List[Type[Node]] = []
    flat_shelves: List[Shelf] = []
    for shelf in shelves:
        subnodes, subshelves = flatten_shelf(shelf)
        nodes.extend(subnodes)
        flat_shelves.extend(subshelves)
    return nodes, flat_shelves


SHELFE_REGISTRY = WeakValueDictionary()


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

    # if shelf.shelf_id in SHELFE_REGISTRY and not ALLOW_SHELFE_OVERWRITE:
    #     if shelf != SHELFE_REGISTRY[shelf.shelf_id]:
    #         raise ValueError("Shelf with same id already exists")

    SHELFE_REGISTRY[shelf.shelf_id] = shelf

    return shelf


class Library(EventEmitterMixin):
    def __init__(self) -> None:
        self._shelves: List[_InnerShelf] = []
        self._dependencies: Dict[str, Set[str]] = {
            "modules": set(),
        }
        super().__init__()

    @property
    def shelves(self) -> List[Shelf]:
        return [shelf.to_shelf() for shelf in self._shelves]

    def add_dependency(self, module: str):
        self._dependencies["modules"].add(module)

    def get_dependencies(self) -> Dict[str, List[str]]:
        return {k: list(v) for k, v in self._dependencies.items()}

    @emit_after()
    def add_shelf(self, shelf: Shelf):
        shelf = check_shelf(shelf)
        shelf_dict = {s.name: s for s in self._shelves}
        if shelf.name in shelf_dict:
            shelf_dict[shelf.name].update(shelf)
            return shelf_dict[shelf.name].to_shelf()
        else:
            self._shelves.append(_InnerShelf.from_shelf(shelf))
            return shelf

    @emit_after()
    def remove_shelf(self, shelf: Shelf):
        for i, _shelf in enumerate(self._shelves):
            if _shelf.to_shelf() == shelf:
                self._shelves.pop(i)
                return
        raise ValueError("Shelf does not exist")

    @emit_after()
    def remove_shelf_path(self, path: List[str]):
        subshelfes = self._shelves
        current_shelf = None
        for _shelf in path:
            for i, subshelf in enumerate(subshelfes):
                if subshelf.name == _shelf:
                    parent_shelf = current_shelf
                    current_shelf = subshelf
                    break
            if current_shelf is None:
                raise ValueError(f"shelf {_shelf} does not exist")
            subshelfes = current_shelf.inner_subshelves

        if parent_shelf is None:
            self._shelves.remove(current_shelf)
        else:
            parent_shelf.inner_subshelves.remove(current_shelf)

    def _add_shelf_recursively(self, path: List[str]):
        subshelfes = self._shelves
        current_shelf = None
        for _shelf in path:
            if _shelf not in [subshelfes.name for subshelfes in subshelfes]:
                current_shelf = _InnerShelf(
                    nodes_ref=[], inner_subshelves=[], name=_shelf, description=""
                )
                subshelfes.append(current_shelf)
            else:
                for subshelf in subshelfes:
                    if subshelf.name == _shelf:
                        current_shelf = subshelf
                        break
            if current_shelf is None:
                raise ValueError("shelf must not be empty")
            subshelfes = current_shelf.inner_subshelves
        if current_shelf is None:
            raise ValueError("shelf must not be empty")
        return current_shelf

    def get_shelf(self, name: str) -> Shelf:
        for shelf in self._shelves:
            if shelf.name == name:
                return shelf.to_shelf()
        raise ValueError(f"Shelf with name {name} not found")

    def full_serialize(self) -> FullLibJSON:
        return {"shelves": [serialize_shelfe(shelf) for shelf in self.shelves]}

    def _repr_json_(self) -> FullLibJSON:
        return self.full_serialize()

    @emit_after()
    def add_nodes(
        self,
        nodes: Sequence[Type[Node]],
        shelf: str | List[str],
    ):
        if isinstance(shelf, str):
            shelf = [shelf]

        if len(shelf) == 0:
            raise ValueError("shelf must not be empty")

        current_shelf = self._add_shelf_recursively(shelf)
        update_nodes_in_shelf(current_shelf, nodes)

    def add_node(self, node: Type[Node], shelf: str | List[str]):
        self.add_nodes([node], shelf)

    def get_shelf_from_path(self, path: List[str]) -> Shelf:
        subshelfes = self._shelves
        current_shelf = None
        for _shelf in path:
            new_subshelfes = None
            for subshelf in subshelfes:
                if subshelf.name == _shelf:
                    new_subshelfes = subshelf.inner_subshelves
                    current_shelf = subshelf
                    break
            if new_subshelfes is None:
                raise ValueError(f"shelf {_shelf} does not exist")
            subshelfes = new_subshelfes
        if current_shelf is None:
            raise ValueError("shelf must not be empty")
        return current_shelf.to_shelf()

    def find_nodeid(self, nodeid: str, all=True) -> List[List[str]]:
        paths = []
        for shelf in self.shelves:
            path = deep_find_node(shelf, nodeid, all=all)
            if len(path) > 0:
                paths.extend(path)
                if not all:
                    break
        return paths

    def has_node_id(self, nodeid: str) -> bool:
        return len(self.find_nodeid(nodeid, all=False)) > 0

    def find_nodeclass(self, node: Type[Node], all=True) -> List[List[str]]:
        return self.find_nodeid(node.node_id, all=all)

    @emit_after()
    def remove_nodeclass(self, node: Type[Node]):
        paths = self.find_nodeclass(node)
        for path in paths:
            shelf = self.get_shelf_from_path(path)
            i, _ = get_node_in_shelf(shelf, node.node_id)
            shelf.nodes.pop(i)

    def remove_nodeclasses(self, nodes: Sequence[Type[Node]]):
        for node in nodes:
            self.remove_nodeclass(node)

    def get_node_by_id(self, nodeid: str) -> Type[Node]:
        paths = self.find_nodeid(nodeid, all=False)

        if len(paths) == 0:
            raise NodeClassNotFoundError(f"Node with id '{nodeid}' not found")

        shelf = self.get_shelf_from_path(paths[0])

        return get_node_in_shelf(shelf, nodeid)[1]


class FullLibJSON(TypedDict):
    """
    FullLibJSON for a full serilization including temporary properties
    """

    shelves: List[SerializedShelf]


def libencode(obj, preview=False):
    if isinstance(obj, Library):
        return Encdata(data=obj.full_serialize(), handeled=True, done=True)
    return Encdata(data=obj, handeled=False)


JSONEncoder.add_encoder(libencode)
