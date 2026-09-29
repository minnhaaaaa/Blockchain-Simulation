import Ajv2020, { type ValidateFunction } from "ajv/dist/2020";
import commonSchema from "../../../contracts/schemas/common.schema.json";
import roomManifestSchema from "../../../contracts/schemas/room-manifest.schema.json";
import policySchema from "../../../contracts/schemas/policy.schema.json";
import jobSchema from "../../../contracts/schemas/job.schema.json";
import acceptanceSchema from "../../../contracts/schemas/job-acceptance.schema.json";
import actionSchema from "../../../contracts/schemas/action.schema.json";
import decisionSchema from "../../../contracts/schemas/decision.schema.json";
import receiptSchema from "../../../contracts/schemas/receipt.schema.json";
import resultSchema from "../../../contracts/schemas/job-result.schema.json";
import violationSchema from "../../../contracts/schemas/security-violation.schema.json";
import eventSchema from "../../../contracts/schemas/agent-event.schema.json";
import type { AgentEvent, RoomManifest } from "../types/api";

const ajv = new Ajv2020({ allErrors: true, strict: false });
const schemaBase = "https://agentguard.local/schemas/";
ajv.addFormat("uuid", /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
const schemas = [
  ["common.schema.json", commonSchema], ["room-manifest.schema.json", roomManifestSchema],
  ["policy.schema.json", policySchema], ["job.schema.json", jobSchema],
  ["job-acceptance.schema.json", acceptanceSchema], ["action.schema.json", actionSchema],
  ["decision.schema.json", decisionSchema], ["receipt.schema.json", receiptSchema],
  ["job-result.schema.json", resultSchema], ["security-violation.schema.json", violationSchema],
  ["agent-event.schema.json", eventSchema]
] as const;
for (const [name, schema] of schemas) ajv.addSchema({ ...schema, $id: `${schemaBase}${name}` });

const manifestValidator = ajv.getSchema(`${schemaBase}room-manifest.schema.json`) as ValidateFunction<RoomManifest>;
const eventValidator = ajv.getSchema(`${schemaBase}agent-event.schema.json`) as ValidateFunction<AgentEvent>;

export class IncompatibleResponseError extends Error {
  constructor(readonly validationErrors: string[]) {
    super("Incompatible server response");
    this.name = "IncompatibleResponseError";
  }
}

function assertValid<T>(validator: ValidateFunction<T>, value: unknown): asserts value is T {
  if (!validator(value)) {
    throw new IncompatibleResponseError((validator.errors ?? []).map(error => `${error.instancePath || "/"} ${error.message ?? "is invalid"}`));
  }
}

export function validateRoomManifest(value: unknown): RoomManifest { assertValid(manifestValidator, value); return value; }
export function validateAgentEvents(value: unknown): AgentEvent[] {
  if (!Array.isArray(value)) throw new IncompatibleResponseError(["/events must be an array"]);
  for (const item of value) assertValid(eventValidator, item);
  return value;
}
