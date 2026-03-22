"use client";

import { useState } from "react";
import { useForm, useFieldArray, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Plus,
  Trash2,
  Loader2,
  ChevronLeft,
  ChevronRight,
  Check,
} from "lucide-react";
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
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { useCreateScope } from "@/hooks/use-scopes";
import { createScopeSchema, type CreateScopeFormValues, ipToNumber } from "@/lib/validators";
import { formatLeaseDuration } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { DHCPScopeRequest, StepResult } from "@/types/api";

const STEPS = ["Basic Info", "DNS", "Exclusions", "Failover", "Review"] as const;

interface StepResultsDialogProps {
  open: boolean;
  onClose: () => void;
  steps: StepResult[];
  scopeName: string;
}

function StepResultsDialog({ open, onClose, steps, scopeName }: StepResultsDialogProps) {
  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Scope Created (Partial)</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Scope <span className="font-medium text-foreground">{scopeName}</span> was created with some steps failing:
        </p>
        <div className="space-y-2">
          {steps.map((step) => (
            <div
              key={step.step}
              className={cn(
                "flex items-start gap-3 rounded-lg border px-3 py-2 text-sm",
                step.success
                  ? "border-green-500/20 bg-green-500/10"
                  : "border-destructive/20 bg-destructive/10"
              )}
            >
              <span className={step.success ? "text-green-500" : "text-destructive"}>
                {step.success ? <Check className="size-4 mt-0.5" /> : "✕"}
              </span>
              <div>
                <div className="font-medium capitalize">{step.step.replace(/_/g, " ")}</div>
                <div className="text-xs text-muted-foreground">{step.detail ?? step.error}</div>
              </div>
            </div>
          ))}
        </div>
        <DialogFooter showCloseButton>
          <Button onClick={onClose} className="cursor-pointer">Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function computeAutoExclusions(network: string): Array<{ start_address: string; end_address: string }> {
  try {
    const base = ipToNumber(network);
    const start1 = (base + 1).toString().split("").reduce((acc) => acc, "");
    const toIp = (n: number) => {
      return [
        (n >>> 24) & 0xff,
        (n >>> 16) & 0xff,
        (n >>> 8) & 0xff,
        n & 0xff,
      ].join(".");
    };
    return [
      { start_address: toIp(base + 1), end_address: toIp(base + 10) },
      { start_address: toIp(base + 241), end_address: toIp(base + 254) },
    ];
  } catch {
    return [];
  }
}

interface CreateScopeWizardProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateScopeWizard({ open, onOpenChange }: CreateScopeWizardProps) {
  const [step, setStep] = useState(0);
  const [useFailover, setUseFailover] = useState(false);
  const [partialResult, setPartialResult] = useState<{ steps: StepResult[]; name: string } | null>(null);
  const createScope = useCreateScope();

  const {
    register,
    control,
    handleSubmit,
    watch,
    setValue,
    trigger,
    reset,
    formState: { errors },
  } = useForm<CreateScopeFormValues>({
    resolver: zodResolver(createScopeSchema),
    defaultValues: {
      scope_name: "",
      network: "",
      subnet_mask: "255.255.255.0",
      start_range: "",
      end_range: "",
      lease_duration_days: 8,
      description: "",
      gateway: "",
      dns_servers: ["10.10.1.5", "10.10.1.6"],
      dns_domain: "lab.local",
      exclusions: [],
      failover: undefined,
    },
  });

  const dnsServers = useWatch({ control, name: "dns_servers" }) as string[];

  function addDns() {
    setValue("dns_servers", [...dnsServers, ""]);
  }

  function removeDns(idx: number) {
    setValue("dns_servers", dnsServers.filter((_, i) => i !== idx));
  }

  const {
    fields: exclusionFields,
    append: appendExclusion,
    remove: removeExclusion,
  } = useFieldArray({
    control,
    name: "exclusions",
  });

  const watchedValues = watch();

  const stepValidationFields: Record<number, (keyof CreateScopeFormValues)[]> = {
    0: ["scope_name", "network", "subnet_mask", "start_range", "end_range", "lease_duration_days", "gateway"],
    1: ["dns_servers", "dns_domain"],
    2: ["exclusions"],
    3: ["failover"],
  };

  async function handleNext() {
    const fields = stepValidationFields[step];
    if (fields) {
      const valid = await trigger(fields);
      if (!valid) return;
    }

    if (step === 2 && watchedValues.network && watchedValues.subnet_mask && exclusionFields.length === 0) {
      // Auto-populate exclusions
      const auto = computeAutoExclusions(watchedValues.network);
      auto.forEach((exc) => appendExclusion(exc));
    }

    setStep((s) => s + 1);
  }

  function handleBack() {
    setStep((s) => Math.max(0, s - 1));
  }

  function handleClose() {
    reset();
    setStep(0);
    setUseFailover(false);
    onOpenChange(false);
  }

  async function onSubmit(values: CreateScopeFormValues) {
    const payload: DHCPScopeRequest = {
      scope_name: values.scope_name,
      network: values.network,
      subnet_mask: values.subnet_mask,
      start_range: values.start_range,
      end_range: values.end_range,
      lease_duration_days: values.lease_duration_days,
      dns_servers: values.dns_servers,
      ...(values.description?.trim() ? { description: values.description } : {}),
      ...(values.gateway?.trim() ? { gateway: values.gateway } : {}),
      ...(values.dns_domain?.trim() ? { dns_domain: values.dns_domain } : {}),
      ...(values.exclusions && values.exclusions.length > 0 ? { exclusions: values.exclusions } : {}),
      failover: useFailover && values.failover
        ? {
            partner_server: (values.failover as NonNullable<typeof values.failover>).partner_server ?? "dhcp02.lab.local",
            mode: (values.failover as NonNullable<typeof values.failover>).mode ?? "HotStandby",
            server_role: (values.failover as NonNullable<typeof values.failover>).server_role ?? "Active",
            reserve_percent: (values.failover as NonNullable<typeof values.failover>).reserve_percent ?? 5,
            load_balance_percent: (values.failover as NonNullable<typeof values.failover>).load_balance_percent ?? 50,
            max_client_lead_time_minutes: (values.failover as NonNullable<typeof values.failover>).max_client_lead_time_minutes ?? 1,
            ...(values.failover && (values.failover as NonNullable<typeof values.failover>).relationship_name
              ? { relationship_name: (values.failover as NonNullable<typeof values.failover>).relationship_name }
              : {}),
          }
        : null,
    };

    try {
      const result = await createScope.mutateAsync(payload);
      if (!result.overall_success) {
        setPartialResult({ steps: result.steps, name: result.scope_name });
        handleClose();
      } else {
        toast.success(`Scope "${result.scope_name}" created successfully`);
        handleClose();
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to create scope");
    }
  }

  const isLastStep = step === STEPS.length - 1;

  return (
    <>
      <Dialog open={open} onOpenChange={handleClose}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Create DHCP Scope</DialogTitle>
          </DialogHeader>

          {/* Step indicator */}
          <div className="flex items-center gap-1 overflow-x-auto pb-1">
            {STEPS.map((label, i) => (
              <div key={label} className="flex items-center gap-1 shrink-0">
                <div
                  className={cn(
                    "flex size-6 items-center justify-center rounded-full text-xs font-medium transition-colors",
                    i < step
                      ? "bg-green-500/20 text-green-500"
                      : i === step
                      ? "text-white"
                      : "bg-muted text-muted-foreground"
                  )}
                  style={
                    i === step
                      ? { background: "oklch(0.577 0.245 27)" }
                      : undefined
                  }
                >
                  {i < step ? <Check className="size-3.5" /> : i + 1}
                </div>
                <span
                  className={cn(
                    "text-xs",
                    i === step ? "font-medium text-foreground" : "text-muted-foreground"
                  )}
                >
                  {label}
                </span>
                {i < STEPS.length - 1 && (
                  <div className="mx-1 h-px w-4 bg-border" />
                )}
              </div>
            ))}
          </div>

          <Separator />

          {/* Step content */}
          <div className="max-h-[50vh] overflow-y-auto">
            <form id="wizard-form" onSubmit={handleSubmit(onSubmit)}>

              {/* Step 0: Basic Info */}
              {step === 0 && (
                <div className="space-y-3 px-0.5 pb-1">
                  <FormField label="Scope Name *" error={errors.scope_name?.message}>
                    <Input placeholder="cluster-01" {...register("scope_name")} aria-invalid={!!errors.scope_name} />
                  </FormField>
                  <div className="grid grid-cols-2 gap-3">
                    <FormField label="Network *" error={errors.network?.message}>
                      <Input placeholder="10.10.10.0" className="font-mono" {...register("network")} aria-invalid={!!errors.network} />
                    </FormField>
                    <FormField label="Subnet Mask *" error={errors.subnet_mask?.message}>
                      <Input placeholder="255.255.255.0" className="font-mono" {...register("subnet_mask")} aria-invalid={!!errors.subnet_mask} />
                    </FormField>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <FormField label="Start Range *" error={errors.start_range?.message}>
                      <Input placeholder="10.10.10.100" className="font-mono" {...register("start_range")} aria-invalid={!!errors.start_range} />
                    </FormField>
                    <FormField label="End Range *" error={errors.end_range?.message}>
                      <Input placeholder="10.10.10.200" className="font-mono" {...register("end_range")} aria-invalid={!!errors.end_range} />
                    </FormField>
                  </div>
                  <FormField label="Lease Duration (days) *" error={errors.lease_duration_days?.message}>
                    <Input
                      type="number"
                      min={1}
                      max={365}
                      className="[appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                      {...register("lease_duration_days", { valueAsNumber: true })}
                      aria-invalid={!!errors.lease_duration_days}
                    />
                  </FormField>
                  <FormField label="Gateway" error={errors.gateway?.message}>
                    <Input placeholder="10.10.10.1 (optional)" className="font-mono" {...register("gateway")} aria-invalid={!!errors.gateway} />
                  </FormField>
                  <FormField label="Description" error={errors.description?.message}>
                    <Input placeholder="Optional description" {...register("description")} aria-invalid={!!errors.description} />
                  </FormField>
                </div>
              )}

              {/* Step 1: DNS */}
              {step === 1 && (
                <div className="space-y-3 px-0.5 pb-1">
                  <FormField label="DNS Domain" error={errors.dns_domain?.message}>
                    <Input placeholder="lab.local" {...register("dns_domain")} />
                  </FormField>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label>DNS Servers *</Label>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={addDns}
                        className="cursor-pointer h-6 gap-1 text-xs"
                      >
                        <Plus className="size-3" />
                        Add
                      </Button>
                    </div>
                    {dnsServers.map((_, idx) => (
                      <div key={idx} className="flex items-center gap-2">
                        <Input
                          placeholder="10.10.1.5"
                          className="font-mono"
                          {...register(`dns_servers.${idx}`)}
                          aria-invalid={!!errors.dns_servers?.[idx]}
                        />
                        <button
                          type="button"
                          onClick={() => removeDns(idx)}
                          disabled={dnsServers.length === 1}
                          className="flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          <Trash2 className="size-3.5" />
                        </button>
                      </div>
                    ))}
                    {errors.dns_servers && !Array.isArray(errors.dns_servers) && (
                      <p className="text-xs text-destructive">{errors.dns_servers.message}</p>
                    )}
                  </div>
                </div>
              )}

              {/* Step 2: Exclusions */}
              {step === 2 && (
                <div className="space-y-3 px-0.5 pb-1">
                  <p className="text-xs text-muted-foreground">
                    Default exclusion ranges are auto-computed from the network (offsets 1–10 and 241–254).
                    You can add, edit, or remove them.
                  </p>
                  {exclusionFields.length === 0 && (
                    <p className="text-sm text-muted-foreground italic">No exclusions yet.</p>
                  )}
                  {exclusionFields.map((field, idx) => (
                    <div key={field.id} className="flex items-start gap-2">
                      <div className="flex-1 space-y-1">
                        <Label className="text-xs">Start</Label>
                        <Input
                          className="font-mono text-xs"
                          {...register(`exclusions.${idx}.start_address`)}
                          aria-invalid={!!errors.exclusions?.[idx]?.start_address}
                        />
                      </div>
                      <div className="flex-1 space-y-1">
                        <Label className="text-xs">End</Label>
                        <Input
                          className="font-mono text-xs"
                          {...register(`exclusions.${idx}.end_address`)}
                          aria-invalid={!!errors.exclusions?.[idx]?.end_address}
                        />
                      </div>
                      <div className="pt-5">
                        <button
                          type="button"
                          onClick={() => removeExclusion(idx)}
                          className="flex size-8 cursor-pointer items-center justify-center rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                        >
                          <Trash2 className="size-3.5" />
                        </button>
                      </div>
                    </div>
                  ))}
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => appendExclusion({ start_address: "", end_address: "" })}
                    className="cursor-pointer gap-1.5"
                  >
                    <Plus className="size-3.5" />
                    Add exclusion
                  </Button>
                </div>
              )}

              {/* Step 3: Failover */}
              {step === 3 && (
                <div className="space-y-4 px-0.5 pb-1">
                  <div className="flex items-center justify-between rounded-lg border border-border px-4 py-3">
                    <div>
                      <div className="text-sm font-medium">Configure Failover</div>
                      <div className="text-xs text-muted-foreground">Set up DHCP failover for high availability</div>
                    </div>
                    <Switch checked={useFailover} onCheckedChange={setUseFailover} />
                  </div>

                  {useFailover && (
                    <div className="space-y-3">
                      <FormField label="Partner Server *" error={(errors.failover as Record<string, {message?: string}>)?.partner_server?.message}>
                        <Input
                          placeholder="dhcp02.lab.local"
                          {...register("failover.partner_server")}
                          defaultValue="dhcp02.lab.local"
                        />
                      </FormField>
                      <FormField label="Relationship Name" error={(errors.failover as Record<string, {message?: string}>)?.relationship_name?.message}>
                        <Input placeholder="Optional" {...register("failover.relationship_name")} />
                      </FormField>
                      <div className="grid grid-cols-2 gap-3">
                        <FormField label="Mode *">
                          <select
                            className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none dark:bg-input/30"
                            {...register("failover.mode")}
                            defaultValue="HotStandby"
                          >
                            <option value="HotStandby">HotStandby</option>
                            <option value="LoadBalance">LoadBalance</option>
                          </select>
                        </FormField>
                        <FormField label="Server Role *">
                          <select
                            className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none dark:bg-input/30"
                            {...register("failover.server_role")}
                            defaultValue="Active"
                          >
                            <option value="Active">Active</option>
                            <option value="Standby">Standby</option>
                          </select>
                        </FormField>
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <FormField label="Reserve %" error={(errors.failover as Record<string, {message?: string}>)?.reserve_percent?.message}>
                          <Input
                            type="number"
                            min={0}
                            max={100}
                            defaultValue={5}
                            {...register("failover.reserve_percent", { valueAsNumber: true })}
                          />
                        </FormField>
                        <FormField label="Load Balance %" error={(errors.failover as Record<string, {message?: string}>)?.load_balance_percent?.message}>
                          <Input
                            type="number"
                            min={0}
                            max={100}
                            defaultValue={50}
                            {...register("failover.load_balance_percent", { valueAsNumber: true })}
                          />
                        </FormField>
                      </div>
                      <FormField label="Max Client Lead Time (minutes)" error={(errors.failover as Record<string, {message?: string}>)?.max_client_lead_time_minutes?.message}>
                        <Input
                          type="number"
                          min={1}
                          defaultValue={1}
                          {...register("failover.max_client_lead_time_minutes", { valueAsNumber: true })}
                        />
                      </FormField>
                      <FormField label="Shared Secret (min 8 chars)" error={(errors.failover as Record<string, {message?: string}>)?.shared_secret?.message}>
                        <Input type="password" placeholder="Optional" {...register("failover.shared_secret")} />
                      </FormField>
                    </div>
                  )}
                </div>
              )}

              {/* Step 4: Review */}
              {step === 4 && (
                <div className="space-y-3 px-0.5 pb-1 text-sm">
                  <ReviewSection title="Basic Info">
                    <ReviewRow label="Name" value={watchedValues.scope_name} />
                    <ReviewRow label="Network" value={`${watchedValues.network} / ${watchedValues.subnet_mask}`} mono />
                    <ReviewRow label="Range" value={`${watchedValues.start_range} – ${watchedValues.end_range}`} mono />
                    <ReviewRow label="Lease" value={formatLeaseDuration(`${watchedValues.lease_duration_days}.00:00:00`)} />
                    {watchedValues.gateway && <ReviewRow label="Gateway" value={watchedValues.gateway} mono />}
                    {watchedValues.description && <ReviewRow label="Description" value={watchedValues.description} />}
                  </ReviewSection>

                  <ReviewSection title="DNS">
                    <ReviewRow label="Domain" value={watchedValues.dns_domain || "—"} />
                    <ReviewRow
                      label="Servers"
                      value={watchedValues.dns_servers.join(", ")}
                      mono
                    />
                  </ReviewSection>

                  <ReviewSection title="Exclusions">
                    {watchedValues.exclusions && watchedValues.exclusions.length > 0 ? (
                      watchedValues.exclusions.map((exc, i) => (
                        <ReviewRow
                          key={i}
                          label={`Range ${i + 1}`}
                          value={`${exc.start_address} – ${exc.end_address}`}
                          mono
                        />
                      ))
                    ) : (
                      <span className="text-muted-foreground italic">None</span>
                    )}
                  </ReviewSection>

                  <ReviewSection title="Failover">
                    {useFailover && watchedValues.failover ? (
                      <>
                        <ReviewRow label="Mode" value={(watchedValues.failover as {mode?: string}).mode ?? "—"} />
                        <ReviewRow label="Partner" value={(watchedValues.failover as {partner_server?: string}).partner_server ?? "—"} mono />
                      </>
                    ) : (
                      <span className="text-muted-foreground italic">Not configured</span>
                    )}
                  </ReviewSection>
                </div>
              )}
            </form>
          </div>

          <Separator />

          {/* Footer navigation */}
          <DialogFooter className="flex-row justify-between border-0 bg-transparent p-0 m-0">
            <Button
              type="button"
              variant="ghost"
              onClick={handleBack}
              disabled={step === 0}
              className="cursor-pointer gap-1.5"
            >
              <ChevronLeft className="size-4" />
              Back
            </Button>

            {isLastStep ? (
              <Button
                type="submit"
                form="wizard-form"
                disabled={createScope.isPending}
                className="cursor-pointer gap-1.5"
              >
                {createScope.isPending ? (
                  <>
                    <Loader2 className="size-4 animate-spin" />
                    Creating…
                  </>
                ) : (
                  <>
                    <Check className="size-4" />
                    Create Scope
                  </>
                )}
              </Button>
            ) : (
              <Button
                type="button"
                onClick={handleNext}
                className="cursor-pointer gap-1.5"
              >
                Next
                <ChevronRight className="size-4" />
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Partial success dialog */}
      {partialResult && (
        <StepResultsDialog
          open={!!partialResult}
          onClose={() => setPartialResult(null)}
          steps={partialResult.steps}
          scopeName={partialResult.name}
        />
      )}
    </>
  );
}

// ─── Helper components ────────────────────────────────────────────────────────

function FormField({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs">{label}</Label>
      {children}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

function ReviewSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2 rounded-lg border border-border p-3">
      <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function ReviewRow({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={cn("text-xs text-right", mono && "font-mono")}>{value}</span>
    </div>
  );
}
