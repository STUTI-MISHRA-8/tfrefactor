"""Shared proposal contract for all refactor operations.

Every refactor op produces a Proposal: a set of file writes relative to the
module root, expressed as *full new file contents* (never a partial patch -
that keeps application and staging trivial and unambiguous). Nothing here
ever touches state; these are .tf source edits only.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from tfrefactor.graph import ModuleGraph, parse_module
from tfrefactor.verify import VerificationResult, verify_no_op


@dataclass
class Proposal:
    op: str
    description: str
    file_writes: dict[str, str] = field(default_factory=dict)  # relative path -> full new content
    deleted_files: frozenset[str] = frozenset()
    expected_removals: frozenset[str] = frozenset()
    human_review: bool = False
    human_review_reason: str | None = None


def materialize(root: Path, proposal: Proposal, staging: Path) -> None:
    """Copy `root` to `staging` then overlay the proposal's file writes."""
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(root, staging)
    for rel_path, content in proposal.file_writes.items():
        target = staging / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    for rel_path in proposal.deleted_files:
        target = staging / rel_path
        if target.exists():
            target.unlink()


def verify_proposal(root: Path, before: ModuleGraph, proposal: Proposal, staging: Path) -> VerificationResult:
    materialize(root, proposal, staging)
    after = parse_module(staging)
    return verify_no_op(
        before,
        after,
        expected_removals=proposal.expected_removals,
        human_review=proposal.human_review,
        human_review_reason=proposal.human_review_reason,
    )


def apply_proposal(root: Path, proposal: Proposal) -> None:
    for rel_path, content in proposal.file_writes.items():
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    for rel_path in proposal.deleted_files:
        target = root / rel_path
        if target.exists():
            target.unlink()
