/**
 * Unit tests for src/lib/format.ts
 *
 * Pure functions — no DOM, no mocking required.
 * Run with: npm test
 */

import { describe, it, expect } from "vitest";
import { formatLeaseDuration, maskToCidr, formatScopeId } from "@/lib/format";

// ─── formatLeaseDuration ─────────────────────────────────────────────────────

describe("formatLeaseDuration", () => {
  it("formats 8 days correctly", () => {
    expect(formatLeaseDuration("8.00:00:00")).toBe("8 days");
  });

  it("formats 1 day as singular", () => {
    expect(formatLeaseDuration("1.00:00:00")).toBe("1 day");
  });

  it("formats 30 days", () => {
    expect(formatLeaseDuration("30.00:00:00")).toBe("30 days");
  });

  it("returns N/A for null", () => {
    expect(formatLeaseDuration(null)).toBe("N/A");
  });

  it("falls back to raw value when format is unrecognised", () => {
    expect(formatLeaseDuration("unknown-format")).toBe("unknown-format");
  });

  it("handles time-only string (no dot prefix) as fallback", () => {
    expect(formatLeaseDuration("00:00:00")).toBe("00:00:00");
  });
});

// ─── maskToCidr ──────────────────────────────────────────────────────────────

describe("maskToCidr", () => {
  it("converts /24 mask", () => {
    expect(maskToCidr("255.255.255.0")).toBe(24);
  });

  it("converts /16 mask", () => {
    expect(maskToCidr("255.255.0.0")).toBe(16);
  });

  it("converts /8 mask", () => {
    expect(maskToCidr("255.0.0.0")).toBe(8);
  });

  it("converts /32 mask", () => {
    expect(maskToCidr("255.255.255.255")).toBe(32);
  });

  it("converts /28 mask", () => {
    expect(maskToCidr("255.255.255.240")).toBe(28);
  });

  it("converts /0 mask", () => {
    expect(maskToCidr("0.0.0.0")).toBe(0);
  });
});

// ─── formatScopeId ───────────────────────────────────────────────────────────

describe("formatScopeId", () => {
  it("formats a /24 scope", () => {
    expect(formatScopeId("10.10.10.0", "255.255.255.0")).toBe("10.10.10.0/24");
  });

  it("formats a /16 scope", () => {
    expect(formatScopeId("10.20.0.0", "255.255.0.0")).toBe("10.20.0.0/16");
  });

  it("formats a /28 scope", () => {
    expect(formatScopeId("192.168.1.0", "255.255.255.240")).toBe(
      "192.168.1.0/28"
    );
  });
});
