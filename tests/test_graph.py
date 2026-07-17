from tfrefactor.graph import parse_module


def test_parses_all_resources_and_data_sources(messy_root):
    g = parse_module(messy_root)
    assert "aws_instance.web" in g.resources
    assert "data.aws_availability_zones.available" in g.resources
    assert g.resources["data.aws_availability_zones.available"].kind == "data"


def test_detects_reference_to_another_resource(messy_root):
    g = parse_module(messy_root)
    assert "random_id.bucket_suffix" in g.resources["aws_s3_bucket.assets"].references


def test_detects_variable_reference(messy_root):
    g = parse_module(messy_root)
    assert "var.ports" in g.resources["aws_security_group.app"].references


def test_detects_explicit_provider_alias(messy_root):
    g = parse_module(messy_root)
    assert g.resources["aws_instance.west_replica"].provider == "aws.west"
    assert g.resources["aws_instance.web"].provider is None


def test_detects_for_each_expression(messy_root):
    g = parse_module(messy_root)
    node = g.resources["aws_subnet.by_az"]
    assert node.for_each_expr is not None
    assert node.count_expr is None


def test_canonicalize_ignores_map_key_order():
    from tfrefactor.graph import canonicalize

    a = {"tags": {"b": 2, "a": 1}, "name": "x"}
    b = {"name": "x", "tags": {"a": 1, "b": 2}}
    assert canonicalize(a) == canonicalize(b)


def test_canonicalize_preserves_list_order():
    from tfrefactor.graph import canonicalize

    assert canonicalize({"x": [1, 2, 3]}) != canonicalize({"x": [3, 2, 1]})
