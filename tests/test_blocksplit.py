from tfrefactor.blocksplit import split_top_level_blocks


def _roundtrip(text: str) -> str:
    blocks = split_top_level_blocks(text)
    out = []
    pos = 0
    for b in blocks:
        out.append(text[pos : b.start])
        out.append(b.text)
        pos = b.end
    out.append(text[pos:])
    return "".join(out)


def test_roundtrip_is_lossless_on_fixtures(messy_root):
    for path in messy_root.glob("*.tf"):
        text = path.read_text()
        assert _roundtrip(text) == text, f"roundtrip mismatch in {path}"


def test_comment_before_block_does_not_shift_start(messy_root):
    text = (messy_root / "main.tf").read_text()
    blocks = split_top_level_blocks(text)
    random_id = next(b for b in blocks if b.address == "random_id.bucket_suffix")
    assert random_id.keyword == "resource"
    assert random_id.text.startswith('resource "random_id" "bucket_suffix"')


def test_heredoc_braces_do_not_break_block_boundaries(messy_root):
    text = (messy_root / "main.tf").read_text()
    blocks = split_top_level_blocks(text)
    role = next(b for b in blocks if b.address == "aws_iam_role.orphan_role")
    assert role.text.count("resource") == 1  # heredoc JSON braces weren't parsed as new blocks


def test_dynamic_block_and_string_interpolation_stay_inside_owning_block(messy_root):
    text = (messy_root / "main.tf").read_text()
    blocks = split_top_level_blocks(text)
    sg = next(b for b in blocks if b.address == "aws_security_group.app")
    assert "dynamic" in sg.text
    assert sg.text.count('resource "aws_security_group"') == 1


def test_god_file_splits_into_correct_number_of_blocks(messy_root):
    text = (messy_root / "services.tf").read_text()
    blocks = split_top_level_blocks(text)
    # 15 services * (2 queues + 1 log group + 1 iam role) = 60
    assert len(blocks) == 60
    assert all(b.keyword == "resource" for b in blocks)
