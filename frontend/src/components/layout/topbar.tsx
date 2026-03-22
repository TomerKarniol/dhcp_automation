"use client";

import { useTheme } from "next-themes";
import { Moon, Sun, LogOut } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { getHealth } from "@/lib/api-client";
import { useAuth } from "@/lib/auth";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import Image from "next/image";

export function Topbar() {
  const { theme, setTheme } = useTheme();
  const { user, logout } = useAuth();
  const router = useRouter();

  const { data: health, isError } = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    refetchInterval: 30_000,
    retry: 1,
  });

  function handleLogout() {
    logout();
    router.replace("/login");
  }

  const isHealthy = !isError && health?.status != null;

  return (
    <header className="fixed top-0 left-0 right-0 z-50 flex h-14 items-center border-b border-border/60 bg-background/95 px-4 backdrop-blur-sm">
      {/* Center logo + title */}
      <div className="absolute left-1/2 -translate-x-1/2 flex items-center gap-4 font-semibold tracking-tight">
        <Image
          src="/redbull-logo.png"
          alt="Red Bull"
          width={72}
          height={72}
          className="object-contain"
        />
        <span className="hidden text-2xl sm:block">DHCP Cluster Manager</span>
      </div>

      <div className="ml-auto flex items-center gap-2">
        {/* Health indicator */}
        <div className="flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-xs text-muted-foreground">
          <span
            className={cn(
              "size-2 rounded-full",
              isHealthy ? "bg-green-500" : "bg-red-500"
            )}
          />
          <span className="hidden sm:block">
            {isHealthy ? "Online" : "Offline"}
          </span>
        </div>

        {/* Theme toggle */}
        <button
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          className="flex size-8 cursor-pointer items-center justify-center rounded-lg border border-border text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          title="Toggle theme"
        >
          {theme === "dark" ? (
            <Sun className="size-4" />
          ) : (
            <Moon className="size-4" />
          )}
        </button>

        {/* User badge */}
        {user && (
          <span className="hidden rounded-full border border-border px-2.5 py-1 text-xs text-muted-foreground sm:block">
            {user.username}
          </span>
        )}

        {/* Logout */}
        <button
          onClick={handleLogout}
          className="flex cursor-pointer items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs text-muted-foreground transition-colors hover:border-destructive/50 hover:bg-destructive/10 hover:text-destructive"
        >
          <LogOut className="size-3.5" />
          <span className="hidden sm:block">Logout</span>
        </button>
      </div>
    </header>
  );
}
