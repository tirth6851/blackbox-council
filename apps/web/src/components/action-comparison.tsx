import type { CandidateAction, CandidateDecision } from "@/lib/types";
import { OutcomeBadge } from "./status-badge";

interface ActionComparisonProps {
  candidates: CandidateAction[];
  decisions: CandidateDecision[];
  selectedCandidateId: string | null;
}

export function ActionComparison({ candidates, decisions, selectedCandidateId }: ActionComparisonProps) {
  const decisionById = new Map(decisions.map((d) => [d.candidate_id, d]));

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-800">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead className="bg-slate-900 text-xs uppercase tracking-wide text-slate-400">
          <tr>
            <th className="px-4 py-3">Candidate</th>
            <th className="px-4 py-3">Operation</th>
            <th className="px-4 py-3">Files</th>
            <th className="px-4 py-3">Outcome</th>
            <th className="px-4 py-3">Why</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800 bg-slate-950">
          {candidates.map((candidate) => {
            const decision = decisionById.get(candidate.id);
            const isSelected = candidate.id === selectedCandidateId;
            return (
              <tr key={candidate.id} className={isSelected ? "bg-slate-900/60" : undefined}>
                <td className="px-4 py-3 font-medium text-slate-100">
                  {candidate.id}
                  {isSelected && (
                    <span className="ml-2 rounded bg-sky-950 px-1.5 py-0.5 text-[10px] font-semibold text-sky-300">
                      SELECTED
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-slate-300">{candidate.operation}</td>
                <td className="px-4 py-3 font-mono text-xs text-slate-400">
                  {candidate.file_ids.length > 0 ? candidate.file_ids.join(", ") : "—"}
                </td>
                <td className="px-4 py-3">
                  {decision ? <OutcomeBadge outcome={decision.outcome} /> : "—"}
                </td>
                <td className="px-4 py-3 text-xs text-slate-400">
                  {decision && decision.prerequisites_missing.length > 0
                    ? decision.prerequisites_missing.join("; ")
                    : "No open prerequisites."}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
