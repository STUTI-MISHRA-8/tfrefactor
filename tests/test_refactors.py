from pathlib import Path

from tfrefactor.graph import parse_module
from tfrefactor.refactors.base import verify_proposal
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


def test_rename_backfill_verifies_clean(copy_of_messy_root, tmp_path):
    graph = parse_module(copy_of_messy_root)
    proposal = propose_rename(graph, "aws_instance.web", "web_server")
    result = verify_proposal(copy_of_messy_root, graph, proposal, tmp_path / "staging")
    assert result.verdict == Verdict.VERIFIED_WITH_CAVEATS
    assert not any(f.severity == "blocker" for f in result.findings)


def test_parameterize_is_a_caveat_not_a_blocker(copy_of_messy_root, tmp_path):
    graph = parse_module(copy_of_messy_root)
    proposal = propose_parameterize(graph, "aws_instance.web", "ami", "web_ami")
    result = verify_proposal(copy_of_messy_root, graph, proposal, tmp_path / "staging")
    assert result.verdict == Verdict.VERIFIED_WITH_CAVEATS
    assert any("default equals the original literal" in f.message for f in result.findings)


def test_split_god_file_is_a_pure_noop(copy_of_messy_root, tmp_path):
    graph = parse_module(copy_of_messy_root)
    fkey = next(k for k in graph.file_text if k.endswith("services.tf"))
    proposal = propose_split_file(graph, fkey)
    result = verify_proposal(copy_of_messy_root, graph, proposal, tmp_path / "staging")
    assert result.verdict == Verdict.VERIFIED_WITH_CAVEATS
    assert not any(f.severity == "blocker" for f in result.findings)
    assert "services.tf" in proposal.deleted_files


def test_dead_code_always_requires_human_review(copy_of_messy_root, tmp_path):
    graph = parse_module(copy_of_messy_root)
    proposal = propose_remove_dead_code(graph, "aws_iam_role.orphan_role")
    assert proposal.human_review is True
    result = verify_proposal(copy_of_messy_root, graph, proposal, tmp_path / "staging")
    assert result.verdict == Verdict.HUMAN_REVIEW_REQUIRED


def test_extract_module_with_no_external_refs_is_clean(copy_of_messy_root, tmp_path):
    graph = parse_module(copy_of_messy_root)
    addrs = [
        "aws_sqs_queue.orders_queue",
        "aws_sqs_queue.orders_dlq",
        "aws_cloudwatch_log_group.orders",
        "aws_iam_role.orders_exec",
    ]
    proposal = propose_extract_module(graph, addrs, "orders")
    result = verify_proposal(copy_of_messy_root, graph, proposal, tmp_path / "staging")
    assert result.verdict == Verdict.VERIFIED_WITH_CAVEATS
    assert not any(f.severity == "blocker" for f in result.findings)


def test_extract_module_threads_external_reference_through_as_input(copy_of_messy_root, tmp_path):
    graph = parse_module(copy_of_messy_root)
    proposal = propose_extract_module(graph, ["aws_s3_bucket.assets"], "storage")
    assert "modules/storage/main.tf" in proposal.file_writes
    assert "var." in proposal.file_writes["modules/storage/main.tf"]
    result = verify_proposal(copy_of_messy_root, graph, proposal, tmp_path / "staging")
    assert result.verdict == Verdict.VERIFIED_WITH_CAVEATS
    assert not any(f.severity == "blocker" for f in result.findings)


def test_extract_module_does_not_false_positive_on_literal_strings_with_dots(copy_of_messy_root, tmp_path):
    graph = parse_module(copy_of_messy_root)
    proposal = propose_extract_module(graph, ["aws_iam_role.orders_exec"], "orders_role")
    module_text = proposal.file_writes["modules/orders_role/main.tf"]
    assert "lambda.amazonaws.com" in module_text  # untouched literal, not rewritten to a variable
    assert "var.lambda_amazonaws_com" not in module_text


def test_extract_module_threads_provider_alias_through_call_site(copy_of_messy_root, tmp_path):
    graph = parse_module(copy_of_messy_root)
    proposal = propose_extract_module(graph, ["aws_instance.west_replica"], "west_compute")
    call_text = proposal.file_writes["module_west_compute.tf"]
    assert "providers" in call_text and "aws.west" in call_text
    result = verify_proposal(copy_of_messy_root, graph, proposal, tmp_path / "staging")
    assert result.verdict == Verdict.VERIFIED_WITH_CAVEATS
    assert not any(f.severity == "blocker" for f in result.findings)


def test_unify_duplicates_detects_cross_environment_groups(messy_root):
    env_roots = {"dev": messy_root / "envs" / "dev", "prod": messy_root / "envs" / "prod"}
    graphs = {label: parse_module(p) for label, p in env_roots.items()}
    groups = find_duplicate_groups(graphs)
    names = {(g.resource_type, g.resource_name) for g in groups}
    assert ("aws_s3_bucket", "logs") in names
    assert ("aws_instance", "worker") in names


def test_unify_duplicates_always_requires_human_review(copy_of_messy_root, tmp_path):
    common_root = copy_of_messy_root
    env_roots = {"envs/dev": common_root / "envs" / "dev", "envs/prod": common_root / "envs" / "prod"}
    graphs = {label: parse_module(p) for label, p in env_roots.items()}
    groups = find_duplicate_groups(graphs)
    group = next(g for g in groups if g.resource_name == "logs")
    proposal = propose_unify(graphs, group, "logs_shared", common_root)
    assert proposal.human_review is True
    results = verify_unify_proposal(common_root, env_roots, proposal, tmp_path / "staging")
    assert combined_verdict(results) == Verdict.HUMAN_REVIEW_REQUIRED
    for r in results.values():
        assert not any(f.severity == "blocker" for f in r.findings)
