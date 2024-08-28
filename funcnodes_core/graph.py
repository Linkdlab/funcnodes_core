from .nodespace import NodeSpace
import networkx as nx


def from_nodespace(ns: NodeSpace):
    G = nx.DiGraph()

    for n in ns.nodes:
        G.add_node(n.uuid)

    for no, ni in ns.edges:
        if no.node is None or ni.node is None:
            continue
        G.add_edge(no.node.uuid, ni.node.uuid)

    return G
