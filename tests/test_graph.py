import sys
import types
from dataclasses import dataclass
from typing import List, Tuple

try:
    import networkx as nx  # pragma: no cover
except ModuleNotFoundError:  # pragma: no cover - fallback for test env

    class _FakeDiGraph:
        def __init__(self):
            self._nodes = set()
            self._edges = set()

        def add_node(self, node):
            self._nodes.add(node)

        def add_edge(self, src, dst):
            self._nodes.add(src)
            self._nodes.add(dst)
            self._edges.add((src, dst))

        @property
        def nodes(self):
            return set(self._nodes)

        @property
        def edges(self):
            return set(self._edges)

        def number_of_edges(self):
            return len(self._edges)

    nx = types.ModuleType("networkx")
    nx.DiGraph = _FakeDiGraph  # type: ignore[attr-defined]
    sys.modules["networkx"] = nx

from funcnodes_core.graph import from_nodespace


@dataclass
class DummyNode:
    uuid: str


@dataclass
class DummyEndpoint:
    node: DummyNode | None


@dataclass
class DummyNodeSpace:
    nodes: List[DummyNode]
    edges: List[Tuple[DummyEndpoint, DummyEndpoint]]


def test_from_nodespace_builds_graph_with_all_edges():
    nodes = [DummyNode("n1"), DummyNode("n2"), DummyNode("n3")]
    ns = DummyNodeSpace(
        nodes=nodes,
        edges=[
            (DummyEndpoint(nodes[0]), DummyEndpoint(nodes[1])),
            (DummyEndpoint(nodes[1]), DummyEndpoint(nodes[2])),
        ],
    )

    graph = from_nodespace(ns)

    assert set(graph.nodes) == {"n1", "n2", "n3"}
    assert ("n1", "n2") in graph.edges
    assert ("n2", "n3") in graph.edges
    assert ("n3", "n1") not in graph.edges


def test_from_nodespace_ignores_edges_missing_nodes():
    nodes = [DummyNode("n1"), DummyNode("n2")]
    ns = DummyNodeSpace(
        nodes=nodes,
        edges=[
            (DummyEndpoint(None), DummyEndpoint(nodes[1])),
            (DummyEndpoint(nodes[0]), DummyEndpoint(None)),
        ],
    )

    graph = from_nodespace(ns)

    assert set(graph.nodes) == {"n1", "n2"}
    assert graph.number_of_edges() == 0
