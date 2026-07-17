"""Extract a group of resources into a reusable module.

The hard part isn't moving text - it's identity and wiring:
  * every relocated resource needs a `moved` block so the root-level
    address (`aws_sqs_queue.orders_queue`) maps to its new module address
    (`module.orders.aws_sqs_queue.queue`).
  * anything the extracted resources reference that lives *outside* the
    extracted set (a variable, a local, a data source, another resource)
    can't just stay as a bare reference inside the module - it has to
    become a module input, threaded through at the call site.
  * an explicit provider alias on an extracted resource has to be passed
    through the module call's `providers = {}` map, or Terraform silently
    resolves it against the wrong provider config (see verify.py).

We keep the module's internals dead simple: one input variable per unique
*external reference expression* found in the extracted blocks (not per
resource/attribute) - this is what lets the wiring work generically instead
of hand-coding per-attribute-type logic.
"""
from __future__ import annotations

import re
from pathlib import Path

from tfrefactor.graph import ModuleGraph
from tfrefactor.refactors.base import Proposal

_RESERVED = {"each", "count", "self", "path", "terraform"}
_EXPR_RE = re.compile(
    r"(?:data\.[A-Za-z_][\w-]*\.[A-Za-z_][\w-]*(?:\.[A-Za-z_][\w-]*)*"
    r"|module\.[A-Za-z_][\w-]*(?:\.[A-Za-z_][\w-]*)*"
    r"|var\.[A-Za-z_][\w-]*"
    r"|local\.[A-Za-z_][\w-]*"
    r"|[A-Za-z_][\w-]*\.[A-Za-z_][\w-]*(?:\.[A-Za-z_][\w-]*)*)"
)


def _base_address(token: str) -> str:
    parts = token.split(".")
    if parts[0] == "data" and len(parts) >= 3:
        return ".".join(parts[:3])
    return ".".join(parts[:2])


def _sanitize(token: str) -> str:
    return re.sub(r"[^0-9A-Za-z_]", "_", token).strip("_")


def propose_extract_module(graph: ModuleGraph, addresses: list[str], module_name: str) -> Proposal:
    missing = [a for a in addresses if a not in graph.resources]
    if missing:
        raise ValueError(f"unknown resource address(es): {missing}")
    addr_set = set(addresses)
    root = graph.root

    blocks_by_addr = {}
    for fpath, blocks in graph.file_blocks.items():
        for b in blocks:
            if b.address in addr_set:
                blocks_by_addr[b.address] = (fpath, b)

    known_bases = set(graph.resources) | {f"var.{n}" for n in graph.variables} | {
        f"local.{n}" for n in graph.locals_
    } | {f"module.{n}" for n in graph.module_calls}

    external_tokens: dict[str, str] = {}  # token -> sanitized var name
    provider_aliases: set[str] = set()

    for addr in addresses:
        node = graph.resources[addr]
        if node.provider:
            provider_aliases.add(node.provider)
        _, block = blocks_by_addr[addr]
        for m in _EXPR_RE.finditer(block.text):
            token = m.group(0)
            prefix = token.split(".")[0]
            if prefix in _RESERVED:
                continue
            base = _base_address(token)
            if base in addr_set:
                continue  # internal cross-reference, address unaffected by extraction
            if base not in known_bases:
                continue  # not an actual reference (e.g. a literal string that happens to contain dots)
            if token not in external_tokens:
                external_tokens[token] = _sanitize(token)

    module_dir = f"modules/{module_name}"
    module_blocks_text = []
    for addr in addresses:
        _, block = blocks_by_addr[addr]
        text = block.text
        for token, var_name in sorted(external_tokens.items(), key=lambda kv: -len(kv[0])):
            text = text.replace(token, f"var.{var_name}")
        module_blocks_text.append(text)

    var_decls = "\n".join(
        f'variable "{var_name}" {{\n  type = any\n}}\n' for var_name in external_tokens.values()
    )
    module_main_tf = (
        f"# Extracted by tfrefactor's extract-module operation.\n"
        f"# Every resource block below is byte-for-byte identical to its\n"
        f"# original source except for external references, which are\n"
        f"# threaded through as module inputs (see the module call site).\n\n"
        + (var_decls + "\n" if var_decls else "")
        + "\n".join(module_blocks_text)
        + "\n"
    )

    call_inputs = "".join(f"  {var_name} = {token}\n" for token, var_name in external_tokens.items())
    providers_line = ""
    if provider_aliases:
        mapping = ", ".join(f"{alias.split('.')[0]} = {alias}" for alias in sorted(provider_aliases))
        providers_line = f"  providers = {{ {mapping} }}\n"
    module_call = (
        f'\nmodule "{module_name}" {{\n'
        f'  source = "./{module_dir}"\n'
        f"{call_inputs}{providers_line}"
        "}\n"
    )

    moved_blocks = "\n".join(
        f"moved {{\n  from = {addr}\n  to   = module.{module_name}.{addr}\n}}\n" for addr in addresses
    )

    file_writes: dict[str, str] = {f"{module_dir}/main.tf": module_main_tf}
    deleted: set[str] = set()

    by_file: dict[str, list] = {}
    for addr in addresses:
        fpath, block = blocks_by_addr[addr]
        by_file.setdefault(fpath, []).append(block)

    for fpath, blocks_to_remove in by_file.items():
        rel = str(Path(fpath).relative_to(root))
        text = graph.file_text[fpath]
        for b in sorted(blocks_to_remove, key=lambda b: -b.start):
            text = text[: b.start] + text[b.end :]
        if text.strip():
            file_writes[rel] = text
        else:
            deleted.add(rel)

    call_path = f"module_{module_name}.tf"
    existing_call_file = graph.file_text.get(str(Path(root) / call_path), "")
    file_writes[call_path] = existing_call_file + module_call

    moves_path = "moves.tf"
    existing_moves = graph.file_text.get(str(Path(root) / moves_path), "")
    file_writes[moves_path] = existing_moves + "\n" + moved_blocks

    return Proposal(
        op="extract_module",
        description=(
            f"Extract {len(addresses)} resources into module '{module_name}' "
            f"({module_dir}/main.tf), with {len(external_tokens)} external references threaded "
            f"through as inputs and moved blocks for every relocated address."
        ),
        file_writes=file_writes,
        deleted_files=frozenset(deleted),
    )
