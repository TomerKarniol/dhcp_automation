/**
 * Unit tests for src/lib/validators.ts
 *
 * Pure Zod schema validation — no DOM, no mocking required.
 * Run with: npm test
 */

import { describe, it, expect } from "vitest";
import {
  ipv4Schema,
  subnetMaskSchema,
  ipToNumber,
  ipInNetwork,
  compareIps,
  dnsUpdateSchema,
  exclusionSchema,
  createScopeSchema,
  stateSchema,
} from "@/lib/validators";

// ─── ipToNumber ──────────────────────────────────────────────────────────────

describe("ipToNumber", () => {
  it("converts 0.0.0.0 to 0", () => {
    expect(ipToNumber("0.0.0.0")).toBe(0);
  });

  it("converts 255.255.255.255 to max uint32", () => {
    expect(ipToNumber("255.255.255.255")).toBe(4294967295);
  });

  it("converts 10.0.0.1 correctly", () => {
    expect(ipToNumber("10.0.0.1")).toBe(167772161);
  });

  it("preserves ordering: 10.0.0.1 < 10.0.0.2", () => {
    expect(ipToNumber("10.0.0.1")).toBeLessThan(ipToNumber("10.0.0.2"));
  });
});

// ─── ipInNetwork ─────────────────────────────────────────────────────────────

describe("ipInNetwork", () => {
  it("returns true for IP inside /24 network", () => {
    expect(ipInNetwork("10.10.10.100", "10.10.10.0", "255.255.255.0")).toBe(
      true
    );
  });

  it("returns true for network address itself", () => {
    expect(ipInNetwork("10.10.10.0", "10.10.10.0", "255.255.255.0")).toBe(
      true
    );
  });

  it("returns false for IP in different /24", () => {
    expect(ipInNetwork("10.10.11.1", "10.10.10.0", "255.255.255.0")).toBe(
      false
    );
  });

  it("returns false for completely different network", () => {
    expect(ipInNetwork("192.168.1.1", "10.10.10.0", "255.255.255.0")).toBe(
      false
    );
  });
});

// ─── compareIps ──────────────────────────────────────────────────────────────

describe("compareIps", () => {
  it("returns negative when first IP is lower", () => {
    expect(compareIps("10.0.0.1", "10.0.0.2")).toBeLessThan(0);
  });

  it("returns positive when first IP is higher", () => {
    expect(compareIps("10.0.0.200", "10.0.0.100")).toBeGreaterThan(0);
  });

  it("returns 0 for equal IPs", () => {
    expect(compareIps("10.0.0.50", "10.0.0.50")).toBe(0);
  });
});

// ─── ipv4Schema ──────────────────────────────────────────────────────────────

describe("ipv4Schema", () => {
  it("accepts a valid IPv4 address", () => {
    expect(() => ipv4Schema.parse("10.10.10.1")).not.toThrow();
  });

  it("accepts 0.0.0.0", () => {
    expect(() => ipv4Schema.parse("0.0.0.0")).not.toThrow();
  });

  it("accepts 255.255.255.255", () => {
    expect(() => ipv4Schema.parse("255.255.255.255")).not.toThrow();
  });

  it("rejects a hostname", () => {
    expect(() => ipv4Schema.parse("dhcp02.lab.local")).toThrow();
  });

  it("rejects an IPv6 address", () => {
    expect(() => ipv4Schema.parse("::1")).toThrow();
  });

  it("rejects an octet above 255", () => {
    expect(() => ipv4Schema.parse("256.0.0.1")).toThrow();
  });

  it("rejects a partial address", () => {
    expect(() => ipv4Schema.parse("10.10.10")).toThrow();
  });

  it("rejects empty string", () => {
    expect(() => ipv4Schema.parse("")).toThrow();
  });
});

// ─── subnetMaskSchema ────────────────────────────────────────────────────────

describe("subnetMaskSchema", () => {
  it("accepts 255.255.255.0 (/24)", () => {
    expect(() => subnetMaskSchema.parse("255.255.255.0")).not.toThrow();
  });

  it("accepts 255.255.0.0 (/16)", () => {
    expect(() => subnetMaskSchema.parse("255.255.0.0")).not.toThrow();
  });

  it("accepts 255.255.255.240 (/28)", () => {
    expect(() => subnetMaskSchema.parse("255.255.255.240")).not.toThrow();
  });

  it("rejects a non-contiguous mask", () => {
    expect(() => subnetMaskSchema.parse("255.0.255.0")).toThrow();
  });

  it("rejects 0.0.0.0", () => {
    expect(() => subnetMaskSchema.parse("0.0.0.0")).toThrow();
  });
});

// ─── stateSchema ─────────────────────────────────────────────────────────────

describe("stateSchema", () => {
  it("accepts Active", () => {
    expect(stateSchema.parse("Active")).toBe("Active");
  });

  it("accepts Inactive", () => {
    expect(stateSchema.parse("Inactive")).toBe("Inactive");
  });

  it("rejects lowercase active", () => {
    expect(() => stateSchema.parse("active")).toThrow();
  });

  it("rejects arbitrary string", () => {
    expect(() => stateSchema.parse("Disabled")).toThrow();
  });
});

// ─── dnsUpdateSchema ─────────────────────────────────────────────────────────

