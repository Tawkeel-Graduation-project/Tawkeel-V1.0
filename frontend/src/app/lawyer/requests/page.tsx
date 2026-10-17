import type { Metadata } from "next";
import { PlaceholderPage, pageTitle } from "@/components/placeholder-page";

export const metadata: Metadata = { title: pageTitle("lawyer", "/lawyer/requests") };

export default function Page() {
  return <PlaceholderPage role="lawyer" href="/lawyer/requests" story="صندوق طلبات المحامي والقبول/الاعتذار" />;
}
