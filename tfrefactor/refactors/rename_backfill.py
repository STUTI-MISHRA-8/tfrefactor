"""Rename a resource and auto-generate the `moved` block so the plan is a
no-op. This is the simplest refactor to prove safe: the resource's own
attributes never change, only its address - and Terraform has a first-class
mechanism (`moved`) for declaring "this address used to mean that address."
"""
from __future__ import annotations

import re
from pathlib import Path

from tfrefactor.graph import ModuleGraph
from tfrefactor.refactors.base import Proposal


def propose_rename(graph: ModuleGraph, old_address: str, new_name: str) -> Proposal:
    if old_address not in graph.resources:
        raise ValueError(f"unknown resource address: {old_address}")
    node = graph.resources[old_address]
    if node.kind != "resource":
        raise ValueError("only resource blocks can be renamed (not data sources)")

    new_address = f"{node.type}.{new_name}"
    if new_address in graph.resources:
        raise ValueError(f"target address already exists: {new_address}")

    file_writes: dict[str, str] = {}
    root = graph.root

    for fpath, text in graph.file_text.items():
        rel = str(Path(fpath).relative_to(root))
        new_text = text
        blocks = graph.file_blocks[fpath]

        own_block = next(
            (b for b in blocks if b.keyword == "resource" and b.address == old_address), None
        )
        if own_block is not None:
            label_pattern = re.compile(
                r'(resource\s+"' + re.escape(node.type) + r'"\s+)"' + re.escape(node.name) + r'"'
            )
            new_block_text = label_pattern.sub(r'\1"' + new_name + '"', own_block.text, count=1)
            new_text = new_text[: own_block.start] + new_block_text + new_text[own_block.end :]

        ref_pattern = re.compile(r"(?<![\w.])" + re.escape(old_address) + r"(?![\w])")
        new_text = ref_pattern.sub(new_address, new_text)

        if new_text != text:
            file_writes[rel] = new_text

    moves_path = "moves.tf"
    existing_moves = graph.file_text.get(str(Path(root) / moves_path), "")
    moved_block = f'\nmoved {{\n  from = {old_address}\n  to   = {new_address}\n}}\n'
    file_writes[moves_path] = existing_moves + moved_block

    return Proposal(
        op="rename_backfill",
        description=f"Rename {old_address} -> {new_address}, with a moved block so the plan is a no-op.",
        file_writes=file_writes,
    )
