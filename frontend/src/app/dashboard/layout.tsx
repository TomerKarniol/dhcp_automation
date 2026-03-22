import { AuthGuard } from "@/components/auth/auth-guard";
import { Topbar } from "@/components/layout/topbar";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthGuard>
      <Topbar />
      <main className="flex flex-1 flex-col pt-14">{children}</main>
    </AuthGuard>
  );
}
