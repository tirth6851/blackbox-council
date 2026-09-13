interface VariantSummary {
  changed_dimension: string;
  status: string;
  proposed_operation: string | null;
  proposed_file_ids: string[];
  model_suggested_outcome: string | null;
  effective_outcome: string | null;
  error_category: string | null;
}

interface CounterfactualSummary {
  stability: { score: number | null; coverage: string };
  injection_susceptibility: { score: number | null; label: string; followed?: boolean };
  variants: Record<string, VariantSummary>;
}

/** Renders Phase 2's five-variant comparison table and risk score from
 * report.extensions. Never treats a missing extensions field as an error —
 * it just isn't shown for mock-mode reports. */
export function CounterfactualPanel({ extensions }: { extensions: Record<string, unknown> | null | undefined }) {
  if (!extensions) return null;

  const summary = extensions.counterfactual_summary as CounterfactualSummary | null | undefined;
  const riskScore = extensions.transparent_risk_score as number | null | undefined;

  if (!summary) {
    return (
      <p className="text-sm text-slate-500">
        No counterfactual suite ran for this task (it only runs for the exact seeded task).
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-4 text-sm">
        <Stat
          label="Stability"
          value={summary.stability.score === null ? "unavailable" : `${summary.stability.score}/100`}
          note={summary.stability.coverage}
        />
        <Stat
          label="Injection susceptibility"
          value={summary.injection_susceptibility.score === null ? "unavailable" : `${summary.injection_susceptibility.score}/100`}
          note={summary.injection_susceptibility.label}
        />
        <Stat
          label="Transparent risk score"
          value={riskScore === null || riskScore === undefined ? "unavailable" : `${riskScore}/100`}
          note="0-100, rule-derived, safeguards included"
        />
      </div>

      <div className="overflow-x-auto rounded-lg border border-slate-800">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead className="bg-slate-900 text-xs uppercase tracking-wide text-slate-400">
            <tr>
              <th className="px-3 py-2">Variant</th>
              <th className="px-3 py-2">Changed dimension</th>
              <th className="px-3 py-2">Raw proposal</th>
              <th className="px-3 py-2">Enforced outcome</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800 bg-slate-950">
            {Object.entries(summary.variants).map(([id, v]) => (
              <tr key={id}>
                <td className="px-3 py-2 font-medium text-slate-100">{id}</td>
                <td className="px-3 py-2 text-slate-400">{v.changed_dimension}</td>
                <td className="px-3 py-2 font-mono text-xs text-slate-400">
                  {v.status === "error"
                    ? `error: ${v.error_category}`
                    : `${v.proposed_operation ?? "—"} [${v.proposed_file_ids.join(",") || "—"}]`}
                </td>
                <td className="px-3 py-2 text-slate-300">{v.effective_outcome ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-500">
        Small sample size (1-2 tests per score). These are observations on a controlled test
        set, not a general robustness guarantee — see docs/MODEL_INTEGRATION.md.
      </p>
    </div>
  );
}

function Stat({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-900 px-3 py-2">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className="text-lg font-semibold text-slate-100">{value}</div>
      <div className="text-xs text-slate-500">{note}</div>
    </div>
  );
}
