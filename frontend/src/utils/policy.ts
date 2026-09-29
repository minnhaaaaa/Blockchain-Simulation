import type { JobCreateRequest, PolicyRuleInput } from "../types/api";

export type RuleDraft = {
  tool_id: string;
  effect: PolicyRuleInput["effect"];
  read_artifact_ids: string[];
  write_scopes: string;
  argument_constraints: string;
};

export type PolicyDraft = {
  rules: RuleDraft[];
  maxActions: string;
  maxRuntime: string;
  maxOutput: string;
  expiry: string;
  rawMode: boolean;
  rawPolicy: string;
};

function positiveInteger(value: string, label: string) {
  const number = Number(value);
  if (!Number.isSafeInteger(number) || number < 1) throw new Error(`${label} must be a positive integer.`);
  return number;
}

export function serializePolicyDraft(draft: PolicyDraft): JobCreateRequest["policy"] {
  if (draft.rawMode) {
    const parsed: unknown = JSON.parse(draft.rawPolicy);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Policy JSON must be an object.");
    return parsed as JobCreateRequest["policy"];
  }

  return {
    rules: draft.rules.map((rule, index) => {
      const constraints: unknown = JSON.parse(rule.argument_constraints);
      if (!constraints || typeof constraints !== "object" || Array.isArray(constraints)) {
        throw new Error(`Rule ${index + 1} argument constraints must be a JSON object.`);
      }
      return {
        tool_id: rule.tool_id,
        effect: rule.effect,
        read_artifact_ids: rule.read_artifact_ids,
        write_scopes: rule.write_scopes.split(",").map((value) => value.trim()).filter(Boolean),
        argument_constraints: constraints as PolicyRuleInput["argument_constraints"]
      };
    }),
    limits: {
      max_actions: positiveInteger(draft.maxActions, "Maximum actions"),
      max_runtime_ms_per_action: positiveInteger(draft.maxRuntime, "Runtime per action"),
      max_output_bytes_per_action: positiveInteger(draft.maxOutput, "Output per action")
    },
    ...(draft.expiry ? { expires_at_ms: new Date(draft.expiry).getTime() } : {})
  };
}
