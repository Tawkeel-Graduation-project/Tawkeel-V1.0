import type { Metadata } from "next";

export const metadata: Metadata = { title: "تسجيل الدخول" };

export default function Layout({ children }: LayoutProps<"/login">) {
  return children;
}
