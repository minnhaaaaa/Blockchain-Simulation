import { describe, expect, it } from "vitest";
import { serializePolicyDraft } from "../src/utils/policy";

describe("policy serialization", () => {
  it("serializes only operator-entered rules and limits", () => {
    const result = serializePolicyDraft({
      rules: [{ tool_id: "sha256", effect: "approval_required", read_artifact_ids: ["artifact-1"], write_scopes: "reports, audit", argument_constraints: '{"type":"object"}' }],
      maxActions: "3", maxRuntime: "2500", maxOutput: "4096", expiry: "", rawMode: false, rawPolicy: ""
    });
    expect(result).toEqual({
      rules: [{ tool_id: "sha256", effect: "approval_required", read_artifact_ids: ["artifact-1"], write_scopes: ["reports", "audit"], argument_constraints: { type: "object" } }],
      limits: { max_actions: 3, max_runtime_ms_per_action: 2500, max_output_bytes_per_action: 4096 }
    });
  });

  it("rejects unsafe limit coercion and non-object constraints", () => {
    const rule = { tool_id: "sha256", effect: "allow" as const, read_artifact_ids: [], write_scopes: "", argument_constraints: "[]" };
    const base = { rules: [rule], maxActions: "0", maxRuntime: "5", maxOutput: "5", expiry: "", rawMode: false, rawPolicy: "" };
    expect(() => serializePolicyDraft(base)).toThrow(/argument constraints/);
    expect(() => serializePolicyDraft({ ...base, rules: [{ ...rule, argument_constraints: "{}" }] })).toThrow(/Maximum actions/);
  });
});