describe("dnsUpdateSchema", () => {
  it("accepts valid DNS servers and domain", () => {
    const result = dnsUpdateSchema.parse({
      dns_servers: ["10.10.1.5", "10.10.1.6"],
      dns_domain: "lab.local",
    });
    expect(result.dns_servers).toHaveLength(2);
    expect(result.dns_domain).toBe("lab.local");
  });

  it("accepts null dns_domain", () => {
    const result = dnsUpdateSchema.parse({
      dns_servers: ["8.8.8.8"],
      dns_domain: null,
    });
    expect(result.dns_domain).toBeNull();
  });

  it("rejects empty dns_servers array", () => {
    expect(() =>
      dnsUpdateSchema.parse({ dns_servers: [], dns_domain: null })
    ).toThrow();
  });

  it("rejects invalid IP in dns_servers", () => {
    expect(() =>
      dnsUpdateSchema.parse({ dns_servers: ["not-an-ip"], dns_domain: null })
    ).toThrow();
  });
});

// ─── exclusionSchema ─────────────────────────────────────────────────────────

describe("exclusionSchema", () => {
  it("accepts a valid range", () => {
    const result = exclusionSchema.parse({
      start_address: "10.10.10.1",
      end_address: "10.10.10.10",
    });
    expect(result.start_address).toBe("10.10.10.1");
    expect(result.end_address).toBe("10.10.10.10");
  });

  it("accepts equal start and end", () => {
    expect(() =>
      exclusionSchema.parse({
        start_address: "10.10.10.5",
        end_address: "10.10.10.5",
      })
    ).not.toThrow();
  });

  it("rejects reversed range (start > end)", () => {
    expect(() =>
      exclusionSchema.parse({
        start_address: "10.10.10.20",
        end_address: "10.10.10.5",
      })
    ).toThrow();
  });

  it("rejects invalid start IP", () => {
    expect(() =>
      exclusionSchema.parse({
        start_address: "bad-ip",
        end_address: "10.10.10.10",
      })
    ).toThrow();
  });
});

// ─── createScopeSchema ───────────────────────────────────────────────────────

const VALID_SCOPE = {
  scope_name: "VLAN-99-Test",
  network: "10.99.0.0",
  subnet_mask: "255.255.255.0",
  start_range: "10.99.0.50",
  end_range: "10.99.0.240",
  lease_duration_days: 8,
  dns_servers: ["10.10.1.5", "10.10.1.6"],
  dns_domain: "lab.local",
};

describe("createScopeSchema", () => {
  it("accepts a minimal valid request", () => {
    const result = createScopeSchema.parse(VALID_SCOPE);
    expect(result.scope_name).toBe("VLAN-99-Test");
  });

  it("accepts optional gateway", () => {
    const result = createScopeSchema.parse({
      ...VALID_SCOPE,
      gateway: "10.99.0.1",
    });
    expect(result.gateway).toBe("10.99.0.1");
  });

  it("accepts optional description", () => {
    const result = createScopeSchema.parse({
      ...VALID_SCOPE,
      description: "Test scope",
    });
    expect(result.description).toBe("Test scope");
  });

  it("rejects scope_name longer than 128 characters", () => {
    expect(() =>
      createScopeSchema.parse({ ...VALID_SCOPE, scope_name: "a".repeat(129) })
    ).toThrow();
  });

  it("rejects empty scope_name", () => {
    expect(() =>
      createScopeSchema.parse({ ...VALID_SCOPE, scope_name: "" })
    ).toThrow();
  });

  it("rejects invalid subnet mask", () => {
    expect(() =>
      createScopeSchema.parse({ ...VALID_SCOPE, subnet_mask: "255.0.255.0" })
    ).toThrow();
  });

  it("rejects reversed IP range (start >= end)", () => {
    expect(() =>
      createScopeSchema.parse({
        ...VALID_SCOPE,
        start_range: "10.99.0.240",
        end_range: "10.99.0.50",
      })
    ).toThrow();
  });

  it("rejects start_range outside the declared network", () => {
    expect(() =>
      createScopeSchema.parse({
        ...VALID_SCOPE,
        start_range: "10.88.0.50",
      })
    ).toThrow();
  });

  it("rejects end_range outside the declared network", () => {
    expect(() =>
      createScopeSchema.parse({
        ...VALID_SCOPE,
        end_range: "10.88.0.240",
      })
    ).toThrow();
  });

  it("rejects lease_duration_days of 0", () => {
    expect(() =>
      createScopeSchema.parse({ ...VALID_SCOPE, lease_duration_days: 0 })
    ).toThrow();
  });

  it("rejects lease_duration_days above 365", () => {
    expect(() =>
      createScopeSchema.parse({ ...VALID_SCOPE, lease_duration_days: 366 })
    ).toThrow();
  });

  it("rejects empty dns_servers array", () => {
    expect(() =>
      createScopeSchema.parse({ ...VALID_SCOPE, dns_servers: [] })
    ).toThrow();
  });

  it("rejects invalid gateway IP", () => {
    expect(() =>
      createScopeSchema.parse({ ...VALID_SCOPE, gateway: "not-an-ip" })
    ).toThrow();
  });

  it("rejects description longer than 256 characters", () => {
    expect(() =>
      createScopeSchema.parse({
        ...VALID_SCOPE,
        description: "x".repeat(257),
      })
    ).toThrow();
  });

  it("accepts empty string for optional gateway (treated as absent)", () => {
    expect(() =>
      createScopeSchema.parse({ ...VALID_SCOPE, gateway: "" })
    ).not.toThrow();
  });

  it("accepts valid exclusion ranges", () => {
    const result = createScopeSchema.parse({
      ...VALID_SCOPE,
      exclusions: [
        { start_address: "10.99.0.1", end_address: "10.99.0.10" },
      ],
    });
    expect(result.exclusions).toHaveLength(1);
  });
});
