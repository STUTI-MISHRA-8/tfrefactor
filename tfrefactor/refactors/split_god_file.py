"""Split an oversized .tf file into logical sections.

This is the cheapest possible safe refactor: Terraform doesn't care about
file boundaries within a module, only what's declared. As long as every
top-level block ends up in exactly one output file with its original text
untouched, this is *always* a no-op - no attribute or address ever changes.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from tfrefactor.blocksplit import Block
from tfrefactor.graph import ModuleGraph
from tfrefactor.refactors.base import Proposal

_HEADER = (
    "# Split from {source} by tfrefactor's split-god-file operation.\n"
    "# Every block below is byte-for-byte identical to the original - see\n"
    "# the accompanying verification report.\n\n"
)


def _group_key(block: Block) -> str:
    if block.keyword in ("resource", "data") and block.labels:
        rtype = block.labels[0]
        # group by service prefix, e.g. aws_sqs_queue -> sqs, aws_iam_role -> iam
        parts = rtype.split("_")
        return parts[1] if len(parts) > 1 else rtype
    return "_shared"


def propose_split_file(graph: ModuleGraph, file_path: str, threshold_lines: int = 500) -> Proposal:
    text = graph.file_text.get(file_path)
    if text is None:
        raise ValueError(f"unknown file: {file_path}")
    line_count = text.count("\n") + 1
    if line_count < threshold_lines:
        raise ValueError(f"{file_path} has {line_count} lines, below the {threshold_lines}-line threshold")

    blocks = graph.file_blocks[file_path]
    root = graph.root
    src_rel = str(Path(file_path).relative_to(root))
    src_name = Path(file_path).stem

    groups: dict[str, list[Block]] = defaultdict(list)
    for b in blocks:
        groups[_group_key(b)].append(b)

    file_writes: dict[str, str] = {}
    for key, group_blocks in groups.items():
        out_name = f"{src_name}_{key}.tf"
        body = "\n".join(b.text for b in group_blocks) + "\n"
        file_writes[out_name] = _HEADER.format(source=src_rel) + body

    return Proposal(
        op="split_god_file",
        description=(
            f"Split {src_rel} ({line_count} lines) into {len(groups)} files grouped by resource family: "
            f"{', '.join(sorted(f'{src_name}_{k}.tf' for k in groups))}."
        ),
        file_writes=file_writes,
        deleted_files=frozenset({src_rel}),
    )
