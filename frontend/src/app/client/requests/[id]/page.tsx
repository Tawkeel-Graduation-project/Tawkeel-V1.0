"use client";

import { useParams } from "next/navigation";
import { IntakeScreen } from "@/components/intake/intake-screen";

export default function IntakeRequestPage() {
  const { id } = useParams<{ id: string }>();
  return <IntakeScreen id={id} />;
}
