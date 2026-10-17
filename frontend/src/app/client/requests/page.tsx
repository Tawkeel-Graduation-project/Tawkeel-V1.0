import type { Metadata } from "next";
import { PlaceholderPage, pageTitle } from "@/components/placeholder-page";

export const metadata: Metadata = { title: pageTitle("client", "/client/requests") };

export default function Page() {
  return <PlaceholderPage role="client" href="/client/requests" story="طلب محامٍ ووكيل جمع المعلومات" />;
}
