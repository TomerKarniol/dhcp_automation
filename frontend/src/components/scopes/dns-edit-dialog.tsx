"use client";

import { useEffect } from "react";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, Trash2, Loader2 } from "lucide-react";
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
import { useUpdateDns } from "@/hooks/use-scopes";
import { dnsUpdateSchema, type DnsUpdateFormValues } from "@/lib/validators";
import { cn } from "@/lib/utils";

interface DnsEditDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  scopeId: string;
  currentDnsServers: string[];
  currentDnsDomain: string | null;
}

export function DnsEditDialog({
  open,
  onOpenChange,
  scopeId,
  currentDnsServers,
  currentDnsDomain,
}: DnsEditDialogProps) {
  const updateDns = useUpdateDns();

  const {
    register,
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<DnsUpdateFormValues>({
    resolver: zodResolver(dnsUpdateSchema),
    defaultValues: {
      dns_servers: currentDnsServers.length > 0 ? currentDnsServers : [""],
      dns_domain: currentDnsDomain ?? "",
    },
  });

  const { fields, append, remove } = useFieldArray({
    control,
    // @ts-expect-error - useFieldArray expects object fields but we have string array
    name: "dns_servers",
  });

  useEffect(() => {
    if (open) {
      reset({
        dns_servers: currentDnsServers.length > 0 ? currentDnsServers : [""],
        dns_domain: currentDnsDomain ?? "",
      });
    }
  }, [open, currentDnsServers, currentDnsDomain, reset]);

  async function onSubmit(values: DnsUpdateFormValues) {
    try {
      await updateDns.mutateAsync({
        scopeId,
        data: {
          dns_servers: values.dns_servers,
          dns_domain: values.dns_domain?.trim() || null,
        },
      });
      toast.success("DNS settings updated");
      onOpenChange(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to update DNS");
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Edit DNS Settings</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {/* DNS Domain */}
          <div className="space-y-1.5">
            <Label htmlFor="dns_domain">DNS Domain</Label>
            <Input
              id="dns_domain"
              placeholder="lab.local"
              {...register("dns_domain")}
              aria-invalid={!!errors.dns_domain}
            />
            {errors.dns_domain && (
              <p className="text-xs text-destructive">{errors.dns_domain.message}</p>
            )}
          </div>

          {/* DNS Servers */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>DNS Servers</Label>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => append("")}
                className="cursor-pointer h-6 gap-1 text-xs"
              >
                <Plus className="size-3" />
                Add server
              </Button>
            </div>

            <div className="space-y-2">
              {fields.map((field, index) => (
                <div key={field.id} className="flex items-center gap-2">
                  <Input
                    placeholder="10.10.1.5"
                    {...register(`dns_servers.${index}`)}
                    aria-invalid={!!errors.dns_servers?.[index]}
                    className={cn(
                      errors.dns_servers?.[index] && "border-destructive"
                    )}
                  />
                  <button
                    type="button"
                    onClick={() => remove(index)}
                    disabled={fields.length === 1}
                    className="flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              ))}
            </div>

            {errors.dns_servers && !Array.isArray(errors.dns_servers) && (
              <p className="text-xs text-destructive">
                {errors.dns_servers.message}
              </p>
            )}
          </div>

          <DialogFooter showCloseButton>
            <Button
              type="submit"
              disabled={updateDns.isPending}
              className="cursor-pointer"
            >
              {updateDns.isPending ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  Saving…
                </>
              ) : (
                "Save changes"
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
