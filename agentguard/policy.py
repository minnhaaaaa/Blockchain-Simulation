from dataclasses import dataclass
from typing import Any

from agentguard.canonical import canonical_bytes, sha256_hex
from agentguard.schema_validation import SchemaValidationError, SchemaValidator


@dataclass(frozen=True)
class PolicyDecision:
    decision: str
    reason_code: str
    reason: str
    rule_id: str | None


class PolicyEvaluator:
    def __init__(self, validator: SchemaValidator, max_schema_nodes: int, max_schema_depth: int):
        if max_schema_nodes<=0 or max_schema_depth<=0: raise ValueError("policy schema bounds must be positive")
        self.validator=validator; self.max_schema_nodes=max_schema_nodes; self.max_schema_depth=max_schema_depth

    def validate_complexity(self,policy:dict):
        for rule in policy["rules"]:
            nodes=0
            def visit(value,depth):
                nonlocal nodes
                nodes+=1
                if nodes>self.max_schema_nodes or depth>self.max_schema_depth:
                    raise ValueError("argument constraint schema exceeds configured complexity")
                if isinstance(value,dict):
                    for item in value.values(): visit(item,depth+1)
                elif isinstance(value,list):
                    for item in value: visit(item,depth+1)
            visit(rule["argument_constraints"],0)

    def evaluate(self, policy: dict, action: dict, write_scopes: list[str], now_ms: int) -> PolicyDecision:
        try: self.validate_complexity(policy)
        except ValueError as exc: return PolicyDecision("deny","POLICY_TOO_COMPLEX",str(exc),None)
        expiry=policy.get("expires_at_ms")
        if expiry is not None and now_ms >= expiry:
            return PolicyDecision("deny", "POLICY_EXPIRED", "The policy has expired.", None)
        matches=[rule for rule in policy["rules"] if rule["tool_id"] == action["tool_id"]]
        if not matches: return PolicyDecision("deny", "NO_MATCHING_RULE", "No rule permits this tool.", None)
        denied=next((rule for rule in matches if rule["effect"]=="deny"), None)
        if denied: return PolicyDecision("deny", "EXPLICIT_DENY", "A matching rule explicitly denies this tool.", denied.get("rule_id"))
        for rule in matches:
            if not set(action["input_artifact_ids"]).issubset(rule["read_artifact_ids"]): continue
            if not set(write_scopes).issubset(rule["write_scopes"]): continue
            try: self.validator.validate_fragment(rule["argument_constraints"], action["arguments"])
            except SchemaValidationError: continue
            decision="approval_required" if rule["effect"]=="approval_required" else "allow"
            return PolicyDecision(decision, "RULE_MATCH", "The action matches the permission rule.", rule.get("rule_id"))
        return PolicyDecision("deny", "SCOPE_OR_ARGUMENT_DENIED", "Artifacts, writes, or arguments exceed permitted scope.", None)

    @staticmethod
    def hash(policy: dict) -> str: return sha256_hex(canonical_bytes(policy))
