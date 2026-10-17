import { AppShell } from "@/components/shell/app-shell";

export default function LawyerLayout({ children }: LayoutProps<"/lawyer">) {
  return <AppShell role="lawyer">{children}</AppShell>;
}
