import { z } from "zod";

// ─── IP / Network helpers ─────────────────────────────────────────────────────

export const ipv4Schema = z
  .string()
  .regex(
    /^((25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(25[0-5]|2[0-4]\d|[01]?\d\d?)$/,
    "Must be a valid IPv4 address"
  );

// Valid contiguous subnet masks
const VALID_MASKS = new Set([
  "128.0.0.0",
  "192.0.0.0",
  "224.0.0.0",
  "240.0.0.0",
  "248.0.0.0",
  "252.0.0.0",
  "254.0.0.0",
  "255.0.0.0",
  "255.128.0.0",
  "255.192.0.0",
  "255.224.0.0",
  "255.240.0.0",
  "255.248.0.0",
  "255.252.0.0",
  "255.254.0.0",
  "255.255.0.0",
  "255.255.128.0",
  "255.255.192.0",
  "255.255.224.0",
  "255.255.240.0",
  "255.255.248.0",
  "255.255.252.0",
  "255.255.254.0",
  "255.255.255.0",
  "255.255.255.128",
  "255.255.255.192",
  "255.255.255.224",
  "255.255.255.240",
  "255.255.255.248",
  "255.255.255.252",
  "255.255.255.254",
]);

export const subnetMaskSchema = ipv4Schema.check((ctx) => {
  if (!VALID_MASKS.has(ctx.value)) {
    ctx.issues.push({
      code: "custom",
      message: "Must be a valid contiguous subnet mask",
      input: ctx.value,
    });
  }
});

// ─── IP arithmetic helpers ────────────────────────────────────────────────────

export function ipToNumber(ip: string): number {
  return ip
    .split(".")
    .reduce((acc, octet) => (acc << 8) + parseInt(octet, 10), 0) >>> 0;
}

export function ipInNetwork(ip: string, network: string, mask: string): boolean {
  try {
    const ipNum = ipToNumber(ip);
    const networkNum = ipToNumber(network);
    const maskNum = ipToNumber(mask);
    return (ipNum & maskNum) === (networkNum & maskNum);
  } catch {
    return false;
  }
}

export function compareIps(a: string, b: string): number {
  return ipToNumber(a) - ipToNumber(b);
}

// ─── Form schemas ─────────────────────────────────────────────────────────────

export const stateSchema = z.enum(["Active", "Inactive"]);

export const dnsUpdateSchema = z.object({
  dns_servers: z
    .array(ipv4Schema)
    .min(1, "At least one DNS server is required"),
  dns_domain: z.string().max(253).nullable(),
});

export const exclusionSchema = z
  .object({
    start_address: ipv4Schema,
    end_address: ipv4Schema,
  })
  .check((ctx) => {
    if (
      ipToNumber(ctx.value.start_address) >
      ipToNumber(ctx.value.end_address)
    ) {
      ctx.issues.push({
        code: "custom",
        message: "Start address must be less than or equal to end address",
        input: ctx.value,
        path: ["end_address"],
      });
    }
  });

export const failoverSchema = z.union([
  z.null(),
  z
    .object({
      partner_server: z.string().min(1, "Partner server is required"),
      relationship_name: z.string().optional(),
      mode: z.enum(["HotStandby", "LoadBalance"]),
      server_role: z.enum(["Active", "Standby"]),
      reserve_percent: z.number().min(0).max(100),
      load_balance_percent: z.number().min(0).max(100),
      max_client_lead_time_minutes: z
        .number()
        .min(1, "Must be at least 1 minute"),
      shared_secret: z
        .string()
        .min(8, "Shared secret must be at least 8 characters")
        .optional()
        .or(z.literal("")),
    })
    .optional(),
]);

export const createScopeSchema = z
  .object({
    scope_name: z
      .string()
      .min(1, "Scope name is required")
      .max(128, "Scope name must be 128 characters or fewer"),
    network: ipv4Schema,
    subnet_mask: subnetMaskSchema,
    start_range: ipv4Schema,
    end_range: ipv4Schema,
    lease_duration_days: z
      .number({ invalid_type_error: "Invalid input: expected number" })
      .min(1, "Minimum 1 day")
      .max(365, "Maximum 365 days"),
    description: z
      .string()
      .max(256, "Description must be 256 characters or fewer")
      .optional()
      .or(z.literal("")),
    gateway: ipv4Schema.optional().or(z.literal("")),
    dns_servers: z
      .array(ipv4Schema)
      .min(1, "At least one DNS server is required"),
    dns_domain: z.string().max(253).optional().or(z.literal("")),
    exclusions: z.array(exclusionSchema).optional(),
    failover: failoverSchema.optional(),
  })
  .check((ctx) => {
    const { start_range, end_range, network, subnet_mask } = ctx.value;

    if (
      start_range &&
      end_range &&
      ipToNumber(start_range) >= ipToNumber(end_range)
    ) {
      ctx.issues.push({
        code: "custom",
        message: "Start range must be less than end range",
        input: ctx.value,
        path: ["end_range"],
      });
    }

    if (network && subnet_mask) {
      if (start_range && !ipInNetwork(start_range, network, subnet_mask)) {
        ctx.issues.push({
          code: "custom",
          message: "Start range must be within the network",
          input: ctx.value,
          path: ["start_range"],
        });
      }
      if (end_range && !ipInNetwork(end_range, network, subnet_mask)) {
        ctx.issues.push({
          code: "custom",
          message: "End range must be within the network",
          input: ctx.value,
          path: ["end_range"],
        });
      }
    }
  });

export type CreateScopeFormValues = z.infer<typeof createScopeSchema>;
export type DnsUpdateFormValues = z.infer<typeof dnsUpdateSchema>;
export type ExclusionFormValues = z.infer<typeof exclusionSchema>;
