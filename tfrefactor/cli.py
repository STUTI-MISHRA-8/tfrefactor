"""tfrefactor CLI: scan, propose, verify.

Non-negotiables enforced here, not just documented:
  - propose never writes to disk unless --apply is passed.
  - --apply refuses to write anything for NOT_VERIFIED or
    HUMAN_REVIEW_REQUIRED results unless the matching override flag is
    passed explicitly - and even then, only .tf files are touched. State
    migrations are always printed as commands for the engineer to run
    themselves, never executed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import click

from tfrefactor.anti_patterns import scan_all
from tfrefactor.graph import parse_module
from tfrefactor.refactors.base import apply_proposal, verify_proposal
from tfrefactor.refactors.dead_code import propose_remove_dead_code
from tfrefactor.refactors.extract_module import propose_extract_module
from tfrefactor.refactors.parameterize import propose_parameterize
from tfrefactor.refactors.rename_backfill import propose_rename
from tfrefactor.refactors.split_god_file import propose_split_file
from tfrefactor.refactors.unify_duplicates import (
    combined_verdict,
    find_duplicate_groups,
    propose_unify,
    verify_unify_proposal,
)
from tfrefactor.verify import Verdict


@click.group()
def main():
    """tfrefactor - safe, verifiable LLM-native Terraform refactoring."""


@main.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option("--god-file-threshold", default=500, show_default=True, help="Line count to flag a file as a god-file.")
def scan(directory, god_file_threshold):
    """Parse a module and report anti-patterns (no changes proposed)."""
    root = Path(directory)
    graph = parse_module(root)
    findings = scan_all(graph, god_file_threshold=god_file_threshold)

    click.echo(f"Parsed {len(graph.resources)} resources/data sources, {len(graph.variables)} variables.")
    if not findings:
        click.echo("No anti-patterns found.")
        return

    by_cat: dict[str, int] = {}
    for f in findings:
        by_cat[f.category] = by_cat.get(f.category, 0) + 1
    click.echo(f"{len(findings)} findings:")
    for f in findings:
        click.echo(f"  [{f.severity}] {f.category} @ {f.location}: {f.message}")
    click.echo()
    click.echo("Summary: " + ", ".join(f"{cat}={n}" for cat, n in sorted(by_cat.items())))


def _print_verdict(result):
    color = {
        Verdict.VERIFIED_NOOP: "green",
        Verdict.VERIFIED_WITH_CAVEATS: "yellow",
        Verdict.NOT_VERIFIED: "red",
        Verdict.HUMAN_REVIEW_REQUIRED: "yellow",
    }[result.verdict]
    click.secho(f"Verdict: {result.verdict.value}", fg=color, bold=True)
    for f in result.findings:
        tag = {"blocker": "BLOCKER", "caveat": "CAVEAT", "info": "info"}[f.severity]
        fg = {"blocker": "red", "caveat": "yellow", "info": "cyan"}[f.severity]
        click.secho(f"  [{tag}] {f.address}: {f.message}", fg=fg)
        if f.recommended_command:
            click.echo(f"      -> {f.recommended_command}")


def _maybe_apply(root, proposal, result, apply, force_unverified, confirm_human_review):
    if not apply:
        click.echo("\n(dry run - pass --apply to write these changes)")
        return
    if result.verdict == Verdict.NOT_VERIFIED and not force_unverified:
        click.secho(
            "\nRefusing to apply: verification failed. Pass --force-unverified to override "
            "(not recommended - review the blockers above first).",
            fg="red",
        )
        sys.exit(1)
    if result.verdict == Verdict.HUMAN_REVIEW_REQUIRED and not confirm_human_review:
        click.secho(
            "\nRefusing to apply: this change requires human review. Pass --confirm-human-review "
            "once you've reviewed it.",
            fg="yellow",
        )
        sys.exit(1)
    apply_proposal(root, proposal)
    click.secho(f"\nApplied. {len(proposal.file_writes)} file(s) written, {len(proposal.deleted_files)} deleted.", fg="green")
    click.echo("This tool never touches state. If any address moved, Terraform's `moved` blocks handle")
    click.echo("adoption automatically on the next plan/apply - no `terraform state mv` needed. Still:")
    click.echo("  terraform plan -out=tfplan   # confirm the plan is empty before applying")


@main.group()
def propose():
    """Propose a refactor operation (verified before any write)."""


@propose.command("rename")
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option("--address", required=True, help="Existing resource address, e.g. aws_instance.web")
@click.option("--to", "new_name", required=True, help="New resource name (label only, not full address)")
@click.option("--apply", is_flag=True)
@click.option("--force-unverified", is_flag=True)
@click.option("--confirm-human-review", is_flag=True)
def propose_rename_cmd(directory, address, new_name, apply, force_unverified, confirm_human_review):
    root = Path(directory)
    graph = parse_module(root)
    proposal = propose_rename(graph, address, new_name)
    click.echo(proposal.description)
    result = verify_proposal(root, graph, proposal, root.parent / f".tfrefactor-staging-{root.name}")
    _print_verdict(result)
    _maybe_apply(root, proposal, result, apply, force_unverified, confirm_human_review)


@propose.command("parameterize")
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option("--address", required=True)
@click.option("--attr", "attr_key", required=True, help="Top-level attribute key to lift, e.g. ami")
@click.option("--var-name", required=True)
@click.option("--apply", is_flag=True)
@click.option("--force-unverified", is_flag=True)
@click.option("--confirm-human-review", is_flag=True)
def propose_parameterize_cmd(directory, address, attr_key, var_name, apply, force_unverified, confirm_human_review):
    root = Path(directory)
    graph = parse_module(root)
    proposal = propose_parameterize(graph, address, attr_key, var_name)
    click.echo(proposal.description)
    result = verify_proposal(root, graph, proposal, root.parent / f".tfrefactor-staging-{root.name}")
    _print_verdict(result)
    _maybe_apply(root, proposal, result, apply, force_unverified, confirm_human_review)


@propose.command("split-file")
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option("--file", "file_name", required=True, help="File name within DIRECTORY, e.g. services.tf")
@click.option("--threshold", default=500, show_default=True)
@click.option("--apply", is_flag=True)
@click.option("--force-unverified", is_flag=True)
@click.option("--confirm-human-review", is_flag=True)
def propose_split_cmd(directory, file_name, threshold, apply, force_unverified, confirm_human_review):
    root = Path(directory)
    graph = parse_module(root)
    fkey = str((root / file_name).resolve())
    matched = next((k for k in graph.file_text if str(Path(k).resolve()) == fkey), None)
    if matched is None:
        raise click.ClickException(f"file not found in parsed module: {file_name}")
    proposal = propose_split_file(graph, matched, threshold_lines=threshold)
    click.echo(proposal.description)
    result = verify_proposal(root, graph, proposal, root.parent / f".tfrefactor-staging-{root.name}")
    _print_verdict(result)
    _maybe_apply(root, proposal, result, apply, force_unverified, confirm_human_review)


@propose.command("extract-module")
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option("--addresses", required=True, help="Comma-separated resource addresses to extract")
@click.option("--module-name", required=True)
@click.option("--apply", is_flag=True)
@click.option("--force-unverified", is_flag=True)
@click.option("--confirm-human-review", is_flag=True)
def propose_extract_cmd(directory, addresses, module_name, apply, force_unverified, confirm_human_review):
    root = Path(directory)
    graph = parse_module(root)
    addr_list = [a.strip() for a in addresses.split(",") if a.strip()]
    proposal = propose_extract_module(graph, addr_list, module_name)
    click.echo(proposal.description)
    result = verify_proposal(root, graph, proposal, root.parent / f".tfrefactor-staging-{root.name}")
    _print_verdict(result)
    _maybe_apply(root, proposal, result, apply, force_unverified, confirm_human_review)


@propose.command("dead-code")
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option("--address", required=True)
@click.option("--apply", is_flag=True)
@click.option("--force-unverified", is_flag=True)
@click.option("--confirm-human-review", is_flag=True)
def propose_dead_code_cmd(directory, address, apply, force_unverified, confirm_human_review):
    root = Path(directory)
    graph = parse_module(root)
    proposal = propose_remove_dead_code(graph, address)
    click.echo(proposal.description)
    result = verify_proposal(root, graph, proposal, root.parent / f".tfrefactor-staging-{root.name}")
    _print_verdict(result)
    _maybe_apply(root, proposal, result, apply, force_unverified, confirm_human_review)


@main.command("unify-duplicates")
@click.argument("common_root", type=click.Path(exists=True, file_okay=False))
@click.argument("env_dirs", nargs=-1, required=True)
@click.option("--apply", is_flag=True)
@click.option("--confirm-human-review", is_flag=True)
def unify_duplicates_cmd(common_root, env_dirs, apply, confirm_human_review):
    """Detect and propose unifying near-duplicate resources across ENV_DIRS
    (paths relative to COMMON_ROOT, e.g. envs/dev envs/prod)."""
    root = Path(common_root)
    env_roots = {d: (root / d) for d in env_dirs}
    graphs = {label: parse_module(p) for label, p in env_roots.items()}
    groups = find_duplicate_groups(graphs)
    if not groups:
        click.echo("No cross-environment duplicates found.")
        return

    for g in groups:
        module_name = f"{g.resource_name}_shared"
        proposal = propose_unify(graphs, g, module_name, root)
        click.echo(f"\n=== {proposal.description}")
        results = verify_unify_proposal(root, env_roots, proposal, root / f".tfrefactor-staging-unify")
        for label, r in results.items():
            click.echo(f"  {label}:")
            _print_verdict(r)
        verdict = combined_verdict(results)
        if apply:
            if verdict == Verdict.HUMAN_REVIEW_REQUIRED and not confirm_human_review:
                click.secho("  Refusing to apply without --confirm-human-review.", fg="yellow")
                continue
            if verdict == Verdict.NOT_VERIFIED:
                click.secho("  Refusing to apply: NOT_VERIFIED.", fg="red")
                continue
            apply_proposal(root, proposal)
            click.secho(f"  Applied module '{module_name}'.", fg="green")
        else:
            click.echo("  (dry run - pass --apply to write these changes)")


@main.command()
@click.argument("before_dir", type=click.Path(exists=True, file_okay=False))
@click.argument("after_dir", type=click.Path(exists=True, file_okay=False))
def verify(before_dir, after_dir):
    """Directly compare two already-materialized directories (e.g. in CI)."""
    from tfrefactor.verify import verify_no_op

    before = parse_module(Path(before_dir))
    after = parse_module(Path(after_dir))
    result = verify_no_op(before, after)
    _print_verdict(result)
    sys.exit(0 if result.verdict in (Verdict.VERIFIED_NOOP, Verdict.VERIFIED_WITH_CAVEATS) else 1)


if __name__ == "__main__":
    main()
