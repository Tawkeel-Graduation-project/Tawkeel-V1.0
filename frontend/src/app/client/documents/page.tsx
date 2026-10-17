import type { Metadata } from "next";
import { PlaceholderPage, pageTitle } from "@/components/placeholder-page";

export const metadata: Metadata = { title: pageTitle("client", "/client/documents") };

export default function Page() {
  return <PlaceholderPage role="client" href="/client/documents" story="رفع المستندات والتعرّف الضوئي (OCR)" />;
}
