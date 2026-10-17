import type { Metadata } from "next";
import { PlaceholderPage, pageTitle } from "@/components/placeholder-page";

export const metadata: Metadata = { title: pageTitle("lawyer", "/lawyer/schedule") };

export default function Page() {
  return <PlaceholderPage role="lawyer" href="/lawyer/schedule" story="الجدولة والمواعيد" />;
}
