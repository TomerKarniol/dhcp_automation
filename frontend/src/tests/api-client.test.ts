/**
 * Unit tests for src/lib/api-client.ts
 *
 * All fetch() calls are intercepted via vi.stubGlobal — no real network.
 * Run with: npm test
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { FullScopeListResponse, FullScopeDetailResponse, HealthResponse } from "@/types/api";

// ─── Helpers ─────────────────────────────────────────────────────────────────

function mockFetch(body: unknown, status = 200) {
  const response = {
    ok: status >= 200 && status < 300,
    status,
    json: vi.fn().mockResolvedValue(body),
  } as unknown as Response;
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
}

function mockFetchError(message: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockRejectedValue(new Error(message))
  );
}

const FAKE_SCOPE_LIST: FullScopeListResponse = {
  scopes: [
    {
      scope_id: "10.10.10.0",
      name: "VLAN-10-Test",
      subnet_mask: "255.255.255.0",
      start_range: "10.10.10.50",
      end_range: "10.10.10.240",
      state: "Active",
      lease_duration: "8.00:00:00",
      description: null,
      gateway: "10.10.10.1",
      dns_servers: ["10.10.1.5"],
      dns_domain: "lab.local",
      exclusions: [],
      failover: null,
    },
  ],
  count: 1,
};

// ─── Tests ───────────────────────────────────────────────────────────────────

describe("getScopes", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("calls /scopes when USE_TEST_DATA is false and returns scope list", async () => {
    vi.stubEnv("NEXT_PUBLIC_USE_TEST_DATA", "false");
    mockFetch(FAKE_SCOPE_LIST);
    const { getScopes } = await import("@/lib/api-client");
    const result = await getScopes();
    expect(result.count).toBe(1);
    expect(result.scopes[0].scope_id).toBe("10.10.10.0");

    const fetchMock = vi.mocked(globalThis.fetch);
    expect(fetchMock).toHaveBeenCalledOnce();
    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain("/scopes");
    expect(url).not.toContain("/test");
  });

  it("calls /scopes/test when USE_TEST_DATA is true", async () => {
    vi.stubEnv("NEXT_PUBLIC_USE_TEST_DATA", "true");
    mockFetch(FAKE_SCOPE_LIST);
    const { getScopes } = await import("@/lib/api-client");
    await getScopes();

    const fetchMock = vi.mocked(globalThis.fetch);
    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain("/scopes/test");
  });

  it("throws when the server returns a non-2xx status", async () => {
    vi.stubEnv("NEXT_PUBLIC_USE_TEST_DATA", "false");
    mockFetch({ detail: "PowerShell unavailable" }, 503);
    const { getScopes } = await import("@/lib/api-client");
    await expect(getScopes()).rejects.toThrow("PowerShell unavailable");
  });

  it("propagates network errors", async () => {
    vi.stubEnv("NEXT_PUBLIC_USE_TEST_DATA", "false");
    mockFetchError("Network request failed");
    const { getScopes } = await import("@/lib/api-client");
    await expect(getScopes()).rejects.toThrow("Network request failed");
  });
});

describe("getScope", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("calls /scopes/{id} with the correct scope ID", async () => {
    const detail: FullScopeDetailResponse = { scope: FAKE_SCOPE_LIST.scopes[0] };
    mockFetch(detail);
    const { getScope } = await import("@/lib/api-client");
    const result = await getScope("10.10.10.0");
    expect(result.scope.scope_id).toBe("10.10.10.0");

    const fetchMock = vi.mocked(globalThis.fetch);
    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain("/scopes/10.10.10.0");
  });

  it("throws 404 error message for missing scope", async () => {
    mockFetch({ detail: "Scope not found" }, 404);
    const { getScope } = await import("@/lib/api-client");
    await expect(getScope("99.99.99.0")).rejects.toThrow("Scope not found");
  });
});

describe("getHealth", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("returns health response", async () => {
    const health: HealthResponse = {
      status: "healthy",
      dhcp_server: "dhcp01.lab.local",
    };
    mockFetch(health);
    const { getHealth } = await import("@/lib/api-client");
    const result = await getHealth();
    expect(result.status).toBe("healthy");
  });
});

describe("setScopeState", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("sends PATCH to /scopes/{id}/state with correct body", async () => {
    mockFetch({ scope_id: "10.10.10.0", state: "Inactive", message: "ok" });
    const { setScopeState } = await import("@/lib/api-client");
    const result = await setScopeState("10.10.10.0", "Inactive");
    expect(result.state).toBe("Inactive");

    const fetchMock = vi.mocked(globalThis.fetch);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/scopes/10.10.10.0/state");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body as string)).toEqual({ state: "Inactive" });
  });
});

describe("deleteScope", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("sends DELETE to /scopes/{id}", async () => {
    mockFetch({ scope_id: "10.10.10.0", message: "Deleted" });
    const { deleteScope } = await import("@/lib/api-client");
    await deleteScope("10.10.10.0");

    const fetchMock = vi.mocked(globalThis.fetch);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/scopes/10.10.10.0");
    expect(init.method).toBe("DELETE");
  });
});

describe("updateDns", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("sends PATCH to /scopes/{id}/dns with correct body", async () => {
    mockFetch({
      scope_id: "10.10.10.0",
      dns_servers: ["8.8.8.8"],
      dns_domain: null,
      message: "updated",
    });
    const { updateDns } = await import("@/lib/api-client");
    await updateDns("10.10.10.0", {
      dns_servers: ["8.8.8.8"],
      dns_domain: null,
    });

    const fetchMock = vi.mocked(globalThis.fetch);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/scopes/10.10.10.0/dns");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body as string).dns_servers).toEqual(["8.8.8.8"]);
  });
});

describe("addExclusion / removeExclusion", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("addExclusion sends POST with correct query params", async () => {
    mockFetch({
      scope_id: "10.10.10.0",
      start_range: "10.10.10.1",
      end_range: "10.10.10.10",
      action: "added",
      message: "ok",
    });
    const { addExclusion } = await import("@/lib/api-client");
    const result = await addExclusion("10.10.10.0", "10.10.10.1", "10.10.10.10");
    expect(result.action).toBe("added");

    const fetchMock = vi.mocked(globalThis.fetch);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/exclusions");
    expect(url).toContain("start=10.10.10.1");
    expect(url).toContain("end=10.10.10.10");
    expect(init.method).toBe("POST");
  });

  it("removeExclusion sends DELETE with correct query params", async () => {
    mockFetch({
      scope_id: "10.10.10.0",
      start_range: "10.10.10.1",
      end_range: "10.10.10.10",
      action: "removed",
      message: "ok",
    });
    const { removeExclusion } = await import("@/lib/api-client");
    const result = await removeExclusion(
      "10.10.10.0",
      "10.10.10.1",
      "10.10.10.10"
    );
    expect(result.action).toBe("removed");

    const fetchMock = vi.mocked(globalThis.fetch);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/exclusions");
    expect(init.method).toBe("DELETE");
  });
});

describe("X-API-Key header", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("includes X-API-Key header from env var", async () => {
    vi.stubEnv("NEXT_PUBLIC_DHCP_API_KEY", "my-secret-key");
    mockFetch({ status: "healthy", dhcp_server: "dhcp01" });
    const { getHealth } = await import("@/lib/api-client");
    await getHealth();

    const fetchMock = vi.mocked(globalThis.fetch);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Record<string, string>;
    expect(headers["X-API-Key"]).toBe("my-secret-key");
  });
});
