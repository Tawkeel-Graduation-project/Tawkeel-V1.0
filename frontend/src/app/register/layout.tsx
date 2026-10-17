import type { Metadata } from "next";

export const metadata: Metadata = { title: "إنشاء حساب" };

export default function Layout({ children }: LayoutProps<"/register">) {
  return children;
}
