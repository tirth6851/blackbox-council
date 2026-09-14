"use client";

import type { ExecutionRecord, RunStatus } from "@/lib/types";

interface ExecutionResultProps {
  status: RunStatus;
  execution: ExecutionRecord | null;
  busy: boolean;
  onRunSimulation: () => void;
  onRollback: (executionId: string) => void;
}

export function ExecutionResult({ status, execution, busy, onRunSimulation, onRollback }: ExecutionResultProps) {
  if (!execution && status === "approved") {
    return (
      <div className="rounded-md border border-slate-800 bg-slate-900 p-4">
        <p className="text-sm text-slate-300">
          Approved. This will run a <strong>simulation only</strong> — no real files are touched.
        </p>
        <button
          type="button"
          onClick={onRunSimulation}
          disabled={busy}
          className="mt-3 rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy ? "Running simulation…" : "Run simulation"}
        </button>
      </div>
    );
  }

  if (!execution) {
    return <p className="text-sm text-slate-500">No simulation has run yet.</p>;
  }

  return (
    <div className="space-y-3 rounded-md border border-slate-800 bg-slate-900 p-4 text-sm">
      <p className="text-slate-200">
        Simulated archive {execution.status === "rolled_back" ? "was rolled back" : "completed"} for file(s){" "}
        <span className="font-mono">{execution.archived_file_ids.join(", ")}</span>.
      </p>
      <p className="text-emerald-400">
        Source file hashes are unchanged — this was a simulation, not a real mutation. The digests
        below describe the simulated archive index, not the source file bytes.
      </p>
      <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <div>
          <dt className="text-xs uppercase text-slate-500">Before digest</dt>
          <dd className="break-all font-mono text-xs text-slate-400">{execution.before_digest}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-slate-500">After digest</dt>
          <dd className="break-all font-mono text-xs text-slate-400">{execution.after_digest}</dd>
        </div>
      </dl>
      {execution.status === "completed" && (
        <button
          type="button"
          onClick={() => onRollback(execution.id)}
          disabled={busy}
          className="rounded-md border border-amber-700 px-4 py-2 text-sm font-medium text-amber-300 transition hover:bg-amber-950 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy ? "Rolling back…" : "Roll back simulation"}
        </button>
      )}
      {execution.status === "rolled_back" && (
        <p className="text-xs text-slate-500">This simulation has been rolled back.</p>
      )}
    </div>
  );
}
