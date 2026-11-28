"use client";

import { useState } from "react";
import { FlaskConical } from "lucide-react";
import { Button } from "@/components/ui";
import { isMockMode, mockRespondToRequest, type ClientRequest } from "@/lib/intake/api";

const SAMPLE_DECLINE_REASON = "لا يتسع وقتي لقضايا جديدة هذا الشهر.";

/**
 * DEV ONLY: in practice mode (no backend), lets you play the lawyer and
 * accept or decline a waiting request, so the client's status screen can be
 * tested before the lawyer screen (SCRUM-348) exists. Renders nothing when a
 * backend is configured.
 */
export function MockLawyerResponse({
  requestId,
  onDone,
}: {
  requestId: string;
  onDone: (request: ClientRequest) => void;
}) {
  const [busy, setBusy] = useState<"accepted" | "declined" | null>(null);
  const [failed, setFailed] = useState(false);

  if (!isMockMode) return null;

  async function respond(decision: "accepted" | "declined") {
    setBusy(decision);
    setFailed(false);
    try {
      onDone(await mockRespondToRequest(requestId, decision, SAMPLE_DECLINE_REASON));
    } catch {
      setFailed(true);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-dashed border-warning/60 bg-warning-soft/40 px-3 py-2 text-xs">
      <FlaskConical aria-hidden className="size-3.5 text-warning" />
      <span className="text-muted">وضع التجربة — محاكاة رد المحامي:</span>
      <Button size="sm" variant="secondary" loading={busy === "accepted"} disabled={busy !== null} onClick={() => void respond("accepted")}>
        قبول
      </Button>
      <Button size="sm" variant="secondary" loading={busy === "declined"} disabled={busy !== null} onClick={() => void respond("declined")}>
        رفض
      </Button>
      {failed ? <span className="text-danger">تعذّرت المحاكاة.</span> : null}
    </div>
  );
}
