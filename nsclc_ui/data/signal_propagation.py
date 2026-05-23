"""V3-2: Random Walk with Restart (RWR) on SIGNOR NSCLC directed graph.

Module-level cache: graph + transition matrix loaded once.

Usage:
    from nsclc_ui.data.signal_propagation import rwr_from_seeds
    scores = rwr_from_seeds(['EGFR', 'TP53'], restart_prob=0.5, top_n=30)
"""
from __future__ import annotations
import pickle
from pathlib import Path
from typing import Iterable

import numpy as np
import networkx as nx
import pandas as pd

# ── Module cache
_BASE = Path(__file__).resolve().parents[2] / 'data' / 'derived'
_GRAPH_PATH = _BASE / 'signor_nsclc_graph.gpickle'
_cache: dict = {}


def _load() -> dict:
    """Load graph + precompute transition matrix (cached)."""
    if _cache:
        return _cache
    with open(_GRAPH_PATH, 'rb') as f:
        G: nx.DiGraph = pickle.load(f)
    nodes = sorted(G.nodes())
    node_idx = {n: i for i, n in enumerate(nodes)}
    n = len(nodes)
    
    # Build weighted adjacency (out-edge based)
    # Use SCORE attribute; default 0.5 if missing
    A = np.zeros((n, n), dtype=np.float64)
    for src, tgt, attrs in G.edges(data=True):
        w = float(attrs.get('score') or 0.5)
        if w <= 0:
            w = 0.5
        A[node_idx[src], node_idx[tgt]] = w
    
    # Column-normalize for random walk: M[:,j] = A[:,j] / sum(A[:,j])
    # Walker at node j moves to i with prob M[i,j]
    # For RWR, we use: p_{t+1} = (1-r) * M @ p_t + r * p_0
    # Here M is column-stochastic, so we transpose A then column-normalize
    M = A.T  # now M[i,j] = weight of edge j→i
    col_sums = M.sum(axis=0, keepdims=True)
    col_sums = np.where(col_sums == 0, 1.0, col_sums)  # avoid div-by-zero
    M = M / col_sums
    
    _cache['graph'] = G
    _cache['nodes'] = nodes
    _cache['node_idx'] = node_idx
    _cache['M'] = M  # column-stochastic transition matrix
    return _cache


def rwr_from_seeds(
    seeds: Iterable[str],
    restart_prob: float = 0.5,
    n_iter: int = 50,
    tol: float = 1e-6,
    top_n: int | None = None,
) -> pd.DataFrame:
    """Run RWR from seed nodes.
    
    Args:
        seeds: gene symbols to start from (e.g., ['EGFR', 'TP53'])
        restart_prob: probability of returning to seed at each step (r)
        n_iter: max iterations
        tol: convergence threshold (L1 norm of p change)
        top_n: return only top-N nodes by influence; None returns all
    
    Returns:
        DataFrame with columns: gene, influence (sorted desc),
        seed_set, is_seed, is_nsclc_target, n_iter_converged
    """
    cache = _load()
    nodes = cache['nodes']
    node_idx = cache['node_idx']
    M = cache['M']
    G = cache['graph']
    
    seeds = [s for s in seeds if s in node_idx]
    if not seeds:
        return pd.DataFrame(columns=['gene', 'influence', 'is_seed', 'is_nsclc_target'])
    
    n = len(nodes)
    p0 = np.zeros(n)
    for s in seeds:
        p0[node_idx[s]] = 1.0
    p0 = p0 / p0.sum()
    
    p = p0.copy()
    converged_iter = n_iter
    for it in range(n_iter):
        p_new = (1 - restart_prob) * (M @ p) + restart_prob * p0
        diff = np.abs(p_new - p).sum()
        p = p_new
        if diff < tol:
            converged_iter = it + 1
            break
    
    seed_set = set(seeds)
    rows = [{
        'gene': nodes[i],
        'influence': p[i],
        'is_seed': nodes[i] in seed_set,
        'is_nsclc_target': bool(G.nodes[nodes[i]].get('is_nsclc_target', 0)),
    } for i in range(n)]
    df = pd.DataFrame(rows).sort_values('influence', ascending=False).reset_index(drop=True)
    df.attrs['n_iter_converged'] = converged_iter
    df.attrs['seeds'] = seeds
    df.attrs['restart_prob'] = restart_prob
    
    if top_n is not None:
        df = df.head(top_n)
    return df


if __name__ == '__main__':
    # ── Sanity: EGFR single-seed RWR
    print('=== EGFR single-seed RWR (r=0.5) ===')
    res = rwr_from_seeds(['EGFR'], restart_prob=0.5, top_n=15)
    print(f"converged in {res.attrs['n_iter_converged']} iter")
    print(res.to_string(index=False))
    print()
    
    # ── EGFR + KRAS (NSCLC double driver)
    print('=== EGFR + KRAS combined RWR ===')
    res2 = rwr_from_seeds(['EGFR', 'KRAS'], restart_prob=0.5, top_n=15)
    print(f"converged in {res2.attrs['n_iter_converged']} iter")
    print(res2.to_string(index=False))
    print()
    
    # ── Domain validation: EGFR direct neighbors should be in top
    print('=== Domain check: EGFR direct out-neighbors in graph ===')
    cache = _load()
    G = cache['graph']
    egfr_out = sorted(G.successors('EGFR'))
    print(f'EGFR out-neighbors ({len(egfr_out)}): {egfr_out[:15]}')
    print()
    
    # ── Effect of restart_prob (sensitivity check)
    print('=== Effect of restart_prob on EGFR top-5 ===')
    for r in [0.2, 0.5, 0.8]:
        res_r = rwr_from_seeds(['EGFR'], restart_prob=r, top_n=5)
        top5 = res_r[~res_r['is_seed']]['gene'].head(5).tolist()
        print(f'  r={r}: {top5}')
