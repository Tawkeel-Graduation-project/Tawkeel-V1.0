import type { Metadata } from "next";
import { pageTitle } from "@/components/placeholder-page";
import { ClientRequestsList } from "@/components/requests/client-requests-list";

export const metadata: Metadata = { title: pageTitle("client", "/client/requests") };

export default function Page() {
  return <ClientRequestsList />;
}
