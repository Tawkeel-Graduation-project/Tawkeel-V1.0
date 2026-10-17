import type { Metadata } from "next";
import { PlaceholderPage, pageTitle } from "@/components/placeholder-page";

export const metadata: Metadata = { title: pageTitle("client", "/client/assistant") };

export default function Page() {
  return <PlaceholderPage role="client" href="/client/assistant" story="المحادثة القانونية مع الاستشهادات (RAG)" />;
}
