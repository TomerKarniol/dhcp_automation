"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Network, Loader2, EyeOff, Eye } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const loginSchema = z.object({
  username: z.string().min(1, "Username is required"),
  password: z.string().min(1, "Password is required"),
});

type LoginFormValues = z.infer<typeof loginSchema>;

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [showPassword, setShowPassword] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
  });

  function onSubmit(values: LoginFormValues) {
    setAuthError(null);
    const success = login(values.username, values.password);
    if (success) {
      router.replace("/dashboard");
    } else {
      setAuthError("Invalid username or password");
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      {/* Background glow effect */}
      <div
        className="pointer-events-none fixed inset-0 opacity-10"
        style={{
          background:
            "radial-gradient(ellipse 60% 50% at 50% 0%, oklch(0.577 0.245 27) 0%, transparent 80%)",
        }}
      />

      <div className="relative w-full max-w-sm">
        {/* Card */}
        <div className="rounded-2xl bg-card ring-1 ring-foreground/10 p-8 shadow-2xl">
          {/* Logo area */}
          <div className="mb-8 flex flex-col items-center gap-3">
            <div
              className="flex size-14 items-center justify-center rounded-2xl"
              style={{
                background:
                  "oklch(0.577 0.245 27 / 15%)",
                border: "1px solid oklch(0.577 0.245 27 / 30%)",
              }}
            >
              <Network
                className="size-7"
                style={{ color: "oklch(0.577 0.245 27)" }}
              />
            </div>
            <div className="text-center">
              <h1 className="text-xl font-semibold tracking-tight">
                DHCP Cluster Manager
              </h1>
              <p className="mt-1 text-sm text-muted-foreground">
                Infrastructure Management Platform
              </p>
            </div>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            {/* Username */}
            <div className="space-y-1.5">
              <label
                htmlFor="username"
                className="text-sm font-medium text-foreground"
              >
                Username
              </label>
              <input
                id="username"
                type="text"
                autoComplete="off"
                autoFocus
                className={cn(
                  "h-10 w-full rounded-lg border bg-background px-3 text-sm outline-none transition-colors placeholder:text-muted-foreground",
                  "focus:border-ring focus:ring-2 focus:ring-ring/30",
                  errors.username
                    ? "border-destructive ring-2 ring-destructive/20"
                    : "border-input dark:bg-input/30"
                )}
                placeholder="Enter your username"
                {...register("username")}
              />
              {errors.username && (
                <p className="text-xs text-destructive">
                  {errors.username.message}
                </p>
              )}
            </div>

            {/* Password */}
            <div className="space-y-1.5">
              <label
                htmlFor="password"
                className="text-sm font-medium text-foreground"
              >
                Password
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="new-password"
                  className={cn(
                    "h-10 w-full rounded-lg border bg-background px-3 pr-10 text-sm outline-none transition-colors placeholder:text-muted-foreground",
                    "focus:border-ring focus:ring-2 focus:ring-ring/30",
                    errors.password
                      ? "border-destructive ring-2 ring-destructive/20"
                      : "border-input dark:bg-input/30"
                  )}
                  placeholder="Enter your password"
                  {...register("password")}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                  tabIndex={-1}
                >
                  {showPassword ? (
                    <EyeOff className="size-4" />
                  ) : (
                    <Eye className="size-4" />
                  )}
                </button>
              </div>
              {errors.password && (
                <p className="text-xs text-destructive">
                  {errors.password.message}
                </p>
              )}
            </div>

            {/* Auth error */}
            {authError && (
              <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {authError}
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={isSubmitting}
              className={cn(
                "mt-2 flex h-10 w-full cursor-pointer items-center justify-center gap-2 rounded-lg text-sm font-medium text-white transition-all",
                "disabled:cursor-not-allowed disabled:opacity-60"
              )}
              style={{
                background: isSubmitting
                  ? "oklch(0.577 0.245 27 / 70%)"
                  : "oklch(0.577 0.245 27)",
              }}
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  Signing in…
                </>
              ) : (
                "Sign in"
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
