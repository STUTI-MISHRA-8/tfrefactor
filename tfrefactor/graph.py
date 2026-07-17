"""Resource graph construction and canonicalization.

We use python-hcl2 for semantic parsing (attributes, references, structure)
and blocksplit.py for exact source spans (needed by refactor operations that
cut/paste text). The two are correlated by address, not by position, since
hcl2 doesn't expose byte offsets.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from pathlib import Path

import hcl2
from hcl2.utils import SerializationOptions

from tfrefactor.blocksplit import Block, split_top_level_blocks

_HCL2_OPTS = SerializationOptions(
    strip_string_quotes=True, explicit_blocks=False, with_comments=False
)

_REF_RE = re.compile(
    r"(?:"
    r"(?P<data>data\.[A-Za-z_][\w-]*\.[A-Za-z_][\w-]*)"
    r"|(?P<var>var\.[A-Za-z_][\w-]*)"
    r"|(?P<local>local\.[A-Za-z_][\w-]*)"
    r"|(?P<module>module\.[A-Za-z_][\w-]*)"
    r"|(?P<res>[A-Za-z_][\w-]*\.[A-Za-z_][\w-]*)"
    r")"
)

_RESERVED_PREFIXES = {"var", "local", "module", "data", "each", "count", "path", "terraform", "self"}


@dataclass
class ResourceNode:
    address: str
    kind: str  # "resource" | "data"
    type: str
    name: str
    file: str
    attributes: dict
    provider: str | None = None
    count_expr: str | None = None
    for_each_expr: str | None = None
    depends_on: tuple[str, ...] = ()
    references: frozenset[str] = field(default_factory=frozenset)


@dataclass
class ModuleGraph:
    root: Path
    resources: dict[str, ResourceNode] = field(default_factory=dict)
    variables: dict[str, dict] = field(default_factory=dict)
    outputs: dict[str, dict] = field(default_factory=dict)
    locals_: dict[str, object] = field(default_factory=dict)
    providers: list[dict] = field(default_factory=list)
    module_calls: dict[str, dict] = field(default_factory=dict)
    moved: list[tuple[str, str]] = field(default_factory=list)
    file_text: dict[str, str] = field(default_factory=dict)
    file_blocks: dict[str, list[Block]] = field(default_factory=dict)


def _unwrap(value):
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return value[2:-1]
    return value


def canonicalize(value):
    """Recursively sort object/map keys (order-insensitive in HCL semantics);
    leave lists as-is (order is semantically meaningful for lists/tuples)."""
    if isinstance(value, dict):
        return {k: canonicalize(value[k]) for k in sorted(value.keys())}
    if isinstance(value, list):
        return [canonicalize(v) for v in value]
    return value


def _iter_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _iter_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _iter_strings(v)


def extract_references(attributes: dict, known_resource_addrs: set[str]) -> frozenset[str]:
    refs: set[str] = set()
    for s in _iter_strings(attributes):
        for m in _REF_RE.finditer(s):
            if m.group("data"):
                refs.add(m.group("data"))
            elif m.group("var"):
                refs.add(m.group("var"))
            elif m.group("local"):
                refs.add(m.group("local"))
            elif m.group("module"):
                head = m.group("module").split(".")
                refs.add(".".join(head[:2]))
            elif m.group("res"):
                candidate = m.group("res")
                prefix = candidate.split(".")[0]
                if prefix in _RESERVED_PREFIXES:
                    continue
                if candidate in known_resource_addrs:
                    refs.add(candidate)
    return frozenset(refs)


def _first_pass_collect_addresses(parsed_files: dict[str, dict]) -> set[str]:
    addrs = set()
    for data in parsed_files.values():
        for block in data.get("resource", []):
            for rtype, named in block.items():
                for name in named:
                    addrs.add(f"{rtype}.{name}")
        for block in data.get("data", []):
            for rtype, named in block.items():
                for name in named:
                    addrs.add(f"data.{rtype}.{name}")
    return addrs


def parse_module(root: Path, *, _prefix: str = "") -> ModuleGraph:
    """Parse a module's own .tf files, then recurse into local module calls
    (``source = "./..."`` or ``"../..."``) so the returned graph's resource
    addresses match what Terraform actually resolves - ``module.name.type.name``
    for anything living in a child module. Remote/registry module sources are
    not expanded; resources inside them are invisible to us and any refactor
    touching them is out of scope for static verification (surfaced as a
    caveat by the caller, not silently ignored).
    """
    root = Path(root)
    graph = ModuleGraph(root=root)
    parsed_files: dict[str, dict] = {}

    tf_files = sorted(p for p in root.glob("*.tf"))
    for path in tf_files:
        text = path.read_text(encoding="utf-8")
        graph.file_text[str(path)] = text
        graph.file_blocks[str(path)] = split_top_level_blocks(text)
        try:
            parsed_files[str(path)] = hcl2.loads(text, serialization_options=_HCL2_OPTS)
        except Exception as exc:  # pragma: no cover - defensive
            raise ValueError(f"Failed to parse {path}: {exc}") from exc

    known_addrs = _first_pass_collect_addresses(parsed_files)

    for fpath, data in parsed_files.items():
        for block in data.get("resource", []):
            for rtype, named in block.items():
                for name, attrs in named.items():
                    attrs = attrs or {}
                    address = f"{rtype}.{name}"
                    provider = _unwrap(attrs.get("provider")) if "provider" in attrs else None
                    depends_on = tuple(_unwrap(x) for x in attrs.get("depends_on", []) or [])
                    node = ResourceNode(
                        address=address,
                        kind="resource",
                        type=rtype,
                        name=name,
                        file=fpath,
                        attributes=attrs,
                        provider=provider,
                        count_expr=_unwrap(attrs["count"]) if "count" in attrs else None,
                        for_each_expr=_unwrap(attrs["for_each"]) if "for_each" in attrs else None,
                        depends_on=depends_on,
                        references=extract_references(attrs, known_addrs),
                    )
                    graph.resources[address] = node

        for block in data.get("data", []):
            for rtype, named in block.items():
                for name, attrs in named.items():
                    attrs = attrs or {}
                    address = f"data.{rtype}.{name}"
                    node = ResourceNode(
                        address=address,
                        kind="data",
                        type=rtype,
                        name=name,
                        file=fpath,
                        attributes=attrs,
                        for_each_expr=_unwrap(attrs["for_each"]) if "for_each" in attrs else None,
                        references=extract_references(attrs, known_addrs),
                    )
                    graph.resources[address] = node

        for block in data.get("variable", []):
            for name, attrs in block.items():
                graph.variables[name] = attrs or {}

        for block in data.get("output", []):
            for name, attrs in block.items():
                graph.outputs[name] = attrs or {}

        for block in data.get("locals", []):
            for name, val in block.items():
                graph.locals_[name] = val

        for block in data.get("provider", []):
            for ptype, attrs in block.items():
                graph.providers.append({"type": ptype, **(attrs or {})})

        for block in data.get("module", []):
            for name, attrs in block.items():
                graph.module_calls[name] = attrs or {}

        for block in data.get("moved", []):
            frm = _unwrap(block.get("from"))
            to = _unwrap(block.get("to"))
            if frm and to:
                graph.moved.append((frm, to))

    if _prefix:
        graph.resources = {
            _prefix + addr: replace(node, address=_prefix + addr) for addr, node in graph.resources.items()
        }

    for name, attrs in graph.module_calls.items():
        source = attrs.get("source")
        if not isinstance(source, str) or not (source.startswith("./") or source.startswith("../")):
            continue  # remote/registry module - out of scope for static verification
        child_root = (root / source).resolve()
        if not child_root.is_dir():
            continue
        child_graph = parse_module(child_root, _prefix=f"{_prefix}module.{name}.")
        graph.resources.update(child_graph.resources)
        graph.moved.extend(child_graph.moved)

    return graph
