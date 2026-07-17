"""The verification harness: proves (or refuses to claim) that a refactor is
a Terraform no-op by diffing the before/after resource graphs.

This is deliberately NOT a naive "same set of resource addresses, same
attributes" comparison. That naive approach is defeated by well-known
real-world Terraform patterns, each handled explicitly below:

  * ``moved`` blocks - a renamed/relocated resource has a *different*
    address but is the same resource. We resolve identity through the
    moved-block alias map before diffing, in both directions (address in
    attribute references too, e.g. ``aws_instance.web`` becoming
    ``module.compute.aws_instance.web``).
  * Volatile resources (``random_id``, ``random_password``, ``tls_private_key``,
    ``time_static``, ...) - a moved block prevents recreation, but a rename
    WITHOUT one silently regenerates the value and cascades to every
    downstream consumer. We detect this class specially and treat it as
    higher severity than an ordinary resource re-creation.
  * ``count`` <-> ``for_each`` conversion - changes instance keys
    (``foo[0]`` -> ``foo["a"]``) even when the final set of instances is
    identical. Never a no-op without an explicit per-instance moved block,
    which Terraform does not let us synthesize generically - always flagged.
  * Provider aliasing - moving a resource with an explicit
    ``provider = aws.west`` into a module silently falls back to the
    module's default provider unless the module call passes a `providers`
    map. We check that explicitly rather than trusting attribute equality.
  * `for_each` over a `data` source - if the data source's result set
    membership can change between plan and apply (not visible to static
    analysis), we cannot prove the instance keys are stable; we surface
    this as a caveat rather than silently declaring victory.

Anything we can't resolve with confidence is NOT_VERIFIED or
HUMAN_REVIEW_REQUIRED - never silently passed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from tfrefactor.graph import ModuleGraph, canonicalize

VOLATILE_TYPES = {
    "random_id",
    "random_string",
    "random_password",
    "random_uuid",
    "random_integer",
    "random_bytes",
    "random_pet",
    "random_shuffle",
    "tls_private_key",
    "tls_self_signed_cert",
    "tls_cert_request",
    "time_static",
    "time_rotating",
    "time_offset",
}


class Verdict(str, Enum):
    VERIFIED_NOOP = "VERIFIED_NOOP"
    VERIFIED_WITH_CAVEATS = "VERIFIED_WITH_CAVEATS"
    NOT_VERIFIED = "NOT_VERIFIED"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"


@dataclass
class Finding:
    severity: str  # "blocker" | "caveat" | "info"
    address: str
    message: str
    recommended_command: str | None = None


@dataclass
class VerificationResult:
    verdict: Verdict
    findings: list[Finding] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"Verdict: {self.verdict.value}"]
        for f in self.findings:
            tag = {"blocker": "BLOCKER", "caveat": "CAVEAT", "info": "info"}[f.severity]
            lines.append(f"  [{tag}] {f.address}: {f.message}")
            if f.recommended_command:
                lines.append(f"      -> {f.recommended_command}")
        return "\n".join(lines)


def _build_identity_map(moved: list[tuple[str, str]]) -> dict[str, str]:
    """Map new address -> old address, following chains."""
    direct = {to: frm for frm, to in moved}
    resolved: dict[str, str] = {}
    for new in direct:
        seen = {new}
        cur = new
        while cur in direct and direct[cur] not in seen:
            cur = direct[cur]
            seen.add(cur)
        resolved[new] = cur
    return resolved


_ADDR_TOKEN_RE = re.compile(r"[A-Za-z_][\w-]*(?:\.[A-Za-z_][\w-]*)+")


_FULL_VAR_REF_RE = re.compile(r"^\$\{var\.([A-Za-z_][\w-]*)\}$")
_EMBEDDED_VAR_REF_RE = re.compile(r"\$\{var\.([A-Za-z_][\w-]*)\}")


def _substitute_var_defaults(value, variables: dict):
    """Resolve a bare ``${var.NAME}`` value to its declared default.

    This is what lets "parameterize hardcoded value" be provably a no-op:
    the raw attribute textually changes from a literal to a variable
    reference, but if the variable's default equals the original literal,
    Terraform resolves to the identical value *as long as nothing supplies
    an override*. We can't see -var/tfvars from static analysis, so this
    downgrades the finding to a caveat rather than a full pass - see
    verify_no_op.
    """
    if isinstance(value, str):
        full = _FULL_VAR_REF_RE.match(value)
        if full and full.group(1) in variables and "default" in (variables[full.group(1)] or {}):
            return variables[full.group(1)]["default"]

        def repl(m):
            name = m.group(1)
            if name in variables and "default" in (variables[name] or {}):
                return str(variables[name]["default"])
            return m.group(0)

        return _EMBEDDED_VAR_REF_RE.sub(repl, value)
    if isinstance(value, dict):
        return {k: _substitute_var_defaults(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_var_defaults(v, variables) for v in value]
    return value


def _module_input_env(graph: ModuleGraph, address: str) -> dict[str, str] | None:
    """For a resource living inside a (locally-sourced) module, return its
    immediate module call's inputs as {var_name: expression_text}. This is
    what lets extract-module be verified exactly: a required module
    variable's value is *statically known* from the call site, unlike an
    ordinary variable default which can be overridden at apply time."""
    if not address.startswith("module."):
        return None
    modname = address.split(".")[1]
    call = graph.module_calls.get(modname)
    if call is None:
        return None
    skip = {"source", "version", "providers", "for_each", "count", "depends_on"}
    return {k: v for k, v in call.items() if k not in skip}


def _resolve_module_inputs(value, var_env: dict):
    """Resolve ``var.NAME`` against a module call's input expressions.

    Call-site values come in two shapes and both must round-trip losslessly:
    a bare expression like ``aws.west`` (hcl2 gives us ``${aws.west}``,
    wrapper included) or a plain literal like ``"t3.small"`` or a tags map
    (no wrapper - it just *is* the value). We never add our own wrapping;
    we substitute whatever hcl2 gave us, verbatim.
    """
    if isinstance(value, str):
        full = _FULL_VAR_REF_RE.match(value)
        if full and full.group(1) in var_env:
            return var_env[full.group(1)]

        def repl(m):
            name = m.group(1)
            if name in var_env and isinstance(var_env[name], str):
                return var_env[name]
            return m.group(0)

        return _EMBEDDED_VAR_REF_RE.sub(repl, value)
    if isinstance(value, dict):
        return {k: _resolve_module_inputs(v, var_env) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_module_inputs(v, var_env) for v in value]
    return value


def _rewrite_addresses(value, rewrite: dict[str, str]):
    """Recursively rewrite any embedded address token per `rewrite` (new->old).

    A matched dotted token like ``random_id.suffix.hex`` may be a resource
    address (``random_id.suffix``) plus an attribute path (``.hex``), so we
    try progressively shorter prefixes rather than requiring an exact match.
    """
    if isinstance(value, str):
        def repl(m):
            token = m.group(0)
            parts = token.split(".")
            for cut in range(len(parts), 1, -1):
                prefix = ".".join(parts[:cut])
                if prefix in rewrite:
                    suffix = ".".join(parts[cut:])
                    return rewrite[prefix] + ("." + suffix if suffix else "")
            return token
        return _ADDR_TOKEN_RE.sub(repl, value)
    if isinstance(value, dict):
        return {k: _rewrite_addresses(v, rewrite) for k, v in value.items()}
    if isinstance(value, list):
        return [_rewrite_addresses(v, rewrite) for v in value]
    return value


def verify_no_op(
    before: ModuleGraph,
    after: ModuleGraph,
    *,
    expected_removals: frozenset[str] = frozenset(),
    human_review: bool = False,
    human_review_reason: str | None = None,
) -> VerificationResult:
    findings: list[Finding] = []

    # `moved` blocks accumulate across refactors and are never expected to be
    # deleted - Terraform keeps them around indefinitely so very old
    # addresses can still be adopted. That means a moved block from a
    # *previous, already-applied* refactor may still be sitting in the repo
    # and would otherwise be misread as applying to *this* diff. Only trust
    # a mapping whose "from" address is actually present in the current
    # before-graph; otherwise it's stale history, not part of this change.
    new_to_old = {
        new: old for new, old in _build_identity_map(after.moved).items() if old in before.resources
    }
    old_to_new = {v: k for k, v in new_to_old.items()}

    def identity_of_after(addr: str) -> str:
        return new_to_old.get(addr, addr)

    before_addrs = set(before.resources)
    after_identities = {identity_of_after(a): a for a in after.resources}

    removed = before_addrs - set(after_identities) - expected_removals
    added = set(after_identities) - before_addrs

    for addr in sorted(expected_removals & before_addrs):
        findings.append(Finding("info", addr, "removed as part of this refactor (human-confirmed)"))

    # Heuristic: an address in `removed` and one in `added` with identical
    # canonical attributes and NO moved block is almost certainly an
    # unrecorded rename - Terraform will destroy+recreate it.
    for r_addr in sorted(removed):
        r_node = before.resources[r_addr]
        r_canon = canonicalize(r_node.attributes)
        for a_identity in sorted(added):
            a_node = after.resources[after_identities[a_identity]]
            if a_node.type != r_node.type:
                continue
            if canonicalize(a_node.attributes) == r_canon:
                sev = "blocker"
                extra = ""
                if r_node.type in VOLATILE_TYPES:
                    extra = (
                        " This is a volatile resource type - recreation generates a NEW "
                        "value and silently changes everything downstream that reads it."
                    )
                findings.append(
                    Finding(
                        sev,
                        r_addr,
                        f"looks like an unrecorded rename to '{after_identities[a_identity]}' "
                        f"(identical attributes, no moved block).{extra}",
                        recommended_command=f'Add: moved {{ from = {r_addr}\n  to   = {after_identities[a_identity]} }}',
                    )
                )

    for addr in sorted(removed):
        findings.append(
            Finding(
                "blocker",
                addr,
                "present before, absent after, with no moved block - Terraform will destroy this resource.",
                recommended_command="terraform plan -out=tfplan  # confirm no unexpected destroys",
            )
        )
    for identity in sorted(added):
        actual = after_identities[identity]
        findings.append(
            Finding(
                "blocker",
                actual,
                "present after, absent before, with no moved block - Terraform will create this as new infrastructure "
                "rather than adopting an existing resource.",
            )
        )

    common = before_addrs & set(after_identities)
    for identity in sorted(common):
        b_node = before.resources[identity]
        a_node = after.resources[after_identities[identity]]

        b_attrs = canonicalize(b_node.attributes)
        a_rewritten_raw = _rewrite_addresses(a_node.attributes, new_to_old)
        a_attrs_rewritten = canonicalize(a_rewritten_raw)

        if b_attrs != a_attrs_rewritten:
            new_addr = after_identities[identity]
            module_env = _module_input_env(after, new_addr)
            module_resolved_raw = _resolve_module_inputs(a_rewritten_raw, module_env) if module_env else a_rewritten_raw
            module_resolved = canonicalize(_rewrite_addresses(module_resolved_raw, new_to_old))

            if module_env and b_attrs == module_resolved:
                findings.append(
                    Finding(
                        "info",
                        identity,
                        "attribute(s) rewritten to module input variable(s) whose call-site expression is "
                        "exactly the original reference - statically equivalent.",
                    )
                )
                continue

            a_attrs_resolved = canonicalize(_substitute_var_defaults(module_resolved_raw, after.variables))
            if b_attrs == a_attrs_resolved:
                findings.append(
                    Finding(
                        "caveat",
                        identity,
                        "attribute(s) replaced with a variable whose default equals the original literal - "
                        "verified assuming no -var/tfvars override supplies a different value at apply time.",
                    )
                )
            else:
                findings.append(
                    Finding("blocker", identity, "attributes differ after canonicalization - not a no-op.")
                )

        if bool(b_node.count_expr) != bool(a_node.count_expr) or bool(b_node.for_each_expr) != bool(
            a_node.for_each_expr
        ):
            findings.append(
                Finding(
                    "blocker",
                    identity,
                    "count <-> for_each conversion detected. This changes instance keys "
                    '(e.g. foo[0] -> foo["a"]) even when the instance set is unchanged - '
                    "Terraform cannot adopt across this without a moved block per instance.",
                    recommended_command="terraform plan -out=tfplan  # inspect per-index replacements",
                )
            )
        elif b_node.for_each_expr and a_node.for_each_expr:
            b_fe = _rewrite_addresses(b_node.for_each_expr, {})
            a_fe = _rewrite_addresses(a_node.for_each_expr, new_to_old)
            if "data\\." in a_fe or "data." in a_fe:
                findings.append(
                    Finding(
                        "caveat",
                        identity,
                        "for_each iterates over a data source; membership can change between "
                        "plan and apply in ways static analysis can't see. Verify with a real plan.",
                        recommended_command="terraform plan -out=tfplan",
                    )
                )

        if b_node.provider != a_node.provider:
            new_addr = old_to_new.get(identity, identity)
            module_prefix = new_addr.split(".")[1] if new_addr.startswith("module.") else None
            passthrough_ok = False
            if module_prefix and b_node.provider:
                mod_call = after.module_calls.get(module_prefix, {})
                providers_map = mod_call.get("providers", {})
                passthrough_ok = any(b_node.provider in str(v) for v in providers_map.values())
            if not passthrough_ok:
                findings.append(
                    Finding(
                        "blocker",
                        identity,
                        f"provider resolution changed (was '{b_node.provider or 'default'}', "
                        f"module call does not pass it through) - resource would be created "
                        f"against the wrong provider/account/region.",
                        recommended_command=f'Add to the module call: providers = {{ {b_node.provider.split(".")[0] if b_node.provider else "aws"} = {b_node.provider} }}'
                        if b_node.provider
                        else None,
                    )
                )

        if b_node.type in VOLATILE_TYPES and identity in old_to_new and old_to_new[identity] != identity:
            findings.append(
                Finding(
                    "caveat",
                    identity,
                    f"volatile resource type '{b_node.type}' relocated via moved block - state is "
                    "preserved so the value does NOT change, but confirm with `terraform plan` since "
                    "some providers still perturb output on refresh.",
                    recommended_command="terraform plan -out=tfplan",
                )
            )

    blockers = [f for f in findings if f.severity == "blocker"]
    caveats = [f for f in findings if f.severity == "caveat"]

    if human_review:
        findings.append(Finding("info", "*", human_review_reason or "requires human review before applying"))
        verdict = Verdict.HUMAN_REVIEW_REQUIRED
    elif blockers:
        verdict = Verdict.NOT_VERIFIED
    elif caveats:
        verdict = Verdict.VERIFIED_WITH_CAVEATS
    else:
        verdict = Verdict.VERIFIED_NOOP

    return VerificationResult(verdict=verdict, findings=findings)
