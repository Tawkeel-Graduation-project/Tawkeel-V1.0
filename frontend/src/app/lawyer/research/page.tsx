import type { Metadata } from "next";
import { PlaceholderPage, pageTitle } from "@/components/placeholder-page";

export const metadata: Metadata = { title: pageTitle("lawyer", "/lawyer/research") };

export default function Page() {
  return <PlaceholderPage role="lawyer" href="/lawyer/research" story="البحث القانوني الموثّق بالمصادر" />;
}
