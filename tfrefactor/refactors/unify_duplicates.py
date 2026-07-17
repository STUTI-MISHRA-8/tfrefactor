"""Find near-duplicate resource declarations across files/environments and
unify them into a module + varying inputs.

This is the least mechanical of the refactor ops: deciding which attributes
are "environment-specific" (should stay a variable) vs. "coincidentally
equal today" (would you want them to diverge later?) is a judgment call
that source code alone can't settle. Detection is solid; the generated
proposal always requires human review, never auto-applies, and never
silently guesses.
"""
from __future__ import annotations

import json
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from tfrefactor.graph import ModuleGraph, canonicalize, parse_module
from tfrefactor.refactors.base import Proposal
from tfrefactor.verify import Verdict, VerificationResult, verify_no_op


@dataclass
class DuplicateGroup:
    resource_type: str
    resource_name: str
    members: list[tuple[str, str]]  # (env_label, address)
    varying_keys: list[str]
    shared_attrs: dict = field(default_factory=dict)


def find_duplicate_groups(graphs: dict[str, ModuleGraph]) -> list[DuplicateGroup]:
    by_type_name: dict[tuple[str, str], list[tuple[str, object]]] = defaultdict(list)
    for label, g in graphs.items():
        for addr, node in g.resources.items():
            if node.kind == "resource":
                by_type_name[(node.type, node.name)].append((label, node))

    groups: list[DuplicateGroup] = []
    for (rtype, rname), entries in sorted(by_type_name.items()):
        if len(entries) < 2:
            continue
        top_keys: set[str] = set()
        for _, node in entries:
            top_keys |= set(node.attributes.keys())
        varying, shared = [], {}
        for k in sorted(top_keys):
            values = [canonicalize(node.attributes.get(k)) for _, node in entries]
            if all(v == values[0] for v in values):
                shared[k] = values[0]
            else:
                varying.append(k)
        if varying:
            groups.append(
                DuplicateGroup(rtype, rname, [(label, f"{rtype}.{rname}") for label, _ in entries], varying, shared)
            )
    return groups


def _hcl_literal(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        if value.startswith("${") and value.endswith("}"):
            return value[2:-1]
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(_hcl_literal(v) for v in value) + "]"
    if isinstance(value, dict):
        inner = " ".join(f"{k} = {_hcl_literal(v)}" for k, v in value.items())
        return "{ " + inner + " }"
    if value is None:
        return "null"
    return json.dumps(str(value))


def propose_unify(
    graphs: dict[str, ModuleGraph], group: DuplicateGroup, module_name: str, common_root: Path
) -> Proposal:
    var_decls = "".join(f'variable "{k}" {{\n  type = any\n}}\n' for k in group.varying_keys)
    shared_lines = "".join(f"  {k} = {_hcl_literal(v)}\n" for k, v in group.shared_attrs.items())
    var_lines = "".join(f"  {k} = var.{k}\n" for k in group.varying_keys)
    module_dir = f"modules/{module_name}"
    module_main = (
        f"# Unified by tfrefactor's unify-duplicates operation from: "
        f"{', '.join(label for label, _ in group.members)}\n\n"
        + var_decls
        + f'\nresource "{group.resource_type}" "{group.resource_name}" {{\n'
        + shared_lines
        + var_lines
        + "}\n"
    )

    file_writes = {f"{module_dir}/main.tf": module_main}

    for label, addr in group.members:
        g = graphs[label]
        node = g.resources[addr]
        fpath = node.file
        rel_from_common = str(Path(fpath).relative_to(common_root))
        block = next(b for b in g.file_blocks[fpath] if b.address == addr)
        text = g.file_text[fpath]
        new_text = text[: block.start] + text[block.end :]

        env_dir_depth = len(Path(rel_from_common).parent.parts)
        rel_source = "../" * env_dir_depth + module_dir
        call_inputs = "".join(f"  {k} = {_hcl_literal(node.attributes.get(k))}\n" for k in group.varying_keys)
        module_call = f'\nmodule "{module_name}" {{\n  source = "{rel_source}"\n{call_inputs}}}\n'
        moved_block = f"\nmoved {{\n  from = {addr}\n  to   = module.{module_name}.{addr}\n}}\n"

        file_writes[rel_from_common] = new_text.rstrip("\n") + "\n" + module_call + moved_block

    return Proposal(
        op="unify_duplicates",
        description=(
            f"Unify {len(group.members)} near-duplicate '{group.resource_type}.{group.resource_name}' "
            f"declarations into module '{module_name}'; varying inputs: {', '.join(group.varying_keys)}."
        ),
        file_writes=file_writes,
        human_review=True,
        human_review_reason=(
            "Unifying duplicates requires a judgment call about which attributes are genuinely "
            "environment-specific vs. coincidentally equal today - confirm the variable/shared split "
            "before applying."
        ),
    )


def verify_unify_proposal(
    common_root: Path, env_roots: dict[str, Path], proposal: Proposal, staging: Path
) -> dict[str, VerificationResult]:
    """Unify spans multiple independent root modules (one per environment),
    so we materialize the whole tree once and verify each environment root
    against its own before/after graph separately."""
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(common_root, staging)
    for rel_path, content in proposal.file_writes.items():
        target = staging / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    results = {}
    for label, env_root in env_roots.items():
        rel = env_root.relative_to(common_root)
        before = parse_module(env_root)
        after = parse_module(staging / rel)
        results[label] = verify_no_op(
            before,
            after,
            human_review=proposal.human_review,
            human_review_reason=proposal.human_review_reason,
        )
    return results


def combined_verdict(results: dict[str, VerificationResult]) -> Verdict:
    order = [Verdict.NOT_VERIFIED, Verdict.HUMAN_REVIEW_REQUIRED, Verdict.VERIFIED_WITH_CAVEATS, Verdict.VERIFIED_NOOP]
    worst = Verdict.VERIFIED_NOOP
    for r in results.values():
        if order.index(r.verdict) < order.index(worst):
            worst = r.verdict
    return worst
