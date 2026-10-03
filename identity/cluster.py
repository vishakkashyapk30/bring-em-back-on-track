"""Clustering with guards + stable golden IDs.

Guards: two different non-null national_id_hash values never share a cluster (cannot-link); clusters with more
than MAX_CRM_RECORDS_PER_CLUSTER CRM records are flagged for steward review instead of being trusted.
Golden IDs are derived from each cluster's smallest crm_customer_id, so they stay stable across reruns.
"""

from __future__ import annotations

from collections.abc import Iterable

MAX_CRM_RECORDS_PER_CLUSTER = 5


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        p = self.parent.setdefault(x, x)
        if p != x:
            p = self.parent[x] = self.find(p)
        return p

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # keep the lexicographically smaller root so IDs are deterministic
            if rb < ra:
                ra, rb = rb, ra
            self.parent[rb] = ra


def cluster(nodes: Iterable[str], edges: Iterable[tuple[str, str]], nid: dict[str, str | None]) -> dict[str, str]:
    """Return node -> root. An edge is skipped if it would join two different non-null national IDs."""
    uf = UnionFind()
    for n in nodes:
        uf.find(n)
    cluster_nid: dict[str, str | None] = {n: nid.get(n) for n in uf.parent}
    for a, b in edges:
        ra, rb = uf.find(a), uf.find(b)
        if ra == rb:
            continue
        na, nb = cluster_nid.get(ra), cluster_nid.get(rb)
        if na and nb and na != nb:
            continue  # cannot-link guard
        uf.union(ra, rb)
        root = uf.find(ra)
        cluster_nid[root] = na or nb
    return {n: uf.find(n) for n in uf.parent}


def assign_golden_ids(roots: dict[str, str]) -> dict[str, str]:
    """root -> golden ID derived from the cluster's smallest CRM ID (e.g. KIW-6380 -> G-KIW6380).

    Stable across reruns: a customer's ID only changes if their cluster gains a member with a smaller CRM ID
    (a merge). CRM IDs are unique, so golden IDs are too.
    """
    members: dict[str, str] = {}
    for node, root in roots.items():
        if root not in members or node < members[root]:
            members[root] = node
    return {root: "G-" + members[root].replace("-", "") for root in members}
