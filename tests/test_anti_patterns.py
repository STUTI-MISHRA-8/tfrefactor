from tfrefactor.anti_patterns import scan_all
from tfrefactor.graph import parse_module


def test_flags_hardcoded_region(messy_root):
    g = parse_module(messy_root)
    findings = scan_all(g)
    assert any(f.category == "hardcoded-region" for f in findings)


def test_flags_hardcoded_ami(messy_root):
    g = parse_module(messy_root)
    findings = scan_all(g)
    assert any(f.category == "hardcoded-value" and "ami" in f.message for f in findings)


def test_flags_missing_provider_version_pin(messy_root):
    g = parse_module(messy_root)
    findings = scan_all(g)
    assert any(f.category == "missing-version-pin" for f in findings)


def test_flags_god_file(messy_root):
    g = parse_module(messy_root)
    findings = scan_all(g, god_file_threshold=500)
    assert any(f.category == "god-file" for f in findings)


def test_flags_referential_dead_code_but_not_leaf_resources(messy_root):
    g = parse_module(messy_root)
    findings = scan_all(g)
    dead_code_addrs = {f.location for f in findings if f.category == "possible-dead-code"}
    assert "aws_iam_role.orphan_role" in dead_code_addrs
    # leaf resources with no inbound references are normal, not "dead code"
    assert "aws_sqs_queue.orders_queue" not in dead_code_addrs
    assert "aws_cloudwatch_log_group.orders" not in dead_code_addrs
