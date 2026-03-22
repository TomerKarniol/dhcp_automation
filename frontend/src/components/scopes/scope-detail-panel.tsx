"use client";

import { useState } from "react";
import { Loader2, Pencil, Trash2, ShieldCheck, Plus } from "lucide-react";
import { toast } from "sonner";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import type { FullScopeInfo } from "@/types/api";
import { formatLeaseDuration, formatScopeId } from "@/lib/format";
import { useSetScopeState } from "@/hooks/use-scopes";
import { DnsEditDialog } from "./dns-edit-dialog";
import { ExclusionManager } from "./exclusion-manager";
import { DeleteScopeDialog } from "./delete-scope-dialog";
import { AddFailoverDialog, EditFailoverDialog } from "./failover-dialog";
import { cn } from "@/lib/utils";

interface ScopeDetailPanelProps {
  scope: FullScopeInfo | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDeleted?: () => void;
}

function InfoRow({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={cn("text-sm", mono && "font-mono")}>{value}</span>
    </div>
  );
}

export function ScopeDetailPanel({
  scope,
  open,
  onOpenChange,
  onDeleted,
}: ScopeDetailPanelProps) {
  const [showDnsEdit, setShowDnsEdit] = useState(false);
  const [showDelete, setShowDelete] = useState(false);
  const [showAddFailover, setShowAddFailover] = useState(false);
  const [showEditFailover, setShowEditFailover] = useState(false);
  const setScopeState = useSetScopeState();

  if (!scope) return null;

  const isActive = scope.state === "Active";
  const cidr = formatScopeId(scope.scope_id, scope.subnet_mask);

  async function handleStateToggle(checked: boolean) {
    const newState = checked ? "Active" : "Inactive";
    try {
      await setScopeState.mutateAsync({
        scopeId: scope.scope_id,
        state: newState,
      });
      toast.success(`Scope ${newState.toLowerCase()}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to update state");
    }
  }

  return (
    <>
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent
          side="right"
          className="flex w-full flex-col gap-0 p-0 md:w-[600px] md:max-w-[600px] sm:max-w-full overflow-hidden"
          showCloseButton={false}
        >
          {/* Panel header */}
          <SheetHeader className="flex flex-row items-center justify-between border-b border-border/60 px-5 py-4">
            <div className="min-w-0">
              <SheetTitle className="truncate text-base">{scope.name}</SheetTitle>
              <p className="font-mono text-xs text-muted-foreground">{cidr}</p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {isActive ? (
                <Badge
                  className="gap-1 bg-green-500/15 text-green-500 border-green-500/20"
                  variant="outline"
                >
                  <span className="size-1.5 rounded-full bg-green-500" />
                  Active
                </Badge>
              ) : (
                <Badge variant="secondary">Inactive</Badge>
              )}
              <button
                onClick={() => onOpenChange(false)}
                className="flex size-7 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              >
                ✕
              </button>
            </div>
          </SheetHeader>

          {/* Tabs */}
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
            <Tabs defaultValue="overview" className="flex min-h-0 flex-1 flex-col gap-0">
              <div className="border-b border-border/60 px-5 pt-3 pb-0">
                <TabsList variant="line" className="w-full justify-start gap-0 h-auto rounded-none bg-transparent p-0">
                  {["overview", "network", "dns", "exclusions", "failover"].map((tab) => (
                    <TabsTrigger
                      key={tab}
                      value={tab}
                      className="capitalize rounded-none border-0 px-3 pb-3 pt-1 text-xs"
                    >
                      {tab}
                    </TabsTrigger>
                  ))}
                </TabsList>
              </div>

              <div className="flex-1 overflow-y-auto">
                {/* Overview */}
                <TabsContent value="overview" className="p-5">
                  <div className="space-y-4">
                    <div className="flex items-center justify-between rounded-lg border border-border px-4 py-3">
                      <div>
                        <div className="text-sm font-medium">Scope State</div>
                        <div className="text-xs text-muted-foreground">
                          {isActive ? "Scope is active and serving leases" : "Scope is inactive"}
                        </div>
                      </div>
                      {setScopeState.isPending ? (
                        <Loader2 className="size-4 animate-spin text-muted-foreground" />
                      ) : (
                        <Switch
                          checked={isActive}
                          onCheckedChange={handleStateToggle}
                        />
                      )}
                    </div>

                    <div className="grid gap-3">
                      <InfoRow label="Scope ID" value={scope.scope_id} mono />
                      <InfoRow label="Name" value={scope.name} />
                      <InfoRow label="Lease Duration" value={formatLeaseDuration(scope.lease_duration)} />
                      <InfoRow
                        label="Description"
                        value={
                          scope.description || (
                            <span className="italic text-muted-foreground">No description</span>
                          )
                        }
                      />
                    </div>
                  </div>
                </TabsContent>

                {/* Network */}
                <TabsContent value="network" className="p-5">
                  <div className="grid gap-3">
                    <InfoRow
                      label="Subnet Mask"
                      value={`${scope.subnet_mask} (/${cidr.split("/")[1]})`}
                      mono
                    />
                    <Separator />
                    <InfoRow label="Start Range" value={scope.start_range} mono />
                    <InfoRow label="End Range" value={scope.end_range} mono />
                    <Separator />
                    <InfoRow
                      label="Gateway"
                      value={
                        scope.gateway || (
                          <span className="italic text-muted-foreground">No gateway configured</span>
                        )
                      }
                      mono={!!scope.gateway}
                    />
                  </div>
                </TabsContent>

                {/* DNS */}
                <TabsContent value="dns" className="p-5">
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <div className="text-sm font-medium">DNS Configuration</div>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setShowDnsEdit(true)}
                        className="cursor-pointer gap-1.5"
                      >
                        <Pencil className="size-3.5" />
                        Edit DNS
                      </Button>
                    </div>

                    <div className="grid gap-3">
                      <InfoRow
                        label="DNS Domain"
                        value={
                          scope.dns_domain || (
                            <span className="italic text-muted-foreground">Not set</span>
                          )
                        }
                      />
                      <div className="flex flex-col gap-1.5">
                        <span className="text-xs text-muted-foreground">DNS Servers</span>
                        <div className="space-y-1">
                          {scope.dns_servers.length === 0 ? (
                            <span className="text-sm italic text-muted-foreground">No servers</span>
                          ) : (
                            scope.dns_servers.map((srv) => (
                              <div
                                key={srv}
                                className="font-mono text-sm rounded-md border border-border px-3 py-1.5"
                              >
                                {srv}
                              </div>
                            ))
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                </TabsContent>

                {/* Exclusions */}
                <TabsContent value="exclusions" className="p-5">
                  <ExclusionManager
                    scopeId={scope.scope_id}
                    exclusions={scope.exclusions}
                  />
                </TabsContent>

                {/* Failover */}
                <TabsContent value="failover" className="p-5">
                  {scope.failover ? (
                    <div className="space-y-4">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <ShieldCheck className="size-4 text-blue-400" />
                          <span className="text-sm font-medium">Failover Configured</span>
                          <Badge
                            className="border-blue-500/30 bg-blue-500/10 text-blue-400"
                            variant="outline"
                          >
                            {scope.failover.mode}
                          </Badge>
                        </div>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setShowEditFailover(true)}
                          className="cursor-pointer gap-1.5"
                        >
                          <Pencil className="size-3.5" />
                          Edit
                        </Button>
                      </div>
                      <div className="grid gap-3">
                        <InfoRow label="Relationship Name" value={scope.failover.relationship_name} />
                        <InfoRow label="Partner Server" value={scope.failover.partner_server} mono />
                        <InfoRow label="Mode" value={scope.failover.mode} />
                        <InfoRow label="State" value={scope.failover.state} />
                        {scope.failover.server_role && (
                          <InfoRow label="Server Role" value={scope.failover.server_role} />
                        )}
                        {scope.failover.reserve_percent != null && (
                          <InfoRow
                            label="Reserve Percent"
                            value={`${scope.failover.reserve_percent}%`}
                          />
                        )}
                        {scope.failover.load_balance_percent != null && (
                          <InfoRow
                            label="Load Balance Percent"
                            value={`${scope.failover.load_balance_percent}%`}
                          />
                        )}
                        {scope.failover.max_client_lead_time && (
                          <InfoRow
                            label="Max Client Lead Time"
                            value={scope.failover.max_client_lead_time}
                          />
                        )}
                        <div className="flex flex-col gap-1.5">
                          <span className="text-xs text-muted-foreground">Scope IDs</span>
                          <div className="flex flex-wrap gap-1">
                            {scope.failover.scope_ids.map((id) => (
                              <Badge key={id} variant="outline" className="font-mono text-xs">
                                {id}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center justify-center gap-4 py-12 text-center">
                      <div className="flex size-14 items-center justify-center rounded-full bg-muted">
                        <ShieldCheck className="size-7 text-muted-foreground opacity-50" />
                      </div>
                      <div>
                        <p className="text-sm font-medium">No failover configured</p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          Add a failover relationship to enable high availability for this scope.
                        </p>
                      </div>
                      <Button
                        onClick={() => setShowAddFailover(true)}
                        className="cursor-pointer gap-2"
                      >
                        <Plus className="size-4" />
                        Configure Failover
                      </Button>
                    </div>
                  )}
                </TabsContent>
              </div>
            </Tabs>
          </div>

          {/* Bottom action bar */}
          <div className="border-t border-border/60 px-5 py-3">
            <Button
              variant="destructive"
              size="sm"
              onClick={() => setShowDelete(true)}
              className="cursor-pointer gap-1.5"
            >
              <Trash2 className="size-3.5" />
              Delete Scope
            </Button>
          </div>
        </SheetContent>
      </Sheet>

      {/* Sub-dialogs */}
      <DnsEditDialog
        open={showDnsEdit}
        onOpenChange={setShowDnsEdit}
        scopeId={scope.scope_id}
        currentDnsServers={scope.dns_servers}
        currentDnsDomain={scope.dns_domain}
      />

      <DeleteScopeDialog
        open={showDelete}
        onOpenChange={setShowDelete}
        scopeId={scope.scope_id}
        scopeName={scope.name}
        onDeleted={() => {
          onOpenChange(false);
          onDeleted?.();
        }}
      />

      <AddFailoverDialog
        open={showAddFailover}
        onOpenChange={setShowAddFailover}
        scopeId={scope.scope_id}
      />

      {scope.failover && (
        <EditFailoverDialog
          open={showEditFailover}
          onOpenChange={setShowEditFailover}
          scopeId={scope.scope_id}
          currentFailover={scope.failover}
        />
      )}
    </>
  );
}
