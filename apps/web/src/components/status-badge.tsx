import type { Outcome } from "@/lib/types";

const OUTCOME_STYLE: Record<Outcome, { label: string; className: string }> = {
  safe: { label: "Safe", className: "bg-emerald-950 text-emerald-300 border-emerald-700" },
  safeguard_required: {
    label: "Safeguard required",
    className: "bg-amber-950 text-amber-300 border-amber-700",
  },
  clarification_required: {
    label: "Clarification required",
    className: "bg-amber-950 text-amber-300 border-amber-700",
  },
  approval_required: {
    label: "Approval required",
    className: "bg-amber-950 text-amber-300 border-amber-700",
  },
  blocked: { label: "Blocked", className: "bg-red-950 text-red-300 border-red-700" },
};

export function OutcomeBadge({ outcome }: { outcome: Outcome }) {
  const style = OUTCOME_STYLE[outcome];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${style.className}`}
    >
      <span aria-hidden="true">
        {outcome === "safe" ? "●" : outcome === "blocked" ? "✕" : "▲"}
      </span>
      {style.label}
    </span>
  );
}

export function ModeBadge({ mode }: { mode: "mock" | "live" }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-sky-700 bg-sky-950 px-2.5 py-0.5 text-xs font-medium text-sky-300">
      Mode: {mode === "mock" ? "Mock" : "Live"}
    </span>
  );
}
