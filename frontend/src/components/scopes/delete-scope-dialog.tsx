"use client";

import { useState } from "react";
import { Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogCancel,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useDeleteScope } from "@/hooks/use-scopes";

interface DeleteScopeDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  scopeId: string;
  scopeName: string;
  onDeleted?: () => void;
}

export function DeleteScopeDialog({
  open,
  onOpenChange,
  scopeId,
  scopeName,
  onDeleted,
}: DeleteScopeDialogProps) {
  const [confirmName, setConfirmName] = useState("");
  const deleteScope = useDeleteScope();

  const canDelete = confirmName === scopeName;

  async function handleDelete() {
    try {
      await deleteScope.mutateAsync(scopeId);
      toast.success(`Scope "${scopeName}" deleted`);
      onOpenChange(false);
      setConfirmName("");
      onDeleted?.();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to delete scope");
    }
  }

  function handleOpenChange(v: boolean) {
    if (!v) setConfirmName("");
    onOpenChange(v);
  }

  return (
    <AlertDialog open={open} onOpenChange={handleOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <Trash2 className="size-4 text-destructive" />
            Delete scope
          </AlertDialogTitle>
          <AlertDialogDescription>
            This action is irreversible. The scope{" "}
            <span className="font-semibold text-foreground">{scopeName}</span>{" "}
            and all its configuration will be permanently deleted.
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">
            Type <span className="font-mono font-medium text-foreground">{scopeName}</span> to confirm:
          </p>
          <Input
            value={confirmName}
            onChange={(e) => setConfirmName(e.target.value)}
            placeholder={scopeName}
            disabled={deleteScope.isPending}
          />
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel disabled={deleteScope.isPending}>
            Cancel
          </AlertDialogCancel>
          <Button
            variant="destructive"
            disabled={!canDelete || deleteScope.isPending}
            onClick={handleDelete}
            className="cursor-pointer"
          >
            {deleteScope.isPending ? (
              <>
                <Loader2 className="size-4 animate-spin" />
                Deleting…
              </>
            ) : (
              <>
                <Trash2 className="size-4" />
                Delete scope
              </>
            )}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
