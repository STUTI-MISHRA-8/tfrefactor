from tfrefactor.graph import parse_module
from tfrefactor.verify import Verdict, verify_no_op


def _patch(root, filename, old, new):
    p = root / filename
    text = p.read_text()
    assert old in text
    p.write_text(text.replace(old, new))


def test_identical_graph_is_a_noop_modulo_known_caveats(messy_root, copy_of_messy_root):
    before = parse_module(messy_root)
    after = parse_module(copy_of_messy_root)
    r = verify_no_op(before, after)
    assert r.verdict == Verdict.VERIFIED_WITH_CAVEATS
    assert all(f.severity != "blocker" for f in r.findings)


def test_rename_with_moved_block_is_verified(messy_root, copy_of_messy_root):
    _patch(copy_of_messy_root, "main.tf", 'resource "aws_instance" "web"', 'resource "aws_instance" "web_server"')
    (copy_of_messy_root / "main.tf").write_text(
        (copy_of_messy_root / "main.tf").read_text()
        + "\nmoved {\n  from = aws_instance.web\n  to   = aws_instance.web_server\n}\n"
    )
    before = parse_module(messy_root)
    after = parse_module(copy_of_messy_root)
    r = verify_no_op(before, after)
    assert r.verdict == Verdict.VERIFIED_WITH_CAVEATS
    assert not any(f.severity == "blocker" for f in r.findings)


def test_rename_without_moved_block_is_rejected(messy_root, copy_of_messy_root):
    _patch(copy_of_messy_root, "main.tf", 'resource "aws_instance" "web"', 'resource "aws_instance" "web_server"')
    before = parse_module(messy_root)
    after = parse_module(copy_of_messy_root)
    r = verify_no_op(before, after)
    assert r.verdict == Verdict.NOT_VERIFIED
    assert any("unrecorded rename" in f.message for f in r.findings)


def test_volatile_resource_renamed_with_moved_block_is_a_caveat_not_a_pass(messy_root, copy_of_messy_root):
    _patch(copy_of_messy_root, "main.tf", 'resource "random_id" "bucket_suffix"', 'resource "random_id" "suffix"')
    _patch(copy_of_messy_root, "main.tf", "random_id.bucket_suffix.hex", "random_id.suffix.hex")
    (copy_of_messy_root / "main.tf").write_text(
        (copy_of_messy_root / "main.tf").read_text()
        + "\nmoved {\n  from = random_id.bucket_suffix\n  to   = random_id.suffix\n}\n"
    )
    before = parse_module(messy_root)
    after = parse_module(copy_of_messy_root)
    r = verify_no_op(before, after)
    assert r.verdict == Verdict.VERIFIED_WITH_CAVEATS
    assert any("volatile resource type" in f.message for f in r.findings)


def test_count_to_for_each_conversion_is_rejected(messy_root, copy_of_messy_root):
    old = (
        'resource "aws_instance" "west_replica" {\n'
        "  provider      = aws.west\n"
        '  ami           = "ami-0abcdef1234567890"\n'
        '  instance_type = "t3.micro"\n'
        "}"
    )
    new = (
        'resource "aws_instance" "west_replica" {\n'
        '  for_each      = toset(["a"])\n'
        "  provider      = aws.west\n"
        '  ami           = "ami-0abcdef1234567890"\n'
        '  instance_type = "t3.micro"\n'
        "}"
    )
    _patch(copy_of_messy_root, "main.tf", old, new)
    before = parse_module(messy_root)
    after = parse_module(copy_of_messy_root)
    r = verify_no_op(before, after)
    assert r.verdict == Verdict.NOT_VERIFIED
    assert any("count <-> for_each" in f.message for f in r.findings)


def test_stale_moved_block_from_a_previous_refactor_is_ignored(messy_root, copy_of_messy_root):
    """A moved block whose `from` no longer exists in the current before-graph
    is history, not part of this diff - it must not be misapplied."""
    _patch(copy_of_messy_root, "main.tf", 'resource "aws_instance" "web"', 'resource "aws_instance" "web_server"')
    (copy_of_messy_root / "main.tf").write_text(
        (copy_of_messy_root / "main.tf").read_text()
        + "\nmoved {\n  from = aws_instance.web\n  to   = aws_instance.web_server\n}\n"
    )
    # `before` here already has "web_server" (the rename already happened, matching
    # the state of a repo after that refactor was applied) - the moved block is stale.
    before = parse_module(copy_of_messy_root)
    after = parse_module(copy_of_messy_root)
    r = verify_no_op(before, after)
    assert r.verdict == Verdict.VERIFIED_WITH_CAVEATS
    assert not any(f.severity == "blocker" for f in r.findings)


def test_removed_resource_without_acknowledgement_is_rejected(messy_root, copy_of_messy_root):
    before = parse_module(messy_root)
    after = parse_module(copy_of_messy_root)
    # simulate: dead-code op deleted a resource but caller forgot expected_removals
    node = before.resources["aws_iam_role.orphan_role"]
    text = (copy_of_messy_root / "main.tf").read_text()
    block = next(b for b in after.file_blocks[str(copy_of_messy_root / "main.tf")] if b.address == "aws_iam_role.orphan_role")
    (copy_of_messy_root / "main.tf").write_text(text[: block.start] + text[block.end :])
    after = parse_module(copy_of_messy_root)
    r = verify_no_op(before, after)
    assert r.verdict == Verdict.NOT_VERIFIED


def test_removed_resource_with_acknowledgement_and_human_review_flag(messy_root, copy_of_messy_root):
    before = parse_module(messy_root)
    text = (copy_of_messy_root / "main.tf").read_text()
    block = next(
        b
        for b in before.file_blocks[str(messy_root / "main.tf")]
        if b.address == "aws_iam_role.orphan_role"
    )
    (copy_of_messy_root / "main.tf").write_text(text[: block.start] + text[block.end :])
    after = parse_module(copy_of_messy_root)
    r = verify_no_op(
        before,
        after,
        expected_removals=frozenset({"aws_iam_role.orphan_role"}),
        human_review=True,
        human_review_reason="test",
    )
    assert r.verdict == Verdict.HUMAN_REVIEW_REQUIRED
