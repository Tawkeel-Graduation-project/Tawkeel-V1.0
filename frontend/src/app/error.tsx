"use client";

import { RouteError } from "@/components/route-states";

export default function RootError(props: { error: unknown; retry: () => void }) {
  return (
    <main className="mx-auto max-w-xl p-6 pt-20">
      <RouteError {...props} />
    </main>
  );
}
