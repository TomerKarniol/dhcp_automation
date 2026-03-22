"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, Trash2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Exclusion } from "@/types/api";
import { useAddExclusion, useRemoveExclusion } from "@/hooks/use-scopes";
import { exclusionSchema, type ExclusionFormValues } from "@/lib/validators";
import { cn } from "@/lib/utils";

interface ExclusionManagerProps {
  scopeId: string;
  exclusions: Exclusion[];
}

export function ExclusionManager({ scopeId, exclusions }: ExclusionManagerProps) {
  const [removingKey, setRemovingKey] = useState<string | null>(null);
  const addExclusion = useAddExclusion();
  const removeExclusion = useRemoveExclusion();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ExclusionFormValues>({
    resolver: zodResolver(exclusionSchema),
    defaultValues: { start_address: "", end_address: "" },
  });

  async function onAdd(values: ExclusionFormValues) {
    try {
      await addExclusion.mutateAsync({
        scopeId,
        start: values.start_address,
        end: values.end_address,
      });
      toast.success("Exclusion added");
      reset();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to add exclusion");
    }
  }

  async function handleRemove(start: string, end: string) {
    const key = `${start}-${end}`;
    setRemovingKey(key);
    try {
      await removeExclusion.mutateAsync({ scopeId, start, end });
      toast.success("Exclusion removed");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to remove exclusion");
    } finally {
      setRemovingKey(null);
    }
  }

  return (
    <div className="space-y-4">
      {/* Existing exclusions */}
      {exclusions.length === 0 ? (
        <p className="text-sm text-muted-foreground">No exclusion ranges configured.</p>
      ) : (
        <div className="space-y-2">
          {exclusions.map((exc) => {
            const key = `${exc.start_range}-${exc.end_range}`;
            const isRemoving = removingKey === key;
            return (
              <div
                key={key}
                className="flex items-center justify-between rounded-lg border border-border px-3 py-2 text-sm"
              >
                <span className="font-mono text-xs">
                  {exc.start_range}
                  <span className="mx-2 text-muted-foreground">–</span>
                  {exc.end_range}
                </span>
                <button
                  onClick={() => handleRemove(exc.start_range, exc.end_range)}
                  disabled={isRemoving}
                  className="flex size-6 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive disabled:cursor-not-allowed disabled:opacity-50"
                  title="Remove exclusion"
                >
                  {isRemoving ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <Trash2 className="size-3.5" />
                  )}
                </button>
              </div>
            );
          })}
        </div>
      )}

      {/* Add form */}
      <form onSubmit={handleSubmit(onAdd)} className="space-y-3">
        <div className="text-sm font-medium text-muted-foreground">Add Exclusion Range</div>
        <div className="flex gap-2">
          <div className="flex-1 space-y-1">
            <Label className="text-xs">Start address</Label>
            <Input
              placeholder="10.10.10.1"
              {...register("start_address")}
              aria-invalid={!!errors.start_address}
              className={cn(
                "font-mono text-xs",
                errors.start_address && "border-destructive"
              )}
            />
            {errors.start_address && (
              <p className="text-xs text-destructive">{errors.start_address.message}</p>
            )}
          </div>
          <div className="flex-1 space-y-1">
            <Label className="text-xs">End address</Label>
            <Input
              placeholder="10.10.10.10"
              {...register("end_address")}
              aria-invalid={!!errors.end_address}
              className={cn(
                "font-mono text-xs",
                errors.end_address && "border-destructive"
              )}
            />
            {errors.end_address && (
              <p className="text-xs text-destructive">{errors.end_address.message}</p>
            )}
          </div>
        </div>
        {errors.end_address?.message?.includes("less than") && (
          <p className="text-xs text-destructive">{errors.end_address.message}</p>
        )}
        <Button
          type="submit"
          variant="outline"
          size="sm"
          disabled={addExclusion.isPending}
          className="cursor-pointer"
        >
          {addExclusion.isPending ? (
            <>
              <Loader2 className="size-3.5 animate-spin" />
              Adding…
            </>
          ) : (
            <>
              <Plus className="size-3.5" />
              Add exclusion
            </>
          )}
        </Button>
      </form>
    </div>
  );
}
