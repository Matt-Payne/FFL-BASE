from utils.preprocess_helpers import remove_lib
from utils.nx_graph_builder import build_nx_graph_cfg_ast, combine_ast_cfg
from cfg import cfg
import networkx as nx
from graph_algos.cfl_match_general import build_cpi
from graph_algos.nx_shortcuts import neighbors_out, neighbors_in


__author__ = "Thanh-Dat Nguyen, thanhdatn@student.unimelb.edu.au"


def ast_node_match_label(n1, ast1, n2, ast2):
    if ast1.node[n1]['ntype'] == ast2.node[n2]['ntype']:
        return True


def ast_node_token_match(n1, ast1, n2, ast2):
    # TODO: consider levenshtein threshold
    return ast1.nodes[n1]['ntype'] == ast2.nodes[n2]['ntype'] and\
        ast1.nodes[n1]['token'] == ast2.nodes[n2]['token']


def simple_top_down_ast_match(ast1: nx.MultiDiGraph, ast2: nx.MultiDiGraph):
    # We don't need fine-grained bottom up like GumTree
    # Since it makes no differences in our case where
    # Whether the node moves or not, we automatically assign
    # Error to parent
    mapping = {}
    # BFS
    queue1 = [ast1.nodes[0]]
    queue2 = [ast2.nodes[0]]
    while len(queue1) > 0 and len(queue2) > 0:
        for i1, n1 in queue1:
            for i2, n2 in queue2:
                if ast_node_match_label(n1, ast1, n2, ast2):
                    # Also check if the all the input edges match
                    pass
                pass
        # Check if it match with any in queue2
        # If it does, add its children and queue2's children in to queue
    pass


def careful_slow_ast_match(ast1: nx.MultiDiGraph, ast2: nx.MultiDiGraph):
    ''' Careful and slow (guaranteed correct) CFL-based AST match '''
    queue = [0]
    sub_graph = nx.MultiDiGraph()
    last_q = None
    while len(queue) > 0:
        node = queue.pop()
        new_temp_subgraph = ast1.subgraph(
            list(sub_graph.nodes()) + [node]).copy()
        # Check if it is isomorphic to ast2
        node_dict, edge_dict, q = build_cpi(
            new_temp_subgraph, ast2, ast_node_token_match, root_name=0)
        # Note: can be faster by caching previous candidates
        if all(len(q.nodes[n]['candidates']) > 0 for n in q.nodes()):
            last_q = q
            sub_graph = new_temp_subgraph
            queue.extend(neighbors_out(node, ast1))

    forward_mapping = {}
    backward_mapping = {}
    if last_q is not None:
        for n2 in ast2.nodes():
            candidates = [n1 for n1 in last_q.nodes()
                          if n2 in last_q.nodes[n1]['candidates']]
            if len(candidates) > 0:
                backward_mapping[n2] = candidates
        forward_mapping = {n1: last_q.nodes[n1]['candidates']
                           for n1 in last_q.nodes()}
    return forward_mapping, backward_mapping


def get_bug_localization(file1, file2):
    nline_removed1 = remove_lib(file1)
    graph = cfg.CFG("temp.c")

    with open("temp.c", 'r') as f:
        code = [line for line in f]

    nx_cfg1, nx_ast1, _ = build_nx_graph_cfg_ast(graph, code)

    nline_removed2 = remove_lib(file2)
    graph = cfg.CFG("temp.c")
    with open("temp.c", 'r') as f:
        code = [line for line in f]

    nx_cfg2, nx_ast2, _ = build_nx_graph_cfg_ast(graph, code)
    # 2 Scenarios
    # 1.
    # Take differences betweeen AST and AST

    forward_mapping, backward_mapping = careful_slow_ast_match(
        nx_ast1, nx_ast2)

    for n_a1 in nx_ast1.nodes():
        nx_ast1.nodes[n_a1]['status'] = 'k' if n_a1 in forward_mapping else 'd'

    for n_a2 in nx_ast2.nodes():
        if n_a2 in backward_mapping:
            continue
        # Get all parents (either 'next sibling' or 'parent-child'
        kept_parents = neighbors_in(
            n_a2, nx_ast2, lambda u, v, k, e: u in backward_mapping)
        for k_p in kept_parents:
            for b_c in backward_mapping[k_p]:
                nx_ast1.nodes[b_c]['status'] = 'i'
    # Map back to CFG and CFG
    for n_c1 in nx_cfg1.nodes():
        nx_cfg1.nodes[n_c1]['status'] = 'k'
    nx_cfg_ast1 = combine_ast_cfg(nx_ast1, nx_cfg1)
    for n_c1 in nx_cfg_ast1.nodes():
        if nx_cfg_ast1.nodes[n_c1]['graph'] != 'cfg':
            continue
        if len(neighbors_out(n_c1, nx_cfg_ast1, lambda u, v, k, e:
                             nx_cfg_ast1.nodes[v]['status'] != 'k' and
                             nx_cfg_ast1.nodes[v]['graph'] == 'ast')) > 0:
            nx_cfg_ast1.nodes[n_c1]['status'] = 'm'     # Modified
    # 2.
    # Take differences between lines
    # Check back to CFG
    # To be implemented
    return nx_ast1, nx_ast2, nx_cfg1, nx_cfg2, nx_cfg_ast1, nline_removed1
