import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClient, ApiError, normalizeApiOrigin } from "../src/api/client";

describe("API client", () => {
  afterEach(() => vi.restoreAllMocks());

  it("normalizes explicit http origins and rejects credentials", () => {
    expect(normalizeApiOrigin("http://localhost:8123/" )).toBe("http://localhost:8123");
    expect(() => normalizeApiOrigin("ftp://localhost")).toThrow(/http/);
    expect(() => normalizeApiOrigin("https://user:pass@example.test")).toThrow(/credentials/);
  });

  it("normalizes structured API errors and preserves request IDs", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ code: "NOPE", message: "Denied", request_id: "req-7" }), { status: 409, headers: { "Content-Type": "application/json" } }));
    const request = new ApiClient("http://localhost:8123").get("/api/status");
    await expect(request).rejects.toMatchObject({ code: "NOPE", message: "Denied", requestId: "req-7", status: 409 });
    await request.catch((error: unknown) => expect(error).toBeInstanceOf(ApiError));
  });

  it("reports transport loss as an offline API error", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("fetch failed"));
    await expect(new ApiClient("http://localhost:8123").get("/health")).rejects.toMatchObject({ code: "NETWORK_ERROR", status: 0 });
  });
});
