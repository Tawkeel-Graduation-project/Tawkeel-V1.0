import { AppShell } from "@/components/shell/app-shell";

export default function ClientLayout({ children }: LayoutProps<"/client">) {
  return <AppShell role="client">{children}</AppShell>;
}
