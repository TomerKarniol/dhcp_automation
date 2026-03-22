"use client";

import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { useAddFailover, useUpdateFailover } from "@/hooks/use-scopes";
import type { FullScopeFailover } from "@/types/api";

// ─── Schemas ─────────────────────────────────────────────────────────────────

const addSchema = z.object({
  partner_server: z.string().min(1, "Partner server is required"),
  relationship_name: z.string().optional(),
  mode: z.enum(["HotStandby", "LoadBalance"]),
  server_role: z.enum(["Active", "Standby"]),
  reserve_percent: z.number({ invalid_type_error: "Invalid input: expected number" }).int().min(0).max(100),
  load_balance_percent: z.number({ invalid_type_error: "Invalid input: expected number" }).int().min(0).max(100),
  max_client_lead_time_minutes: z.number({ invalid_type_error: "Invalid input: expected number" }).int().min(1),
  shared_secret: z.string().min(8, "Minimum 8 characters").optional().or(z.literal("")),
});

const updateSchema = z.object({
  server_role: z.enum(["Active", "Standby"]).optional(),
  reserve_percent: z.number({ invalid_type_error: "Invalid input: expected number" }).int().min(0).max(100).nullable().optional(),
  load_balance_percent: z.number({ invalid_type_error: "Invalid input: expected number" }).int().min(0).max(100).nullable().optional(),
  max_client_lead_time_minutes: z.number({ invalid_type_error: "Invalid input: expected number" }).int().min(1).nullable().optional(),
  shared_secret: z.string().min(8, "Minimum 8 characters").optional().or(z.literal("")),
});

type AddFormValues = z.infer<typeof addSchema>;
type UpdateFormValues = z.infer<typeof updateSchema>;

// ─── Helper ──────────────────────────────────────────────────────────────────

