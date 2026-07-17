"""Static anti-pattern detection over a parsed module graph.

These are advisory only - nothing here blocks a refactor proposal, they
just surface pre-existing issues in the codebase (separate from the
no-op verification of a *change*).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from tfrefactor.graph import ModuleGraph

_AWS_ACCESS_KEY_RE = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_SECRET_KEY_NAMES = re.compile(r"(password|secret|private_key|access_key|api_key|token)$", re.I)
_HARDCODED_REGION_RE = re.compile(r"^[a-z]{2}-[a-z]+-\d$")
_HARDCODED_AMI_RE = re.compile(r"^ami-[0-9a-f]{8,}$")


@dataclass
class AntiPattern:
    severity: str  # "high" | "medium" | "low"
    category: str
    location: str
    message: str


def _walk_attrs(prefix: str, attrs: dict, findings: list[AntiPattern]):
    for key, value in attrs.items():
        if isinstance(value, str):
            if _AWS_ACCESS_KEY_RE.search(value):
                findings.append(
                    AntiPattern("high", "hardcoded-secret", prefix, f"attribute '{key}' contains what looks like a literal AWS access key ID")
                )
            elif _SECRET_KEY_NAMES.search(key) and not value.startswith("${"):
                findings.append(
                    AntiPattern(
                        "high",
                        "hardcoded-secret",
                        prefix,
                        f"attribute '{key}' looks like a credential but is a literal string, not a var/local/data reference",
                    )
                )
            elif _HARDCODED_REGION_RE.match(value):
                findings.append(
                    AntiPattern("medium", "hardcoded-region", prefix, f"attribute '{key}' hardcodes region '{value}' instead of a variable")
                )
            elif _HARDCODED_AMI_RE.match(value):
                findings.append(
                    AntiPattern("low", "hardcoded-value", prefix, f"attribute '{key}' hardcodes AMI id '{value}' - consider a variable or data source")
                )
        elif isinstance(value, dict):
            _walk_attrs(prefix, value, findings)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _walk_attrs(prefix, item, findings)


def scan_hardcoded_values(graph: ModuleGraph) -> list[AntiPattern]:
    findings: list[AntiPattern] = []
    for addr, node in graph.resources.items():
        _walk_attrs(addr, node.attributes, findings)
    for p in graph.providers:
        region = p.get("region")
        if isinstance(region, str) and _HARDCODED_REGION_RE.match(region):
            label = p["type"] + (f".{p['alias']}" if "alias" in p else "")
            findings.append(
                AntiPattern("medium", "hardcoded-region", f"provider.{label}", f"region hardcoded to '{region}'")
            )
    return findings


def scan_provider_pinning(graph: ModuleGraph) -> list[AntiPattern]:
    findings: list[AntiPattern] = []
    pinned_types: set[str] = set()
    for fpath, blocks in graph.file_blocks.items():
        for b in blocks:
            if b.keyword == "terraform" and "required_providers" in b.text:
                # crude but sufficient: does each provider entry carry a version key?
                m = re.search(r"required_providers\s*\{(.*?)\n\s*\}", b.text, re.S)
                if m:
                    body = m.group(1)
                    for name_m in re.finditer(r"(\w+)\s*=\s*\{([^}]*)\}", body):
                        if "version" in name_m.group(2):
                            pinned_types.add(name_m.group(1))
    seen_types = {p["type"] for p in graph.providers}
    for ptype in seen_types:
        if ptype not in pinned_types:
            findings.append(
                AntiPattern(
                    "medium",
                    "missing-version-pin",
                    f"provider.{ptype}",
                    f"provider '{ptype}' has no version constraint in required_providers - upgrades can silently change behavior",
                )
            )
    return findings


def scan_god_files(graph: ModuleGraph, threshold_lines: int = 500) -> list[AntiPattern]:
    findings = []
    for fpath, text in graph.file_text.items():
        n = text.count("\n") + 1
        if n >= threshold_lines:
            findings.append(
                AntiPattern("low", "god-file", fpath, f"{n} lines (>= {threshold_lines}) - candidate for splitting")
            )
    return findings



# Resource types where "nothing else in the graph points at me" is a
# meaningful signal, because these types exist specifically to be attached
# to / referenced by something else. Deliberately NOT applied to leaf
# resources (queues, log groups, instances, buckets, ...) that are
# routinely unreferenced within Terraform yet very much alive - they're
# consumed by applications at runtime, not by sibling resources. Flagging
# those would just be noise that trains reviewers to ignore the tool.
_REFERENTIAL_TYPES = {
    "aws_iam_role",
    "aws_iam_policy",
    "aws_security_group",
    "aws_subnet",
    "aws_vpc",
    "aws_kms_key",
    "aws_launch_template",
    "aws_acm_certificate",
    "aws_route_table",
}


def scan_orphan_resources(graph: ModuleGraph) -> list[AntiPattern]:
    from tfrefactor.graph import extract_references

    referenced: set[str] = set()
    for node in graph.resources.values():
        referenced |= node.references
    for output in graph.outputs.values():
        referenced |= extract_references(output, set(graph.resources))

    findings = []
    for addr, node in graph.resources.items():
        if (
            node.kind == "resource"
            and node.type in _REFERENTIAL_TYPES
            and addr not in referenced
        ):
            findings.append(
                AntiPattern(
                    "low",
                    "possible-dead-code",
                    addr,
                    f"a '{node.type}' that nothing else in the graph references - candidate for removal "
                    "(human review required: static analysis can't prove nothing external/out-of-repo depends on it)",
                )
            )
    return findings


def scan_all(graph: ModuleGraph, god_file_threshold: int = 500) -> list[AntiPattern]:
    findings = []
    findings += scan_hardcoded_values(graph)
    findings += scan_provider_pinning(graph)
    findings += scan_god_files(graph, god_file_threshold)
    findings += scan_orphan_resources(graph)
    return findings
