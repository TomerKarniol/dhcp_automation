import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  addExclusion,
  addFailover,
  createScope,
  deleteScope,
  getScope,
  getScopes,
  removeExclusion,
  setScopeState,
  updateDns,
  updateFailover,
} from "@/lib/api-client";
import type {
  AddFailoverRequest,
  DHCPScopeRequest,
  UpdateDnsRequest,
  UpdateFailoverRequest,
} from "@/types/api";

export function useScopes() {
  return useQuery({
    queryKey: ["scopes"],
    queryFn: getScopes,
  });
}

export function useScope(id: string) {
  return useQuery({
    queryKey: ["scope", id],
    queryFn: () => getScope(id),
    enabled: Boolean(id),
  });
}

export function useCreateScope() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: DHCPScopeRequest) => createScope(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scopes"] });
    },
  });
}

export function useDeleteScope() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (scopeId: string) => deleteScope(scopeId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scopes"] });
    },
  });
}

export function useSetScopeState() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      scopeId,
      state,
    }: {
      scopeId: string;
      state: "Active" | "Inactive";
    }) => setScopeState(scopeId, state),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ["scopes"] });
      qc.invalidateQueries({ queryKey: ["scope", variables.scopeId] });
    },
  });
}

export function useUpdateDns() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      scopeId,
      data,
    }: {
      scopeId: string;
      data: UpdateDnsRequest;
    }) => updateDns(scopeId, data),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ["scope", variables.scopeId] });
      qc.invalidateQueries({ queryKey: ["scopes"] });
    },
  });
}

export function useAddExclusion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      scopeId,
      start,
      end,
    }: {
      scopeId: string;
      start: string;
      end: string;
    }) => addExclusion(scopeId, start, end),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ["scope", variables.scopeId] });
      qc.invalidateQueries({ queryKey: ["scopes"] });
    },
  });
}

export function useRemoveExclusion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      scopeId,
      start,
      end,
    }: {
      scopeId: string;
      start: string;
      end: string;
    }) => removeExclusion(scopeId, start, end),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ["scope", variables.scopeId] });
      qc.invalidateQueries({ queryKey: ["scopes"] });
    },
  });
}

export function useAddFailover() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ scopeId, data }: { scopeId: string; data: AddFailoverRequest }) =>
      addFailover(scopeId, data),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ["scopes"] });
      qc.invalidateQueries({ queryKey: ["scope", variables.scopeId] });
    },
  });
}

export function useUpdateFailover() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ scopeId, data }: { scopeId: string; data: UpdateFailoverRequest }) =>
      updateFailover(scopeId, data),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ["scopes"] });
      qc.invalidateQueries({ queryKey: ["scope", variables.scopeId] });
    },
  });
}
