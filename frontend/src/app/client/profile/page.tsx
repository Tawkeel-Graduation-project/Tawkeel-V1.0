import type { Metadata } from "next";
import { PlaceholderPage, pageTitle } from "@/components/placeholder-page";

export const metadata: Metadata = { title: pageTitle("client", "/client/profile") };

export default function Page() {
  return <PlaceholderPage role="client" href="/client/profile" story="الحساب والمصادقة" />;
}
