"""Read-only local dashboard: browse scan findings and refactor proposals
with their verification verdicts. Never writes to disk - there is no
"apply" endpoint. Applying a refactor stays a deliberate CLI action
(`tfrefactor propose ... --apply`), per the "human review required, nothing
auto-applied" non-negotiable.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from tfrefactor.anti_patterns import scan_all
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

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "messy_project"

app = FastAPI(title="tfrefactor dashboard")


def _resolve(directory: str) -> Path:
    p = Path(directory)
    if not p.is_absolute():
        p = (REPO_ROOT / directory).resolve()
    if not p.is_dir():
        raise HTTPException(404, f"not a directory: {directory}")
    return p


def _finding_dict(f):
    return {
        "severity": f.severity,
        "address": f.address,
        "message": f.message,
        "recommended_command": f.recommended_command,
    }


def _result_dict(result):
    return {"verdict": result.verdict.value, "findings": [_finding_dict(f) for f in result.findings]}


@app.get("/api/presets")
def presets():
    return {
        "presets": [
            {"label": "messy_project (root)", "path": str(FIXTURE_ROOT)},
            {"label": "messy_project/envs/dev", "path": str(FIXTURE_ROOT / "envs" / "dev")},
            {"label": "messy_project/envs/prod", "path": str(FIXTURE_ROOT / "envs" / "prod")},
        ]
    }


@app.get("/api/resources")
def resources(directory: str):
    root = _resolve(directory)
    graph = parse_module(root)
    return {
        "resources": [
            {"address": addr, "type": n.type, "kind": n.kind, "file": str(Path(n.file).name)}
            for addr, n in sorted(graph.resources.items())
        ],
        "files": sorted({str(Path(p).name) for p in graph.file_text}),
    }


class ScanRequest(BaseModel):
    directory: str
    god_file_threshold: int = 500


@app.post("/api/scan")
def scan(req: ScanRequest):
    root = _resolve(req.directory)
    graph = parse_module(root)
    findings = scan_all(graph, god_file_threshold=req.god_file_threshold)
    return {
        "resource_count": len(graph.resources),
        "variable_count": len(graph.variables),
        "findings": [
            {"severity": f.severity, "category": f.category, "location": f.location, "message": f.message}
            for f in findings
        ],
    }


class ProposeRequest(BaseModel):
    directory: str
    op: str
    address: Optional[str] = None
    new_name: Optional[str] = None
    attr_key: Optional[str] = None
    var_name: Optional[str] = None
    file_name: Optional[str] = None
    threshold: int = 500
    addresses: Optional[list[str]] = None
    module_name: Optional[str] = None


@app.post("/api/propose")
def propose(req: ProposeRequest):
    root = _resolve(req.directory)
    graph = parse_module(root)

    try:
        if req.op == "rename":
            proposal = propose_rename(graph, req.address, req.new_name)
        elif req.op == "parameterize":
            proposal = propose_parameterize(graph, req.address, req.attr_key, req.var_name)
        elif req.op == "split-file":
            fkey = next((k for k in graph.file_text if Path(k).name == req.file_name), None)
            if fkey is None:
                raise ValueError(f"file not found: {req.file_name}")
            proposal = propose_split_file(graph, fkey, threshold_lines=req.threshold)
        elif req.op == "extract-module":
            proposal = propose_extract_module(graph, req.addresses or [], req.module_name)
        elif req.op == "dead-code":
            proposal = propose_remove_dead_code(graph, req.address)
        else:
            raise ValueError(f"unknown op: {req.op}")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    with tempfile.TemporaryDirectory() as staging:
        result = verify_proposal(root, graph, proposal, Path(staging) / "staged")

    return {
        "description": proposal.description,
        "human_review": proposal.human_review,
        "human_review_reason": proposal.human_review_reason,
        "file_writes": proposal.file_writes,
        "deleted_files": sorted(proposal.deleted_files),
        "result": _result_dict(result),
    }


class UnifyRequest(BaseModel):
    common_root: str
    env_dirs: list[str]


@app.post("/api/unify")
def unify(req: UnifyRequest):
    root = _resolve(req.common_root)
    env_roots = {d: (root / d) for d in req.env_dirs}
    for label, p in env_roots.items():
        if not p.is_dir():
            raise HTTPException(404, f"not a directory: {label}")
    graphs = {label: parse_module(p) for label, p in env_roots.items()}
    groups = find_duplicate_groups(graphs)

    out = []
    for g in groups:
        module_name = f"{g.resource_name}_shared"
        proposal = propose_unify(graphs, g, module_name, root)
        with tempfile.TemporaryDirectory() as staging:
            results = verify_unify_proposal(root, env_roots, proposal, Path(staging) / "staged")
        out.append(
            {
                "resource_type": g.resource_type,
                "resource_name": g.resource_name,
                "varying_keys": g.varying_keys,
                "shared_attrs": g.shared_attrs,
                "description": proposal.description,
                "file_writes": proposal.file_writes,
                "per_environment": {label: _result_dict(r) for label, r in results.items()},
                "combined_verdict": combined_verdict(results).value,
            }
        )
    return {"groups": out}


static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    return (static_dir / "index.html").read_text(encoding="utf-8")
