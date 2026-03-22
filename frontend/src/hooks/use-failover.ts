import { useQuery } from "@tanstack/react-query";
import { getFailover } from "@/lib/api-client";

export function useFailover() {
  return useQuery({
    queryKey: ["failover"],
    queryFn: getFailover,
  });
}
