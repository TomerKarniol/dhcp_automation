import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export function ScopeCardSkeleton() {
  return (
    <Card className="flex flex-col gap-0 overflow-hidden">
      <CardHeader className="border-b border-border/60 pb-3">
        <div className="flex items-center justify-between">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-5 w-16 rounded-full" />
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 py-4">
        <div className="space-y-1.5">
          <Skeleton className="h-3 w-16" />
          <Skeleton className="h-4 w-36" />
        </div>
        <div className="space-y-1.5">
          <Skeleton className="h-3 w-12" />
          <Skeleton className="h-4 w-24" />
        </div>
        <div className="space-y-1.5">
          <Skeleton className="h-3 w-10" />
          <Skeleton className="h-4 w-28" />
        </div>
        <div className="flex gap-2 pt-1">
          <Skeleton className="h-5 w-20 rounded-full" />
          <Skeleton className="h-5 w-24 rounded-full" />
        </div>
      </CardContent>
    </Card>
  );
}
