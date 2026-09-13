"use client";

import { useState } from "react";
import type { ApprovalRecord, FinalDecision, RunStatus } from "@/lib/types";

interface ApprovalPanelProps {
  finalDecision: FinalDecision;
  approval: ApprovalRecord | null;
  status: RunStatus;
  busy: boolean;
  onApprove: (reason: string) => void;
  onReject: (reason: string) => void;
}

export function ApprovalPanel({ finalDecision, approval, status, busy, onApprove, onReject }: ApprovalPanelProps) {
  const [reason, setReason] = useState("");

  if (finalDecision.outcome !== "approval_required") {
    return (
      <p className="text-sm text-slate-500">
        No simulated mutation is proposed for this outcome ({finalDecision.outcome}); nothing to approve.
      </p>
    );
  }

  const canDecide = status === "awaiting_approval";

  return (
    <div className="space-y-4">
      <div className="rounded-md border border-slate-800 bg-slate-900 p-4 text-sm">
        <p className="text-slate-200">{finalDecision.summary}</p>
        <dl className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase text-slate-500">Safeguards</dt>
            <dd className="text-slate-300">{finalDecision.safeguards.join(", ") || "None"}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Action hash</dt>
            <dd className="break-all font-mono text-xs text-slate-400" title={finalDecision.action_hash ?? undefined}>
              {finalDecision.action_hash}
            </dd>
          </div>
        </dl>
      </div>

      {approval && (
        <p className="text-sm text-slate-400">
          Last decision: <span className="font-medium text-slate-200">{approval.decision}</span>
          {approval.reason ? ` — "${approval.reason}"` : ""}
        </p>
      )}

      <label className="block text-sm text-slate-300">
        Reason (optional)
        <textarea
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          maxLength={500}
          disabled={!canDecide || busy}
          rows={2}
          className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 p-2 text-sm text-slate-100 disabled:opacity-50"
        />
      </label>

      <div className="flex gap-3">
        <button
          type="button"
          onClick={() => onApprove(reason)}
          disabled={!canDecide || busy}
          className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Approve simulation
        </button>
        <button
          type="button"
          onClick={() => onReject(reason)}
          disabled={!canDecide || busy}
          className="rounded-md border border-red-700 px-4 py-2 text-sm font-medium text-red-300 transition hover:bg-red-950 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Reject
        </button>
      </div>
    </div>
  );
}
