"""Propose removing a resource flagged as dead code.

Removing a declared resource is *never* a provable no-op against real
infrastructure - it always means "destroy this if it exists in state."
Static analysis can't see whether something outside the repo still depends
on it, so this always comes back HUMAN_REVIEW_REQUIRED regardless of how
confident the graph diff looks - never auto-applied.
"""
from __future__ import annotations

from pathlib import Path

from tfrefactor.graph import ModuleGraph
from tfrefactor.refactors.base import Proposal


def propose_remove_dead_code(graph: ModuleGraph, address: str) -> Proposal:
    if address not in graph.resources:
        raise ValueError(f"unknown resource address: {address}")
    node = graph.resources[address]
    fpath = node.file
    root = graph.root
    rel = str(Path(fpath).relative_to(root))
    text = graph.file_text[fpath]

    block = next(b for b in graph.file_blocks[fpath] if b.address == address)
    new_text = text[: block.start] + text[block.end :]

    return Proposal(
        op="dead_code",
        description=(
            f"Remove {address} ({node.type}), flagged as unreferenced. This destroys the resource if it "
            f"exists in state - run `terraform state list | grep {node.name}` first to confirm."
        ),
        file_writes={rel: new_text},
        expected_removals=frozenset({address}),
        human_review=True,
        human_review_reason=(
            f"Removing {address} destroys real infrastructure if it's in state. Confirm nothing outside "
            "this repo (another workspace, manual dependency, runbook) relies on it before applying."
        ),
    )
