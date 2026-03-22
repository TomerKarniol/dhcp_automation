"use client";

import { useState, useMemo } from "react";
import { Plus, RefreshCw, Search, Filter, ChevronDown } from "lucide-react";
import { useScopes } from "@/hooks/use-scopes";
import { ScopeCard } from "@/components/scopes/scope-card";
import { ScopeCardSkeleton } from "@/components/scopes/scope-card-skeleton";
import { ScopeDetailPanel } from "@/components/scopes/scope-detail-panel";
import { CreateScopeWizard } from "@/components/scopes/create-scope-wizard";
import type { FullScopeInfo } from "@/types/api";
import { cn } from "@/lib/utils";

type StateFilter = "all" | "Active" | "Inactive";

const SITES = ["London", "NewYork", "Tokyo", "Berlin", "Paris"] as const;

export default function DashboardPage() {
  const { data, isLoading, isFetching, isError, error, refetch } = useScopes();

  const [search, setSearch] = useState("");
  const [stateFilter, setStateFilter] = useState<StateFilter>("all");
  const [selectedScopeId, setSelectedScopeId] = useState<string | null>(null);
  const [showCreateWizard, setShowCreateWizard] = useState(false);
  const [collapsedSites, setCollapsedSites] = useState<Set<string>>(new Set());

  function toggleSite(city: string) {
    setCollapsedSites((prev) => {
      const next = new Set(prev);
      if (next.has(city)) next.delete(city);
      else next.add(city);
      return next;
    });
  }

  const scopes = data?.scopes ?? [];
  const selectedScope = scopes.find((s) => s.scope_id === selectedScopeId) ?? null;

  const filtered = useMemo(() => {
    return scopes.filter((scope) => {
      const matchesSearch =
        !search ||
        scope.name.toLowerCase().includes(search.toLowerCase()) ||
        scope.scope_id.includes(search) ||
        scope.description?.toLowerCase().includes(search.toLowerCase());

      const matchesState =
        stateFilter === "all" || scope.state === stateFilter;

      return matchesSearch && matchesState;
    });
  }, [scopes, search, stateFilter]);

  const siteGroups = useMemo(() => {
    const groups: Record<string, typeof filtered> = { Other: [] };
    for (const city of SITES) groups[city] = [];
    for (const scope of filtered) {
      const city = SITES.find((c) =>
        scope.name.toLowerCase().includes(c.toLowerCase())
      );
      if (city) groups[city].push(scope);
      else groups["Other"].push(scope);
    }
    return groups;
  }, [filtered]);

  function handleSelectScope(scope: FullScopeInfo) {
    setSelectedScopeId(scope.scope_id);
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* Page header */}
      <div className="border-b border-border/60 bg-background/80 px-6 py-4">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-lg font-semibold">DHCP Scopes</h1>
            <p className="text-sm text-muted-foreground">
              {isLoading
                ? "Loading scopes…"
                : `${scopes.length} scope${scopes.length !== 1 ? "s" : ""} total`}
            </p>
          </div>
          <button
            onClick={() => setShowCreateWizard(true)}
            className="flex cursor-pointer items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-white transition-all hover:opacity-90 active:scale-95"
            style={{ background: "oklch(0.577 0.245 27)" }}
          >
            <Plus className="size-4" />
            <span className="hidden sm:inline">New Scope</span>
          </button>
        </div>

        {/* Filters */}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {/* Search */}
          <div className="relative flex-1 min-w-48">
            <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name, IP, description…"
              className="h-8 w-full rounded-lg border border-input bg-transparent pl-8 pr-3 text-sm outline-none placeholder:text-muted-foreground focus:border-ring focus:ring-2 focus:ring-ring/30 dark:bg-input/30"
            />
          </div>

          {/* State filter */}
          <div className="flex items-center gap-1 rounded-lg border border-input p-0.5">
            {(["all", "Active", "Inactive"] as StateFilter[]).map((f) => (
              <button
                key={f}
                onClick={() => setStateFilter(f)}
                className={cn(
                  "cursor-pointer rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                  stateFilter === f
                    ? "bg-foreground text-background"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                {f === "all" ? "All" : f}
              </button>
            ))}
          </div>

          {/* Count badge */}
          {!isLoading && (
            <span className="text-xs text-muted-foreground">
              {filtered.length} result{filtered.length !== 1 ? "s" : ""}
            </span>
          )}

          {/* Refresh */}
          <button
            onClick={() => refetch()}
            title="Refresh"
            disabled={isFetching}
            className="flex size-8 cursor-pointer items-center justify-center rounded-lg border border-border text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:cursor-default disabled:opacity-60"
          >
            <RefreshCw className={cn("size-3.5", isFetching && "animate-spin")} />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-5">
        {/* Error state */}
        {isError && (
          <div className="flex flex-col items-center justify-center gap-4 py-20 text-center">
            <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-6 py-5">
              <p className="text-sm font-medium text-destructive">
                Failed to load scopes
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {error instanceof Error ? error.message : "Unknown error"}
              </p>
              <button
                onClick={() => refetch()}
                className="mt-3 cursor-pointer rounded-lg border border-border px-3 py-1.5 text-xs text-foreground transition-colors hover:bg-muted"
              >
                Try again
              </button>
            </div>
          </div>
        )}

        {/* Loading skeletons */}
        {isLoading && (
          <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <ScopeCardSkeleton key={i} />
            ))}
          </div>
        )}

        {/* City sections — always visible when not loading/error */}
        {!isLoading && !isError && (
          <div className="space-y-6">
            {[...SITES, "Other" as const].map((city) => {
              const cityScopes = siteGroups[city] ?? [];
              const isCollapsed = collapsedSites.has(city);
              // Hide "Other" section entirely when empty
              if (city === "Other" && cityScopes.length === 0) return null;

              return (
                <section key={city}>
                  {/* Section header — clickable to collapse */}
                  <button
                    type="button"
                    onClick={() => toggleSite(city)}
                    className="mb-3 flex w-full cursor-pointer items-center gap-3 group"
                  >
                    <ChevronDown
                      className={cn(
                        "size-3.5 text-muted-foreground transition-transform duration-200",
                        isCollapsed && "-rotate-90"
                      )}
                    />
                    <h2 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground group-hover:text-foreground transition-colors">
                      {city}
                    </h2>
                    <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                      {cityScopes.length}
                    </span>
                    <div className="flex-1 border-t border-border/40" />
                  </button>

                  {/* Cards or empty state */}
                  {!isCollapsed && (
                    cityScopes.length > 0 ? (
                      <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
                        {cityScopes.map((scope) => (
                          <ScopeCard
                            key={scope.scope_id}
                            scope={scope}
                            onSelect={handleSelectScope}
                          />
                        ))}
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 rounded-lg border border-dashed border-border/50 px-4 py-3 text-xs text-muted-foreground">
                        <Filter className="size-3.5 opacity-50" />
                        {scopes.length === 0
                          ? "No scopes yet"
                          : "No matching scopes"}
                      </div>
                    )
                  )}
                </section>
              );
            })}
          </div>
        )}
      </div>

      {/* Detail panel */}
      <ScopeDetailPanel
        scope={selectedScope}
        open={selectedScopeId !== null}
        onOpenChange={(open) => { if (!open) setSelectedScopeId(null); }}
        onDeleted={() => setSelectedScopeId(null)}
      />

      {/* Create wizard */}
      <CreateScopeWizard
        open={showCreateWizard}
        onOpenChange={setShowCreateWizard}
      />
    </div>
  );
}
