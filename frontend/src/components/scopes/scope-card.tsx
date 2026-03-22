"use client";

import { useState } from "react";
import {
  Power,
  Trash2,
  Globe,
  Clock,
  Server,
  ShieldCheck,
  Loader2,
} from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DeleteScopeDialog } from "@/components/scopes/delete-scope-dialog";
import type { FullScopeInfo } from "@/types/api";
import { formatLeaseDuration, formatScopeId } from "@/lib/format";
import { useSetScopeState } from "@/hooks/use-scopes";
import { cn } from "@/lib/utils";

interface ScopeCardProps {
  scope: FullScopeInfo;
  onSelect: (scope: FullScopeInfo) => void;
}

export function ScopeCard({ scope, onSelect }: ScopeCardProps) {
  const [hovered, setHovered] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const setScopeState = useSetScopeState();

  const isActive = scope.state === "Active";
  const cidr = formatScopeId(scope.scope_id, scope.subnet_mask);

  async function handleToggleState(e: React.MouseEvent) {
    e.stopPropagation();
    const newState = isActive ? "Inactive" : "Active";
    try {
      await setScopeState.mutateAsync({ scopeId: scope.scope_id, state: newState });
      toast.success(`Scope ${newState.toLowerCase()}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to update state");
    }
  }

  function handleDeleteClick(e: React.MouseEvent) {
    e.stopPropagation();
    setShowDeleteDialog(true);
  }

  return (
    <>
      <Card
        className={cn(
          "flex cursor-pointer flex-col gap-0 overflow-hidden transition-all duration-200",
          hovered ? "ring-2" : "ring-1 ring-foreground/10"
        )}
        style={
          hovered
            ? { boxShadow: "0 0 0 2px oklch(0.577 0.245 27 / 40%)" }
            : undefined
        }
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        onClick={() => onSelect(scope)}
      >
        {/* Header */}
        <CardHeader className="border-b border-border/60 pb-3">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="truncate font-semibold leading-tight">{scope.name}</div>
              <div className="mt-0.5 text-xs text-muted-foreground font-mono">{cidr}</div>
            </div>
            <div className="flex shrink-0 items-center gap-1">
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
            </div>
          </div>
        </CardHeader>

        {/* Body */}
        <CardContent className="flex flex-1 flex-col gap-3 py-3">
          {/* Network */}
          <div className="flex items-start gap-2 text-sm">
            <Globe className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
            <div className="min-w-0">
              <div className="text-xs text-muted-foreground">Network</div>
              <div className="font-mono text-xs">
                {scope.start_range} – {scope.end_range}
              </div>
              <div className="text-xs text-muted-foreground">
                {scope.gateway ? `Gateway: ${scope.gateway}` : "No gateway"}
              </div>
            </div>
          </div>

          {/* Config */}
          <div className="flex items-start gap-2 text-sm">
            <Clock className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
            <div className="min-w-0">
              <div className="text-xs text-muted-foreground">Lease</div>
              <div className="text-xs">{formatLeaseDuration(scope.lease_duration)}</div>
              {scope.description ? (
                <div className="truncate text-xs text-muted-foreground">
                  {scope.description}
                </div>
              ) : (
                <div className="text-xs italic text-muted-foreground">No description</div>
              )}
            </div>
          </div>

          {/* DNS */}
          <div className="flex items-start gap-2 text-sm">
            <Server className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
            <div className="min-w-0">
              <div className="text-xs text-muted-foreground">Search domain: {scope.dns_domain || "—"}</div>
              <div className="text-xs text-muted-foreground">DNS servers: {scope.dns_servers.length > 0 ? scope.dns_servers.join(", ") : "—"}</div>
            </div>
          </div>

          {/* Badges */}
          <div className="flex flex-wrap gap-1.5 pt-1">
            {scope.exclusions.length > 0 && (
              <Badge variant="outline" className="text-xs">
                {scope.exclusions.length} exclusion{scope.exclusions.length !== 1 ? "s" : ""}
              </Badge>
            )}
            {scope.failover ? (
              <Badge
                variant="outline"
                className="gap-1 border-blue-500/30 bg-blue-500/10 text-blue-400 text-xs"
              >
                <ShieldCheck className="size-3" />
                {scope.failover.mode}
              </Badge>
            ) : (
              <Badge variant="secondary" className="text-xs">
                No failover
              </Badge>
            )}
          </div>
        </CardContent>

        {/* Quick actions */}
        <div className="flex items-center justify-end gap-1 border-t border-border/60 px-3 py-2">
          <button
            onClick={handleToggleState}
            disabled={setScopeState.isPending}
            title={isActive ? "Deactivate scope" : "Activate scope"}
            className={cn(
              "flex size-7 cursor-pointer items-center justify-center rounded-md transition-colors",
              isActive
                ? "text-muted-foreground hover:bg-amber-500/10 hover:text-amber-400"
                : "text-muted-foreground hover:bg-green-500/10 hover:text-green-400",
              "disabled:cursor-not-allowed disabled:opacity-50"
            )}
          >
            {setScopeState.isPending ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Power className="size-3.5" />
            )}
          </button>
          <button
            onClick={handleDeleteClick}
            title="Delete scope"
            className="flex size-7 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
          >
            <Trash2 className="size-3.5" />
          </button>
        </div>
      </Card>

      <DeleteScopeDialog
        open={showDeleteDialog}
        onOpenChange={setShowDeleteDialog}
        scopeId={scope.scope_id}
        scopeName={scope.name}
      />
    </>
  );
}
