// ─── Shared / Primitives ────────────────────────────────────────────────────

export interface Exclusion {
  start_range: string;
  end_range: string;
}

export interface ExclusionInput {
  start_address: string;
  end_address: string;
}

// ─── Failover ───────────────────────────────────────────────────────────────

export interface FullScopeFailover {
  relationship_name: string;
  partner_server: string;
  mode: string;
  state: string;
  server_role: string | null;
  reserve_percent: number | null;
  load_balance_percent: number | null;
  max_client_lead_time: string | null;
  scope_ids: string[];
}

export interface FailoverConfig {
  partner_server: string;
  relationship_name?: string;
  mode: "HotStandby" | "LoadBalance";
  server_role: "Active" | "Standby";
  reserve_percent: number;
  load_balance_percent: number;
  max_client_lead_time_minutes: number;
  shared_secret?: string;
}

// ─── Scope ──────────────────────────────────────────────────────────────────

export interface FullScopeInfo {
  scope_id: string;
  name: string;
  subnet_mask: string;
  start_range: string;
  end_range: string;
  state: string;
  lease_duration: string | null;
  description: string | null;
  gateway: string | null;
  dns_servers: string[];
  dns_domain: string | null;
  exclusions: Exclusion[];
  failover: FullScopeFailover | null;
}

// ─── Request Models ─────────────────────────────────────────────────────────

export interface DHCPScopeRequest {
  scope_name: string;
  network: string;
  subnet_mask: string;
  start_range: string;
  end_range: string;
  lease_duration_days: number;
  description?: string;
  gateway?: string;
  dns_servers: string[];
  dns_domain?: string;
  exclusions?: ExclusionInput[];
  failover?: FailoverConfig | null;
}

export interface SetScopeStateRequest {
  state: "Active" | "Inactive";
}

export interface UpdateDnsRequest {
  dns_servers: string[];
  dns_domain: string | null;
}

// ─── Response Models ─────────────────────────────────────────────────────────

export interface FullScopeListResponse {
  scopes: FullScopeInfo[];
  count: number;
}

export interface FullScopeDetailResponse {
  scope: FullScopeInfo;
}

export interface StepResult {
  step: string;
  success: boolean;
  command: string;
  detail: string | null;
  error: string | null;
}

export interface DHCPScopeResponse {
  scope_name: string;
  network: string;
  overall_success: boolean;
  steps: StepResult[];
}

export interface DeleteScopeResponse {
  deleted: string;
  steps: StepResult[];
  overall_success: boolean;
}

export interface ScopeStateResponse {
  scope_id: string;
  state: "Active" | "Inactive";
}

export interface DNSUpdateResponse {
  scope_id: string;
  dns_servers: string[];
  dns_domain: string | null;
}

export interface ExclusionResponse {
  scope_id: string;
  start: string;
  end: string;
  action: "added" | "removed";
}

export interface FailoverRelationship {
  relationship_name: string;
  partner_server: string;
  mode: string;
  state: string;
  scope_ids: string[];
}

export interface FailoverListResponse {
  relationships: FailoverRelationship[];
  count: number;
}

export interface AddFailoverRequest {
  partner_server: string;
  relationship_name?: string;
  mode: "HotStandby" | "LoadBalance";
  server_role: "Active" | "Standby";
  reserve_percent: number;
  load_balance_percent: number;
  max_client_lead_time_minutes: number;
  shared_secret?: string;
}

export interface UpdateFailoverRequest {
  server_role?: "Active" | "Standby" | null;
  reserve_percent?: number | null;
  load_balance_percent?: number | null;
  max_client_lead_time_minutes?: number | null;
  shared_secret?: string | null;
}

export interface FailoverOperationResponse {
  scope_id: string;
  action: "added" | "updated";
  success: boolean;
}

export interface HealthResponse {
  status: string;
  dhcp_server: string;
}

export interface ApiError {
  detail?: string;
  error?: string;
}
