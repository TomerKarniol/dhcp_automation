import { API_BASE_URL, API_KEY, USE_TEST_DATA } from "./api-config";
import type {
  AddFailoverRequest,
  DHCPScopeRequest,
  DHCPScopeResponse,
  DeleteScopeResponse,
  DNSUpdateResponse,
  ExclusionResponse,
  FailoverListResponse,
  FailoverOperationResponse,
  FullScopeDetailResponse,
  FullScopeListResponse,
  HealthResponse,
  ScopeStateResponse,
  UpdateDnsRequest,
  UpdateFailoverRequest,
} from "@/types/api";

function buildHeaders(): HeadersInit {
  return {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY,
  };
}

async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const response = await fetch(url, {
    ...options,
    headers: {
      ...buildHeaders(),
      ...options?.headers,
    },
  });

  if (!response.ok) {
    let errorMessage = `HTTP ${response.status}`;
    try {
      const errorBody = await response.json();
      errorMessage = errorBody.detail || errorBody.error || errorMessage;
    } catch {
      // ignore parse errors
    }
    throw new Error(errorMessage);
  }

  return response.json() as Promise<T>;
}

// ─── Scopes ──────────────────────────────────────────────────────────────────

export async function getScopes(): Promise<FullScopeListResponse> {
  const path = USE_TEST_DATA ? "/scopes/test" : "/scopes";
  return apiFetch<FullScopeListResponse>(path);
}

export async function getScope(scopeId: string): Promise<FullScopeDetailResponse> {
  return apiFetch<FullScopeDetailResponse>(`/scopes/${encodeURIComponent(scopeId)}`);
}

export async function createScope(data: DHCPScopeRequest): Promise<DHCPScopeResponse> {
  return apiFetch<DHCPScopeResponse>("/scopes", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function deleteScope(scopeId: string): Promise<DeleteScopeResponse> {
  return apiFetch<DeleteScopeResponse>(`/scopes/${encodeURIComponent(scopeId)}`, {
    method: "DELETE",
  });
}

export async function setScopeState(
  scopeId: string,
  state: "Active" | "Inactive"
): Promise<ScopeStateResponse> {
  return apiFetch<ScopeStateResponse>(
    `/scopes/${encodeURIComponent(scopeId)}/state`,
    {
      method: "PATCH",
      body: JSON.stringify({ state }),
    }
  );
}

// ─── DNS ─────────────────────────────────────────────────────────────────────

export async function updateDns(
  scopeId: string,
  data: UpdateDnsRequest
): Promise<DNSUpdateResponse> {
  return apiFetch<DNSUpdateResponse>(
    `/scopes/${encodeURIComponent(scopeId)}/dns`,
    {
      method: "PATCH",
      body: JSON.stringify(data),
    }
  );
}

// ─── Exclusions ───────────────────────────────────────────────────────────────

export async function addExclusion(
  scopeId: string,
  start: string,
  end: string
): Promise<ExclusionResponse> {
  const params = new URLSearchParams({ start, end });
  return apiFetch<ExclusionResponse>(
    `/scopes/${encodeURIComponent(scopeId)}/exclusions?${params}`,
    { method: "POST" }
  );
}

export async function removeExclusion(
  scopeId: string,
  start: string,
  end: string
): Promise<ExclusionResponse> {
  const params = new URLSearchParams({ start, end });
  return apiFetch<ExclusionResponse>(
    `/scopes/${encodeURIComponent(scopeId)}/exclusions?${params}`,
    { method: "DELETE" }
  );
}

// ─── Failover ─────────────────────────────────────────────────────────────────

export async function getFailover(): Promise<FailoverListResponse> {
  return apiFetch<FailoverListResponse>("/failover");
}

export async function addFailover(
  scopeId: string,
  data: AddFailoverRequest
): Promise<FailoverOperationResponse> {
  return apiFetch<FailoverOperationResponse>(
    `/scopes/${encodeURIComponent(scopeId)}/failover`,
    { method: "POST", body: JSON.stringify(data) }
  );
}

export async function updateFailover(
  scopeId: string,
  data: UpdateFailoverRequest
): Promise<FailoverOperationResponse> {
  return apiFetch<FailoverOperationResponse>(
    `/scopes/${encodeURIComponent(scopeId)}/failover`,
    { method: "PATCH", body: JSON.stringify(data) }
  );
}

// ─── Health ───────────────────────────────────────────────────────────────────

export async function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/health");
}
