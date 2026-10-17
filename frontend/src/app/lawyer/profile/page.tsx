import type { Metadata } from "next";
import { PlaceholderPage, pageTitle } from "@/components/placeholder-page";

export const metadata: Metadata = { title: pageTitle("lawyer", "/lawyer/profile") };

export default function Page() {
  return <PlaceholderPage role="lawyer" href="/lawyer/profile" story="ملف المحامي والتخصصات" />;
}
