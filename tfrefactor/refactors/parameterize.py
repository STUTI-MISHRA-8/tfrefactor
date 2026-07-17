"""Lift a hardcoded value to a variable, defaulted to the original literal.

Provably a no-op *conditional* on nothing overriding the new variable's
default at apply time (-var, tfvars, TF_VAR_*) - we can't see those from
static analysis, so verify.py surfaces this as a caveat rather than a bare
pass. That's the honest answer, not a false guarantee.
"""
from __future__ import annotations

import re
from pathlib import Path

from tfrefactor.graph import ModuleGraph
from tfrefactor.refactors.base import Proposal


def propose_parameterize(graph: ModuleGraph, address: str, attr_key: str, var_name: str) -> Proposal:
    if address not in graph.resources:
        raise ValueError(f"unknown resource address: {address}")
    node = graph.resources[address]
    if attr_key not in node.attributes:
        raise ValueError(f"{address} has no top-level attribute '{attr_key}'")
    value = node.attributes[attr_key]
    if not isinstance(value, str) or value.startswith("${"):
        raise ValueError(f"{address}.{attr_key} is not a literal string - nothing to parameterize")
    if var_name in graph.variables:
        raise ValueError(f"variable '{var_name}' already exists")

    root = graph.root
    fpath = node.file
    text = graph.file_text[fpath]
    rel = str(Path(fpath).relative_to(root))

    block = next(
        b
        for b in graph.file_blocks[fpath]
        if b.address == address and b.keyword in ("resource", "data", "provider")
    )
    attr_pattern = re.compile(
        r'(^|\n)(\s*' + re.escape(attr_key) + r'\s*=\s*)"' + re.escape(value) + r'"',
    )
    new_block_text, count = attr_pattern.subn(r"\1\2var." + var_name, block.text, count=1)
    if count == 0:
        raise ValueError(f"could not locate a literal assignment for '{attr_key}' in {address}'s source text")
    new_text = text[: block.start] + new_block_text + text[block.end :]

    variables_path = "variables.tf"
    existing_vars = graph.file_text.get(str(Path(root) / variables_path), "")
    var_block = f'\nvariable "{var_name}" {{\n  type    = string\n  default = "{value}"\n}}\n'

    file_writes = {rel: new_text, variables_path: existing_vars + var_block}

    return Proposal(
        op="parameterize",
        description=(
            f"Lift {address}.{attr_key} ('{value}') to var.{var_name}, defaulted to the original value."
        ),
        file_writes=file_writes,
    )
