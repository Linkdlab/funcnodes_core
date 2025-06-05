from __future__ import annotations
from weakref import ref
from typing import TYPE_CHECKING, List, Optional
from .utils.serialization import JSONEncoder, Encdata

if TYPE_CHECKING:
    from .node import Node


class DataPath:
    def __init__(self, node: Node, io: str):
        self.src_paths: List[DataPath] = list()
        self.dst_paths: List[DataPath] = list()
        self.node_ref = ref(node)
        self.io = io

    def add_src_path(self, src_path: "DataPath"):
        if src_path not in self.src_paths:
            self.src_paths.append(src_path)
            src_path.add_dst_path(self)

    def add_dst_path(self, dst_path: "DataPath"):
        if dst_path not in self.dst_paths:
            self.dst_paths.append(dst_path)
            dst_path.add_src_path(self)

    def src_repr(self) -> str:
        prev_reps = sorted([path.src_repr() for path in self.src_paths])
        prev_reps_lines = []
        for rep in prev_reps:
            if "\n" in rep:
                prev_reps_lines.extend(rep.split("\n"))
            else:
                prev_reps_lines.append(rep)
        max_prev_length = max((len(rep) for rep in prev_reps_lines), default=0)
        # append " " before each previous representation to make them aligned
        prev_reps = [rep.rjust(max_prev_length) for rep in prev_reps_lines]

        new_lines = []
        if len(prev_reps) == 0:
            return str(self)
        for i, p in enumerate(prev_reps):
            if i == len(prev_reps) // 2:
                new_lines.append(p + " -> " + str(self))
            else:
                new_lines.append(p)

        new_lines_max_length = max((len(line) for line in new_lines), default=0)
        new_lines = [line.ljust(new_lines_max_length) for line in new_lines]
        return "\n".join(new_lines)

    def done(self, breaking_nodes: Optional[List[Node]] = None) -> bool:
        """Mark this DataPath as done, removing it from the src_paths and dst_paths."""
        if breaking_nodes is None:
            breaking_nodes = []
        node = self.node_ref()
        if node is None:
            return True
        if node in breaking_nodes:
            return True
        if node.in_trigger_soon:
            return False
        for trg_path in self.dst_paths:
            if not trg_path.done(breaking_nodes=breaking_nodes):
                return False
        return True

    def __str__(self):
        node = self.node_ref()
        return f"{node.name}({self.io})" if node else f"Unknown Node({self.io})"

    def src_graph(self):
        return [[path.src_graph() + [path] for path in self.src_paths]]

    def str_src_graph(self):
        return [[path.str_src_graph() + [str(path)] for path in self.src_paths]]


def datapath_handler(obj, preview=False):
    """
    Encodes bytes objects to base64 strings.
    """
    if isinstance(obj, DataPath):
        # Convert bytes to base64 string
        return Encdata(done=False, handeled=True, data=obj.src_graph())
    return Encdata(data=obj, handeled=False)


JSONEncoder.add_encoder(datapath_handler, enc_cls=[DataPath])
