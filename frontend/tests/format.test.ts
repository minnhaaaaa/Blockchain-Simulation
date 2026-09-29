import { describe, expect, it } from "vitest";
import { relativeAge, shortId, titleCase } from "../src/utils/format";

describe("display formatting", () => {
  it("shortens long identifiers without losing the prefix", () => expect(shortId("abcdef0123456789", 10)).toBe("abcdef0…"));
  it("formats ages deterministically", () => expect(relativeAge(1_000, 121_000)).toBe("2m ago"));
  it("turns protocol tokens into labels", () => expect(titleCase("action.approval_required")).toBe("Action · Approval Required"));
});