function FormField({
  label,
  error,
  hint,
  children,
}: {
  label: string;
  error?: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs">{label}</Label>
      {children}
      {hint && !error && <p className="text-xs text-muted-foreground">{hint}</p>}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

// ─── Add Failover Dialog ──────────────────────────────────────────────────────

interface AddFailoverDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  scopeId: string;
}

export function AddFailoverDialog({ open, onOpenChange, scopeId }: AddFailoverDialogProps) {
  const addFailover = useAddFailover();

  const {
    register,
    handleSubmit,
    watch,
    reset,
    formState: { errors },
  } = useForm<AddFormValues>({
    resolver: zodResolver(addSchema),
    defaultValues: {
      partner_server: "dhcp02.lab.local",
      relationship_name: "",
      mode: "HotStandby",
      server_role: "Active",
      reserve_percent: 5,
      load_balance_percent: 50,
      max_client_lead_time_minutes: 60,
      shared_secret: "",
    },
  });

  const mode = watch("mode");

  function handleClose() {
    reset();
    onOpenChange(false);
  }

  async function onSubmit(values: AddFormValues) {
    try {
      await addFailover.mutateAsync({
        scopeId,
        data: {
          partner_server: values.partner_server,
          relationship_name: values.relationship_name || undefined,
          mode: values.mode,
          server_role: values.server_role,
          reserve_percent: values.reserve_percent,
          load_balance_percent: values.load_balance_percent,
          max_client_lead_time_minutes: values.max_client_lead_time_minutes,
          shared_secret: values.shared_secret || undefined,
        },
      });
      toast.success("Failover relationship added");
      handleClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to add failover");
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) handleClose(); }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2.5">
            <div className="flex size-8 items-center justify-center rounded-full bg-blue-500/15">
              <ShieldCheck className="size-4 text-blue-400" />
            </div>
            Configure Failover
          </DialogTitle>
        </DialogHeader>

        <form id="add-failover-form" onSubmit={handleSubmit(onSubmit)}>
          <div className="space-y-3 max-h-[60vh] overflow-y-auto px-0.5 pb-1">
            <FormField label="Partner Server *" error={errors.partner_server?.message}>
              <Input placeholder="dhcp02.lab.local" {...register("partner_server")} />
            </FormField>

            <FormField label="Relationship Name" error={errors.relationship_name?.message} hint="Auto-generated if left blank">
              <Input placeholder="FO-cluster-01 (optional)" {...register("relationship_name")} />
            </FormField>

            <Separator />

            <FormField label="Mode *">
              <select
                className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none dark:bg-input/30"
                {...register("mode")}
              >
                <option value="HotStandby">HotStandby</option>
                <option value="LoadBalance">LoadBalance</option>
              </select>
            </FormField>

            {mode === "HotStandby" && (
              <FormField label="Server Role *">
                <select
                  className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none dark:bg-input/30"
                  {...register("server_role")}
                >
                  <option value="Active">Active</option>
                  <option value="Standby">Standby</option>
                </select>
              </FormField>
            )}

            {mode === "HotStandby" ? (
              <FormField label="Reserve Percent (0–100)" error={errors.reserve_percent?.message}>
                <Input
                  type="number"
                  min={0}
                  max={100}
                  className="[appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                  {...register("reserve_percent", { valueAsNumber: true })}
                />
              </FormField>
            ) : (
              <FormField label="Load Balance Percent (0–100)" error={errors.load_balance_percent?.message}>
                <Input
                  type="number"
                  min={0}
                  max={100}
                  className="[appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                  {...register("load_balance_percent", { valueAsNumber: true })}
                />
              </FormField>
            )}

            <FormField label="Max Client Lead Time (minutes)" error={errors.max_client_lead_time_minutes?.message}>
              <Input
                type="number"
                min={1}
                className="[appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                {...register("max_client_lead_time_minutes", { valueAsNumber: true })}
              />
            </FormField>

            <FormField label="Shared Secret (min 8 chars)" error={errors.shared_secret?.message} hint="Optional">
              <Input type="password" placeholder="Optional" {...register("shared_secret")} />
            </FormField>
          </div>
        </form>

        <DialogFooter className="gap-2 sm:gap-2">
          <Button variant="outline" onClick={handleClose} disabled={addFailover.isPending} className="cursor-pointer flex-1">
            Cancel
          </Button>
          <Button
            type="submit"
            form="add-failover-form"
            disabled={addFailover.isPending}
            className="cursor-pointer flex-1 gap-2"
          >
            {addFailover.isPending ? (
              <><Loader2 className="size-4 animate-spin" />Adding…</>
            ) : (
              <><ShieldCheck className="size-4" />Add Failover</>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Edit Failover Dialog ─────────────────────────────────────────────────────

interface EditFailoverDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  scopeId: string;
  currentFailover: FullScopeFailover;
}

export function EditFailoverDialog({
  open,
  onOpenChange,
  scopeId,
  currentFailover,
}: EditFailoverDialogProps) {
  const updateFailover = useUpdateFailover();
  const isHotStandby = currentFailover.mode === "HotStandby";

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<UpdateFormValues>({
    resolver: zodResolver(updateSchema),
  });

  // Populate form with current values when dialog opens
  useEffect(() => {
    if (open) {
      reset({
        server_role: isHotStandby ? (currentFailover.server_role as "Active" | "Standby" | undefined ?? "Active") : undefined,
        reserve_percent: isHotStandby ? (currentFailover.reserve_percent ?? undefined) : undefined,
        load_balance_percent: !isHotStandby ? (currentFailover.load_balance_percent ?? undefined) : undefined,
        max_client_lead_time_minutes: undefined,
        shared_secret: "",
      });
    }
  }, [open, currentFailover, isHotStandby, reset]);

  function handleClose() {
    reset();
    onOpenChange(false);
  }

  async function onSubmit(values: UpdateFormValues) {
    try {
      await updateFailover.mutateAsync({
        scopeId,
        data: {
          server_role: isHotStandby ? (values.server_role ?? null) : null,
          reserve_percent: isHotStandby ? (values.reserve_percent ?? null) : null,
          load_balance_percent: !isHotStandby ? (values.load_balance_percent ?? null) : null,
          max_client_lead_time_minutes: values.max_client_lead_time_minutes ?? null,
          shared_secret: values.shared_secret || null,
        },
      });
      toast.success("Failover relationship updated");
      handleClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to update failover");
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) handleClose(); }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2.5">
            <div className="flex size-8 items-center justify-center rounded-full bg-blue-500/15">
              <ShieldCheck className="size-4 text-blue-400" />
            </div>
            Edit Failover
          </DialogTitle>
        </DialogHeader>

        {/* Read-only info */}
        <div className="rounded-lg border border-border bg-muted/30 px-4 py-3 space-y-1.5 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Relationship</span>
            <span className="font-mono text-xs">{currentFailover.relationship_name}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Partner</span>
            <span className="font-mono text-xs">{currentFailover.partner_server}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Mode</span>
            <span className="text-xs">{currentFailover.mode}</span>
          </div>
        </div>

        <p className="text-xs text-muted-foreground">
          Mode and partner server cannot be changed. To change these, delete and recreate the scope.
        </p>

        <form id="edit-failover-form" onSubmit={handleSubmit(onSubmit)}>
          <div className="space-y-3 px-0.5">
            {isHotStandby && (
              <>
                <FormField label="Server Role" error={errors.server_role?.message}>
                  <select
                    className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none dark:bg-input/30"
                    {...register("server_role")}
                  >
                    <option value="Active">Active</option>
                    <option value="Standby">Standby</option>
                  </select>
                </FormField>
                <p className="rounded-md border border-amber-500/25 bg-amber-500/8 px-3 py-2 text-xs text-amber-400">
                  Changing Server Role removes and recreates the failover relationship. The shared secret will be cleared.
                </p>
              </>
            )}
            {isHotStandby ? (
              <FormField label="Reserve Percent (0–100)" error={errors.reserve_percent?.message}>
                <Input
                  type="number"
                  min={0}
                  max={100}
                  className="[appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                  {...register("reserve_percent", { valueAsNumber: true })}
                />
              </FormField>
            ) : (
              <FormField label="Load Balance Percent (0–100)" error={errors.load_balance_percent?.message}>
                <Input
                  type="number"
                  min={0}
                  max={100}
                  className="[appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                  {...register("load_balance_percent", { valueAsNumber: true })}
                />
              </FormField>
            )}

            <FormField
              label="Max Client Lead Time (minutes)"
              error={errors.max_client_lead_time_minutes?.message}
              hint={currentFailover.max_client_lead_time ? `Current: ${currentFailover.max_client_lead_time}` : undefined}
            >
              <Input
                type="number"
                min={1}
                placeholder="Leave blank to keep current"
                autoComplete="off"
                className="[appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                {...register("max_client_lead_time_minutes", { valueAsNumber: true })}
              />
            </FormField>

            <FormField label="New Shared Secret (min 8 chars)" error={errors.shared_secret?.message} hint="Leave blank to keep current">
              <Input type="password" placeholder="Leave blank to keep current" autoComplete="new-password" {...register("shared_secret")} />
            </FormField>
          </div>
        </form>

        <DialogFooter className="gap-2 sm:gap-2">
          <Button variant="outline" onClick={handleClose} disabled={updateFailover.isPending} className="cursor-pointer flex-1">
            Cancel
          </Button>
          <Button
            type="submit"
            form="edit-failover-form"
            disabled={updateFailover.isPending}
            className="cursor-pointer flex-1 gap-2"
          >
            {updateFailover.isPending ? (
              <><Loader2 className="size-4 animate-spin" />Saving…</>
            ) : (
              <><ShieldCheck className="size-4" />Save Changes</>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
