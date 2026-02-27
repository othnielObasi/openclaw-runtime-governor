import { describe, it, mock, beforeEach } from "node:test";
import assert from "node:assert/strict";

// We test the compiled output — run `npm run build` first.
import { GovernorClient, GovernorBlockedError } from "../dist/cjs/index.js";

describe("GovernorClient", () => {
  it("constructs with defaults", () => {
    const c = new GovernorClient();
    assert.equal(c.baseUrl, "http://localhost:8000");
    assert.equal(c.apiKey, "");
  });

  it("constructs with explicit options", () => {
    const c = new GovernorClient({
      baseUrl: "https://example.com/",
      apiKey: "ocg_test123",
      timeoutMs: 5000,
    });
    assert.equal(c.baseUrl, "https://example.com");
    assert.equal(c.apiKey, "ocg_test123");
  });

  it("evaluate throws GovernorBlockedError on block", async () => {
    const mockResponse = {
      decision: "block",
      risk_score: 95,
      explanation: "Dangerous command",
      policy_ids: ["shell-dangerous"],
      modified_args: null,
    };

    const originalFetch = globalThis.fetch;
    globalThis.fetch = async () =>
      new Response(JSON.stringify(mockResponse), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });

    try {
      const c = new GovernorClient({ baseUrl: "http://localhost:9999" });
      await assert.rejects(
        () => c.evaluate("shell", { cmd: "rm -rf /" }),
        (err) => {
          assert.ok(err instanceof GovernorBlockedError);
          assert.equal(err.decision.decision, "block");
          assert.equal(err.decision.risk_score, 95);
          return true;
        },
      );
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("evaluate returns decision on allow", async () => {
    const mockResponse = {
      decision: "allow",
      risk_score: 10,
      explanation: "Safe read operation",
      policy_ids: [],
      modified_args: null,
    };

    const originalFetch = globalThis.fetch;
    globalThis.fetch = async () =>
      new Response(JSON.stringify(mockResponse), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });

    try {
      const c = new GovernorClient({ baseUrl: "http://localhost:9999" });
      const result = await c.evaluate("file_read", { path: "/tmp/safe.txt" });
      assert.equal(result.decision, "allow");
      assert.equal(result.risk_score, 10);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("sends X-API-Key header when apiKey is set", async () => {
    let capturedHeaders = {};
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (_url, opts) => {
      capturedHeaders = opts.headers;
      return new Response(
        JSON.stringify({ decision: "allow", risk_score: 0, explanation: "", policy_ids: [], modified_args: null }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    };

    try {
      const c = new GovernorClient({ baseUrl: "http://localhost:9999", apiKey: "ocg_testkey" });
      await c.evaluate("noop", {});
      assert.equal(capturedHeaders["X-API-Key"], "ocg_testkey");
      assert.equal(capturedHeaders["Content-Type"], "application/json");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("omits X-API-Key header when apiKey is empty", async () => {
    let capturedHeaders = {};
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (_url, opts) => {
      capturedHeaders = opts.headers;
      return new Response(
        JSON.stringify({ decision: "allow", risk_score: 0, explanation: "", policy_ids: [], modified_args: null }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    };

    try {
      const c = new GovernorClient({ baseUrl: "http://localhost:9999" });
      await c.evaluate("noop", {});
      assert.equal(capturedHeaders["X-API-Key"], undefined);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
