import type { Metadata } from "next";
import { PlaceholderPage, pageTitle } from "@/components/placeholder-page";

export const metadata: Metadata = { title: pageTitle("lawyer", "/lawyer/cases") };

export default function Page() {
  return <PlaceholderPage role="lawyer" href="/lawyer/cases" story="سجل القضايا ومساحة العمل" />;
}
